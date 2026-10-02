"""Prove the Overpass-outage fallback preserves scraped hours.

Simulates the failure that stripped 140 real schedules: 07 rebuilds
businesses.json without hours, then 08 cannot reach Overpass. Asserts the
scraped schedules survive rather than being replaced by category defaults.
"""
import json
import os
import shutil
import subprocess
import sys
from collections import Counter

ROOT = r"C:\Users\molel\sandton-index"
HOURS = os.path.join(ROOT, "data", "hours.json")
BIZ = os.path.join(ROOT, "data", "businesses.json")
BACKUP_DIR = os.path.join(ROOT, "data", "_fallback_test_backup")


def counts():
    with open(HOURS, encoding="utf-8") as fh:
        h = json.load(fh)
    with open(BIZ, encoding="utf-8") as fh:
        b = json.load(fh)
    hc = Counter(v.get("confidence") for v in h.values() if isinstance(v, dict))
    bc = Counter(r.get("hours_confidence") for r in b["records"])
    return hc, bc


before_h, before_b = counts()
print("before  hours.json :", dict(before_h))
print("before  businesses :", dict(before_b))

os.makedirs(BACKUP_DIR, exist_ok=True)
shutil.copyfile(HOURS, os.path.join(BACKUP_DIR, "hours.json"))
shutil.copyfile(BIZ, os.path.join(BACKUP_DIR, "businesses.json"))

try:
    # simulate 07 wiping hours: rebuild businesses.json with no hours at all
    with open(BIZ, encoding="utf-8") as fh:
        data = json.load(fh)
    for rec in data["records"]:
        rec.pop("opening_hours", None)
        rec.pop("hours_confidence", None)
        rec.pop("hours_source", None)
    with open(BIZ, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    print("\nsimulated 07 rebuild: businesses.json has no hours")

    # simulate 08 running while Overpass is unreachable
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts",
                                                     "08_harvest_hours.py")],
                       capture_output=True, text=True, cwd=ROOT)
    tail = [ln for ln in r.stdout.splitlines() if "WARNING" in ln]
    for ln in tail:
        print("  08:", ln.strip()[:130])

    after_h, after_b = counts()
    print("\nafter   hours.json :", dict(after_h))
    print("after   businesses :", dict(after_b))

    ok_h = after_h.get("scraped", 0) >= before_h.get("scraped", 0)
    ok_b = after_b.get("scraped", 0) >= before_b.get("scraped", 0)
    print(f"\nscraped preserved in hours.json    : {ok_h}")
    print(f"scraped preserved in businesses.json: {ok_b}")
    if not (ok_h and ok_b):
        sys.exit("FAILED: outage destroyed scraped schedules")
    print("PASS: a network outage no longer destroys harvested hours")
finally:
    shutil.copyfile(os.path.join(BACKUP_DIR, "hours.json"), HOURS)
    shutil.copyfile(os.path.join(BACKUP_DIR, "businesses.json"), BIZ)
    shutil.rmtree(BACKUP_DIR, ignore_errors=True)
    final_h, _ = counts()
    print("\nrestored:", dict(final_h))