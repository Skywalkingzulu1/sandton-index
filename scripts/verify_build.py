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

    # --- 3 & 4. hours honesty ------------------------------------------
    ld_count = 0
    schema_leaks = []
    missing_notice = []
    estimated_ids = {r["id"] for r in records
                     if r.get("hours_confidence") == "default"}
    scraped_ids = {r["id"] for r in records
                   if r.get("hours_confidence") == "scraped"}

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
            if "openingHours" in data and "Typical hours, not confirmed" in html:
                schema_leaks.append(p)

    # Estimated-hours pages must carry the visible warning
    for r in records:
        if r["id"] not in estimated_ids:
            continue
        p = os.path.join(SITE, r["path"], "index.html")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            html = fh.read()
        if "Typical hours, not confirmed" not in html:
            missing_notice.append(r["path"])

    if schema_leaks:
        failures.append(f"{len(schema_leaks)} estimated hours leaked into "
                        f"JSON-LD, e.g. {schema_leaks[:3]}")
    if missing_notice:
        failures.append(f"{len(missing_notice)} estimated-hours pages missing "
                        f"the visible notice, e.g. {missing_notice[:3]}")

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
        if m and "openingHours" in m.group(1):
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

    # --- 6. chains never told they have no website ----------------------
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
