#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
07_classify_and_group.py -- Reclassify the master DB and group branches.

The source DB's `has_website` flag is unreliable for chains (it comes from OSM
tag absence, not from checking the web). This script produces a clean,
enriched dataset that the site generator consumes:

  - reclassifies every record into a pitch tier
  - maps the 115 raw categories onto ~24 hub groups
  - groups branches of the same brand into a parent/child structure
  - computes a slug for every record and every brand

Pitch tiers:
  A  -- No website, not a chain. THE sales target. Gets a free template site.
  B  -- Chain/franchise location (known brand with a corporate site). Gets a
        branch page and a "near me" hub, but is never pitched "no website".
  C  -- Has a website. Listed on hubs for completeness, no outreach.

Outputs:
  data/businesses.json   -- enriched records grouped by brand
  data/chain_report.csv  -- which records the guard reclassified, for review
"""
import csv
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (  # noqa: E402
    DATA,
    HUB_BY_SLUG,
    SRC_DB,
    is_known_chain,
    map_category_to_hub,
    normalize_brand,
    slugify,
    zone_meta,
)


def load_master(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify(rec):
    """Return (tier, reason) for a single record."""
    name = rec.get("company_name", "")
    has_site = str(rec.get("has_website", "")).strip().lower() == "true"
    site_url = (rec.get("website_url") or "").strip()

    if has_site or site_url:
        return "C", "has_website flag or website_url present"
    if is_known_chain(name):
        return "B", "matches known chain guard (OSM had no tag, brand has a site)"
    return "A", "no website and not a known chain"


def main():
    if not os.path.exists(SRC_DB):
        sys.exit(f"Source DB not found: {SRC_DB}")

    rows = load_master(SRC_DB)
    records = []
    reclassified = []

    for r in rows:
        tier, reason = classify(r)
        name = (r.get("company_name") or "").strip()
        site_url = (r.get("website_url") or "").strip()
        brand = normalize_brand(name) or slugify(name)
        hub = map_category_to_hub(r.get("category_industry"))
        zone_raw = (r.get("sandton_zone") or "").strip()
        zone_key = slugify(zone_raw.replace(" ", "-")) if zone_raw else "sandton"
        zone_display, landmark = zone_meta(zone_raw)

        # Original flag vs our tier -- record anything the guard corrected
        orig_flag = str(r.get("has_website", "")).strip().lower() == "true"
        if tier == "B" and not orig_flag:
            reclassified.append({
                "company_name": name,
                "category": r.get("category_industry", ""),
                "orig_has_website": orig_flag,
                "new_tier": tier,
                "reason": reason,
            })

        rec = {
            "id": r.get("company_id", "") or slugify(name),
            "name": name,
            "brand_key": brand,
            "hub": hub,
            "hub_title": HUB_BY_SLUG.get(hub, {}).get("title", "Other"),
            "category_raw": r.get("category_industry", ""),
            "zone": zone_key,
            "zone_display": zone_display,
            "zone_landmark": landmark,
            "street_address": (r.get("street_address") or "").strip(),
            "building_name": (r.get("building_name") or "").strip(),
            "postcode": (r.get("postcode") or "").strip(),
            "phone": (r.get("phone_number") or "").strip(),
            "website": site_url,
            "has_website": orig_flag,
            "lat": to_float(r.get("lat")),
            "lng": to_float(r.get("lng")),
            "tier": tier,
            "tier_reason": reason,
            "harvest_source": r.get("harvest_source", ""),
        }
        records.append(rec)

    # ---- group branches by brand (only for known multi-branch brands) ----
    by_brand = defaultdict(list)
    for rec in records:
        by_brand[rec["brand_key"]].append(rec)

    brands = {}
    for brand_key, members in by_brand.items():
        # A brand is a chain if most of its members hit tier B/C
        chainy = sum(1 for m in members if m["tier"] in ("B", "C"))
        is_chain = chainy >= max(1, len(members) // 2) and len(members) > 1

        parent_slug = slugify(brand_key)
        for m in members:
            m["brand_slug"] = parent_slug
            m["is_chain_brand"] = is_chain
            m["branch_count"] = len(members)

        brands[brand_key] = {
            "brand_key": brand_key,
            "display_name": members[0]["name"],
            "slug": parent_slug,
            "is_chain": is_chain,
            "member_ids": [m["id"] for m in members],
            "count": len(members),
        }

    # Per-record unique path slug.
    #
    # Chains store many genuinely separate locations that share one trading
    # name -- the source DB holds 9 separate Woolworths branches all named
    # exactly "Woolworths". Keying the branch slug off the name alone
    # collapsed all 9 onto a single URL and silently dropped 8 of them from
    # the build. A branch slug therefore combines brand + zone, and a numeric
    # suffix resolves the remainder, where even that collides (two Shell
    # stations in one zone).
    branch_counts = defaultdict(int)
    branch_seen = defaultdict(int)

    for rec in records:
        b = brands[rec["brand_key"]]
        rec["brand_slug"] = slugify(b["slug"])
        if b["count"] > 1:
            rec["path"] = (f"{rec['brand_slug']}/"
                           f"{slugify(rec['zone'])}-{slugify(rec['hub'], 24)}")
        else:
            rec["path"] = rec["brand_slug"]

    # Disambiguate any remaining duplicates deterministically by input order.
    for rec in records:
        key = rec["path"]
        if branch_seen[key]:
            branch_seen[key] += 1
            rec["path"] = f"{key}-{branch_seen[key]}"
        else:
            branch_seen[key] = 1

    for rec in records:
        branch_counts[rec["brand_slug"]] += 1
    for rec in records:
        rec["branch_count"] = branch_counts[rec["brand_slug"]]

    # Fail loudly rather than ship URLs that need percent-encoding. A space in
    # a path produces a link that works locally and 404s once served, and it
    # did exactly that before slugify was fixed.
    import re as _re
    bad_paths = sorted({r["path"] for r in records
                        if not _re.fullmatch(r"[a-z0-9\-/]+", r["path"])})
    if bad_paths:
        sys.exit(f"Invalid URL paths generated ({len(bad_paths)}): "
                 f"{bad_paths[:5]}")
    dup_paths = [p for p, n in Counter(
        r["path"] for r in records).items() if n > 1]
    if dup_paths:
        sys.exit(f"Path collisions remain ({len(dup_paths)}): {dup_paths[:5]}")

    # ---- summary ----
    tier_counts = defaultdict(int)
    hub_counts = defaultdict(int)
    for rec in records:
        tier_counts[rec["tier"]] += 1
        hub_counts[rec["hub"]] += 1

    out = {
        "meta": {
            "source": SRC_DB,
            "total_records": len(records),
            "total_brands": len(brands),
            "multi_branch_brands": sum(1 for b in brands.values() if b["count"] > 1),
            "tier_counts": dict(tier_counts),
        },
        "brands": brands,
        "records": records,
    }

    # Identify thin hub/zone combinations. A page listing a single business
    # cannot outrank the big chains, adds no navigational value, and reads as
    # padding to both visitors and a search engine. They are flagged here so
    # the generator can fall back to a link into the parent category page
    # rather than publishing a near-empty surface.
    MIN_HUB_LISTINGS = 3
    for rec in records:
        key = (rec["hub"], rec["zone"])
        count = sum(1 for r in records
                    if r["hub"] == rec["hub"] and r["zone"] == rec["zone"])
        rec["hub_zone_count"] = count
        rec["thin_hub"] = count < MIN_HUB_LISTINGS

    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "businesses.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    with open(os.path.join(DATA, "chain_report.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["company_name", "category",
                                           "orig_has_website", "new_tier", "reason"])
        w.writeheader()
        w.writerows(reclassified)

    # ---- console summary ----
    print("=" * 62)
    print("SANDTON INDEX -- classification & grouping")
    print("=" * 62)
    print(f"Records       : {len(records)}")
    print(f"Brands        : {len(brands)}")
    print(f"Multi-branch  : {out['meta']['multi_branch_brands']}")
    print(f"Guard reclass : {len(reclassified)} chains moved off 'no website'")
    print("-" * 62)
    print("Pitch tiers")
    for t in ("A", "B", "C"):
        desc = {"A": "no site, not chain  <- SALES TARGET",
                "B": "chain/franchise    <- branch page only",
                "C": "has website        <- list only"}[t]
        print(f"  {t}: {tier_counts.get(t, 0):>4}  {desc}")
    print("-" * 62)
    print("Hub coverage (top 15)")
    for slug, count in sorted(hub_counts.items(), key=lambda x: -x[1])[:15]:
        title = HUB_BY_SLUG.get(slug, {}).get("title", slug)
        print(f"  {count:>4}  {title}")
    print("=" * 62)


if __name__ == "__main__":
    main()
