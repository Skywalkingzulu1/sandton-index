#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
property_schema.py -- structured data for the property pages.

Type selection is deliberately narrow, because every term here is a factual
claim about someone else's building.

Verified against schema.org during this build:
    ApartmentComplex            real
    CivicStructure              real
    LandmarksOrHistoricalBuildings  real
    Building                    404
    OfficeBuilding              404
    IndustrialBuilding          404
    CommercialBuilding          404

So an office park is NOT typed as OfficeBuilding -- that term does not exist,
and the nearest real term (CivicStructure) is worse than useless because it
asserts the building is civic. Office and industrial buildings are therefore
emitted as a bare Place carrying only name, coordinates and address: the facts
we actually hold. Residential complexes get ApartmentComplex, which is both
real and correct.

Nothing is asserted that OSM does not carry. No unit counts, no storeys
unless building:levels is tagged, no occupancy, no amenities, no year built,
no aggregateRating.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SITE_URL  # noqa: E402

LD = "https://schema.org"

CLASS_TITLE = {
    "residential": "Residential complex",
    "commercial": "Commercial building",
    "industrial": "Industrial building",
}


def e(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _ld(obj):
    """Emit a complete JSON-LD script element.

    Matches page_modules._ld so callers concatenate these straight into
    extra_head without wrapping each one themselves.
    """
    return ('<script type="application/ld+json">'
            f'{json.dumps(obj, ensure_ascii=False, indent=None)}</script>')


def _addr(prop):
    """Postal address, but only if a street was actually tagged."""
    street = (prop.get("street_address") or "").strip()
    if not street:
        return None
    return {
        "@type": "PostalAddress",
        "streetAddress": street,
        "addressLocality": "Sandton",
        "addressRegion": "Gauteng",
        "addressCountry": "ZA",
    }


def schema_property(prop, nearby_businesses=()):
    """One property node. Type reflects only what we can defend."""
    node = {
        "@type": f"{LD}/ApartmentComplex" if prop["class"] == "residential"
                 else f"{LD}/Place",
        "@id": f"{SITE_URL}/properties/{e(prop['path'])}/#property",
        "name": prop["name"],
        "description": (
            f"{prop['name']} is a {CLASS_TITLE.get(prop['class'], 'building')} "
            f"in {prop.get('area_display', 'the Sandton area')}, Johannesburg. "
            "Building details on the Sandton Index are mapped from "
            "OpenStreetMap and may be incomplete; confirm details with the "
            "managing agent before relying on them."),
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": prop["lat"],
            "longitude": prop["lon"],
        },
        "isPartOf": {
            "@type": "WebSite",
            "@id": f"{SITE_URL}/#website",
            "name": "Sandton Index",
            "url": f"{SITE_URL}/",
        },
    }

    addr = _addr(prop)
    if addr:
        node["address"] = addr

    # building:levels is the one dimensional fact OSM actually carries for
    # these. Emitted only when present, and never as a range or estimate.
    if prop.get("levels") is not None:
        node["numberOfFloors"] = prop["levels"]

    if prop.get("website"):
        node["url"] = prop["website"]

    if not prop.get("class") == "residential":
        # Names the real building use without claiming a schema type that
        # does not exist. additionalType is the sanctioned slot for this.
        node["additionalType"] = prop.get("building_tag") or prop["class"]

    return _ld(node)


def schema_breadcrumbs(trail):
    items = []
    for i, (label, url) in enumerate(trail, start=1):
        items.append({
            "@type": "ListItem",
            "position": i,
            "name": label,
            "item": url,
        })
    return _ld({
        "@context": LD,
        "@type": "BreadcrumbList",
        "itemListElement": items,
    })


def schema_itemlist(title, slug, props):
    """ItemList for a property index or near-me page."""
    items = [{
        "@type": "ListItem",
        "position": i,
        "url": f"{SITE_URL}/properties/{e(p['path'])}/",
        "name": p["name"],
    } for i, p in enumerate(props, start=1)]
    return _ld({
        "@context": LD,
        "@type": "ItemList",
        "name": title,
        "numberOfItems": len(items),
        "itemListElement": items,
    })


NO_AGGREGATE_RATING = True