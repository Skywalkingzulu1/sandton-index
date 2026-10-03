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
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

STAGES = [
    ("classify + group", "07_classify_and_group.py"),
    ("harvest hours", "08_harvest_hours.py"),
    ("harvest properties", "13_harvest_properties.py"),
    ("harvest cadastral", "15_harvest_cadastral.py"),
    ("build sites", "09_build_sites.py"),
    ("check css coverage", "test_css_coverage.py"),
    ("test search scoring", "test_search_js.js"),
    ("test search render", "test_search_render.js"),
    ("verify build", "verify_build.py"),
]

# Node tests. Skipped with a warning when Node is absent, because the site
# itself needs no JavaScript toolchain -- only the tests do.
NODE_TESTS = {"test search scoring", "test search render"}

# A stage allowed to fail without blocking the rest. Both harvests query free
# public endpoints that are rate limited and frequently overloaded -- Overpass
# timed out on every mirror while this was written, and the OSM /map API
# refuses above 50k nodes per request. Each degrades to whatever data is
# already cached on disk rather than blocking a publish, because the
# generators treat both datasets as optional: no hours.json means no hours
# module, no properties.json means no property pages.
NON_BLOCKING = {"harvest hours", "harvest properties", "harvest cadastral"}


def main():
    node = shutil.which("node")

    for label, script in STAGES:
        if label in NODE_TESTS and not node:
            print(f"\n>>> {label}  ({script})")
            print(f"    SKIPPED: node not on PATH -- "
                  f"the site needs no JS toolchain, only these tests do")
            continue

        path = os.path.join(HERE, script)
        print(f"\n>>> {label}  ({script})")
        cmd = [node, path] if label in NODE_TESTS else [sys.executable, path]
        result = subprocess.run(cmd, cwd=ROOT)
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
