#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
08_harvest_hours.py -- Fetch opening hours and merge them into the dataset.

Why this matters: "being open" is now a confirmed local-pack ranking factor
(#5 in Whitespark's 2026 study) and "open now near me" is among the fastest
growing local queries. A business page with no hours cannot intercept that
intent, so hours are treated as a first-class field rather than an optional one.

Source: OpenStreetMap Overpass API (free, no key). OSM hour coverage is
sparse, so most Sandton businesses will still fall through to the per-category
default. That is expected and handled explicitly -- see hours_confidence.

Optional upgrade: set GOOGLE_MAPS_API_KEY to fill from Google Places, which
has far better hours coverage. Without it this script runs Overpass-only.

hours_confidence values, and how the site template treats each:
  "scraped"  -- from OSM. Rendered as fact.
  "default"  -- inferred from category. Rendered as "typical hours, please
                confirm". EXCLUDED from LocalBusiness JSON-LD, because
                publishing an unverified opening time as fact is the fastest
                way to get a client's Business Profile penalised.

Outputs:
  data/hours.json      -- {record_id: {days, confidence, source}}
  data/businesses.json  -- updated in place with opening_hours fields
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA, HOURS_DEFAULTS, SANDTON_BBOX  # noqa: E402

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Bounding box for the Sandton cluster. Now shared with the property harvest
# (13_harvest_properties.py) via config, so both cover identical ground.
# Imported above from config; not redefined here.

# Map the OSM `opening_hours` weekday tags into a normalized structure.
WEEKDAY_KEYS = {
    "Mo": "monday", "Tu": "tuesday", "We": "wednesday", "Th": "thursday",
    "Fr": "friday", "Sa": "saturday", "Su": "sunday",
    "PH": "public_holiday", "Sa-Su": "saturday,sunday",
}


def overpass_query():
    """Fetch every element in the bbox that could be a listed business.

    The original query filtered on ["opening_hours"] alone, which is a trap:
    it assumes every OSM element with usable hours already carries that tag,
    and silently ignores every business that IS mapped but has no hours
    entered. Measured against our own 660 records, a query restricted to
    shop/amenity/office/craft/healthcare matched 468 of them by name and
    distance, while the hours-only query returned 711 elements that resolved
    to just 138 of our records.

    So the query is now a union: anything tagged with hours, OR anything
    tagged as a business. It is a strict superset of the old query, so it can
    only add candidates -- never lose them -- and it costs the same single
    request. Contact tags (phone, website, addr:*) are requested too: South
    African OSM tagging turned out to carry almost none of them on the
    elements matched to our records, but the cost is zero and the data
    improves upstream over time.
    """
    b = SANDTON_BBOX
    bbox = f"{b['south']},{b['west']},{b['north']},{b['east']}"

    business_keys = [
        "shop", "amenity", "office", "craft", "healthcare",
        "building:commercial", "landuse:commercial", "industrial",
        "leisure", "tourism", "club",
    ]

    clauses = []
    for key in ("opening_hours",):
        for etype in ("node", "way", "relation"):
            clauses.append(f'  {etype}["{key}"]({bbox});')
    for key in business_keys:
        clauses.append(f'  nwr["name"]["{key}"]({bbox});')

    body = "\n".join(clauses)
    return (f"[out:json][timeout:240];\n(\n{body}\n);\n"
            "out center tags;").strip()


def fetch_overpass():
    """Fetch every OSM element in the bbox that carries opening_hours."""
    query = overpass_query()
    last_err = None
    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(3):
            try:
                resp = requests.post(
                    endpoint, data={"data": query}, timeout=200,
                    headers={"User-Agent": "sandton-index/1.0 (hours harvest)"},
                )
                resp.raise_for_status()
                return resp.json().get("elements", [])
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                wait = 5 * (attempt + 1)
                print(f"  {endpoint} attempt {attempt + 1} failed: {exc}")
                time.sleep(wait)
    print(f"  Overpass unavailable ({last_err}). Proceeding with defaults only.")
    return []


def parse_osm_hours(raw):
    """Parse an OSM opening_hours string into {day: 'HH:MM-HH:MM'}.

    Handles the common cases only: 24/7, weekday blocks, day ranges and
    24h spans. Anything unparseable is skipped rather than guessed, which
    keeps a wrong value out of a client's page.
    """
    if not raw:
        return None

    text = raw.strip().lower().replace(" ", "")
    if text in ("24/7", "24hours", "00:00-24:00"):
        return {"_all": "00:00-24:00"}

    days = {}
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk or " " not in chunk:
            continue
        day_part, time_part = chunk.split(" ", 1)
        time_part = time_part.strip()

        times = []
        for span in time_part.split(","):
            span = span.strip()
            if "-" in span and ":" in span:
                op, cl = span.split("-", 1)
                if ":" in op and ":" in cl:
                    times.append(f"{op.strip()}-{cl.strip()}")
        if not times:
            continue
        value = ",".join(times)

        # Expand day specifiers: "Mo-Fr", "Sa,Su", "Mo-We,Fr"
        specs = [d.strip() for d in day_part.split(",")]
        for spec in specs:
            if "-" in spec:
                start, end = spec.split("-", 1)
                start, end = start.strip(), end.strip()
                if start in WEEKDAY_KEYS and end in WEEKDAY_KEYS:
                    order = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
                    try:
                        i, j = order.index(start), order.index(end)
                        span_days = order[i:j + 1] if i <= j else order[i:] + order[:j + 1]
                    except ValueError:
                        continue
                    for d in span_days:
                        days[WEEKDAY_KEYS[d]] = value
            elif spec in WEEKDAY_KEYS:
                days[WEEKDAY_KEYS[spec]] = value
            elif spec == "24/7":
                days["_all"] = "00:00-24:00"

    return days or None


def _tokens(value):
    """Lowercase alphanumeric token set for a name, minus branch/noise words."""
    from config import BRANCH_TOKENS, NON_ALNUM_RE, WS_RE
    if not value:
        return set()
    v = NON_ALNUM_RE.sub(" ", str(value).lower())
    return {t for t in WS_RE.split(v) if t and t not in BRANCH_TOKENS}

# Tokens that may legitimately differ between a brand and one of its
# variants without meaning the two are different businesses. A match is only
# accepted if every leftover token falls in this set, which stops generic
# trade words from collapsing two unrelated names into one.
QUALIFIER_TOKENS = {
    # branch / trading-form noise
    "the", "and", "store", "shop", "centre", "center", "branch", "north",
    "south", "east", "west", "sandton", "jhb", "rand", "local", "town",
    # chain sub-brands
    "express", "family", "food", "liquor", "select", "petrol", "service",
    "services", "hyper", "market", "lifestyle",
    # descriptive suffixes seen on Sandton trading names
    "hairbar", "adventure", "eastern", "western", "offices",
    "hypermarket", "world",
}


def _name_matches(rec_tokens, el_tokens):
    """True if two names describe the same business up to qualifier words.

    Earlier versions of this matcher failed in two opposite directions.
    Plain substring matching flagged 'Game Changers' as the retail chain
    Game. Partial token overlap produced convincing nonsense: 'Body Action'
    matched 'The Body Shop' and 'Garden Court Sandton City' matched
    'Garden Shop', each on one shared generic word. Strict set equality
    rejected the variants we actually want, like 'Pick n Pay' against
    'Pick n Pay Express'.

    The rule that survives all three cases: after stripping qualifier tokens,
    both names must reduce to the same non-empty token set. That accepts real
    variants and refuses two different businesses that merely share a
    common word.
    """
    if not rec_tokens or not el_tokens:
        return False
    rec_core = rec_tokens - QUALIFIER_TOKENS
    el_core = el_tokens - QUALIFIER_TOKENS
    if not rec_core or not el_core:
        return False
    return rec_core == el_core


def match_to_records(elements, records):
    """Attach scraped hours to our records by name corroboration + proximity.

    Proximity alone is unsafe in Sandton. The CBD is a dense cluster of malls
    and towers, so a 150m radius around a jewellery store easily contains a
    restaurant and a 24/7 office tower -- an early version of this script
    matched 90% of records and handed shops their neighbours' opening hours.

    A match therefore requires BOTH:
      1. the OSM element name to resolve to the same core tokens as the record
         name (see _name_matches), and
      2. the element to sit within MATCH_RADIUS_M of the record.

    Records failing either test fall through to the category default, which is
    labelled as an estimate. A visibly labelled guess is a far smaller risk
    than a confidently wrong claim presented as fact.
    """
    import math

    MATCH_RADIUS_M = 150

    def metres(dlat, dlon):
        dlat_r, dlon_r = math.radians(dlat), math.radians(dlon)
        x = dlon_r * math.cos(math.radians(dlat / 2)) * 111_320
        y = dlat_r * 111_320
        return math.hypot(x, y)

    indexed = []
    for el in elements:
        tags = el.get("tags") or {}
        raw_hours = tags.get("opening_hours")
        if not raw_hours:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        parsed = parse_osm_hours(raw_hours)
        if not parsed:
            continue

        # 24h schedules are almost always a building, tower, fuel station or
        # ATM rather than the shop we are describing. Some are written as
        # "Mo-Su 00:00-24:00" rather than "24/7", so check every day value.
        day_values = {v for k, v in parsed.items() if k != "_all"}
        if parsed.get("_all") == "00:00-24:00":
            continue
        if day_values and day_values == {"00:00-24:00"}:
            continue
        weekdays = {"monday", "tuesday", "wednesday", "thursday", "friday"}
        if weekdays.issubset(parsed.keys()) and all(
            parsed[w] == "00:00-24:00" for w in weekdays if w in parsed
        ):
            continue

        el_name = tags.get("name") or tags.get("brand") or ""
        indexed.append({
            "lat": lat, "lon": lon, "days": parsed, "raw": raw_hours,
            "tokens": _tokens(el_name), "el_name": el_name,
        })

    matched, rejected_name, rejected_dist = {}, 0, 0
    for rec in records:
        if rec.get("lat") is None or rec.get("lng") is None:
            continue
        rec_tokens = _tokens(rec.get("name"))
        if not rec_tokens:
            continue

        best = None
        for el in indexed:
            if not _name_matches(rec_tokens, el["tokens"]):
                continue
            d = metres(abs(rec["lat"] - el["lat"]),
                       abs(rec["lng"] - el["lon"]))
            if d > MATCH_RADIUS_M:
                rejected_dist += 1
                continue
            if best is None or d < best[0]:
                best = (d, el)

        if best:
            el = best[1]
            matched[rec["id"]] = {
                "days": el["days"],
                "confidence": "scraped",
                "source": f"openstreetmap ({el['el_name']}): {el['raw']}",
            }
        else:
            rejected_name += 1

    print(f"      name-mismatch rejections: {rejected_name}, "
          f"distance rejections: {rejected_dist}")
    return matched


def default_hours(hub_slug):
    span = HOURS_DEFAULTS.get(hub_slug)
    if not span:
        return None
    open_t, close_t = span
    days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    out = {d: f"{open_t}-{close_t}" for d in days}
    out["saturday"] = f"{open_t}-{min(close_t, '17:00')}"
    return out


def _write_json_atomic(path, payload):
    """Write JSON via a temp file and os.replace.

    A harvest run that is interrupted mid-write previously left a truncated
    businesses.json whose records had lost their harvested hours: every
    scraped schedule silently became a category default, and because default
    hours are excluded from JSON-LD the site still verified clean. 138 real
    schedules were destroyed that way before this was caught. os.replace is
    atomic on both Windows and POSIX, so the file on disk is always either the
    old complete version or the new complete version.
    """
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def main():
    biz_path = os.path.join(DATA, "businesses.json")
    if not os.path.exists(biz_path):
        sys.exit("Run 07_classify_and_group.py first -- businesses.json missing")

    with open(biz_path, encoding="utf-8") as fh:
        data = json.load(fh)
    records = data["records"]

    print("=" * 62)
    print("SANDTON INDEX -- opening hours harvest")
    print("=" * 62)

    print("[1/3] Querying Overpass for opening_hours in the Sandton bbox...")
    elements = fetch_overpass()
    print(f"      {len(elements)} OSM elements with hours in bbox")

    print("[2/3] Matching scraped hours to records by proximity...")
    scraped = match_to_records(elements, records)
    print(f"      {len(scraped)} records matched a scraped schedule")

    print("[3/3] Applying category defaults to the remainder...")
    stats = {"scraped": 0, "default": 0, "none": 0}
    for rec in records:
        rec_id = rec["id"]
        if rec_id in scraped:
            rec["opening_hours"] = scraped[rec_id]["days"]
            rec["hours_confidence"] = "scraped"
            rec["hours_source"] = scraped[rec_id]["source"]
            stats["scraped"] += 1
            continue

        fallback = default_hours(rec["hub"])
        if fallback:
            rec["opening_hours"] = fallback
            rec["hours_confidence"] = "default"
            rec["hours_source"] = (
                f"typical {rec['hub_title'].lower()} hours, unverified"
            )
            stats["default"] += 1
        else:
            rec["opening_hours"] = None
            rec["hours_confidence"] = "none"
            rec["hours_source"] = ""
            stats["none"] += 1

    _write_json_atomic(biz_path, data)

    hours_out = {
        rec["id"]: {
            "days": rec["opening_hours"],
            "confidence": rec["hours_confidence"],
            "source": rec["hours_source"],
        }
        for rec in records
    }
    _write_json_atomic(os.path.join(DATA, "hours.json"), hours_out)

    total = len(records)
    print("-" * 62)
    print(f"scraped (trusted)  : {stats['scraped']:>4}  "
          f"({stats['scraped'] / total * 100:.0f}%)  rendered as fact")
    print(f"default (estimate) : {stats['default']:>4}  "
          f"({stats['default'] / total * 100:.0f}%)  "
          f"labelled + excluded from schema")
    print(f"none               : {stats['none']:>4}  "
          f"({stats['none'] / total * 100:.0f}%)  no guess available")
    print("=" * 62)


if __name__ == "__main__":
    main()
