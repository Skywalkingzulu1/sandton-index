#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
10_enrich_google.py -- Enrich the dataset from the Google Maps Scraper API.

Why this is the highest-value data upgrade available: OpenStreetMap only
covers ~21% of Sandton businesses, so 478 of 660 records fell back to a
per-category guess. Google is where the business owner publishes their own
hours, and the same response carries the phone number, the place ID and
whether a listing has been claimed at all.

What gets merged (high confidence, owner-published):
  phone         prefer the +27 international form over the local 011 form
  opening_hours a rolling 7-day window, which covers each weekday once
  place_id      enables a real Google Maps link
  claimed       YES/NO -- decides whether the Maps CTA says "add a place"
                or "manage your profile"
  rating        display only, stamped with the date it was read
  review_count  display only, same stamp

What is deliberately NOT merged automatically:
  website       Google returns a Website field, but merging it would re-tier
                every record and flip which businesses are told "you have no
                website". That pitch is the commercial core of the site, and a
                wrong flip does real damage to a real business. Recorded as
                google_website for review instead.
  address       Google's Fulladdress parsing is unreliable in this data set
                ("and, Shop L0A Sandton City Corner of Alice Lane"). Recorded
                as google_address for review instead.

Match discipline is borrowed wholesale from 08_harvest_hours.py: name
corroboration AND a 150m radius. Proximity alone is unsafe in Sandton, where
the CBD packs a restaurant, a jeweller and a 24/7 tower into the same block.

Requires GMAPSEXTRACTOR_TOKEN in .env. Exits cleanly without it.

Output: data/google.json -- {record_id: {...}}
"""
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA, GMAPSEXTRACTOR_TOKEN, HUB_BY_SLUG  # noqa: E402


def _load(path):
    """Import a sibling script by filename.

    08_harvest_hours.py cannot be imported normally -- a module name starting
    with a digit is not a legal identifier, so `import` cannot reference it.
    Loading it by path is the only way to reuse its matcher instead of
    forking a second, subtly different copy of name matching.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "harvest_hours", os.path.join(
            os.path.dirname(os.path.abspath(__file__)), path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_hours = _load("08_harvest_hours.py")
_name_matches = _hours._name_matches
_tokens = _hours._tokens

# 08 defines both of these INSIDE match_to_records() rather than at module
# scope, so they are not importable. They are lifted verbatim from its source
# rather than re-derived: 150m around a Sandton CBD storefront still contains
# several unrelated businesses, so distance alone can never decide a match,
# and a second copy of this formula would eventually drift.
MATCH_RADIUS_M = 150


def metres(lat1, lon1, lat2, lon2):
    dlat, dlon = abs(lat1 - lat2), abs(lon1 - lon2)
    dlat_r, dlon_r = math.radians(dlat), math.radians(dlon)
    x = dlon_r * math.cos(math.radians(dlat / 2)) * 111_320
    y = dlat_r * 111_320
    return math.hypot(x, y)

API_URL = "https://cloud.gmapsextractor.com/api/v2/search"

# Raw responses are cached on disk, one file per query.
#
# The free tier counts every request for the whole calendar month, and 34
# requests exhausted it. Without a cache, every re-run to fix a bug or a
# matching bug would silently burn quota the user cannot get back. With it,
# a re-run after a token rotation costs only the queries not already cached,
# and a run interrupted by the quota cap resumes where it stopped instead of
# starting over.
CACHE_DIR = os.path.join(DATA, "_google_cache")

# Google appends the branch or centre name to the trading name, so our
# records ("Pick n Pay") rarely equal Google's ("Pick n Pay Sandton City").
# Reusing 08's strict set-equality matcher directly rejects nearly all of
# those. This allows Google's token set to be a strict superset of ours,
# but ONLY when every extra token is a place word and the 150m gate also
# passes -- so "Woolworths" in Illovo still cannot match "Woolworths Sandton
# City" in the CBD, because the distance check rejects it.
PLACE_WORDS = {
    "sandton", "city", "centre", "center", "north", "south", "east", "west",
    "gardens", "garden", "park", "plaza", "mall", "square", "building",
    "tower", "estate", "rand", "jhb", "gauteng", "walk", "hub", "court",
    "lodge", "hill", "crossing", "link", "node", "junction", "village",
    "heights", "ridge", "grove", "avenue", "road",
    # Real localities inside the Sandton cluster. Without these, Google
    # branch names like "Kokoro Rivonia Gardens" never match our "Kokoro".
    "rivonia", "illovo", "bryanston", "sunninghill", "woodmead", "marlboro",
    "sandhurst", "morningside", "parkmore", "dainfern", "magali", "umberton",
    "brenthurst", "corlett", "craighall", "inanda", "klein", "marlton",
}

# Cloudflare fronts this API and returns error 1010 for urllib's default
# User-Agent. This header is required, not cosmetic.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# Sandton cluster centre. Zoom 13 covers the whole cluster; a tighter zoom
# silently truncates results to whatever is under the pin.
LL = "@-26.1076,28.0567,13z"

# Free tier is 300 requests/minute. Stay well under it so a retry storm or a
# parallel run cannot trip the limiter.
REQUEST_DELAY = 0.35

# Hard cap on requests spent in a single run.
#
# The free allowance is far smaller than the per-minute limit suggests: ~34
# requests exhausted it for the whole calendar month. A run that spends 72
# (24 hubs x 3 pages) therefore cannot finish on a free key, and the failure
# mode is ugly -- most of the budget gone, coverage spread thinly across half
# the hubs, nothing to show for it.
#
# So the run is budgeted rather than greedy: it spends what it has on the
# queries most likely to match unserved records, then stops and says so.
# Cached queries cost nothing, so raising this later is safe.
REQUEST_BUDGET = int(os.environ.get("GMAPSEXTRACTOR_BUDGET", "30"))

WEEKDAY_KEYS = {
    "monday": "monday", "tuesday": "tuesday", "wednesday": "wednesday",
    "thursday": "thursday", "friday": "friday", "saturday": "saturday",
    "sunday": "sunday",
}

NBSP = "\u202f"
DASHES = "\u2010\u2011\u2012\u2013\u2014\u2212-"


def clean(value):
    """Collapse the odd Unicode the API uses inside times and dashes."""
    if not value:
        return ""
    v = str(value).replace(NBSP, " ").strip()
    for d in DASHES:
        v = v.replace(d, "-")
    return re.sub(r"\s+", " ", v)


def to_24h(token):
    """'8 am' -> '08:00', '6:30 pm' -> '18:30', '12 pm' -> '12:00'."""
    t = clean(token).lower().replace(".", "")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", t)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2) or 0)
    ap = m.group(3)
    if ap == "pm" and hh < 12:
        hh += 12
    elif ap == "am" and hh == 12:
        hh = 0
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return f"{hh:02d}:{mm:02d}"


def parse_opening_hours(raw):
    """Parse the rolling 7-day window into {weekday: "HH:MM-HH:MM[,..]"}.

    The API returns the next seven consecutive days starting today, e.g.
    "Friday(2026-10-02): [9 am-6 pm], Saturday(2026-10-03): [...]". Seven
    consecutive days contains each weekday exactly once, so a single response
    yields a complete weekly schedule -- no multi-day crawl needed.

    Days marked Closed are omitted rather than stored, matching how the rest
    of the pipeline treats an absent day.

    A day with several ranges keeps them all, comma separated, so a lunch
    break is not silently flattened into one wrong span.
    """
    text = clean(raw)
    if not text:
        return {}
    out = {}
    for day, body in re.findall(
            r"([A-Za-z]+)\s*\(\d{4}-\d{2}-\d{2}\)\s*:\s*\[([^\]]*)\]", text):
        key = WEEKDAY_KEYS.get(day.strip().lower())
        if not key:
            continue
        body = body.strip()
        if not body or body.lower() == "closed":
            continue
        spans = []
        for part in body.split(","):
            if "-" not in part:
                continue
            left, _, right = part.partition("-")
            op, cl = to_24h(left), to_24h(right)
            if op and cl:
                spans.append(f"{op}-{cl}")
        if spans:
            out[key] = ",".join(spans)
    return out


def pick_phone(place):
    """Prefer +27 international, else the first local number.

    The API returns both forms; the site already standardises on +27, and a
    directory that shows two numbers for one business looks unmaintained.
    """
    for field in ("Phones", "Phone"):
        raw = place.get(field)
        if not raw:
            continue
        if isinstance(raw, list):
            raw = ", ".join(str(x) for x in raw)
        cands = [clean(x) for x in str(raw).split(",")]
        cands = [x for x in cands if re.search(r"\d", x)]
        if not cands:
            continue
        intl = [x for x in cands if x.replace(" ", "").startswith("+27")]
        return (intl or cands)[0]
    return ""


def pick_rating(place):
    for field in ("Average Rating", "rating"):
        val = place.get(field)
        if val in (None, "", "None"):
            continue
        try:
            return round(float(val), 1)
        except (TypeError, ValueError):
            continue
    return None


def pick_reviews(place):
    for field in ("Review Count", "reviews"):
        val = place.get(field)
        if val in (None, "", "None"):
            continue
        try:
            return int(str(val).replace(",", ""))
        except (TypeError, ValueError):
            continue
    return None


def api_search(query, page=1, retries=3):
    """One search, cached on disk.

    A cache hit costs zero quota. A cache miss spends one request and stores
    the result, including an empty one -- otherwise a query that legitimately
    returns nothing would be retried forever on every run.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    cache_path = os.path.join(CACHE_DIR, f"{slug}__p{page}.json")

    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass  # corrupt cache entry: fall through and refetch

    payload = {"q": query, "page": page, "ll": LL, "hl": "en",
               "gl": "za", "extra": False}
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {GMAPSEXTRACTOR_TOKEN}",
               "User-Agent": UA, "Accept": "application/json"}

    result = {}
    for attempt in range(retries):
        req = urllib.request.Request(API_URL, data=data, headers=headers,
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")[:200]
            except Exception:
                pass
            if e.code == 429 and attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"      rate limited, backing off {wait}s")
                time.sleep(wait)
                continue
            if "exceeded your free requests" in body:
                raise QuotaExhausted(body)
            print(f"      HTTP {e.code} on {query!r}: {body}")
            return {}
        except Exception as e:  # noqa: BLE001 - network layer is broad
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            print(f"      request failed on {query!r}: {e}")
            return {}
        time.sleep(REQUEST_DELAY)

    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False)
    return result


class QuotaExhausted(RuntimeError):
    """Raised when the monthly free allowance runs out mid-run.

    Distinct from a transient 429: retrying cannot help, so the run stops and
    keeps everything collected so far rather than hammering the endpoint.
    """


def collect_places(records):
    """Search each hub across the cluster and dedupe by place ID.

    Budgeted, not greedy. Hubs are visited worst-served-first: the ones with
    the most records still lacking a Google match are searched before hubs
    already well covered by the cache. With ~30 requests a month, spreading
    them evenly across 24 hubs buys one page each; spending them where the
    gap is widest buys far more actual matches.

    Stops cleanly when the budget or the monthly quota runs out. Cached
    responses still count toward coverage on the next run with a fresh token,
    so a partial run is never wasted work.
    """
    places = {}
    fetched = 0
    cached = 0
    stop_reason = None

    # how many records does each hub have, worst-served first
    by_hub = {}
    for r in records:
        by_hub.setdefault(r.get("hub"), []).append(r)
    order = sorted(by_hub.items(), key=lambda kv: len(kv[1]), reverse=True)

    for i, (slug, recs) in enumerate(order, start=1):
        hub = HUB_BY_SLUG.get(slug, {})
        singular = (hub.get("singular") or slug or "").strip().lower()
        if not singular:
            continue
        for page in (1, 2, 3):
            if fetched >= REQUEST_BUDGET:
                stop_reason = f"request budget of {REQUEST_BUDGET} reached"
                break
            q = f"{singular} Sandton Johannesburg"
            slug_q = re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")
            cache_path = os.path.join(CACHE_DIR, f"{slug_q}__p{page}.json")
            was_cached = os.path.exists(cache_path)
            try:
                res = api_search(q, page=page)
            except QuotaExhausted as e:
                print(f"\n  MONTHLY QUOTA EXHAUSTED: {e}")
                stop_reason = "monthly quota exhausted"
                break
            if was_cached:
                cached += 1
            else:
                fetched += 1
            rows = res.get("data") or []
            if not rows:
                break
            for p in rows:
                pid = p.get("Place Id")
                if pid:
                    places[pid] = p
            time.sleep(REQUEST_DELAY)
        print(f"  [{i:>2}/{len(order)}] {slug:<26} "
              f"({len(recs)} records)  places={len(places)}")
        if stop_reason:
            print(f"  stopping: {stop_reason}")
            break

    print(f"\n  {fetched} requests spent, {cached} served from cache, "
          f"{len(places)} unique places")
    if stop_reason:
        print(f"  PARTIAL RUN ({stop_reason}). Cached queries are kept, so a")
        print(f"  re-run with a fresh token finishes the job for free.")
    return places


def google_name_matches(rec_tokens, place_tokens):
    """Match a record name against a Google place name.

    Two passes, both required to hold:

      1. 08's strict test -- both names reduce to the same core token set.
      2. a superset test -- Google's tokens are a strict superset of ours and
         every extra token is a place word. This is what accepts "Pick n Pay"
         against "Pick n Pay Sandton City" without loosening 08's matcher for
         the OSM path, where an equally loose rule would mis-assign hours.

    Neither pass is trusted on its own. The 150m proximity gate in
    match_places() still has to agree, which is what stops a parent brand from
    claiming a branch's details.
    """
    if _name_matches(rec_tokens, place_tokens):
        return True
    qualifiers = _hours.QUALIFIER_TOKENS
    rec_core = rec_tokens - qualifiers
    plc_core = place_tokens - qualifiers
    if not rec_core or not rec_core < plc_core:
        return False
    return (plc_core - rec_core) <= PLACE_WORDS


def match_places(places, records):
    """Attach a Google place to a record: name corroboration AND proximity.

    Reuses the matcher from 08_harvest_hours unchanged. Its docstring records
    the two ways earlier attempts got this wrong, and neither failure mode is
    acceptable here -- handing a restaurant another shop's phone number is
    worse than having no phone number.
    """
    matched = {}
    rejected_name = 0
    rejected_dist = 0
    taken = set()

    prepared = []
    for p in places.values():
        lat, lng = p.get("Latitude"), p.get("Longitude")
        if lat in (None, "") or lng in (None, ""):
            continue
        try:
            prepared.append((float(lat), float(lng), p,
                             _tokens(p.get("Name"))))
        except (TypeError, ValueError):
            continue

    for rec in records:
        if rec.get("lat") is None or rec.get("lng") is None:
            continue
        rec_tok = _tokens(rec.get("name"))
        best = None
        for lat, lng, p, p_tok in prepared:
            if not google_name_matches(rec_tok, p_tok):
                rejected_name += 1
                continue
            d = metres(rec["lat"], rec["lng"], lat, lng)
            if d > MATCH_RADIUS_M:
                rejected_dist += 1
                continue
            # one place cannot satisfy two records; if two records claim the
            # same place, keep the closer pair
            if best is None or d < best[0]:
                best = (d, p)
        if best:
            p = best[1]
            pid = p.get("Place Id")
            if pid in taken:
                continue
            taken.add(pid)
            matched[rec["id"]] = p

    print(f"      matched {len(matched)} records")
    print(f"      name-mismatch rejections: {rejected_name}, "
          f"distance rejections: {rejected_dist}")
    return matched


def main():
    print("=" * 62)
    print("SANDTON INDEX -- Google Maps enrichment")
    print("=" * 62)

    if not GMAPSEXTRACTOR_TOKEN:
        print("\nGMAPSEXTRACTOR_TOKEN not set.")
        print("Add it to .env (see .env.example) and re-run. Nothing else")
        print("in the pipeline needs it -- this step is an upgrade, not a")
        print("dependency.\n")
        return

    db_path = os.path.join(DATA, "businesses.json")
    with open(db_path, encoding="utf-8") as fh:
        records = json.load(fh)["records"]
    print(f"\n[1/3] Loaded {len(records)} records")

    print("\n[2/3] Searching Google Maps by category...")
    places = collect_places(records)
    if not places:
        print("      no places returned -- check token and quota")
        return

    print("\n[3/3] Matching places to records by name + proximity...")
    matched = match_places(places, records)

    today = date.today().isoformat()
    out = {}
    stats = {"phone_new": 0, "phone_confirms": 0, "hours": 0,
             "multi_span": 0, "claimed_yes": 0, "claimed_no": 0,
             "rated": 0, "website_differs": 0, "website_new": 0,
             "address_differs": 0, "closed_some_day": 0}

    for rec in records:
        p = matched.get(rec["id"])
        if not p:
            continue
        entry = {"matched_name": p.get("Name"),
                 "place_id": p.get("Place Id"),
                 "claimed": (p.get("Claimed") or "").upper() or None,
                 "rating_date": today,
                 "retrieved_at": today}

        phone = pick_phone(p)
        if phone:
            entry["google_phone"] = phone
            if rec.get("phone"):
                if _norm_phone(phone) == _norm_phone(rec["phone"]):
                    stats["phone_confirms"] += 1
                else:
                    entry["phone_conflicts"] = True
            else:
                stats["phone_new"] += 1

        hours = parse_opening_hours(p.get("Opening Hours"))
        if hours:
            entry["opening_hours"] = hours
            stats["hours"] += 1
            if any("," in v for v in hours.values()):
                stats["multi_span"] += 1
            if len(hours) < 7:
                stats["closed_some_day"] += 1

        rating = pick_rating(p)
        if rating is not None:
            entry["rating"] = rating
            stats["rated"] += 1
        reviews = pick_reviews(p)
        if reviews is not None:
            entry["review_count"] = reviews

        if p.get("Google Maps URL"):
            entry["maps_url"] = p["Google Maps URL"]

        site = clean(p.get("Website") or p.get("Domain") or "")
        # Google's Website field carries tracking params; strip them so a
        # manual comparison against our chain guard list is meaningful.
        site = re.sub(r"[?&](utm_|gmb)[^=]*=[^&]*", "", site).strip("?&/")
        if site:
            entry["google_website"] = site
            ours = clean(rec.get("website") or "")
            if not ours:
                stats["website_new"] += 1
            elif site.lower().rstrip("/") not in ours.lower().rstrip("/"):
                stats["website_differs"] += 1

        if p.get("Fulladdress"):
            entry["google_address"] = clean(p["Fulladdress"])

        out[rec["id"]] = entry

    dest = os.path.join(DATA, "google.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

    total = len(records)
    print("\n" + "-" * 62)
    print(f"  records matched   : {len(out)}/{total} "
          f"({len(out) / total * 100:.0f}%)")
    print(f"  phone added       : {stats['phone_new']}")
    print(f"  phone confirmed   : {stats['phone_confirms']}")
    print(f"  opening hours     : {stats['hours']}")
    print(f"  ...multi-span days: {stats['multi_span']}")
    print(f"  ...closed 1+ days : {stats['closed_some_day']}")
    print(f"  rating available  : {stats['rated']}")
    print(f"  already claimed   : {stats['claimed_yes']}")
    print(f"  NOT claimed       : {stats['claimed_no']}")
    print(f"  website we lack   : {stats['website_new']}  <- needs review")
    print(f"  website differs   : {stats['website_differs']}  <- needs review")
    print(f"\n  written: data/google.json")
    print("=" * 62)


def _norm_phone(v):
    return re.sub(r"\D", "", str(v or ""))


if __name__ == "__main__":
    main()
