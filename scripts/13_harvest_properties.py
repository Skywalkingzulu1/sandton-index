#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
13_harvest_properties.py -- Harvest named buildings from OpenStreetMap.

Why the OSM /map API and not Overpass
-------------------------------------
Overpass was the obvious tool and it is the one the hours harvest uses, but
every public mirror timed out or refused while this was built (overpass-api.de
406, kumi/private.coffee/mail.ru read timeouts). The OSM main API at
api.openstreetmap.org/api/0.6/map is separate infrastructure and answered
normally, so this harvests through that instead. It has no query language, so
the bbox is tiled instead of filtered remotely.

What is and is not collected
----------------------------
Only what OSM actually tags. No unit counts, storeys, amenities, occupancy,
leasing status or security details are inferred -- those are almost never
mapped, and inventing them is how a property directory publishes false claims
about someone else's building. building:levels is taken when present and
absent otherwise, never estimated.

Duplicate handling: OSM frequently maps the same building twice (an outer
footprint and an inner one, or a building and its centre). Entries are keyed
by (name, rounded coordinate) so those collapse, and genuinely distinct
buildings sharing a name at different coordinates are kept.
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
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA, SANDTON_BBOX  # noqa: E402

API = "https://api.openstreetmap.org/api/0.6/map"
UA = "sandton-index-directory/1.0 (business directory; contact: site operator)"

# Raw tile responses. The OSM API is rate-limited and the full grid is a few
# hundred requests, so re-runs must not re-spend them. Gitignored.
CACHE = os.path.join(DATA, "_osm_cache")

# 0.01 deg is roughly 1.1 km. The API caps a request at 50k nodes and refuses
# anything over 0.25 square degrees; 0.01 keeps dense CBD tiles well inside
# both while staying small enough to walk the whole Sandton bbox quickly.
TILE = 0.01

# Only tags that mean "a building someone could search for". A bare
# building=yes carries no type and is excluded: without a type there is
# nothing to file the entry under.
TYPE_MAP = {
    # residential
    "apartments": "residential",
    "residential": "residential",
    "dormitory": "residential",
    "detached": "residential",
    "semidetached_house": "residential",
    "terrace": "residential",
    "bungalow": "residential",
    "hut": "residential",
    # industrial
    "industrial": "industrial",
    "warehouse": "industrial",
    "factory": "industrial",
    "hangar": "industrial",
    "manufacture": "industrial",
    # commercial
    "commercial": "commercial",
    "office": "commercial",
    "retail": "commercial",
    "supermarket": "commercial",
    "hotel": "commercial",
    "kiosk": "commercial",
    "service": "commercial",
    "garage": "commercial",
    "garages": "commercial",
}

# Names that describe a feature of the map rather than a building somebody
# would search for. A page for "Rubbish Dump" or "Informal Settlement" is
# worse than no page: it is thin, it misleads, and it drags the site's quality
# signal down across the other 300-odd pages.
JUNK_NAME = re.compile(
    r"^(informal settlement|informel settlement|rubbish dump|garbage|"
    r"rubbish|dump|carport|garage|garages|garage block|clubhouse|club house|"
    r"swimming pool|pool|temple|church|mosque|church hall|substation|"
    r"transformer|pumping station|pump house|toilets|ablutions|ablution|"
    r"unclassified|unknown|shed|construction site|situation|settlement|"
    r"koppie|kopje|copy|duplicate|test|placeholder|name|building [0-9]+)$",
    re.I)

# Names that signal a multi-occupancy building rather than one business.
# OSM often tags an individual shop's own footprint as building=commercial or
# building=retail, which would turn this into a second copy of the business
# directory. These words, or an estate/park landuse, mean the thing is a
# building people live in or work in as a group.
COMPLEX_WORDS = re.compile(
    r"\b(office park|business park|industrial park|commercial park|"
    r"estate|estates|court|mansions|mansion|heights|residence|residences|"
    r"terrace|terraces|square|centre|center|complex|tower|towers|"
    r"plaza|galleria|shopping centre|shopping center|mall|lifestyle|"
    r"apartments|apartment|place|park|gardens|villa|villas|lodge|"
    r"retirement|lifecare|medical centre|medical center|clinic|hospital|"
    r"college|school|academy|church|place)\b", re.I)


def is_complex(rec):
    """True when this entry is a building, not one business inside one.

    Two independent signals, either of which is enough:
      1. an estate/park-style landuse, which is about the whole site; or
      2. a name that reads as a multi-occupancy building.
    A bare building=retail with a shop name is a single-occupancy unit and is
    excluded -- those businesses already have a page from the main directory.
    """
    if rec["landuse_tag"] in ("industrial", "commercial", "residential"):
        return True
    return bool(COMPLEX_WORDS.search(rec["name"]))


def tiles():
    b = SANDTON_BBOX
    south, north = b["south"], b["north"]
    west, east = b["west"], b["east"]
    lat = south
    while lat < north:
        lon = west
        while lon < east:
            yield (round(lat, 4), round(lon, 4),
                   round(min(lat + TILE, north), 4),
                   round(min(lon + TILE, east), 4))
            lon += TILE
        lat += TILE


def fetch_tile(s, w, n, e):
    """Return the parsed XML root for one tile, cached on disk."""
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
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
            # Write via temp+replace so an interrupted run cannot leave a
            # half-written tile that later parses as valid-but-empty.
            tmp = path + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(raw)
            os.replace(tmp, path)
            return raw
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 + attempt * 3)
    print(f"    tile {s},{w} failed: {str(last)[:70]}")
    return None


def node_positions(root):
    """Map node id -> (lat, lon) for everything in one tile.

    Required because the /map API returns real geometry, not Overpass-style
    <center> elements. A way building carries only <nd ref=...> children, so
    without this lookup every way-based building is dropped. Named buildings
    are almost always ways, so this single missing step cut a 400-entry
    harvest to 13.
    """
    pos = {}
    for el in root.findall("node"):
        try:
            pos[int(el.get("id"))] = (float(el.get("lat")),
                                      float(el.get("lon")))
        except (TypeError, ValueError):
            continue
    return pos


def way_centroid(el, pos):
    """Mean of a way's node coordinates."""
    pts = []
    for nd in el.findall("nd"):
        p = pos.get(int(nd.get("ref")))
        if p:
            pts.append(p)
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts))


def centre(el, pos):
    """Latitude/longitude for a node, way or relation."""
    if el.tag == "node":
        try:
            return float(el.get("lat")), float(el.get("lon"))
        except (TypeError, ValueError):
            return None
    if el.tag == "way":
        return way_centroid(el, pos)
    # relations (multipolygons, site complexes): average the member ways
    pts = []
    for member in el.findall("member"):
        if member.get("type") != "way":
            continue
        ref = member.get("ref")
        sub = pos.get(("way", ref))
        if sub:
            pts.append(sub)
    if pts:
        return (sum(p[0] for p in pts) / len(pts),
                sum(p[1] for p in pts) / len(pts))
    return None


def records_from_xml(raw):
    root = ET.fromstring(raw)
    pos = node_positions(root)
    way_centroids = {}
    for w in root.findall("way"):
        c = way_centroid(w, pos)
        if c:
            way_centroids[int(w.get("id"))] = c

    out = []
    for el in root:
        if el.tag not in ("node", "way", "relation"):
            continue
        tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
        name = tags.get("name")
        if not name:
            continue
        name = name.strip()
        if JUNK_NAME.match(name):
            continue
        btype = tags.get("building")
        luse = tags.get("landuse")
        klass = TYPE_MAP.get(btype or "") or TYPE_MAP.get(luse or "")
        if not klass:
            continue
        if el.tag == "way":
            loc = way_centroids.get(int(el.get("id")))
        elif el.tag == "relation":
            loc = centre(el, {})
        else:
            loc = centre(el, pos)
        if not loc:
            continue
        lat, lon = loc
        street = tags.get("addr:street") or ""
        num = tags.get("addr:housenumber") or ""
        parts = [p for p in (num, street) if p]
        addr = " ".join(parts)
        levels = tags.get("building:levels")
        try:
            levels = int(float(levels)) if levels else None
        except ValueError:
            levels = None
        out.append({
            "osm_type": el.tag,
            "osm_id": int(el.get("id")),
            "name": name,
            "class": klass,
            "building_tag": btype or "",
            "landuse_tag": luse or "",
            "street_address": addr,
            "street": street,
            "housenumber": num,
            "suburb": tags.get("addr:suburb", ""),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            # present only when OSM carries it; never estimated
            "levels": levels,
            "operator": tags.get("operator", ""),
            "website": tags.get("website") or tags.get("contact:website", ""),
            "phone": tags.get("phone") or tags.get("contact:phone", ""),
        })
    return out


def dedupe(recs):
    """Collapse duplicate mappings of one building, keyed on name+position."""
    buckets = defaultdict(list)
    for r in recs:
        # ~20 m grid: fine enough to merge inner/outer footprints of the same
        # building, coarse enough not to merge two genuinely separate ones.
        buckets[(r["name"].lower(), round(r["lat"], 3),
                 round(r["lon"], 3))].append(r)
    out = []
    for _key, group in buckets.items():
        # Prefer the entry carrying the most evidence, so an address or a
        # levels tag on a duplicate is not thrown away.
        group.sort(key=lambda r: (
            bool(r["street_address"]), r["levels"] is not None,
            bool(r["website"]), bool(r["phone"])), reverse=True)
        out.append(group[0])
    return out


def main():
    print("=" * 62)
    print("SANDTON INDEX -- property harvest (OpenStreetMap /map API)")
    print("=" * 62)
    tlist = list(tiles())
    print(f"[1/3] {len(tlist)} tiles at {TILE} deg over the Sandton bbox")

    raw_recs = []
    failed = 0
    cached = 0
    for i, (s, w, n, e) in enumerate(tlist, start=1):
        path = os.path.join(CACHE, f"{s}_{w}_{n}_{e}.xml")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            cached += 1
        raw = fetch_tile(s, w, n, e)
        if raw is None:
            failed += 1
            continue
        raw_recs += records_from_xml(raw)
        if i % 20 == 0 or i == len(tlist):
            print(f"      {i}/{len(tlist)} tiles, {len(raw_recs)} raw entries")

    print(f"[2/3] tiles served from cache: {cached}, failed: {failed}")
    if failed:
        print(f"      WARNING: {failed} tiles unavailable; coverage is partial")

    recs = dedupe(raw_recs)

    complexes = [r for r in recs if is_complex(r)]
    singles = [r for r in recs if not is_complex(r)]

    by_class = defaultdict(int)
    for r in complexes:
        by_class[r["class"]] += 1
    with_addr = sum(1 for r in complexes if r["street_address"])
    with_levels = sum(1 for r in complexes if r["levels"] is not None)
    with_site = sum(1 for r in complexes if r["website"])
    with_suburb = sum(1 for r in complexes if r["suburb"])

    print("[3/3] Classifying...")
    print(f"      named buildings total  : {len(recs)}")
    print(f"      single-occupancy (shop): {len(singles)}  excluded")
    print(f"      complexes / buildings  : {len(complexes)}")
    for k, v in sorted(by_class.items(), key=lambda x: -x[1]):
        print(f"        {k:<12} {v}")
    print(f"      with street address    : {with_addr}")
    print(f"      with addr:suburb       : {with_suburb}")
    print(f"      with building:levels   : {with_levels}")
    print(f"      with website           : {with_site}")

    out = os.path.join(DATA, "properties.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"source": "openstreetmap /map API",
                   "bbox": SANDTON_BBOX,
                   "tiles_fetched": len(tlist) - failed,
                   "tiles_failed": failed,
                   "records": complexes}, fh, indent=1, ensure_ascii=False)
    print(f"      wrote {out}")
    print("=" * 62)


if __name__ == "__main__":
    main()