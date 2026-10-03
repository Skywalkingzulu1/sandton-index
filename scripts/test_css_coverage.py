"""Check that every class emitted into the site is styled, and that the
stylesheet parses. A hand-written stylesheet drifting from the markup is the
easiest defect in this project to ship without noticing.

Run after 09_build_sites.py:

    python scripts/test_css_coverage.py

Exits 1 if the stylesheet has unbalanced braces or if a page emits a class
with no rule behind it. Classes present in the stylesheet but absent from the
static HTML are reported as a note, not a failure: several are injected at
runtime by sandton.js (.result, .search-empty, .open) or only rendered under a
data condition (.conflict, .today).
"""
import io
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))          # scripts
SITE = os.path.join(os.path.dirname(ROOT), "site")
CSS_PATH = os.path.join(ROOT, "assets", "sandton.css")

if not os.path.isdir(SITE):
    print(f"  x site not found at {SITE} -- run 09_build_sites.py first")
    sys.exit(1)

css = io.open(CSS_PATH, encoding="utf-8").read()

# strip comments before parsing
css_nc = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

# --- 1. balanced braces ------------------------------------------------
depth = 0
line_no = 1
for ch in css_nc:
    if ch == "\n":
        line_no += 1
    elif ch == "{":
        depth += 1
    elif ch == "}":
        depth -= 1
        if depth < 0:
            print(f"  x unexpected }} at line {line_no}")
            sys.exit(1)
print("braces balanced      :", "yes" if depth == 0 else f"NO (depth {depth})")

# --- 2. selectors defined ---------------------------------------------
defined = set()
for m in re.finditer(r"([^{}]+)\{", css_nc):
    sel = m.group(1)
    # drop at-rules that prefix a selector (@media ...)
    sel = re.sub(r"@(?:media|supports|container)[^{]*$", "", sel).strip()
    if not sel or sel.startswith("@"):
        continue
    for part in sel.split(","):
        for cls in re.findall(r"\.([A-Za-z0-9_-]+)", part):
            defined.add(cls)
print("classes in stylesheet:", len(defined))

# --- 3. classes used in the site --------------------------------------
used = Counter()
for root, _d, files in os.walk(SITE):
    for f in files:
        if f.endswith(".html"):
            h = io.open(os.path.join(root, f), encoding="utf-8",
                        errors="replace").read()
            for m in re.finditer(r'class="([^"]+)"', h):
                for k in m.group(1).split():
                    used[k] += 1

missing = {k: v for k, v in used.items() if k not in defined}
if missing:
    print(f"\n  x {len(missing)} class(es) emitted but never styled:")
    for k, v in sorted(missing.items(), key=lambda x: -x[1]):
        print(f"      .{k:<24} used {v}x")
else:
    print("unstyled classes     : none -- every emitted class has a rule")

unused = sorted(defined - set(used))
if unused:
    print(f"\n  note {len(unused)} styled class(es) not currently emitted:")
    print("      " + ", ".join("." + c for c in unused))

sys.exit(1 if missing else 0)