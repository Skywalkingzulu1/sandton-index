#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
15_harvest_cadastral.py -- Sandton-area cadastral data from Council for Geoscience.

Why this exists
---------------
The OSM property harvest (13) found 168 named complexes, 61 of them with a
street address. That is thin, because OSM coverage of Sandton is thin: of
20,599 building-tagged elements in the bbox only 1,186 carry a name.

The Council for Geoscience publishes the South African cadastral (property
parcel) layer, free and without registration:

    .../Administrative_Boundaries_and_Cadastral_Data/MapServer/22

Layer 22 is Erf for Gauteng, which is where Sandton sits. Two fields do the
work:

  SS_NAME      the surveyed property name -- an official registered name, not
               a crowd-sourced guess. 2,173 parcels in this bbox carry one.
  MIN_REGION   the suburb, e.g. SANDTON, SANDOWN, HOUGHTON ESTATE. 250 distinct
               values across the bbox. This is the authoritative suburb
               assignment the OSM side could never supply.

What is NOT taken from here
--------------------------
GEOM_AREA is the area of the erf (the parcel), not of any building on it.
Publishing it as a building's floor area would be a fabrication, so it is
stored as erf_area_m2 and never rendered as building area.

SS_NAME is not proof a name identifies one building. Many entries are
address-derived ("63 MAIN ROAD", "56 ON ALEX") or refer to a stand rather
than a structure ("LOT 1854"). Those are classified as non-property names
and are not published as property pages; they are kept in the data file so the
classification is auditable.

No street name or street number is published from this source: the layer
carries parcel and deed numbers, not a postal address. Deeds numbers are
property records, so they are harvested but not published.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA, SANDTON_BBOX  # noqa: E402

SERVICE = ("https://maps.geoscience.org.za/hosting/rest/services/"
           "Administrative_Boundaries_and_Cadastral_Data/MapServer")
LAYER = 22          # Gauteng > Erf
UA = "sandton-index-cadastral/1.0 (business directory; non-commercial)"

CACHE = os.path.join(DATA, "_cadastral_cache")

# A name that is an address or a stand rather than a property name.
ADDRESS_LIKE = {
    "lot", "stand", "portion", "rem", "erf", "unit", "sector", "farm",
    "ptn", "the farm", "vaal", "kraal", "laagte", "hoogte",
}


def _cache_path(key):
    return os.path.join(CACHE, key)


def query(where, out_fields, geometry=None, order_by="", page_size=2000,
          extra=""):
    """Paged ArcGIS query. Results cached per (where, fields) signature."""
    sig = urllib.parse.quote(
        f"{where}|{','.join(out_fields)}|{geometry}|{order_by}")[:180]
    path = _cache_path(sig)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    os.makedirs(CACHE, exist_ok=True)
    base = (f"{SERVICE}/{LAYER}/query?where={urllib.parse.quote(where)}"
            f"&outFields={','.join(out_fields)}&returnGeometry=false"
            f"&resultRecordCount={page_size}"
            "&f=json" + extra)
    if geometry:
        base += (f"&geometry={urllib.parse.quote(json.dumps(geometry))}"
                 "&geometryType=esriGeometryEnvelope&inSR=4326"
                 "&spatialRel=esriSpatialRelIntersects")

    out = []
    offset = 0
    while True:
        url = f"{base}&resultOffset={offset}"
        payload = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=180) as r:
                    payload = json.loads(r.read().decode("utf-8"))
                if "error" in payload:
                    raise RuntimeError(payload["error"])
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    print(f"    page offset {offset} failed: {str(exc)[:70]}")
                    return out
                time.sleep(2 + attempt * 3)
        if payload is None:
            return out

        page = payload.get("features", [])
        out += page
        # Stop on a short page, not on exceedsMaxRecordCount. ArcGIS only sets
        # that flag inconsistently, and relying on it silently truncated a
        # 2,173-row query to a single 2,000-row page.
        if len(page) < page_size:
            break
        offset += page_size
        if offset % 20000 == 0:
            print(f"      {offset} rows...")

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    os.replace(tmp, path)
    return out


def classify_name(raw, suburb=""):
    """Return (is_property_name, reason).

    Only names that identify a property may become a property page. This is
    the most important filter in this script: the cadastral SS_NAME field
    mixes registered property names with address strings and stand
    descriptions, and treating "63 MAIN ROAD" as a property would publish a
    page for a road.

    Single words are NOT rejected. A first version discarded them, on the
    theory that a lone word was a fragment -- and threw away BROOKWOOD,
    GLENHURST, AMBLESIDE, PINEHURST, MADISON and PORTOFINO, which are real
    registered property names. The address-like and numeric rules already
    catch the junk that matters.
    """
    name = (raw or "").strip().upper()
    if not name or name in {" ", "-", "N/A"}:
        return False, "blank"
    words = name.replace("-", " ").replace("/", " ").split()

    # all-digit or mostly-digit: a stand number, not a name
    digits = sum(ch.isdigit() for ch in name)
    if digits / len(name) > 0.4:
        return False, "mostly numeric"
    if any(w in ADDRESS_LIKE for w in words):
        return False, "address-like token"
    # "63 MAIN ROAD", "8 RUTLAND AVENUE", "24 BUCKINGHAM AVENUE": a leading
    # number followed by a street word is an address, not a property name.
    # Checked across all trailing words, not just the second -- an earlier
    # version only looked at words[1] and let "63 MAIN ROAD" through, because
    # "MAIN" is not a street word but "ROAD" further along is.
    street_words = {"ROAD", "RD", "AVENUE", "AVE", "STREET", "ST", "DRIVE",
                    "DR", "LANE", "LN", "BOULEVARD", "BLVD", "CLOSE", "CREST",
                    "COURT", "CRT", "WALK", "WAY", "PLACE", "SQUARE",
                    "SQ", "TERRACE", "TCE", "PARK", "GARDENS", "GARDEN",
                    "ON", "AT", "CORNER"}
    if re.match(r"^\d+[A-Z]?$", words[0]):
        if any(w in street_words for w in words[1:]):
            return False, "street address"
        if len(words) == 2:
            # "15A HAMILTON" -- number plus one word is far more likely to be
            # "<number> <street>" than a property name.
            return False, "number plus single word"
        if len(name) < 6:
            return False, "too short"
    # the SS_NAME merely repeats the suburb: the parcel has no registered
    # property name, so there is nothing to publish under
    if suburb and name == (suburb or "").strip().upper():
        return False, "name repeats suburb"
    if digits == 0 and len(words) == 1 and len(name) < 4:
        return False, "too short"
    return True, "ok"


def main():
    print("=" * 62)
    print("SANDTON INDEX -- cadastral harvest (Council for Geoscience)")
    print("=" * 62)
    b = SANDTON_BBOX
    bbox = {"xmin": b["west"], "ymin": b["south"],
            "xmax": b["east"], "ymax": b["north"]}

    print("[1/3] Named parcels (SS_NAME present)...")
    named = query(
        "SS_NAME IS NOT NULL AND SS_NAME <> ' '",
        ["OBJECTID", "PRCL_KEY", "SS_NAME", "MIN_REGION", "MAJ_REGION",
         "PARCEL_NO", "PORTION", "GEOM_AREA", "TAG_X", "TAG_Y", "LSTATUS",
         "PROVINCE", "DATE_STAMP"],
        geometry=bbox)
    print(f"      {len(named)} named parcels")

    print("[2/3] Parcel index (suburb lookup for every point in the bbox)...")
    # TAG_X/TAG_Y is the cadastral reference point of each parcel. Carrying one
    # point per parcel is enough to resolve a suburb by proximity, and avoids
    # downloading 109k polygon geometries.
    index = query("1=1", ["MIN_REGION", "TAG_X", "TAG_Y"], geometry=bbox,
                  page_size=2000)
    print(f"      {len(index)} parcel reference points")

    regions = {}
    for row in index:
        a = row.get("attributes", {})
        r = (a.get("MIN_REGION") or "").strip().upper()
        if r:
            regions[r] = regions.get(r, 0) + 1
    print(f"      {len(regions)} distinct MIN_REGION values")

    print("[3/3] Classifying property names...")
    keep, drop = [], []
    seen = set()
    for row in named:
        a = row.get("attributes", {})
        raw = a.get("SS_NAME") or ""
        suburb = (a.get("MIN_REGION") or "").strip().upper()
        ok, reason = classify_name(raw, suburb)
        entry = {
            "name": raw.strip(),
            "suburb": suburb,
            "erf": f"{a.get('PARCEL_NO')}/{a.get('PORTION')}",
            "parcel_key": a.get("PRCL_KEY") or "",
            # parcel area, NOT building area -- never rendered as the latter
            "erf_area_m2": round(float(a.get("GEOM_AREA") or 0), 1),
            "lat": a.get("TAG_Y"),
            "lon": a.get("TAG_X"),
            "legal_status": a.get("LSTATUS") or "",
            "name_ok": ok,
            "name_reason": reason,
        }
        if not ok:
            drop.append(entry)
            continue
        # dedupe on name + position; the same property is often split into
        # several portions, each with its own erf number
        key = (entry["name"].lower(), round(entry["lat"] or 0, 3),
               round(entry["lon"] or 0, 3))
        if key in seen:
            continue
        seen.add(key)
        keep.append(entry)

    print(f"      usable property names : {len(keep)}")
    print(f"      rejected as non-names : {len(drop)}")
    reasons = {}
    for d in drop:
        reasons[d["name_reason"]] = reasons.get(d["name_reason"], 0) + 1
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"        {k:<22} {v}")

    out_named = os.path.join(DATA, "cadastral_named.json")
    with open(out_named, "w", encoding="utf-8") as fh:
        json.dump({"source": "Council for Geoscience, Gauteng Erf layer",
                   "layer_url": f"{SERVICE}/{LAYER}",
                   "bbox": SANDTON_BBOX,
                   "usable": keep, "rejected": drop}, fh, indent=1,
                  ensure_ascii=False)

    # The index is large; store it compactly as parallel arrays.
    # Note each cached row is {"attributes": {...}} -- the inner attributes
    # must be unwrapped. A version that read TAG_X off the row itself
    # produced 109,146 null points while the region histogram next to it
    # counted 249 correctly, which is the shape of bug that only shows up
    # downstream.
    out_idx = os.path.join(DATA, "cadastral_index.json")
    with open(out_idx, "w", encoding="utf-8") as fh:
        json.dump({
            "source": "Council for Geoscience, Gauteng Erf layer",
            "regions": regions,
            "points": [[row.get("attributes", {}).get("TAG_X"),
                        row.get("attributes", {}).get("TAG_Y"),
                        (row.get("attributes", {}).get("MIN_REGION")
                         or "").strip().upper()]
                       for row in index],
        }, fh, separators=(",", ":"), ensure_ascii=False)
    print(f"      wrote {out_named}")
    print(f"      wrote {out_idx}")
    print("=" * 62)


if __name__ == "__main__":
    main()