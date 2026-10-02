#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data_overlay.py -- Merge enrichment sources with explicit precedence.

The lesson that drives this file: never let one data provider be a single
point of failure.

The site already has three possible sources for any given field, and they
disagree constantly:

  OSM     scraped from OpenStreetMap. Sparse in Sandton (~21% coverage) but
          free, unlimited, and no key to expire.
  google  from the Maps Scraper API. Best coverage and it is what the owner
          published, but it is quota-metered and went to zero mid-project.
  default a per-category guess from config.HOURS_DEFAULTS. Always available,
          never trustworthy enough to state as fact.

If 09_build_sites.py read one source directly, the project would break
whenever that source did. Instead every source writes its own sidecar file
and this module resolves them at render time. If a sidecar is missing,
corrupt, or empty, the site still builds with whatever is left.

Precedence for hours, best evidence first:

  google  owner-published, so the best evidence available. Rendered with a
          "confirm with the business" caveat and EXCLUDED from JSON-LD,
          because Google is a third-party copy and can be months stale.
  scraped OSM-corroborated. Rendered as fact, included in JSON-LD.
  default category guess. Rendered with the strongest warning possible,
          excluded from JSON-LD.

Provenance is attached to every value that reaches a page, so a future
reader can tell a guess from a scrape at a glance, and so a stale overlay
can be identified rather than silently trusted.
"""
import json
import os

# hours_confidence values, and what the site is allowed to do with each.
#
#   google  -- real data, owner-published, third-party copy. Shown with a
#              caveat. Never in JSON-LD.
#   scraped -- from OSM after name + proximity corroboration. Shown as fact.
#              Allowed in JSON-LD.
#   default -- our own guess. Shown with the strongest warning. Never in
#              JSON-LD.
#   none    -- nothing to show at all.
CONFIDENCE_ORDER = ["none", "default", "google", "scraped"]

# Only these two may reach LocalBusiness JSON-LD. Anything else is a guess or
# a third-party copy, and publishing either as fact about a real business is
# how a listing gets penalised.
SCHEMA_ALLOWED = {"scraped"}


def load_overlay(data_dir, filename="google.json"):
    """Read an enrichment sidecar. Returns {} on any problem.

    A missing or malformed overlay must never stop the build -- that is the
    entire point of the sidecar design.
    """
    path = os.path.join(data_dir, filename)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def best_hours(rec, google_entry):
    """Resolve one record's hours across sources.

    Returns (hours_dict, confidence, source_label).
    """
    existing = rec.get("opening_hours")
    existing_conf = rec.get("hours_confidence")

    google_hours = (google_entry or {}).get("opening_hours")

    if existing_conf == "scraped":
        return existing, "scraped", "OpenStreetMap"
    if google_hours:
        return google_hours, "google", "Google"
    if existing:
        if existing_conf == "default":
            return existing, "default", "category estimate"
        return existing, existing_conf or "default", "category estimate"
    return {}, "none", "none"


def hours_in_schema(confidence):
    return confidence in SCHEMA_ALLOWED


def enrich_record(rec, overlay):
    """Attach overlay data to one record, without ever overwriting good data.

    Only fills gaps. An existing phone is never replaced by Google's, even
    when they disagree -- a conflict is recorded for review rather than
    silently resolved, because guessing wrong publishes a wrong number to
    someone trying to phone a shop.
    """
    entry = overlay.get(rec.get("id")) or {}
    if not entry:
        return {
            "hours": rec.get("opening_hours") or {},
            "confidence": rec.get("hours_confidence") or "none",
            "hours_source": "category estimate",
            "rating": None,
            "rating_date": None,
            "review_count": None,
            "claimed": None,
            "phone": rec.get("phone"),
            "phone_conflict": False,
            "google_website": None,
            "maps_url": None,
            "place_id": None,
        }

    hours, confidence, source = best_hours(rec, entry)

    return {
        "hours": hours,
        "confidence": confidence,
        "hours_source": source,
        "rating": entry.get("rating"),
        "rating_date": entry.get("rating_date"),
        "review_count": entry.get("review_count"),
        "claimed": (entry.get("claimed") or "").upper() or None,
        # existing phone wins; Google's is kept only as a conflict flag
        "phone": rec.get("phone") or entry.get("google_phone"),
        "phone_conflict": bool(entry.get("phone_conflicts")),
        "google_website": entry.get("google_website"),
        "maps_url": entry.get("maps_url"),
        "place_id": entry.get("place_id"),
    }
