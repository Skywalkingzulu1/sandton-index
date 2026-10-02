#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_build.py -- Fail the build if the generated site is unsafe to publish.

This exists because three separate defects shipped past a build that reported
success: 80 business pages silently overwrote each other, 411 URL paths
contained spaces, and estimated opening hours leaked into JSON-LD. Each was
found by inspecting output after the fact. These checks turn that into a
build-time gate.

Checks:
  1. every record produced a page, and no path collided
  2. every internal link resolves
  3. no estimated opening hours appear in structured data
  4. every page carrying estimated hours shows the visible notice
  5. no page is missing a title, description or canonical
  6. chain businesses are never pitched "you have no website"

Exit code 1 on any failure, with every failure listed rather than the first.
"""
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA, MIN_HUB_LISTINGS, SITE  # noqa: E402
from data_overlay import load_overlay  # noqa: E402

LD_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.S)
LINK_RE = re.compile(r'href="(/[^"#?]*)/?"')
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
DESC_RE = re.compile(r'name="description" content="(.*?)"')
CANON_RE = re.compile(r'rel="canonical" href="(.*?)"')


def collect_pages():
    out = []
    for root, _dirs, files in os.walk(SITE):
        for f in files:
            if f == "index.html":
                out.append(os.path.join(root, f))
    return out


def main():
    failures = []
    notes = []

    biz_path = os.path.join(DATA, "businesses.json")
    if not os.path.exists(biz_path):
        sys.exit("businesses.json missing -- run 07 and 08 first")
    if not os.path.isdir(SITE):
        sys.exit("site/ missing -- run 09 first")

    with open(biz_path, encoding="utf-8") as fh:
        records = json.load(fh)["records"]
    pages = collect_pages()

    # --- 1. one page per record, no collisions -------------------------
    paths = Counter(r["path"] for r in records)
    dupes = [p for p, n in paths.items() if n > 1]
    if dupes:
        failures.append(f"{len(dupes)} path collisions, records overwritten: "
                        f"{dupes[:3]}")

    missing = [r for r in records
               if not os.path.exists(os.path.join(SITE, r["path"], "index.html"))]
    if missing:
        failures.append(f"{len(missing)} records have no page, e.g. "
                        f"{[r['path'] for r in missing[:3]]}")

    # --- 2. internal links resolve -------------------------------------
    broken = {}
    for p in pages:
        with open(p, encoding="utf-8") as fh:
            html = fh.read()
        for href in LINK_RE.findall(html):
            rel = href.strip("/")
            if rel and not os.path.exists(os.path.join(SITE, rel, "index.html")):
                broken.setdefault(href, []).append(p)
    if broken:
        failures.append(f"{len(broken)} broken internal links, e.g. "
                        f"{sorted(broken)[:3]}")

    # --- 3 & 4. hours honesty ------------------------------------------    #
    # Hours now have three possible provenances, not two, and the rule for
    # each is different:
    #   scraped -- OSM, name + proximity corroborated. May be stated as fact
    #             and may enter JSON-LD.
    #   google  -- copied from the business's own Google profile. Real data,
    #             but one third-party snapshot that can be months stale, so it
    #             carries a caveat and must stay OUT of JSON-LD.
    #   default -- our own per-category guess. Strongest warning, and out of
    #             JSON-LD.
    #
    # The check that matters most is the negative one: nothing but "scraped"
    # is allowed to become a published openingHoursSpecification.
    ld_count = 0
    schema_leaks = []
    missing_notice = []
    estimated_ids = {r["id"] for r in records
                     if r.get("hours_confidence") == "default"}
    scraped_ids = {r["id"] for r in records
                   if r.get("hours_confidence") == "scraped"}

    # Optional enrichment sidecar. Absent in a fresh clone, which is fine --
    # the site builds and verifies without it.
    overlay = load_overlay(DATA)

    # the two caveats that must appear, per provenance
    CAVEAT = {
        "default": "Typical hours, not confirmed",
        "google": "As listed on Google, not confirmed directly",
    }

    for p in pages:
        with open(p, encoding="utf-8") as fh:
            html = fh.read()
        for m in LD_RE.finditer(html):
            ld_count += 1
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                schema_leaks.append(f"{p}: malformed JSON-LD")
                continue
            # any page showing a caveat must not also publish hours as fact
            if "openingHoursSpecification" in data and any(
                    c in html for c in CAVEAT.values()):
                schema_leaks.append(p)

    # --- 4b. structured-data safety rules -------------------------------
    # These are the claims that would get a listing suppressed, or that
    # would be a fabricated fact about a real business. Each is checked
    # explicitly rather than trusted to the generator.
    ratings = []
    coupon_leaks = []
    coupon_pages = 0
    for p in pages:
        with open(p, encoding="utf-8") as fh:
            html = fh.read()
        blocks = []
        for m in LD_RE.finditer(html):
            try:
                blocks.append(json.loads(m.group(1)))
            except json.JSONDecodeError:
                continue
        for d in blocks:
            if isinstance(d, dict) and "aggregateRating" in d:
                ratings.append(p)
            # the cross-promotion must never be attached to a listed
            # business: a tyre shop does not sell discounted consults
            if isinstance(d, dict) and "discount" in d \
                    and "LocalBusiness" not in str(d.get("@type", "")) \
                    and d.get("@type") not in ("Offer",):
                coupon_leaks.append(p)
            if isinstance(d, dict) and "Offer" in str(d.get("@type", "")):
                if any(k in d for k in ("telephone", "geo", "streetAddress")):
                    coupon_leaks.append(p)
        if 'class="coupon' in html:
            coupon_pages += 1

    if ratings:
        failures.append(f"{len(ratings)} pages emit aggregateRating "
                        f"(never permitted here), e.g. {ratings[:3]}")
    if coupon_leaks:
        failures.append(f"{len(coupon_leaks)} pages attach the coupon to a "
                        f"listed business, e.g. {coupon_leaks[:3]}")
    if coupon_pages < len(pages):
        notes.append(f"coupon module on {coupon_pages}/{len(pages)} pages")

    # Every page showing hours below "fact" confidence must carry the
    # matching visible caveat. Resolved through the overlay, because Google
    # hours override a record's category default -- checking records.json
    # alone would demand a default-hours notice on a page now showing real
    # Google hours.
    google_ids = {rid for rid, entry in overlay.items()
                  if isinstance(entry, dict) and entry.get("opening_hours")}
    for r in records:
        rid = r["id"]
        is_default = rid in estimated_ids
        is_google = rid in google_ids and rid not in scraped_ids
        if not (is_default or is_google):
            continue
        p = os.path.join(SITE, r["path"], "index.html")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            html = fh.read()
        wanted = CAVEAT["google" if is_google else "default"]
        if wanted not in html:
            missing_notice.append(f"{r['path']} ({wanted})")

    if schema_leaks:
        failures.append(f"{len(schema_leaks)} unverified hours leaked into "
                        f"JSON-LD, e.g. {schema_leaks[:3]}")
    if missing_notice:
        failures.append(f"{len(missing_notice)} pages missing the visible "
                        f"hours caveat, e.g. {missing_notice[:3]}")

    if google_ids:
        notes.append(f"Google-sourced hours on {len(google_ids)} pages "
                     f"(caveated, excluded from schema)")

    # Sanity: every scraped record should carry hours in its schema
    schema_with_hours = 0
    for r in records:
        if r["id"] not in scraped_ids:
            continue
        p = os.path.join(SITE, r["path"], "index.html")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            html = fh.read()
        m = LD_RE.search(html)
        if m and "openingHoursSpecification" in m.group(1):
            schema_with_hours += 1
    if scraped_ids and schema_with_hours != len(scraped_ids):
        notes.append(f"scraped hours in schema: {schema_with_hours}/"
                     f"{len(scraped_ids)}")

    # --- 5. page basics -------------------------------------------------
    bad_meta = []
    for p in pages:
        with open(p, encoding="utf-8") as fh:
            html = fh.read()
        if not TITLE_RE.search(html) or not DESC_RE.search(html) \
                or not CANON_RE.search(html):
            bad_meta.append(p)
    if bad_meta:
        failures.append(f"{len(bad_meta)} pages missing title/description/"
                        f"canonical, e.g. {bad_meta[:3]}")

    # --- 5b. no unrendered template artefacts ---------------------------
    # A f-string typo renders as literal braces on a live page, and a broken
    # JSON-LD block is silently dropped by Google, so both fail quietly and
    # both are cheap to catch here.
    leaks = []
    for p in pages:
        with open(p, encoding="utf-8") as fh:
            html = fh.read()
        for bad in ("{}", "{e(", "&amp;amp;"):
            if bad in html:
                leaks.append(f"{p} ({bad!r})")
        if re.search(r"\b(?:nan|NaN|None|undefined)\b", html):
            leaks.append(f"{p} (bare word)")
        for m in LD_RE.finditer(html):
            try:
                json.loads(m.group(1))
            except json.JSONDecodeError:
                leaks.append(f"{p} (JSON-LD parse)")
    if leaks:
        failures.append(f"{len(leaks)} pages have template leaks or unparseable "
                        f"JSON-LD, e.g. {leaks[:3]}")

    # --- 6b. fabrication gates ------------------------------------------
    # The intent engine and DOW modules add a lot of new page furniture. Each
    # of these is a specific way that furniture could publish something false
    # about a real business, so each is checked rather than trusted.
    pill_faults = []
    pending_faults = []
    voucher_leaks = []
    stale_domain = []
    status_faults = []

    SCRAPED = {r["id"] for r in records
               if r.get("hours_confidence") == "scraped"}
    by_id = {r["id"]: r for r in records}

    for p in pages:
        with open(p, encoding="utf-8") as fh:
            html = fh.read()
        body = html.split("</style>")[-1]

        # 1. A live open/closed pill is a factual claim about whether a real
        #    business is trading right now. It may only appear where we hold
        #    corroborated hours.
        if 'class="pill' in body:
            m = re.search(r'class="wrap biz".*?</h1>', body, re.S)
            rel = os.path.relpath(p, SITE).replace("\\", "/")
            rel = rel[:-len("/index.html")] if rel.endswith("/index.html") \
                else rel
            hit = [r for r in records if r.get("path") == rel]
            if not hit or hit[0]["id"] not in SCRAPED:
                pill_faults.append(rel)

        # 2. Voucher codes are generated but NEVER approved by Doctors on
        #    Wheels. A page presenting one as redeemable is a commitment we
        #    cannot make on their behalf.
        if re.search(r"\b[A-Z][A-Z0-9]{4,}\s?50\b", body):
            voucher_leaks.append(p)

        # 3. The claim that any benefit is approved must be present wherever
        #    a pending-benefit notice is shown.
        if "dow-pending" in body and "pending approval" not in body:
            pending_faults.append(p)

        # 4. No hardcoded "open now" state or invented operating hours.
        if re.search(r"status.{0,12}OPEN_NOW", body) or \
                re.search(r"Closes at \d\d:\d\d", body):
            status_faults.append(p)

        # 5. The project brief proposed claim URLs on sandtonindex.co.za.
        #    That domain was never registered; any internal link to it is a
        #    dead absolute link and fails the broken-link check as a false
        #    pass.
        if "sandtonindex.co.za" in html:
            stale_domain.append(p)

    if pill_faults:
        failures.append(f"{len(pill_faults)} pages show a live open/closed "
                        f"pill without corroborated hours, e.g. {pill_faults[:3]}")
    if voucher_leaks:
        failures.append(f"{len(voucher_leaks)} pages present an unapproved "
                        f"voucher code as redeemable, e.g. {voucher_leaks[:3]}")
    if pending_faults:
        failures.append(f"{len(pending_faults)} pages show a pending benefit "
                        f"without the approval notice, e.g. {pending_faults[:3]}")
    if status_faults:
        failures.append(f"{len(status_faults)} pages hardcode an open/closed "
                        f"state, e.g. {status_faults[:3]}")
    if stale_domain:
        failures.append(f"{len(stale_domain)} pages link the unregistered "
                        f"sandtonindex.co.za domain, e.g. {stale_domain[:3]}")

    # --- 7. Search Console verification present -------------------------
    # Cheap to check, and its absence is silent: Google simply never confirms
    # the property and nobody notices until search performance is being
    # wondered about months later.
    from config import GOOGLE_SITE_VERIFICATION  # noqa: PLC0415
    if GOOGLE_SITE_VERIFICATION:
        tag = f'name="google-site-verification" content="{GOOGLE_SITE_VERIFICATION}"'
        missing = [p for p in pages
                   if tag not in open(p, encoding="utf-8").read()]
        vf = os.path.join(
            SITE, f"google{GOOGLE_SITE_VERIFICATION}.html")
        if not os.path.exists(vf):
            failures.append("Search Console verification file is missing: "
                            f"{os.path.basename(vf)}")
        if missing:
            failures.append(f"{len(missing)} pages missing the Search Console "
                            f"verification tag, e.g. {missing[:3]}")
    else:
        notes.append("Search Console verification token not configured")

    # --- 8. chains never told they have no website ----------------------
    bad_pitch = []
    for r in records:
        if r["tier"] != "B":
            continue
        p = os.path.join(SITE, r["path"], "index.html")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            html = fh.read()
        if "No website yet" in html or "Claim this listing" in html:
            bad_pitch.append(r["path"])
    if bad_pitch:
        failures.append(f"{len(bad_pitch)} chain pages pitched 'no website', "
                        f"e.g. {bad_pitch[:3]}")

    # --- thin hub sanity ------------------------------------------------
    thin = sum(1 for c in Counter((r["hub"], r["zone"])
                                  for r in records).values()
               if c < MIN_HUB_LISTINGS)
    thin_published = sum(
        1 for (h, z) in {(r["hub"], r["zone"]) for r in records}
        if sum(1 for r in records if r["hub"] == h and r["zone"] == z)
        < MIN_HUB_LISTINGS
        and os.path.exists(os.path.join(SITE, h, z, "index.html")))
    if thin_published:
        failures.append(f"{thin_published} thin hub pages published "
                        f"(should have been folded into category pages)")

    # --- 9. sitemap is actually submittable ------------------------------
    # A sitemap that silently truncates is invisible: the file validates, the
    # submission succeeds, Google reports no error, and half the site simply
    # never gets crawled. This shipped once already -- 775 URLs in one flat
    # file, of which Google processed 500.
    sitemap = os.path.join(SITE, "sitemap.xml")
    sitemap_faults = []
    total_urls = 0
    if not os.path.exists(sitemap):
        sitemap_faults.append("sitemap.xml is missing")
    else:
        sm = open(sitemap, encoding="utf-8").read()
        if "<sitemapindex" in sm:
            refs = re.findall(r"<loc>(.*?)</loc>", sm)
            if not refs:
                sitemap_faults.append("sitemap index lists no sitemaps")
            for ref in refs:
                name = ref.rstrip("/").split("/")[-1]
                fp = os.path.join(SITE, name)
                if not os.path.exists(fp):
                    sitemap_faults.append(f"sitemap index references missing "
                                          f"{name}")
                    continue
                txt = open(fp, encoding="utf-8").read()
                n = len(re.findall(r"<loc>", txt))
                if n > 500:
                    sitemap_faults.append(f"{name} has {n} URLs "
                                          "(Google free tier processes 500)")
                total_urls += n
        else:
            n = len(re.findall(r"<loc>", sm))
            if n > 500:
                sitemap_faults.append(
                    f"flat sitemap has {n} URLs; shard it behind a sitemap "
                    "index or Google will only process 500")
            total_urls = n
    if sitemap_faults:
        failures.append(f"{len(sitemap_faults)} sitemap problem(s): "
                        f"{sitemap_faults[:3]}")
    else:
        notes.append(f"sitemap: {total_urls} URLs across "
                     f"{max(1, -(-total_urls // 500))} file(s)")

    # --- 10. property pages claim nothing they cannot source -------------
# A building page is almost entirely about someone else's property. The
# failure mode is publishing a unit count, a price, an occupancy figure or an
# amenity list that nobody supplied. Each of those is a specific fabricated
# claim, so each is checked rather than trusted.
    prop_faults = []
    prop_pages = 0
    prop_tenancy = []

    # Facts about a property that would be fabrication unless sourced. Each is
    # scanned with a surrounding window so the page's own disclaimer ("unit
    # numbers, occupancy, amenities and leasing status are not published
    # here") is not mistaken for a claim. A disclaimer that names the term is
    # the opposite of asserting it.
    FORBIDDEN = [
        (r"\b\d+\s*(?:residential\s+)?units?\b", "unit count"),
        (r"\b\d+\s*(?:office\s+)?units?\s*(?:available|let|for rent)", "let units"),
        (r"\boccupancy\b", "occupancy"),
        # allow "floor area of 12400", "floor area is 12400", "lettable: 5000"
        (r"\b(?:floor area|lettable|rentable|gla)\b[^.]{0,24}\d", "floor area"),
        # thousands separators, optionally spaced: R1 850 000 / R1,850,000
        (r"\bR\s?\d[\d\s,\.]{3,}", "rental price"),
        (r"\b(?:built|year built|completed in)\s*(?:in\s*)?(?:19|20)\d\d",
         "year built"),
        (r"\b(?:24\/7|24-7)\s*(?:security|access|manned)\b", "security claim"),
        # amenity followed closely by an availability claim
        (r"\b(?:gym|swimming pool|pool|sauna|tennis court|generator|"
         r"backup water)\b[^.]{0,30}(?:included|available|on site|onsite|"
         r"for residents|free)", "amenity claim"),
    ]
    DISCLAIMER = (
        "not published here", "cannot be verified", "are never published",
        "never published here", "cannot verify", "not something open mapping",
        "not verifiable", "no unit numbers",
    )
    TENANT_WORDS = re.compile(
        r"\b(tenant[s]?|occupier[s]?|lessee[s]?)\b", re.I)

    for p in pages:
        rel = os.path.relpath(p, SITE).replace("\\", "/")
        if not (rel.startswith("properties/") or "/properties/" in rel):
            continue
        prop_pages += 1
        with open(p, encoding="utf-8") as fh:
            html = fh.read()
        body = html.split("</style>")[-1]
        for pattern, label in FORBIDDEN:
            # finditer, not search: the page's own disclaimer names these
            # terms ("unit numbers, occupancy, amenities ... are not
            # published here"), and search would stop at that excused first
            # match and never examine a genuine claim further down.
            for m in re.finditer(pattern, body, re.I):
                window = body[max(0, m.start() - 110):m.end() + 110].lower()
                if any(w in window for w in DISCLAIMER):
                    continue
                prop_faults.append(
                    f"{rel} publishes a {label} ({m.group(0)!r})")
                break
        for m in TENANT_WORDS.finditer(body):
            window = body[max(0, m.start() - 110):m.end() + 110].lower()
            if not any(w in window for w in DISCLAIMER
                       + ("not presented as tenants", "add a tenant directory",
                          "tenant directory")):
                prop_tenancy.append(f"{rel} ({m.group(0)!r})")
                break
        # OpenStreetMap must be credited wherever building data appears
        if "OpenStreetMap" not in body and "openstreetmap" not in html:
            prop_faults.append(f"{rel} shows building data without crediting "
                               "OpenStreetMap")

    if prop_faults:
        failures.append(f"{len(prop_faults)} property claim problem(s), e.g. "
                        f"{prop_faults[:3]}")
    if prop_tenancy:
        failures.append(f"{len(prop_tenancy)} property pages assert tenancy "
                        f"without the disclaimer, e.g. {prop_tenancy[:3]}")
    if prop_pages:
        notes.append(f"property pages checked: {prop_pages}")

    # --- report ---------------------------------------------------------
    print("=" * 62)
    print("SANDTON INDEX -- build verification")
    print("=" * 62)
    print(f"  pages generated     : {len(pages)}")
    print(f"  business records    : {len(records)}")
    print(f"  JSON-LD blocks      : {ld_count}")
    print(f"  hours scraped       : {len(scraped_ids)} (trusted, in schema)")
    print(f"  hours estimated     : {len(estimated_ids)} (labelled, no schema)")
    print(f"  thin hub combos     : {thin} (folded into category pages)")
    for n in notes:
        print(f"  note: {n}")
    print("-" * 62)
    if failures:
        print(f"FAILED with {len(failures)} problem(s):")
        for f in failures:
            print(f"  x {f}")
        print("=" * 62)
        sys.exit(1)
    print("All checks passed. Safe to publish.")
    print("=" * 62)


if __name__ == "__main__":
    main()
