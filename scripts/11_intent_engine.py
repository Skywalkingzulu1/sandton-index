#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
11_intent_engine.py -- Map every record into a local-search intent cluster.

Why a second taxonomy when config.HUB_GROUPS already has 24 groups:

HUB_GROUPS answers "what is this business". The nine clusters answer "what is
someone typing into Google right now". Those are different questions and they
produce different pages.

  "clothing store"                -> /clothing-fashion/sandton-cbd/
  "shops near me after work"      -> /intents/daily-retail/

A page that only serves the first query competes with 660 other directories.
A page that serves the second is the only one on the site answering it.

Each mapping records WHICH keyword fired, so a bad assignment can be traced
rather than guessed at -- an intent map nobody can audit is an intent map
nobody can trust.

Output: data/intent.json -- {record_id: {cluster, matched, keywords}}
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA  # noqa: E402

# The nine micro-moment clusters.
#
# Ordered by intent strength, strongest first: a person searching "mobile GP
# near me" at 9pm is far closer to booking than someone browsing "gym". The
# order is also the tie-break order when a record matches several clusters.
CLUSTERS = [
    {
        "slug": "health-medical-urgent",
        "title": "Health, Medical & Urgent Care",
        "singular": "health provider",
        "intent": "Mobile GPs, 24/7 clinics, pharmacies, dental, "
                  "occupational health",
        # DOW is itself in this cluster, which is why the health partner
        # module is weighted hardest here.
        "dow_role": "category_owner",
        "keywords": ["clinic", "doctor", "gp", "pharmacy", "chemist",
                     "medical", "dental", "dentist", "physio", "physiother",
                     "optical", "optician", "health", "wellness", "hospital",
                     "surgery", "x-ray", "lab", "pathology", "therapy",
                     "rehab", "occupational"],
    },
    {
        "slug": "housing-managed-complexes",
        "title": "Housing & Managed Complexes",
        "singular": "managed residential complex",
        "intent": "Sectional title estates, apartment complexes, HOA offices, "
                  "gatehouses",
        "dow_role": "resident_benefit",
        # NOTE: bare "park" is deliberately NOT a keyword. Sandton is full of
        # places named "... Park" -- Hyde Park, Hydro Park, Discovery Soccer
        # Park, PSG Wealth Hyde Park -- and matching the word put hotels, a
        # wealth manager and a sports venue into the residential cluster.
        # A place name is not a property type.
        "keywords": ["estate", "apartment", "apartments", "sectional",
                     "residential", "townhouse", "manor", "lodge", "court",
                     "villa", "villas", "complex", "residences", "heights",
                     "gated", "hoa", "gated village", "retirement"],
    },
    {
        "slug": "commercial-industrial-hubs",
        "title": "Commercial & Industrial Hubs",
        "singular": "commercial hub",
        "intent": "Office parks, co-working, light industrial complexes, "
                  "warehousing depots",
        "dow_role": "workforce_partner",
        "keywords": ["office", "offices", "office park", "commercial park",
                     "industrial", "industrial park", "warehouse",
                     "warehousing", "logistics", "depot", "freight", "yard",
                     "corporate park", "business park", "co-working",
                     "coworking", "workspace", "business centre",
                     "business center", "tower", "building", "plaza"],
    },
    {
        "slug": "daily-retail-conveniences",
        "title": "Daily Retail & Conveniences",
        "singular": "retailer",
        "intent": "Supermarkets, specialty coffee, express delis, hardware, "
                  "dry cleaning",
        "dow_role": "worker_welfare",
        "keywords": ["supermarket", "grocery", "grocer", "convenience",
                     "cafe", "coffee", "bakery", "deli", "takeaway",
                     "restaurant", "hardware", "cleaner", "cleaning",
                     "laundry", "dry cleaning", "store", "shop", "retail",
                     "market", "butchery", "bistro", "food"],
    },
    {
        "slug": "civic-public-services",
        "title": "Civic & Public Services",
        "singular": "public service",
        "intent": "Police stations, municipal billing, DLTCs, post offices",
        "dow_role": "none",
        "keywords": ["police", "municipal", "city", "council", "post office",
                     "postnet", "dltc", "licensing", "station", "depot mail",
                     "government", "public", "embassy", "consulate", "court"],
    },
    {
        "slug": "education-family",
        "title": "Education & Family",
        "singular": "education provider",
        "intent": "Preschools, primary/high schools, tutoring, aftercare hubs",
        "dow_role": "family_benefit",
        "keywords": ["school", "preschool", "pre-school", "creche",
                     "crèche", "academy", "college", "university", "campus",
                     "tutor", "tuition", "aftercare", "after-care",
                     "daycare", "day care", "kindergarten", "montessori"],
    },
    {
        "slug": "transport-logistics",
        "title": "Transport & Logistics",
        "singular": "transport provider",
        "intent": "Gautrain stops, EV chargers, parking garages, courier "
                  "lockers",
        "dow_role": "driver_welfare",
        "keywords": ["gautrain", "train", "parking", "garage", "ev charger",
                     "charging", "shuttle", "courier", "locker", "taxi",
                     "bus", "transport", "motoring", "petrol", "service station",
                     "fuel", "tire", "tyre"],
    },
    {
        "slug": "recreation-lifestyle",
        "title": "Recreation & Lifestyle",
        "singular": "recreation provider",
        "intent": "Padel courts, gyms, public parks, community halls",
        "dow_role": "member_benefit",
        "keywords": ["padel", "gym", "fitness", "sport", "sports", "yoga",
                     "pilates", "swim", "pool", "tennis", "soccer",
                     "recreation", "leisure", "club", "golf", "squash",
                     "community hall", "hall"],
    },
    {
        "slug": "home-maintenance-trades",
        "title": "Home Maintenance & Trades",
        "singular": "trade provider",
        "intent": "Emergency plumbers, electricians, solar installers, gate "
                  "automation",
        "dow_role": "none",
        "keywords": ["plumber", "electrician", "solar", "locksmith", "gate",
                     "automation", "handyman", "builder", "construction",
                     "renovation", "pest", "roofing", "carpenter", "painter",
                     "plumbing", "electrical", "hvac", "aircon", "air con",
                     "garden", "landscap", "security", "alarmed"],
    },
]

CLUSTER_BY_SLUG = {c["slug"]: c for c in CLUSTERS}

# Hub -> cluster. Derived from the hub's own meaning, not from keywords, so
# the mapping is stable when a business is renamed. Keywords are the fallback
# for records in the "other" hub, where the hub says nothing.
HUB_TO_CLUSTER = {
    "health-wellness": "health-medical-urgent",
    "beauty-hair": "recreation-lifestyle",
    "fitness-sports": "recreation-lifestyle",
    "hotels-accommodation": "housing-managed-complexes",
    "offices-coworking": "commercial-industrial-hubs",
    "malls-shopping-centres": "commercial-industrial-hubs",
    "doityourself-hardware": "home-maintenance-trades",
    "services-home": "home-maintenance-trades",
    "automotive": "transport-logistics",
    "education-training": "education-family",
    "travel-tourism": "transport-logistics",
    "media-printing": "commercial-industrial-hubs",
    "auctions-pawn": "daily-retail-conveniences",
    # everything a person walks into on the way home
    "restaurants-takeaways": "daily-retail-conveniences",
    "supermarkets": "daily-retail-conveniences",
    "convenience-liquor": "daily-retail-conveniences",
    "clothing-fashion": "daily-retail-conveniences",
    "home-furniture": "home-maintenance-trades",
    "professional-services": "commercial-industrial-hubs",
    "banks-financial": "commercial-industrial-hubs",
    "tech-it": "commercial-industrial-hubs",
    "pets-animals": "daily-retail-conveniences",
    "cannabis": "daily-retail-conveniences",
}


def classify(record, clusters=None):
    """Return (cluster_slug, reason).

    Hub mapping first, because it is the strongest signal we have. Keyword
    matching over name + raw category is the fallback, and it records which
    keyword fired so a misclassification is traceable to a word rather than
    being an unexplained fact.
    """
    clusters = clusters or CLUSTERS

    hub = record.get("hub") or ""
    slug = HUB_TO_CLUSTER.get(hub)
    if slug:
        return slug, f"hub:{hub}"

    # "other" hub: fall through to keywords
    #
    # hub_title is deliberately NOT in the haystack. For the "other" hub it
    # reads "Other Sandton Businesses", and a substring search for "bus"
    # matched inside "Businesses" -- which is how fifteen jewellery stores
    # ended up filed under Transport & Logistics. Matching is word-bounded for
    # the same reason.
    haystack = " ".join([
        str(record.get("name") or ""),
        str(record.get("category_raw") or ""),
        str(record.get("building_name") or ""),
    ]).lower()

    hits = []
    for c in clusters:
        matched = [k for k in c["keywords"]
                   if re.search(r"\b" + re.escape(k) + r"\b", haystack)]
        if matched:
            hits.append((len(matched), c["slug"], matched))

    if hits:
        # most keyword hits wins; ties broken by cluster order (intent
        # strength), which is the correct tie-break for local search
        hits.sort(key=lambda x: (-x[0], [c["slug"] for c in clusters]
                                 .index(x[1])))
        best = hits[0]
        return best[1], f"keyword:{','.join(best[2][:3])}"

    return "daily-retail-conveniences", "fallback:unclassified"


def is_complex(record, cluster_slug):
    """Does this record behave like a managed property?

    Drives the tenant-portal layout instead of a service showcase. Driven by
    cluster plus an explicit name check, because "office" appears in the
    trading name of plenty of businesses that are not office parks.
    """
    if cluster_slug in ("housing-managed-complexes",
                        "commercial-industrial-hubs"):
        name = str(record.get("name") or "").lower()
        # "park" is absent on purpose -- see the note in CLUSTERS. Every
        # explicit multi-word form is a genuine property type; a single
        # "Park" in Sandton is usually a place name.
        signals = ["office park", "business park", "industrial park",
                   "commercial park", "corporate park", "estate",
                   "apartments", "sectional", "residences", "gated",
                   "townhouse", "heights"]
        return any(s in name for s in signals)
    return False


def main():
    path = os.path.join(DATA, "businesses.json")
    with open(path, encoding="utf-8") as fh:
        records = json.load(fh)["records"]

    out = {}
    counts = {c["slug"]: 0 for c in CLUSTERS}
    reasons = {}
    complexes = 0

    for rec in records:
        slug, reason = classify(rec)
        complex_flag = is_complex(rec, slug)
        counts[slug] += 1
        reasons[reason.split(":")[0]] = reasons.get(
            reason.split(":")[0], 0) + 1
        if complex_flag:
            complexes += 1
        out[rec["id"]] = {
            "cluster": slug,
            "reason": reason,
            "is_complex": complex_flag,
        }

    dest = os.path.join(DATA, "intent.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

    total = len(records)
    print("=" * 62)
    print("SANDTON INDEX -- intent mapping")
    print("=" * 62)
    for c in sorted(CLUSTERS, key=lambda x: -counts[x["slug"]]):
        n = counts[c["slug"]]
        bar = "#" * max(0, round(n / total * 40))
        print(f"  {c['title']:<34} {n:>4}  {bar}")
    print(f"\n  assignment basis : {reasons}")
    print(f"  property portals : {complexes} records")
    print(f"  written          : data/intent.json")
    print("=" * 62)


if __name__ == "__main__":
    main()
