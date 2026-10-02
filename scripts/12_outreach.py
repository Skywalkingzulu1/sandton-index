#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
12_outreach.py -- Generate per-record B2B proposals from real attributes.

This is the sales-facing deliverable: one proposal per business, built from
what we actually know about them, so a person on the phone opens with facts
rather than a template.

Three rules constrain every proposal generated here.

1. NO INVENTED FACTS. Headcount, hours, phone, website status and hours
   quality all come from the dataset or are reported as unknown. A pitch that
   says "we noticed your 85 staff" when we have no headcount data is a lie
   that gets caught on the first call.

2. NO UNAPPROVED COMMERCIAL OFFERS. The proposals are generated as DRAFTS with
   an explicit approval_required flag. No voucher code, discount, price or
   compliance benefit in this file has been agreed by Doctors on Wheels. The
   copy names the benefit but marks it pending, because a salesperson reading
   a document that quotes "15 free consultations" will quote it.

3. NO COMPLIANCE GUARANTEE. B-BBEE Code 700 / SED spend is a regulated
   determination. These proposals say the engagement is *structured around*
   an SED budget where one exists -- never that any spend "completes",
   "satisfies" or "certifies" a score. That determination belongs to a
   verification professional, not to a scraper.

Output: data/outreach.json + data/outreach_summary.csv
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA, SITE_URL  # noqa: E402

# What a DOW module is worth to this record's cluster. Used to pick the angle,
# never to promise a value.
CLUSTER_ANGLE = {
    "health-medical-urgent":
        ("clinical partnership", "referral flow and on-site screening days"),
    "commercial-industrial-hubs":
        ("workplace health", "occupational screening days for park staff "
                             "and tenants"),
    "housing-managed-complexes":
        ("resident health", "mobile GP access for residents without "
                            "travelling to a practice"),
    "education-family":
        ("family health", "staff health days and home visits for families"),
    "transport-logistics":
        ("occupational health", "fit-for-work and driver assessments around "
                                "shift patterns"),
    "recreation-lifestyle":
        ("member health", "screening days at the facility"),
    "daily-retail-conveniences":
        ("worker welfare", "primary care and screening vouchers for "
                           "frontline staff"),
    "civic-public-services": (None, None),
    "home-maintenance-trades": (None, None),
}

# B-BBEE language the proposals are allowed to use.
# "structured around" is the ceiling. Nothing here says a spend satisfies a
# score, because that is a determination this project cannot make.
SED_FRAMING = (
    "Structured around your B-BBEE SED (Code 700) planning where one exists, "
    "so the health spend and the compliance budget can be considered together "
    "by whoever does your verification."
)


def load(name, default=None):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return default if default is not None else {}
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}


def hours_quality(rec):
    """Plain-language read of how much we can say about this business."""
    conf = rec.get("hours_confidence")
    if conf == "scraped":
        return "verified", ("we hold published opening hours for them")
    if rec.get("opening_hours"):
        return "estimated", ("we hold estimated hours for them")
    return "unknown", "we hold no hours for them"


def build_proposal(rec, intent, overlay_entry):
    rid = rec["id"]
    cluster = (intent.get(rid) or {}).get("cluster", "")
    is_complex = (intent.get(rid) or {}).get("is_complex", False)

    has_site = bool(rec.get("website"))
    tier = rec.get("tier")
    quality, quality_phrase = hours_quality(rec)
    angle, benefit = CLUSTER_ANGLE.get(cluster, (None, None))

    # ---- the opening line: one verified fact about THEM -----------------
    if not has_site:
        opener = ("They have no website of their own, which is the single "
                  "biggest reason they do not appear in the searches that "
                  "would otherwise find them.")
    elif quality == "verified":
        opener = ("They have a website and published hours, so they are "
                  "already indexable -- the offer here is reach, not "
                  "remediation.")
    else:
        opener = ("They have a website but no published hours, and hours are "
                  "the strongest single signal for 'open now near me' "
                  "searches.")

    # ---- the ask -------------------------------------------------------
    if not has_site:
        ask = ("Claim administrative control of the page already built for "
               "them at no cost.")
    elif is_complex:
        ask = ("Activate the tenant directory and resident portal for their "
               "property.")
    else:
        ask = "Claim the listing to correct and complete their details."

    # ---- blockers we must be honest about -------------------------------
    blockers = []
    if not rec.get("phone"):
        blockers.append("no phone number on record - contact by email or "
                        "in person")
    if quality != "verified":
        blockers.append(f"hours are {quality}, so do not quote them")
    if rec.get("lat") is None:
        blockers.append("no coordinates on record - location unverified")

    return {
        "id": rid,
        "name": rec["name"],
        "hub": rec["hub"],
        "zone": rec.get("zone_display"),
        "path": rec["path"],
        "url": f"{SITE_URL}/{rec['path']}/",
        "claim_url": f"{SITE_URL}/needs-a-website/?b={rid}",
        "tier": tier,
        "cluster": cluster,
        "is_complex": is_complex,
        "has_website": has_site,
        "hours_quality": quality,
        "phone_on_record": bool(rec.get("phone")),
        "angle": angle,
        "benefit": benefit,
        "sed_framing": SED_FRAMING,
        "approved_claim": (
            f"{rec['name']} already has a free, fully built page here. "
            "Claiming it costs nothing and lets them correct the details."
        ),
        "unknowns_to_avoid_claiming": blockers,
        "notes_for_reps": opener,
        "primary_ask": ask,
        # Everything commercial in this file is unapproved. A rep who reads
        # only the booleans still cannot quote anything as agreed.
        "approval_required": {
            "voucher_codes": True,
            "discount_terms": True,
            "sed_compliance_claims": True,
            "dow_participation": True,
            "status": "DRAFT - not approved by Doctors on Wheels",
        },
    }


def main():
    db = load("businesses.json")
    records = db.get("records", [])
    intent = load("intent.json")
    overlay = load("google.json")

    props = []
    for rec in records:
        props.append(build_proposal(rec, intent,
                                    overlay.get(rec["id"])))

    dest = os.path.join(DATA, "outreach.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(props, fh, ensure_ascii=False, indent=1)

    cols = ["name", "zone", "hub", "cluster", "tier", "has_website",
            "hours_quality", "phone_on_record", "is_complex", "angle",
            "primary_ask", "url", "claim_url"]
    csv_path = os.path.join(DATA, "outreach_summary.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for p in props:
            w.writerow(p)

    # ---- summary -------------------------------------------------------
    no_site = [p for p in props if not p["has_website"]]
    complex_recs = [p for p in props if p["is_complex"]]
    pitched = [p for p in props if p["angle"]]
    no_phone = [p for p in props if not p["phone_on_record"]]

    print("=" * 62)
    print("SANDTON INDEX -- outreach proposals")
    print("=" * 62)
    print(f"  proposals generated        : {len(props)}")
    print(f"  web-absent (free-site ask) : {len(no_site)}")
    print(f"  property/portal activations: {len(complex_recs)}")
    print(f"  with a DOW angle           : {len(pitched)}")
    print(f"  no phone on record         : {len(no_phone)}  "
          f"(email/in-person outreach only)")
    print(f"\n  every proposal is a DRAFT  : no voucher code, discount or")
    print(f"  compliance claim in this file has been approved by DOW.")
    print(f"\n  written: data/outreach.json")
    print(f"           data/outreach_summary.csv")
    print("=" * 62)


if __name__ == "__main__":
    main()
