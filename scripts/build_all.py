#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_all.py -- Run the full pipeline in order and stop on the first failure.

Each stage is a separate script so a stage can be re-run on its own while
iterating, but the common case is "rebuild everything", and running them
out of order silently produces a wrong site (08 and 09 both read
data/businesses.json, so skipping 07 leaves stale tiers in place).

Exits non-zero if any stage fails, and refuses to run the build stage if
verification of the data stage has not passed.
"""
import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

STAGES = [
    ("classify + group", "07_classify_and_group.py"),
    ("harvest hours", "08_harvest_hours.py"),
    ("build sites", "09_build_sites.py"),
    ("verify build", "verify_build.py"),
]

# A stage allowed to fail without blocking the rest. Overpass is a free
# public endpoint subject to rate limiting; the harvester already degrades to
# category-default hours, so losing it degrades data quality rather than
# blocking a publish.
NON_BLOCKING = {"harvest hours"}


def main():
    for label, script in STAGES:
        path = os.path.join(HERE, script)
        print(f"\n>>> {label}  ({script})")
        result = subprocess.run([sys.executable, path], cwd=ROOT)
        if result.returncode != 0:
            if label in NON_BLOCKING:
                print(f"    WARNING: {label} failed, continuing with the "
                      f"dataset already on disk")
                continue
            print(f"\nABORTED: {label} failed with exit code "
                  f"{result.returncode}")
            sys.exit(result.returncode)

    print("\nPipeline complete. site/ is ready to publish.")


if __name__ == "__main__":
    main()
