#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_google_enrich.py -- Offline regression tests for the Google enrichment.

Runs with no API calls and no token. Two things are tested, and they are the
two places this pipeline can silently produce a WRONG FACT about a real
business:

  1. parse_opening_hours -- turns the API's rolling 7-day string into the
     weekly schedule the site publishes. A bad time here becomes a published
     opening time for someone else's shop.

  2. google_name_matches -- decides which Google result belongs to which of
     our records. A bad match here puts another business's phone number on a
     page.

The matcher cases include the three false positives recorded in
08_harvest_hours.py's own docstring ("Game" vs "Game Changers", "Body Action"
vs "The Body Shop", "Garden Court Sandton City" vs "Garden Shop"). Those were
real bugs once. They are here so a future edit to the place-word list cannot
reintroduce them without this file going red.

Run: python scripts/test_google_enrich.py
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

spec = importlib.util.spec_from_file_location(
    "enrich", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "10_enrich_google.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["enrich"] = m
spec.loader.exec_module(m)

NARROW_NBSP = "\u202f"
EN_DASH = "\u2013"

# ---------------------------------------------------------------- hours
HOUR_CASES = [
    ("simple week",
     "Friday(2026-10-02): [8{nb}am{d}8{nb}pm], Saturday(2026-10-03): "
     "[8{nb}am{d}8{nb}pm], Sunday(2026-10-04): [9{nb}am{d}7{nb}pm], "
     "Monday(2026-10-05): [9{nb}am{d}8{nb}pm], Tuesday(2026-10-06): "
     "[9{nb}am{d}8{nb}pm], Wednesday(2026-10-07): [9{nb}am{d}8{nb}pm], "
     "Thursday(2026-10-08): [9{nb}am{d}8{nb}pm]",
     {"friday": "08:00-20:00", "saturday": "08:00-20:00",
      "sunday": "09:00-19:00", "monday": "09:00-20:00",
      "tuesday": "09:00-20:00", "wednesday": "09:00-20:00",
      "thursday": "09:00-20:00"}),

    # A closed day must be absent, not stored as a zero-length span.
    ("closed day omitted",
     "Friday(2026-10-02): [9{nb}am{d}6:30{nb}pm], Sunday(2026-10-04): "
     "[Closed], Monday(2026-10-05): [9{nb}am{d}6:30{nb}pm]",
     {"friday": "09:00-18:30", "monday": "09:00-18:30"}),

    # A lunch break must not be flattened into one wrong span.
    ("split shift preserved",
     "Friday(2026-10-02): [9{nb}am{d}12{nb}pm, 5{nb}pm{d}8{nb}pm]",
     {"friday": "09:00-12:00,17:00-20:00"}),

    # 12 am is midnight, not noon. Getting this backwards publishes a shop
    # as open at the wrong end of the day.
    ("midnight is 00:00",
     "Friday(2026-10-02): [12{nb}am{d}11:59{nb}pm]",
     {"friday": "00:00-23:59"}),

    ("unparseable day dropped",
     "Saturday(2026-10-03): [Open 24 hours], Friday(2026-10-02): "
     "[9{nb}am{d}5{nb}pm]",
     {"friday": "09:00-17:00"}),

    ("empty input", None, {}),
    ("garbage input", "not a schedule", {}),
    ("empty string", "", {}),
]

# ---------------------------------------------------------------- names
NAME_CASES = [
    # (ours, google, should_match, why)
    ("Pick n Pay", "Pick n Pay Sandton City", True,
     "Google appends the branch/centre name"),
    ("Pick n Pay", "Pick n Pay", True, "identical"),
    ("Woolworths", "Woolworths Sandton City", True, "branch suffix"),
    ("Checkers Hyper", "Checkers Hyper Sandton", True,
     "qualifier plus place word"),
    ("Kokoro", "Kokoro Rivonia Gardens", True, "locality word"),
    ("Cape Union Mart", "Cape Union Mart Sandton", True, "brand plus city"),

    # --- must not match -------------------------------------------------
    ("Game", "Game Changers", False,
     "regression: documented false positive in 08"),
    ("Body Action", "The Body Shop", False,
     "regression: documented false positive in 08"),
    ("Garden Court Sandton City", "Garden Shop", False,
     "regression: documented false positive in 08"),
    ("Spar", "Spar South Africa", False,
     "country name is not a branch word"),
    ("Food Basics", "Food Basics Fine", False,
     "extra token is not a place word"),
    ("Alpha Hair", "Beta Hair", False, "genuinely different businesses"),
    ("", "Woolworths Sandton", False, "no record name"),
    ("Woolworths", "", False, "no place name"),
]


def main():
    fails = []

    print("=" * 62)
    print("opening-hours parser")
    print("=" * 62)
    for name, raw, expected in HOUR_CASES:
        fmt = (raw or "")
        if "{nb}" in fmt:
            fmt = fmt.format(nb=NARROW_NBSP, d=EN_DASH)
        got = m.parse_opening_hours(fmt or None)
        ok = got == expected
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            fails.append(name)
            print(f"          expected {expected}")
            print(f"          got      {got}")

    print("\n  24-hour conversion")
    for token, expected in [("8 am", "08:00"), ("12 am", "00:00"),
                            ("12 pm", "12:00"), ("6:30 pm", "18:30"),
                            ("11:59 pm", "23:59"), ("bogus", None)]:
        got = m.to_24h(token)
        ok = got == expected
        print(f"    {'PASS' if ok else 'FAIL'}  {token!r:10} -> {got}")
        if not ok:
            fails.append(f"to_24h({token})")

    print("\n" + "=" * 62)
    print("name matcher")
    print("=" * 62)
    for ours, goog, expected, why in NAME_CASES:
        got = bool(m.google_name_matches(m._tokens(ours), m._tokens(goog)))
        ok = got == expected
        print(f"  {'PASS' if ok else 'FAIL'}  {ours!r:<22} vs {goog!r:<26} "
              f"-> {'match' if got else 'no'}")
        print(f"        {why}")
        if not ok:
            fails.append(f"{ours} / {goog}")

    print("\n" + "=" * 62)
    if fails:
        print(f"FAILED: {len(fails)}")
        for f in fails:
            print(f"  - {f}")
        return 1
    total = len(HOUR_CASES) + 6 + len(NAME_CASES)
    print(f"all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
