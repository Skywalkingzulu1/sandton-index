#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cadastral.py -- authoritative suburb lookup and registered-property names.

Two separate datasets from the Council for Geoscience, and they are used for
two different jobs:

  cadastral_index.json  one reference point per parcel (109,146 of them) with
                        the parcel's MIN_REGION. Resolving a coordinate to a
                        suburb by nearest parcel replaces the proximity
                        inference the property pages previously used, which
                        guessed an area from the closest indexed business and
                        silently guessed wrong wherever the businesses were
                        sparse.

  cadastral_named.json  parcels carrying SS_NAME, a registered property name.

Why cadastral properties carry no class
---------------------------------------
SS_NAME is a name and nothing else. The layer has no land-use field, so there
is no honest basis for calling a parcel residential, commercial or industrial
-- and inferring it from the wording of the name would be exactly the kind of
fabricated claim the rest of this project refuses. They are therefore emitted
under a separate "Registered property" heading rather than folded into the
residential/commercial/industrial classes, which come from OSM building tags.

Erf area is the area of the parcel, not of any building on it. It is carried
as erf_area_m2 and never rendered as floor area.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA  # noqa: E402

_INDEX = None
_NAMED = None

# ~0.005 deg buckets, roughly 550 m across. Small enough that nearest-point
# resolution is accurate at street level, large enough that 109k points index
# without a spatial library.
_CELL = 0.005


def load_index():
    """Load the parcel reference points into a grid, once."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    path = os.path.join(DATA, "cadastral_index.json")
    if not os.path.exists(path):
        _INDEX = (None, 0)
        return _INDEX
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    grid = {}
    for lon, lat, region in raw.get("points", []):
        if lon is None or lat is None or not region:
            continue
        key = (int(lat / _CELL), int(lon / _CELL))
        grid.setdefault(key, []).append((lat, lon, region))
    _INDEX = (grid, len(raw.get("points", [])))
    return _INDEX


def suburb_for(lat, lon):
    """Nearest parcel's MIN_REGION for a coordinate, or "" if none is near.

    Search expands outwards cell by cell and stops as soon as it has any hit,
    so a point close to a parcel boundary still resolves, but a point far
    outside any mapped parcel returns "" rather than the nearest region from
    kilometres away.
    """
    grid, _n = load_index()
    if not grid:
        return ""
    ci, cj = int(lat / _CELL), int(lon / _CELL)
    best, best_d = "", float("inf")
    for radius in range(0, 4):
        found = []
        for di in range(-radius, radius + 1):
            for dj in range(-radius, radius + 1):
                if radius and max(abs(di), abs(dj)) != radius:
                    continue
                found += grid.get((ci + di, cj + dj), [])
        for plat, plon, region in found:
            dy = (plat - lat) * 111320.0
            dx = (plon - lon) * 111320.0 * math.cos(math.radians(lat))
            d = math.hypot(dx, dy)
            if d < best_d:
                best, best_d = region, d
        if best:
            break
    # a region "nearest" from more than ~1.2 km is not a suburb, it is a guess
    return best if best_d <= 1200 else ""


def load_named():
    """Registered property names with coordinates."""
    global _NAMED
    if _NAMED is not None:
        return _NAMED
    path = os.path.join(DATA, "cadastral_named.json")
    if not os.path.exists(path):
        _NAMED = []
        return _NAMED
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    out = []
    for rec in data.get("usable", []):
        if rec.get("lat") is None or rec.get("lon") is None:
            continue
        out.append({
            "name": rec["name"],
            "suburb": rec.get("suburb", ""),
            "erf": rec.get("erf", ""),
            "parcel_key": rec.get("parcel_key", ""),
            "erf_area_m2": rec.get("erf_area_m2"),
            "lat": rec["lat"],
            "lon": rec["lon"],
            "class": "registered",
        })
    _NAMED = out
    return _NAMED


def suburb_display(region):
    """'HOUGHTON ESTATE' -> 'Houghton Estate'.

    MIN_REGION values sometimes carry a registry suffix -- 'WESTDENE(IR)',
    'WESTDENE(IQ)' -- where the bracketed code distinguishes the same place
    name registered under different magisterial districts. It is an internal
    marker, not part of the suburb name, so it is stripped before display.
    """
    name = (region or "").strip()
    if name.endswith(")") and "(" in name:
        name = name[:name.rindex("(")].strip()
    return name.title()


def source_note():
    return ("Suburb and parcel data: Council for Geoscience, South African "
            "cadastral erf layer (Gauteng). Building geometry: OpenStreetMap.")