#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_property_gates.py -- prove the property safety gates actually fire.

A verification check that never fails is indistinguishable from no check. This
injects each fabricated-claim pattern into a real generated property page and
asserts verify_build.py rejects the build, then restores the file and asserts
the clean build passes again.

Run after changing the FORBIDDEN patterns in verify_build.py. When a pattern
is loosened enough to stop catching its own failure, this fails loudly instead
of the gate quietly becoming decoration.

The first version of these patterns passed this test only for 4 of 8 claims:
re.search stopped at the page's own disclaimer (which names "occupancy" and
"unit numbers" in order to disclaim them) and never reached the injected
claim below it.
"""
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
VERIFY = os.path.join(ROOT, "scripts", "verify_build.py")

CLAIMS = [
    ("unit count", "This complex has 248 units."),
    ("let units", "12 units available for lease right now."),
    ("rental price", "Units available from R1 850 000 per month."),
    ("occupancy", "Current occupancy is 92 percent."),
    ("floor area", "The floor area is 12400 square metres."),
    ("year built", "Completed in 2008 by a leading developer."),
    ("security claim", "24/7 security on site with controlled access."),
    ("amenity claim", "A gym and swimming pool are available to residents."),
    ("tenancy claim", "Tenants include a medical practice and a creche."),
]


def run_verify():
    return subprocess.run([sys.executable, VERIFY], capture_output=True,
                          text=True, cwd=ROOT)


def pick_page():
    """Any generated individual property page will do."""
    base = os.path.join(SITE, "properties")
    for root, _dirs, files in os.walk(base):
        if "index.html" in files:
            rel = os.path.relpath(root, SITE).replace("\\", "/")
            # skip the index itself; want a real building page
            if rel.count("/") >= 1 and rel != "properties":
                return os.path.join(root, "index.html")
    return None


def main():
    page = pick_page()
    if not page:
        sys.exit("no property page found -- run 09 first")
    print(f"target: {os.path.relpath(page, ROOT)}\n")

    backup = page + ".bak"
    shutil.copyfile(page, backup)
    original = open(backup, encoding="utf-8").read()

    missed = []
    try:
        for label, claim in CLAIMS:
            with open(page, "w", encoding="utf-8") as fh:
                fh.write(original.replace("</body>", f"<p>{claim}</p></body>"))
            r = run_verify()
            caught = r.returncode != 0
            print(f"  {label:<16} {'CAUGHT' if caught else 'MISSED'}")
            if not caught:
                missed.append(label)
    finally:
        shutil.copyfile(backup, page)
        if os.path.exists(backup):
            os.remove(backup)

    r = run_verify()
    clean = r.returncode == 0
    print(f"\nrestored -> verify {'PASSES' if clean else 'STILL FAILS'}")
    if missed:
        print(f"\nFAILED: {len(missed)} gate(s) no longer catch their own "
              f"failure: {missed}")
        sys.exit(1)
    if not clean:
        print("\nFAILED: clean build does not pass verify")
        sys.exit(1)
    print(f"All {len(CLAIMS)} fabricated-claim gates fire, and the clean build "
          "still passes.")


if __name__ == "__main__":
    main()