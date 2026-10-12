#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
17_harvest_gauteng_businesses.py -- Harvest every named business in Gauteng
from OpenStreetMap, recording whether OSM lists a website for it.

Why the tiled /map API and not Overpass or Google
-------------------------------------------------
Overpass times out on province-scale geometry queries from the public
mirrors (see 16_harvest_gauteng_suburbs.py). The Google scraper free tier
dies after ~34 requests a month, and Gauteng needs thousands. The OSM main
API answers reliably; it has no query language, so the province is tiled
adaptively: 0.1-degree tiles where sparse, subdividing to 0.025 where the
API refuses a dense tile. Every tile response is cached, so reruns and
resume cost nothing.

What "has a website" means here
-------------------------------
Strictly: the OSM element carries website=*, contact:website=* or url=*.
Tag absence is NOT proof a business has no website (the CHAIN_GUARD lesson
from the Sandton directory: 60 chain records were mistagged exactly this
way). The output field is therefore has_website_osm, and every consumer
must label it "website listed in OSM" vs "no website listed in OSM" --
never "has no website".

What is collected: named nodes/ways/relations whose primary tag is
business-like (shops, food/drink, offices, crafts, healthcare,
hospitality, services). Civic, education, worship, transport and utility
tags are excluded: they are not companies. Junk names (toilets, parking,
vending machines...) are dropped, as are entries without coordinates.

District assignment reuses data/gauteng_suburbs.json: each business takes
the district of its nearest mapped suburb within 5 km. Beyond that it is
left unassigned rather than guessed. This is proximity inference and is
labelled as such everywhere it surfaces.

Output: data/gauteng_businesses.json (gitignored above ~2 MB; the
dashboard degrades to Sandton-only figures without it).
"""
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA  # noqa: E402

API = "https://api.openstreetmap.org/api/0.6/map"
UA = "sandton-index-directory/1.0 (business directory; contact: site operator)"
CACHE = os.path.join(DATA, "_osm_biz_cache")
OUT_PATH = os.path.join(DATA, "gauteng_businesses.json")

TILE = 0.1
MAX_DEPTH = 2
ASSIGN_KM = 5.0

# key -> allowed values (None = any value). Everything not listed here is
# not a company for this harvest's purposes.
BIZ_KEYS = {
    "shop": None,
    "office": None,
    "craft": None,
    "healthcare": None,
    "amenity": {
        "restaurant", "cafe", "fast_food", "food_court", "bar", "pub",
        "biergarten", "ice_cream", "bank", "clinic", "doctors", "dentist",
        "pharmacy", "optician", "hospital", "veterinary", "car_rental",
        "car_wash", "fuel", "cinema", "theatre", "arts_centre", "casino",
        "nightclub", "marketplace",
    },
    "tourism": {"hotel", "guest_house", "hostel", "motel", "apartment",
                "chalet", "camp_site", "caravan_site"},
    "leisure": {"fitness_centre", "sports_centre", "bowling_alley",
                "golf_course", "water_park", "amusement_arcade"},
}

JUNK_NAME = re.compile(
    r"^(toilets?|ablutions?|parking|parkings|parking lot|atm|atms|"
    r"vending machine|post box|postbox|telephone|phone booth|rubbish|"
    r"dump|recycling|drinking water|water tap|bench|benches|shelter|"
    r"bus stop|taxi rank|station|unclassified|unknown|test|placeholder|"
    r"name|copy|duplicate|building [0-9]+)$", re.I)


def fetch_tile(s, w, n, e, depth=0):
    """Raw tile bytes, cached; subdivides on refusal up to MAX_DEPTH."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{s}_{w}_{n}_{e}.xml")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "rb") as fh:
            return fh.read()
    url = API + "?" + urllib.parse.urlencode(
        {"bbox": f"{w},{s},{e},{n}"})
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read()
            tmp = path + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(raw)
            os.replace(tmp, path)
            return raw
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(3 + attempt * 4)
    # Refused (dense tile) or dead: subdivide once more if allowed.
    if depth < MAX_DEPTH:
        mid_lat = round((s + n) / 2, 4)
        mid_lon = round((w + e) / 2, 4)
        out = b""
        for ss, ww, nn, ee in (
                (s, w, mid_lat, mid_lon), (s, mid_lon, mid_lat, e),
                (mid_lat, w, n, mid_lon), (mid_lat, mid_lon, n, e)):
            sub = fetch_tile(ss, ww, nn, ee, depth + 1)
            if sub:
                out += sub
        if out:
            with open(path, "wb") as fh:
                fh.write(out)
            return out
    print(f"    tile {s},{w} failed at depth {depth}: {str(last)[:70]}",
          flush=True)
    return None


def parse_tile(raw):
    """(businesses, ) from one tile's XML. Businesses are dicts.

    Subdivided tiles are stored as several XML documents concatenated in
    one cache file, which no parser accepts whole -- so split on the XML
    declaration and parse each document separately. Without this, every
    dense (i.e. subdivided, i.e. urban) tile silently yields nothing.
    """
    docs = [d for d in re.split(rb"<\?xml", raw) if d.strip()]
    if not docs:
        return []
    roots = []
    for doc in docs:
        try:
            roots.append(ET.fromstring(b"<?xml" + doc))
        except ET.ParseError:
            continue
    # One pass for node positions across ALL documents first: a way near a
    # subdivision boundary references nodes that live in the sibling
    # document. Parsing each document in isolation would drop those ways.
    pos = {}
    for root in roots:
        for el in root.findall("node"):
            try:
                pos[int(el.get("id"))] = (float(el.get("lat")),
                                          float(el.get("lon")))
            except (TypeError, ValueError):
                continue
    out = []
    for root in roots:
        out.extend(_parse_root(root, pos))
    return out


def _parse_root(root, pos):
    out = []
    for el in list(root.findall("node")) + list(root.findall("way")):
        tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
        name = (tags.get("name") or "").strip()
        if not name or JUNK_NAME.match(name):
            continue
        key, val = None, None
        for k, allowed in BIZ_KEYS.items():
            if k in tags and (allowed is None or tags[k] in allowed):
                key, val = k, tags[k]
                break
        if key is None:
            continue
        if el.tag == "node":
            try:
                lat, lon = float(el.get("lat")), float(el.get("lon"))
            except (TypeError, ValueError):
                continue
        else:
            pts = [pos[int(nd.get("ref"))] for nd in el.findall("nd")
                   if nd.get("ref", "").isdigit()
                   and int(nd.get("ref")) in pos]
            if not pts:
                continue
            lat = sum(p[0] for p in pts) / len(pts)
            lon = sum(p[1] for p in pts) / len(pts)
        site = (tags.get("website") or tags.get("contact:website")
                or tags.get("url") or "").strip()
        addr = ", ".join(p for p in (
            tags.get("addr:housenumber"), tags.get("addr:street"),
            tags.get("addr:suburb"), tags.get("addr:city")) if p)
        out.append({
            "name": name, "key": key, "value": val,
            "lat": round(lat, 6), "lon": round(lon, 6),
            "website": site,
            "has_website_osm": bool(site),
            "phone": (tags.get("phone") or tags.get("contact:phone")
                      or "").strip(),
            "addr": addr,
            "osm_id": f"{el.tag}/{el.get('id')}",
        })
    return out


def haversine_km(lat1, lon1, lat2, lon2):
    p = math.radians
    dlat, dlon = p(lat2 - lat1), p(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(p(lat1)) * math.cos(p(lat2))
         * math.sin(dlon / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))


def main():
    with open(os.path.join(DATA, "gauteng_suburbs.json"),
              encoding="utf-8") as fh:
        suburbs = json.load(fh)["suburbs"]
    lats = [s["lat"] for s in suburbs]
    lons = [s["lon"] for s in suburbs]
    south, north = min(lats) - 0.03, max(lats) + 0.03
    west, east = min(lons) - 0.03, max(lons) + 0.03
    print(f">>> bbox {south:.2f},{west:.2f} {north:.2f},{east:.2f}",
          flush=True)

    seen_id, seen_name = set(), set()
    biz = []
    n_tiles = n_fail = 0
    lat = south
    while lat < north:
        lon = west
        while lon < east:
            n = min(round(lat + TILE, 4), round(north, 4))
            e = min(round(lon + TILE, 4), round(east, 4))
            raw = fetch_tile(round(lat, 4), round(lon, 4), n, e)
            n_tiles += 1
            if raw is None:
                n_fail += 1
            else:
                for b in parse_tile(raw):
                    if b["osm_id"] in seen_id:
                        continue
                    seen_id.add(b["osm_id"])
                    key = (b["name"].lower(),
                           round(b["lat"], 4), round(b["lon"], 4))
                    if key in seen_name:
                        continue
                    seen_name.add(key)
                    biz.append(b)
            time.sleep(1.0)  # polite: shared OSM main API
            lon += TILE
        lat += TILE
        print(f"    ... {len(biz)} businesses, {n_tiles} tiles "
              f"({n_fail} failed)", flush=True)

    # district + suburb via nearest mapped suburb (<= ASSIGN_KM), else
    # unassigned. Both are proximity inference and labelled as such
    # everywhere they surface.
    for b in biz:
        best, best_d, best_s = "", ASSIGN_KM, ""
        for s in suburbs:
            d = haversine_km(b["lat"], b["lon"], s["lat"], s["lon"])
            if d < best_d:
                best, best_d, best_s = s.get("district", ""), d, s["name"]
        b["district"] = best
        b["suburb"] = best_s
        b["nearest_suburb_km"] = round(best_d, 2) if best else None
    biz.sort(key=lambda b: (b["district"], b["name"].lower()))

    payload = {"meta": {
        "source": "OpenStreetMap main API, tiled",
        "tiles": n_tiles, "tiles_failed": n_fail,
        "has_website_means": "website/contact:website/url tag present in "
                             "OSM; absence is NOT proof of no website",
        "district_means": f"district of nearest mapped suburb within "
                          f"{ASSIGN_KM} km; else unassigned",
    }, "businesses": biz}
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    size_mb = os.path.getsize(OUT_PATH) / 1048576
    with_site = sum(1 for b in biz if b["has_website_osm"])
    print(f"wrote {OUT_PATH} ({len(biz)} businesses, {size_mb:.1f} MB; "
          f"{with_site} website-in-OSM, {len(biz) - with_site} not; "
          f"{n_fail} tiles failed)", flush=True)


if __name__ == "__main__":
    main()
