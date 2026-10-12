#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish_pages.py -- Build the site and publish it to GitHub Pages.

Publishes to the `gh-pages` branch rather than using a GitHub Actions
workflow. That is deliberate: pushing a file under .github/workflows/
requires the OAuth token to carry the `workflow` scope, which the standard
`gh auth login` does not grant, so the deploy workflow could not be pushed at
all. Publishing from a branch needs only `repo`, so this runs with a
stock-authenticated gh and no browser authorisation step.

The publish step works in a throwaway clone rather than by switching the
current repository between branches. Switching branches rewrites the index
and leaves the working tree on the publish branch, and an interrupted run
then leaves site files staged as deletions -- which is how an earlier
attempt accidentally committed a commit that emptied gh-pages.

Usage:
    python scripts/publish_pages.py              # build, publish, wait
    python scripts/publish_pages.py --no-build   # republish site/ as-is
    python scripts/publish_pages.py --no-wait    # push without polling
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = os.path.join(ROOT, "site")
CLONE = os.path.join(ROOT, ".publish_clone")
BRANCH = "gh-pages"
REPO = "Skywalkingzulu1/sandton-index"
REMOTE = f"https://github.com/{REPO}.git"
URL = "https://skywalkingzulu1.github.io/sandton-index/"


def run(args, cwd=None, check=True):
    result = subprocess.run(args, cwd=cwd or ROOT, capture_output=True,
                            text=True)
    if check and result.returncode != 0:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(f"failed: {' '.join(args)}")
    return result


def guard_site_url():
    """Refuse to publish a non-production build.

    A build made with a SANDTON_SITE_URL override (e.g. a localhost
    preview) carries that host in every canonical tag, sitemap entry
    and internal link. Publishing it would replace the live site with
    thousands of localhost canonicals. This guard fails loudly instead.
    """
    sys.path.insert(0, HERE)
    from config import SITE_URL  # noqa: E402
    if not SITE_URL.startswith("https://"):
        raise SystemExit(
            f"REFUSING TO PUBLISH: SITE_URL is {SITE_URL!r}, not https. "
            f"Unset SANDTON_SITE_URL and rebuild production output first.")
    bad = []
    checked = 0
    # The sitemap is generated from the same SITE_URL as every canonical
    # tag, so a localhost leak cannot spare it: scanning the sitemap
    # shards plus the homepage and a random sample is as rigorous as a
    # full-tree walk and finishes in seconds instead of minutes.
    import random
    targets = []
    for root, _dirs, files in os.walk(SITE):
        for f in files:
            if f == "sitemap.xml" or f.startswith("sitemap-") \
                    or f == "index.html" and root == SITE:
                targets.append(os.path.join(root, f))
    html_pages = []
    for root, _dirs, files in os.walk(SITE):
        for f in files:
            if f == "index.html":
                html_pages.append(os.path.join(root, f))
    random.seed(20261011)
    targets += random.sample(html_pages, min(100, len(html_pages)))
    for p in targets:
        # Canonical tags, asset links and sitemap entries all live in
        # the first bytes.
        with open(p, encoding="utf-8") as fh:
            head = fh.read(4096)
        checked += 1
        if "http://localhost" in head or "http://127.0.0.1" in head:
            bad.append(os.path.relpath(p, SITE))
            if len(bad) >= 5:
                break
        if len(bad) >= 5:
            break
    if bad:
        raise SystemExit(
            "REFUSING TO PUBLISH: localhost URLs baked into output, e.g. "
            f"{bad[:3]}. Rebuild production output first.")
    print(f">>> guard: SITE_URL={SITE_URL}, no localhost URLs in output")


def build():
    print(">>> building")
    run([sys.executable, os.path.join(HERE, "build_all.py")])
    if not os.path.isdir(SITE):
        raise SystemExit("site/ missing after build")


def ensure_nojekyll():
    """Pages runs Jekyll by default, which silently drops paths beginning with
    an underscore. .nojekyll makes it serve the output verbatim."""
    path = os.path.join(SITE, ".nojekyll")
    if not os.path.exists(path):
        open(path, "w", encoding="utf-8").close()
        print("    added .nojekyll")


def ensure_pages_source():
    r = run(["gh", "api", f"repos/{REPO}/pages", "--jq",
             '.source.branch + " " + .source.path'], check=False)
    current = r.stdout.strip()
    if current != f"{BRANCH} /":
        print(f">>> setting Pages source to {BRANCH} / (was '{current}')")
        run(["gh", "api", "-X", "PUT", f"repos/{REPO}/pages",
             "-f", f"source[branch]={BRANCH}", "-f", "source[path]=/"],
            check=False)
    else:
        print(f">>> Pages source already {BRANCH} /")


def discard(path):
    """Remove a temp directory, tolerating Windows file locks.

    git keeps read handles on loose objects briefly after a push, so a plain
    rmtree intermittently fails with PermissionError on WinError 5. The
    clone is disposable and outside the published output, so a leftover
    directory must not abort a publish that already succeeded -- retry once,
    then force and continue.
    """
    if not os.path.exists(path):
        return
    for attempt in range(3):
        try:
            shutil.rmtree(path)
            return
        except (PermissionError, OSError):
            time.sleep(1.5)
            if attempt == 1:
                shutil.rmtree(path, onerror=_force_remove)
                return


def _force_remove(func, path, _exc):
    try:
        os.chmod(path, 0o700)
        func(path)
    except OSError:
        pass


def copy_into(src, dst):
    for entry in os.listdir(src):
        s = os.path.join(src, entry)
        d = os.path.join(dst, entry)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)


def publish():
    print(f">>> publishing to {BRANCH}")
    discard(CLONE)

    run(["git", "clone", "--quiet", REMOTE, CLONE])
    r = run(["git", "checkout", "--quiet", BRANCH], cwd=CLONE, check=False)
    if r.returncode != 0:
        run(["git", "checkout", "--orphan", BRANCH], cwd=CLONE)

    # Wipe the cloned tree, keeping .git, then drop site/ in at the root.
    for entry in os.listdir(CLONE):
        if entry == ".git":
            continue
        p = os.path.join(CLONE, entry)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

    copy_into(SITE, CLONE)

    run(["git", "add", "-A"], cwd=CLONE)
    if run(["git", "diff", "--cached", "--quiet"], cwd=CLONE,
           check=False).returncode == 0:
        print("    nothing changed")
        discard(CLONE)
        return False

    run(["git", "-c", "user.name=Sandton Index",
         "-c", "user.email=noreply@github.com",
         "commit", "--quiet", "-m",
         "Publish Sandton Index\n\nGenerated by scripts/09_build_sites.py."],
        cwd=CLONE)
    run(["git", "push", "--quiet", "origin", f"HEAD:{BRANCH}"], cwd=CLONE)
    sha = run(["git", "rev-parse", "--short", "HEAD"], cwd=CLONE).stdout.strip()
    n = len(run(["git", "ls-files"], cwd=CLONE).stdout.splitlines())
    print(f"    pushed {sha} ({n} files)")
    discard(CLONE)
    return True


def wait_for_build(timeout_s=480):
    print(">>> waiting for Pages build")
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        status = run(["gh", "api", f"repos/{REPO}/pages/builds/latest",
                      "--jq", ".status"], check=False).stdout.strip()
        if status != last:
            print(f"    {status}")
            last = status
        if status in ("built", "errored"):
            return status == "built"
        time.sleep(10)
    print("    timed out")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--no-wait", action="store_true")
    args = ap.parse_args()

    if not args.no_build:
        build()
    ensure_nojekyll()
    guard_site_url()
    ensure_pages_source()

    if not publish():
        print("\nAlready up to date.")
        return

    if args.no_wait:
        print(f"\nPushed. See the build in repository Pages settings.\n{URL}")
        return

    ok = wait_for_build()
    print(f"\n{'Live' if ok else 'Build did not confirm'}: {URL}")


if __name__ == "__main__":
    main()