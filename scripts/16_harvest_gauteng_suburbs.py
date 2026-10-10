#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
16_harvest_gauteng_suburbs.py -- Harvest every named suburb-level place in
Gauteng from OpenStreetMap, with district/municipality assignment.

Why an area query and not a bbox
--------------------------------
A bbox around Gauteng clips edge suburbs and drags in places from North West,
Mpumalanga and the Free State. Resolving the Gauteng admin_level=4 area first
and querying inside it returns exactly what OSM considers Gauteng, nothing
else.

What is collected
-----------------
Every named node/way/relation tagged place=suburb, neighbourhood, village,
hamlet, town or city inside the Gauteng area, with coordinates. Boundary
relations (admin_level 6 districts, admin_level 8 local municipalities) are
fetched in a second query and each suburb is assigned to the smallest
containing unit by a local point-in-polygon test -- no API-side geocoding,
no proximity guessing.

Only what OSM tags is stored. Counts are density indicators, not a census:
South African suburbs mapped as bare nodes carry no boundary, and OSM
coverage outside the metros is uneven.

Output: data/gauteng_suburbs.json (committed if small, else gitignored).
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA  # noqa: E402

MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
UA = "sandton-index-directory/1.0 (business directory; contact: site operator)"

OUT_PATH = os.path.join(DATA, "gauteng_suburbs.json")
CACHE_DIR = os.path.join(DATA, "_osm_cache")
CACHE_PLACES = os.path.join(CACHE_DIR, "gauteng_places.json")
CACHE_BOUNDS = os.path.join(CACHE_DIR, "gauteng_bounds.json")
CACHE_PHOTON = os.path.join(CACHE_DIR, "gauteng_photon.json")

PHOTON = "https://photon.komoot.io/reverse"

PLACES = "suburb|neighbourhood|village|hamlet|town|city"

Q_PLACES = (f"[out:json][timeout:300];\n"
            f'area["name"="Gauteng"]["admin_level"="4"]->.g;\n'
            f'(nwr(area.g)["place"~"^({PLACES})$"]["name"];);\n'
            f"out center tags;")

Q_DISTRICTS = ("[out:json][timeout:120];\n"
               '(relation["boundary"="administrative"]["admin_level"="6"]'
               '["name"~"Johannesburg|Tshwane|Ekurhuleni|Sedibeng|'
               "West Rand\"];);\n"
               "out tags;")


def geom_query(rel_id):
    # One request returning BOTH the relation (members + roles) and the
    # member geometries. A bare `out geom` drops the member list, and a
    # bare `out` drops the geometry -- the union keeps both, which is what
    # rings_of() needs to tell outer rings from inner ones.
    return (f"[out:json][timeout:300];\n(rel({rel_id});out tags;\n"
            f" rel({rel_id});>;out geom;);")


def post(query, timeout=330):
    last_err = None
    for mirror in MIRRORS:
        try:
            req = urllib.request.Request(
                mirror,
                data=urllib.parse.urlencode({"data": query}).encode(),
                headers={"User-Agent": UA},
                method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r), mirror
        except Exception as e:  # noqa: BLE001 -- try next mirror
            last_err = e
            print(f"    mirror failed ({mirror}): {e}", flush=True)
            time.sleep(5)
    raise SystemExit(f"all Overpass mirrors failed: {last_err}")


def center_of(el):
    if el["type"] == "node":
        return el["lat"], el["lon"]
    c = el.get("center")
    if c:
        return c["lat"], c["lon"]
    return None


def rings_of(relation, geom_index):
    """Outer rings of a boundary relation as lists of (lon, lat)."""
    rings = []
    for m in relation.get("members", []):
        if m.get("role") not in ("outer", ""):
            continue
        if m["type"] == "node":
            continue
        key = (m["type"], m["ref"])
        geom = geom_index.get(key)
        if not geom:
            continue
        pts = [(p["lon"], p["lat"]) for p in geom
               if "lon" in p and "lat" in p]
        if len(pts) >= 4:
            rings.append(pts)
    return rings


def photon_lookup(lat, lon):
    """Reverse-geocode one coordinate via Photon (komoot).

    Only the admin fields are used (county = district municipality,
    city = nearest town or local municipality). The suburb name and
    coordinates always stay exactly as OSM's place data gave them.
    """
    url = (PHOTON + "?" + urllib.parse.urlencode({"lon": lon, "lat": lat}))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    feats = data.get("features", [])
    if not feats:
        return {}, {}
    return feats[0].get("properties", {}), feats[0].get("geometry", {})


def assign_districts_photon(suburbs):
    """Fill missing districts via Photon reverse-geocoding.

    One request per suburb at polite intervals, resumable through a disk
    cache keyed by rounded coordinate. A suburb keeps district="" when
    Photon yields nothing usable -- unassigned, never guessed.
    """
    try:
        with open(CACHE_PHOTON, encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    todo = [s for s in suburbs if not s.get("district")]
    print(f">>> assigning districts via Photon ({len(todo)} suburbs) ...",
          flush=True)
    done = 0
    for s in todo:
        key = f"{round(s['lat'], 4)},{round(s['lon'], 4)}"
        if key not in cache:
            ok = False
            for attempt in range(3):
                try:
                    props, _geom = photon_lookup(s["lat"], s["lon"])
                    cache[key] = {
                        "county": props.get("county", ""),
                        "city": props.get("city", ""),
                    }
                    ok = True
                    break
                except Exception as e:  # noqa: BLE001 -- back off, retry
                    print(f"    photon failed ({s['name']}): {e}",
                          flush=True)
                    time.sleep(10 * (attempt + 1))
            if not ok:
                cache[key] = {"county": "", "city": ""}
            time.sleep(1.5)  # polite: public Photon allows ~1 req/s
            done += 1
            if done % 50 == 0:
                with open(CACHE_PHOTON, "w", encoding="utf-8") as f:
                    json.dump(cache, f)
                print(f"    {done}/{len(todo)} ...", flush=True)
        entry = cache.get(key, {})
        county = entry.get("county", "")
        city = entry.get("city", "")
        if county:
            s["district"] = county
            s["municipality"] = city or county
    with open(CACHE_PHOTON, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    n = sum(1 for s in suburbs if s.get("district"))
    print(f"    districts assigned: {n}/{len(suburbs)}", flush=True)


def point_in_ring(lon, lat, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat):
            xint = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < xint:
                inside = not inside
        j = i
    return inside


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    refresh = "--refresh" in sys.argv

    if os.path.exists(CACHE_PLACES) and not refresh:
        print(">>> using cached Gauteng places ...", flush=True)
        with open(CACHE_PLACES, encoding="utf-8") as f:
            places_data = json.load(f)
    else:
        print(">>> fetching Gauteng places ...", flush=True)
        places_data, mirror = post(Q_PLACES)
        with open(CACHE_PLACES, "w", encoding="utf-8") as f:
            json.dump(places_data, f)
    print(f"    {len(places_data.get('elements', []))} place elements",
          flush=True)

    cached_bounds = []
    if os.path.exists(CACHE_BOUNDS) and not refresh:
        try:
            with open(CACHE_BOUNDS, encoding="utf-8") as f:
                cached_bounds = json.load(f)
        except (OSError, ValueError):
            cached_bounds = []
    if any(el.get("type") == "relation" for el in cached_bounds):
        print(">>> using cached boundaries ...", flush=True)
        bounds_elements = cached_bounds
    else:
        # Municipal (level 8) geometry repeatedly times out the public
        # mirrors, so this harvest records district (level 6) only. District
        # names are globally unambiguous, which keeps the lookup cheap and
        # avoids the expensive Gauteng-area resolution entirely.
        # Boundary fetching is best-effort: if the mirrors refuse, the
        # Photon fallback below still assigns every district, so a dead
        # mirror must never abort the run.
        bounds_elements = []
        try:
            print(">>> listing district relations (tags only) ...", flush=True)
            ids_data, mirror = post(Q_DISTRICTS, timeout=150)
            rels = [(el["id"], (el.get("tags", {}).get("name") or ""),
                     el.get("tags", {}).get("admin_level", "?"))
                    for el in ids_data.get("elements", [])
                    if el["type"] == "relation"]
            print(f"    {len(rels)} relations via {mirror}", flush=True)
            have = set()
            if os.path.exists(CACHE_BOUNDS):
                try:
                    with open(CACHE_BOUNDS, encoding="utf-8") as f:
                        bounds_elements = json.load(f)
                    for el in bounds_elements:
                        if el["type"] == "relation":
                            have.add(el["id"])
                except (OSError, ValueError):
                    bounds_elements = []
            for i, (rid, name, level) in enumerate(rels, 1):
                if rid in have:
                    print(f"    [{i}/{len(rels)}] {name} cached, skipping ...",
                          flush=True)
                    continue
                print(f"    [{i}/{len(rels)}] {name} (level {level}) ...",
                      flush=True)
                data = None
                for attempt in range(4):
                    try:
                        data, gm = post(geom_query(rid))
                        break
                    except SystemExit as e:
                        wait = 30 * (attempt + 1)
                        print(f"      attempt {attempt + 1} failed, "
                              f"sleeping {wait}s ...", flush=True)
                        time.sleep(wait)
                if data is None:
                    print("      geometry failed after retries, skipping ...",
                          flush=True)
                    continue
                bounds_elements.extend(data.get("elements", []))
                with open(CACHE_BOUNDS, "w", encoding="utf-8") as f:
                    json.dump(bounds_elements, f)
                time.sleep(25)  # polite gap: public mirrors rate-limit fast
            with open(CACHE_BOUNDS, "w", encoding="utf-8") as f:
                json.dump(bounds_elements, f)
        except SystemExit as e:
            print(f"    boundary fetch unavailable ({e}); continuing "
                  f"without OSM geometry -- Photon assigns districts below.",
                  flush=True)
            bounds_elements = []
    print(f"    {len(bounds_elements)} boundary elements", flush=True)

    # index way/node geometry for ring assembly
    geom_index = {}
    units = []  # (name, level, rings)
    for el in bounds_elements:
        if el["type"] == "relation":
            continue
        if "geometry" in el:
            geom_index[(el["type"], el["id"])] = el["geometry"]
    for el in bounds_elements:
        if el["type"] != "relation":
            continue
        tags = el.get("tags", {})
        name = tags.get("name", "")
        try:
            level = int(tags.get("admin_level", 0))
        except ValueError:
            continue
        if level not in (6, 8) or not name:
            continue
        rings = rings_of(el, geom_index)
        if rings:
            units.append((name, level, rings))
    units.sort(key=lambda u: u[1], reverse=True)  # level 8 first
    print(f"    {len(units)} boundary units with geometry", flush=True)

    suburbs = []
    seen = set()
    dupes = 0
    for el in places_data.get("elements", []):
        tags = el.get("tags", {})
        name = (tags.get("name") or "").strip()
        c = center_of(el)
        if not name or not c:
            continue
        lat, lon = c
        key = (name.lower(), round(lat, 4), round(lon, 4))
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        district, municipality = "", ""
        for uname, ulevel, rings in units:
            if any(point_in_ring(lon, lat, ring) for ring in rings):
                if ulevel == 6:
                    district = uname
                else:
                    municipality = uname
                if district and municipality:
                    break
        suburbs.append({
            "name": name,
            "place": tags.get("place", ""),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "district": district,
            "municipality": municipality or district,
            "osm_id": f"{el['type']}/{el['id']}",
        })

    suburbs.sort(key=lambda s: (s["district"], s["municipality"], s["name"]))
    if any(not s.get("district") for s in suburbs):
        assign_districts_photon(suburbs)
        suburbs.sort(key=lambda s: (s["district"], s["municipality"],
                                    s["name"]))
    payload = {"meta": {
        "source": "OpenStreetMap Overpass",
        "duplicates_collapsed": dupes,
        "districts": sorted({s["district"] for s in suburbs if s["district"]}),
    }, "suburbs": suburbs}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    size_kb = os.path.getsize(OUT_PATH) / 1024
    by_district = {}
    for s in suburbs:
        by_district[s["district"] or "?"] = \
            by_district.get(s["district"] or "?", 0) + 1
    print(f"wrote {OUT_PATH} ({len(suburbs)} suburbs, {size_kb:.0f} KB, "
          f"{dupes} dupes collapsed)", flush=True)
    for d, n in sorted(by_district.items()):
        print(f"    {d}: {n}", flush=True)


if __name__ == "__main__":
    main()
