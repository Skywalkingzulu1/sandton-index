#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
09_build_sites.py -- Generate the static site.

Three page types, three different jobs:

  1. HUB  /<category>/<zone>/   the traffic surface. Targets queries like
     "supermarket sandton" and "supermarket near me". This is where the index
     earns its keep, and where every listed business is a sales lead.

  2. BRANCH  /<brand>/<branch>/ a chain location. Carries NAP, hours, map,
     JSON-LD. Never pitched "you have no website" -- these are tier B.

  3. SITE  /<brand>/            a free starter site for a tier-A business that
     has nothing. Single page, Maps embed, click-to-call, and a visible
     "these hours are a guess, claim your listing" prompt that feeds the
     outreach loop back into the dataset.

Design constraints that came out of the data, not preference:
  - Estimated hours are labelled in the UI and omitted from JSON-LD.
  - Every business with coordinates gets a Google Maps embed, because Maps is
    where local intent now resolves and it costs no API key.
  - pages/ is emitted as a flat mirror so GitHub Pages can serve it from a
    subpath without server rewrites.

Outputs: site/ (ready to publish)
"""
import html
import json
import os
import shutil
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (  # noqa: E402
    DATA,
    HUB_BY_SLUG,
    MIN_HUB_LISTINGS,
    SITE,
    SITE_DESCRIPTION,
    SITE_NAME,
    SITE_URL,
    slugify,
)

DAY_LABELS = [
    ("monday", "Monday"), ("tuesday", "Tuesday"), ("wednesday", "Wednesday"),
    ("thursday", "Thursday"), ("friday", "Friday"), ("saturday", "Saturday"),
    ("sunday", "Sunday"),
]

# Map a raw category onto a schema.org type for JSON-LD.
SCHEMA_TYPE_BY_HUB = {
    "restaurants-takeaways": "Restaurant",
    "supermarkets": "GroceryStore",
    "convenience-liquor": "ConvenienceStore",
    "clothing-fashion": "ClothingStore",
    "beauty-hair": "BeautySalon",
    "health-wellness": "MedicalBusiness",
    "hotels-accommodation": "Hotel",
    "home-furniture": "FurnitureStore",
    "doityourself-hardware": "HardwareStore",
    "automotive": "AutomotiveBusiness",
    "professional-services": "ProfessionalService",
    "banks-financial": "FinancialService",
    "tech-it": "ProfessionalService",
    "offices-coworking": "Office",
    "malls-shopping-centres": "ShoppingMall",
    "fitness-sports": "ExerciseGym",
    "services-home": "HomeAndConstructionBusiness",
    "education-training": "EducationalOrganization",
    "pets-animals": "VeterinaryCare",
    "media-printing": "Store",
    "travel-tourism": "TravelAgency",
    "auctions-pawn": "Store",
    "cannabis": "Store",
    "other": "LocalBusiness",
}

CSS = """
:root{--ink:#12211a;--mut:#5c6b63;--line:#e3e8e4;--bg:#fbfcfa;--card:#fff;
--acc:#1d6b45;--acc-d:#12502f;--warn:#8a5a00;--warn-bg:#fff8e6;--r:12px}
*{box-sizing:border-box}
body{margin:0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg)}
a{color:var(--acc);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
header.site{background:var(--card);border-bottom:1px solid var(--line);
position:sticky;top:0;z-index:20}
header.site .wrap{display:flex;align-items:center;gap:16px;
justify-content:space-between;height:62px}
.brand{font-weight:800;font-size:19px;color:var(--ink);letter-spacing:-.3px}
.brand span{color:var(--acc)}
nav.site a{margin-left:18px;font-size:14px;color:var(--mut);font-weight:500}
.hero{padding:52px 0 34px;background:linear-gradient(180deg,#f2f7f3,#fbfcfa)}
.hero h1{margin:0 0 12px;font-size:clamp(28px,4.4vw,44px);line-height:1.12;
letter-spacing:-1px}
.hero p{margin:0;color:var(--mut);font-size:18px;max-width:62ch}
.crumb{font-size:13px;color:var(--mut);padding:16px 0 0}
.crumb a{color:var(--mut)}
h2.sec{font-size:14px;text-transform:uppercase;letter-spacing:.09em;
color:var(--mut);font-weight:700;margin:38px 0 14px}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(310px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
padding:17px 18px;display:flex;flex-direction:column;gap:8px}
.card h3{margin:0;font-size:17px;line-height:1.3}
.card .meta{font-size:13.5px;color:var(--mut)}
.card .acts{margin-top:auto;padding-top:9px;display:flex;gap:14px;font-size:14px;
font-weight:600}
.hrs{font-size:13.5px;color:var(--mut)}
.hrs .row{display:flex;justify-content:space-between;gap:12px;padding:1px 0}
.hrs .row.today{color:var(--acc);font-weight:700}
.map{width:100%;height:290px;border:0;border-radius:var(--r);display:block;
border:1px solid var(--line)}
.badge{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.04em;
padding:2px 8px;border-radius:99px;text-transform:uppercase}
.b-a{background:#e7f4ec;color:var(--acc-d)}
.b-b{background:#eef1f6;color:#3d4d63}
.b-c{background:#f1f1f1;color:#6b6b6b}
.b-none{background:#f4f4f4;color:#8a8a8a}
.guess{background:var(--warn-bg);border:1px solid #f0dca8;border-radius:9px;
padding:11px 13px;font-size:13.5px;color:var(--warn);margin:12px 0}
.guess strong{color:#6b4500}
.cta{background:var(--acc);color:#fff;border-radius:var(--r);padding:26px;
margin:34px 0;text-align:center}
.cta h2{color:#fff;margin:0 0 8px;font-size:22px}
.cta p{color:#dcebe2;margin:0 0 16px}
.btn{display:inline-block;background:#fff;color:var(--acc-d);padding:10px 20px;
border-radius:9px;font-weight:700;font-size:15px}
.btn:hover{text-decoration:none;opacity:.92}
.sib{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
padding:15px 17px;margin-bottom:10px}
.sib h3{margin:0 0 5px;font-size:16px}
.empty{color:var(--mut);padding:30px 0;font-size:16px}
footer.site{border-top:1px solid var(--line);margin-top:56px;padding:26px 0;
font-size:13.5px;color:var(--mut);background:var(--card)}
.foot{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap}
.breadcrumb-trail{font-size:13px;color:var(--mut);padding:14px 0 0}
@media(max-width:640px){
nav.site a{margin-left:11px;font-size:13px}
.hero{padding:34px 0 24px}
.card{padding:15px 16px}
}
""".strip()


def e(value):
    """HTML-escape, coercing None to an empty string."""
    return html.escape(str(value if value is not None else ""))


def fmt_span(value):
    """'09:00-17:00' -> '9:00 am - 5:00 pm'. Keeps the 24h value if unparseable."""
    if not value or "-" not in value:
        return e(value) if value else "Closed"
    op, cl = value.split("-", 1)
    return f"{_fmt_time(op)} - {_fmt_time(cl)}"


def _fmt_time(t):
    try:
        hh, mm = t.split(":")
        hh_i = int(hh)
        suffix = "am" if hh_i < 12 else "pm"
        h12 = hh_i % 12 or 12
        return f"{h12}:{mm} {suffix}" if mm != "00" else f"{h12} {suffix}"
    except (ValueError, AttributeError):
        return e(t)


def maps_embed_url(rec):
    """Keyless Google Maps iframe for a record.

    Using the query form (name + address) rather than the API means no key,
    no billing, and no quota to manage. A keyless embed still renders a live
    pin, address and directions button.
    """
    lat, lng = rec.get("lat"), rec.get("lng")
    if lat is not None and lng is not None:
        center = f"{lat},{lng}"
        zoom = 17
    else:
        label = rec.get("name", "")
        loc = " ".join(x for x in [label, rec.get("street_address", ""),
                                   rec.get("zone_display", "")] if x)
        center = e(loc)
        zoom = 15

    return (f"https://www.google.com/maps?q={center}&z={zoom}&output=embed")


def maps_link(rec):
    """Tap-through directions link."""
    lat, lng = rec.get("lat"), rec.get("lng")
    if lat is not None and lng is not None:
        return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"
    label = " ".join(x for x in [rec.get("name", ""),
                                 rec.get("street_address", ""),
                                 rec.get("zone_display", "")] if x)
    return f"https://www.google.com/maps/search/?api=1&query={e(label)}"


def address_text(rec):
    parts = [
        rec.get("building_name", ""),
        rec.get("street_address", ""),
        rec.get("zone_display", ""),
    ]
    seen, out = set(), []
    for p in parts:
        p = (p or "").strip()
        # building_name often just repeats the trading name in this dataset
        if p and p.lower() != rec.get("name", "").lower() and p not in seen:
            seen.add(p)
            out.append(p)
    postcode = (rec.get("postcode") or "").strip()
    if postcode:
        out.append(postcode)
    return ", ".join(out) or "Sandton, Johannesburg"


def hours_block(rec, compact=False):
    """Render opening hours with an explicit confidence treatment.

    Scraped hours are shown as fact. Inferred hours are shown with a visible
    notice, because printing a guess in the same visual weight as verified
    information is how a directory ends up sending customers to a closed door.
    """
    days = rec.get("opening_hours")
    confidence = rec.get("hours_confidence", "none")

    if not days:
        return ('<p class="hrs"><strong>Opening hours</strong><br>'
                'Not published &mdash; ask the business directly.</p>')

    rows = []
    for key, label in DAY_LABELS:
        val = days.get(key)
        if val:
            rows.append(f'<div class="row"><span>{label}</span>'
                        f'<span>{fmt_span(val)}</span></div>')
    if not rows:
        return ('<p class="hrs"><strong>Opening hours</strong><br>'
                'Not published &mdash; ask the business directly.</p>')

    out = ['<p class="hrs"><strong>Opening hours</strong></p>',
           '<div class="hrs">'] + rows + ['</div>']

    if confidence == "default" and not compact:
        out.append(
            '<div class="guess"><strong>Typical hours, not confirmed.</strong> '
            'These are an estimate for this type of business. If this is your '
            'business, claim the listing to correct them &mdash; wrong opening '
            'hours push you down local results.</div>'
        )
    return "".join(out)


def jsonld_local_business(rec):
    """LocalBusiness schema.

    openingHours is only emitted when the schedule was actually scraped.
    Emitting an inferred schedule inside structured data would have Google
    publish an unverified claim about a real business, which is exactly the
    failure mode that gets a listing suppressed.
    """
    data = {
        "@context": "https://schema.org",
        "@type": SCHEMA_TYPE_BY_HUB.get(rec["hub"], "LocalBusiness"),
        "name": rec["name"],
        "address": {
            "@type": "PostalAddress",
            "addressLocality": "Sandton",
            "addressRegion": "Gauteng",
            "addressCountry": "ZA",
            "streetAddress": rec.get("street_address")
            or rec.get("building_name") or "",
            "postalCode": rec.get("postcode", ""),
        },
    }
    if rec.get("phone"):
        data["telephone"] = rec["phone"]
    if rec.get("lat") is not None and rec.get("lng") is not None:
        data["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": rec["lat"],
            "longitude": rec["lng"],
        }
    if rec.get("website"):
        data["url"] = rec["website"]
    if rec.get("opening_hours") and rec.get("hours_confidence") == "scraped":
        data["openingHours"] = [
            v for k, v in rec["opening_hours"].items() if k != "_all" and v
        ]

    script = json.dumps(data, ensure_ascii=False)
    return f'<script type="application/ld+json">{script}</script>'


def tier_badge(rec):
    tier = rec.get("tier", "C")
    label = {"A": "No website yet", "B": "Chain location",
             "C": "Has website"}.get(tier, "")
    return f'<span class="badge b-{tier.lower()}">{e(label)}</span>'


def header_html():
    return f"""<header class="site"><div class="wrap">
<a class="brand" href="{SITE_URL}/">{e(SITE_NAME)}<span>.</span></a>
<nav class="site">
<a href="{SITE_URL}/">Home</a>
<a href="{SITE_URL}/categories/">Categories</a>
<a href="{SITE_URL}/zones/">Suburbs</a>
<a href="{SITE_URL}/needs-a-website/">Get listed free</a>
</nav></div></header>"""


def footer_html():
    return f"""<footer class="site"><div class="wrap foot">
<div><strong>{e(SITE_NAME)}</strong><br>
A directory of businesses across Sandton, Johannesburg.</div>
<div>Map data &copy; OpenStreetMap contributors.<br>
Hours shown are indicative &mdash; confirm before travelling.</div>
</div></footer>"""


def page(title, description, body, canonical, extra_head=""):
    """Wrap a page body in the shared shell."""
    return f"""<!doctype html>
<html lang="en-ZA">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{e(canonical)}">
{extra_head}
<style>{CSS}</style>
</head>
<body>
{header_html()}
{body}
{footer_html()}
</body></html>
"""


def business_card(rec):
    """A single listing card used on hub pages and sibling lists."""
    phone = rec.get("phone", "")
    phone_html = (f'<a href="tel:{e(phone.replace(" ", ""))}">{e(phone)}</a>'
                  if phone else "")
    acts = [f'<a href="{SITE_URL}/{e(rec["path"])}/">Details</a>',
            f'<a href="{maps_link(rec)}" target="_blank" rel="noopener">Directions</a>']
    if phone_html:
        acts.append(phone_html)
    hz = hub_zone_url(rec)
    if hz:
        acts.append(f'<a href="{e(hz)}">All {e(rec["hub_title"].lower())} '
                    f'here</a>')

    return f"""<article class="card">
<h3><a href="{SITE_URL}/{e(rec['path'])}/">{e(rec['name'])}</a></h3>
<div class="meta">{e(rec['hub_title'])} &middot; {e(rec['zone_display'])}</div>
<div class="meta">{e(address_text(rec))}</div>
<div class="acts">{' '.join(acts)}</div>
</article>"""


def hub_zone_url(rec):
    """Link to the category x suburb page, or None when that page is thin.

    Guards every link to a near-me landing page, so folding thin hubs into
    the category index cannot leave a dangling internal link.
    """
    if rec.get("hub_zone_count", 0) >= MIN_HUB_LISTINGS:
        return f"{SITE_URL}/{e(rec['hub'])}/{e(rec['zone'])}/"
    return None


def write(path_rel, content):
    """Write a page into the site root.

    No pages/ mirror is emitted. Internal links are absolute against
    SITE_URL, so a mirrored copy under pages/ would be unreachable and would
    double the build for nothing. When the base URL is a GitHub Pages project
    path, the repo root already serves at that path and the root copy is
    correct.
    """
    dest = os.path.join(SITE, path_rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(content)


# ---------------------------------------------------------------- hubs
def build_hub_page(hub_slug, zone_key, recs):
    hub = HUB_BY_SLUG.get(hub_slug, {"title": "Sandton Businesses",
                                     "singular": "business"})
    zone_display = recs[0]["zone_display"] if recs else "Sandton"
    landmark = recs[0]["zone_landmark"] if recs else "Sandton"
    singular = hub["singular"]

    title = f"{hub['title']} in {zone_display} | {SITE_NAME}"
    desc = (f"{len(recs)} {singular} options in {zone_display}, Sandton. "
            f"Opening hours, directions and contact details, all on one map.")
    canonical = f"{SITE_URL}/{hub_slug}/{zone_key}/"

    # Sort so the best-provisioned listings appear first: they carry the
    # contact details that make the directory useful rather than a stub list.
    recs = sorted(recs, key=lambda r: (
        bool(r.get("phone")), bool(r.get("lat")), r.get("name", "")
    ))

    cards = "".join(business_card(r) for r in recs)
    no_hours = sum(1 for r in recs if not r.get("opening_hours"))
    no_site = sum(1 for r in recs if r.get("tier") == "A")

    facts = []
    if no_site:
        facts.append(f"{no_site} of these have no website yet")
    if no_hours:
        facts.append(f"{no_hours} have no published opening hours")

    body = f"""<div class="hero"><div class="wrap">
<div class="crumb"><a href="{SITE_URL}/">Home</a> /
<a href="{SITE_URL}/categories/">Categories</a> / {e(hub['title'])}</div>
<h1>{e(hub['title'])} in {e(zone_display)}</h1>
<p>{len(recs)} places near {e(landmark)} with hours, directions and contact
details. {' Also: ' + ', '.join(facts) + '.' if facts else ''}</p>
</div></div>
<div class="wrap">
<h2 class="sec">All {len(recs)} in {e(zone_display)}</h2>
<div class="grid">{cards}</div>
<div class="cta">
<h2>Running a {singular} in {zone_display}?</h2>
<p>Claim your free listing with your real hours, photos and contact details.</p>
<a class="btn" href="{SITE_URL}/needs-a-website/">Get a free listing</a>
</div>
</div>"""
    write(os.path.join(hub_slug, zone_key, "index.html"),
          page(title, desc, body, canonical))


# ---------------------------------------------------------------- business
def build_business_page(rec, siblings):
    """Detail page for one business, covering both branch and template roles."""
    hub = HUB_BY_SLUG.get(rec["hub"], {"title": "Sandton Business",
                                       "singular": "business"})
    title = (f"{rec['name']}, {rec['zone_display']} | "
             f"{hub['singular'].capitalize()} in Sandton")
    desc = (f"{rec['name']} in {rec['zone_display']}, Sandton. "
            f"Address, opening hours, phone and directions.")
    canonical = f"{SITE_URL}/{rec['path']}/"

    bits = []
    if rec.get("phone"):
        bits.append(f'<a href="tel:{e(rec["phone"].replace(" ", ""))}">'
                    f'{e(rec["phone"])}</a>')
    if rec.get("website"):
        bits.append(f'<a href="{e(rec["website"])}" target="_blank" '
                    f'rel="noopener">Website</a>')
    bits.append(f'<a href="{maps_link(rec)}" target="_blank" rel="noopener">'
                f'Directions</a>')
    contact = " &middot; ".join(bits) if bits else "No phone published"

    # Tier A businesses get the conversion pitch on their own page. Tier B
    # chains are never told they need a website -- they have one.
    if rec["tier"] == "A":
        claim = f"""<div class="cta">
<h2>Is this your business?</h2>
<p>You have no website listed. Claim this free page and we will set up your
details, photos and opening hours properly.</p>
<a class="btn" href="{SITE_URL}/claim/?b={e(rec['id'])}">Claim this listing</a>
</div>"""
    else:
        claim = f"""<div class="cta">
<h2>Found a mistake in these details?</h2>
<p>Hours, address or phone out of date? Claim the listing to correct it
&mdash; accurate details are what local search rewards.</p>
<a class="btn" href="{SITE_URL}/claim/?b={e(rec['id'])}">Update these details</a>
</div>"""

    sib_html = ""
    if siblings:
        items = "".join(f"""<div class="sib">
<h3><a href="{SITE_URL}/{e(s['path'])}/">{e(s['name'])}</a></h3>
<div class="meta">{e(s['zone_display'])} &middot;
{e(s.get('street_address') or address_text(s))}</div>
</div>""" for s in siblings)
        label = ("Other branches" if len(siblings) > 1 else "Nearby")
        sib_html = f"""<h2 class="sec">{label} of {e(rec['name'].split()[0])}</h2>
{items}"""

    hz = hub_zone_url(rec)
    crumb_hub = (f'<a href="{e(hz)}">{e(hub["title"])}</a>' if hz
                 else f'<a href="{SITE_URL}/{e(rec["hub"])}/">{e(hub["title"])}</a>')

    body = f"""<div class="hero"><div class="wrap">
<div class="crumb"><a href="{SITE_URL}/">Home</a> /
{crumb_hub} / {e(rec['name'])}</div>
<h1>{e(rec['name'])}</h1>
<p>{e(hub['singular'].capitalize())} in {e(rec['zone_display'])}.
{e(address_text(rec))}</p>
</div></div>
<div class="wrap">
<p style="margin:18px 0">{tier_badge(rec)}</p>
<div class="grid" style="grid-template-columns:1fr 1fr;align-items:start">
<div>
<p><strong>Address</strong><br>{e(address_text(rec))}<br>Sandton,
{('2196' if rec.get('postcode') else 'Johannesburg, Gauteng')}, South Africa</p>
<p><strong>Contact</strong><br>{contact}</p>
{hours_block(rec)}
</div>
<div>
<iframe class="map" title="Map showing {e(rec['name'])}"
src="{maps_embed_url(rec)}" loading="lazy"
referrerpolicy="no-referrer-when-downgrade"></iframe>
<p style="font-size:13.5px;color:var(--mut);margin-top:9px">
<a href="{maps_link(rec)}" target="_blank" rel="noopener">Open in Google
Maps</a> &mdash; add or correct this listing there too. It is where most people
actually look for a business.</p>
</div>
</div>
{sib_html}
{claim}
</div>"""
    write(os.path.join(rec["path"], "index.html"),
          page(title, desc, body, canonical,
               extra_head=jsonld_local_business(rec)))


# ---------------------------------------------------------------- indexes
def build_home(records, hubs_by_zone):
    total = len(records)
    no_site = sum(1 for r in records if r["tier"] == "A")
    zones = sorted(hubs_by_zone.keys())

    zone_cards = "".join(f"""<article class="card">
<h3><a href="{SITE_URL}/zones/">{e(z)}</a></h3>
<div class="meta">{sum(len(v) for k, v in hubs_by_zone.items() if k == z)}
businesses listed</div></article>""" for z in zones)

    title = f"{SITE_NAME} | Every business in Sandton, Johannesburg"
    desc = SITE_DESCRIPTION
    body = f"""<div class="hero"><div class="wrap">
<h1>Every business in Sandton, on one map.</h1>
<p>{total} businesses across {len(zones)} suburbs of Sandton, Johannesburg
&mdash; with opening hours, directions and contact details. {no_site} of them
have no website yet and can claim a free page here.</p>
</div></div>
<div class="wrap">
<h2 class="sec">Browse by suburb</h2>
<div class="grid">{zone_cards}</div>
<h2 class="sec">Browse by category</h2>
<div class="grid">
{''.join(f'''<article class="card"><h3><a href="{SITE_URL}/{h['slug']}/">{e(h['title'])}</a></h3>
<div class="meta">{sum(1 for r in records if r['hub'] == h['slug'])} listings
across Sandton</div></article>''' for h in HUB_BY_SLUG.values()
 if any(r['hub'] == h['slug'] for r in records))}
</div>
<div class="cta">
<h2>No website? Get a free listing.</h2>
<p>Hours, map, phone and directions on a page of your own. Free.</p>
<a class="btn" href="{SITE_URL}/needs-a-website/">Claim your business</a>
</div>
</div>"""
    write("index.html", page(title, desc, body, f"{SITE_URL}/"))


def build_categories_index(records):
    counts = defaultdict(int)
    for r in records:
        counts[r["hub"]] += 1
    cards = "".join(f"""<article class="card">
<h3><a href="{SITE_URL}/{h['slug']}/">{e(h['title'])}</a></h3>
<div class="meta">{counts.get(h['slug'], 0)} listings across Sandton</div>
</article>""" for h in HUB_BY_SLUG.values() if counts.get(h["slug"], 0))

    body = f"""<div class="hero"><div class="wrap">
<h1>Categories</h1>
<p>Every category of business listed in the Sandton Index.</p>
</div></div>
<div class="wrap"><div class="grid">{cards}</div></div>"""
    write(os.path.join("categories", "index.html"),
          page(f"Categories | {SITE_NAME}",
               "Browse Sandton businesses by category.", body,
               f"{SITE_URL}/categories/"))


def build_hub_index(hub, zones, records):
    # Only list suburbs that earned their own page. A zone whose listing count
    # is below MIN_HUB_LISTINGS has no page to link to, and linking to a
    # non-existent near-me page would be a dead end for both crawler and user.
    cards = "".join(f"""<article class="card">
<h3><a href="{SITE_URL}/{e(hub['slug'])}/{e(z)}/">{e(label)}</a></h3>
<div class="meta">{n} listings</div></article>"""
                    for z, label, n in zones if n >= MIN_HUB_LISTINGS)
    if not cards:
        cards = ('<p class="empty">No suburb has enough listings yet for its '
                 'own page. Browse all listings by suburb instead.</p>')

    body = f"""<div class="hero"><div class="wrap">
<div class="crumb"><a href="{SITE_URL}/">Home</a> /
<a href="{SITE_URL}/categories/">Categories</a></div>
<h1>{e(hub['title'])}</h1>
<p>Pick your suburb to see {e(hub['singular'])} options near you.</p>
</div></div>
<div class="wrap"><div class="grid">{cards}</div></div>"""
    write(os.path.join(hub["slug"], "index.html"),
          page(f"{hub['title']} in Sandton | {SITE_NAME}",
               f"{hub['title']} across Sandton, Johannesburg.", body,
               f"{SITE_URL}/{hub['slug']}/"))


def build_zone_index(zone_key, label, recs):
    by_hub = defaultdict(list)
    for r in recs:
        by_hub[r["hub"]].append(r)
    # Heading links to the near-me hub page only when that page exists;
    # otherwise it links to the category index, which always does.
    groups = "".join(
        (f"""<h2 class="sec"><a href="{SITE_URL}/{e(hub_slug)}/{e(zone_key)}/">
{e(HUB_BY_SLUG[hub_slug]['title'])}</a> <span style="font-weight:400;
text-transform:none;letter-spacing:0">({len(by_hub[hub_slug])})</span></h2>
<div class="grid">{''.join(business_card(r) for r in by_hub[hub_slug])}</div>"""
         if len(by_hub[hub_slug]) >= MIN_HUB_LISTINGS else
         f"""<h2 class="sec"><a href="{SITE_URL}/{e(hub_slug)}/">
{e(HUB_BY_SLUG[hub_slug]['title'])}</a> <span style="font-weight:400;
text-transform:none;letter-spacing:0">({len(by_hub[hub_slug])})</span></h2>
<div class="grid">{''.join(business_card(r) for r in by_hub[hub_slug])}</div>""")
        for hub_slug in sorted(by_hub, key=lambda s: -len(by_hub[s])))
    body = f"""<div class="hero"><div class="wrap">
<div class="crumb"><a href="{SITE_URL}/">Home</a> /
<a href="{SITE_URL}/zones/">Suburbs</a></div>
<h1>{e(label)}</h1>
<p>{len(recs)} businesses listed in {e(label)}, Sandton.</p>
</div></div>
<div class="wrap">{groups}</div>"""
    write(os.path.join("zones", zone_key, "index.html"),
          page(f"{label} businesses | {SITE_NAME}",
               f"Every listed business in {label}, Sandton, Johannesburg.",
               body, f"{SITE_URL}/zones/{zone_key}/"))


def build_zone_index_page(all_zones):
    cards = "".join(f"""<article class="card">
<h3><a href="{SITE_URL}/zones/{e(z)}/">{e(label)}</a></h3>
<div class="meta">{n} businesses listed</div></article>"""
                    for z, label, n in all_zones)
    body = f"""<div class="hero"><div class="wrap">
<h1>Sandton suburbs</h1>
<p>Browse the index by area.</p>
</div></div>
<div class="wrap"><div class="grid">{cards}</div></div>"""
    write(os.path.join("zones", "index.html"),
          page(f"Suburbs | {SITE_NAME}",
               "Browse the Sandton Index by suburb.", body,
               f"{SITE_URL}/zones/"))


def build_landing(records, slug, heading, blurb, cta_label, extra=""):
    tier_a = [r for r in records if r["tier"] == "A"]
    if slug == "needs-a-website":
        body = f"""<div class="hero"><div class="wrap">
<h1>Get a free page for your Sandton business</h1>
<p>{blurb}</p>
</div></div>
<div class="wrap">
<div class="cta" style="background:var(--card);border:1px solid var(--line);
color:var(--ink)">
<h2 style="color:var(--ink)">{len(tier_a)} Sandton businesses have no
website yet</h2>
<p style="color:var(--mut)">If that is you, a basic page with your hours, map,
phone and directions costs you nothing. It is the minimum for showing up when
someone searches for what you do.</p>
<a class="btn" href="mailto:hello@{SITE_URL.split('//')[1]}?subject=Claim%20my%20Sandton%20listing">{cta_label}</a>
</div>
{extra}
</div>"""
    else:
        body = f"""<div class="hero"><div class="wrap">
<h1>{e(heading)}</h1>
<p>{e(blurb)}</p>
</div></div>
<div class="wrap">{extra}</div>"""
    write(os.path.join(slug, "index.html"),
          page(f"{heading} | {SITE_NAME}", blurb, body, f"{SITE_URL}/{slug}/"))


# ---------------------------------------------------------------- sitemap
def build_sitemap(paths):
    urls = "".join(f"<url><loc>{e(SITE_URL)}/{p}</loc></url>"
                   for p in paths if p != "index.html")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f"{urls}\n</urlset>\n")
    os.makedirs(SITE, exist_ok=True)
    with open(os.path.join(SITE, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write(xml)


def main():
    biz_path = os.path.join(DATA, "businesses.json")
    if not os.path.exists(biz_path):
        sys.exit("Run 07 and 08 first -- businesses.json missing")
    with open(biz_path, encoding="utf-8") as fh:
        data = json.load(fh)
    records = data["records"]

    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE, exist_ok=True)

    # --- group for pages ---
    by_hub_zone = defaultdict(list)
    by_zone = defaultdict(list)
    by_hub = defaultdict(list)
    by_brand = defaultdict(list)
    for r in records:
        by_hub_zone[(r["hub"], r["zone"])].append(r)
        by_zone[r["zone"]].append(r)
        by_hub[r["hub"]].append(r)
        by_brand[r["brand_slug"]].append(r)

    print("=" * 62)
    print("SANDTON INDEX -- static site build")
    print("=" * 62)

    # 1. business pages
    n_biz = 0
    for rec in records:
        siblings = [s for s in by_brand[rec["brand_slug"]] if s["id"] != rec["id"]]
        build_business_page(rec, siblings)
        n_biz += 1
    print(f"  business pages : {n_biz}")

    # 2. hub x zone pages
    #
    # Only combinations with enough listings to be worth indexing get their
    # own page. A hub listing a single business cannot compete for
    # "supermarket sandton", offers the visitor nothing the category page
    # does not, and reads as filler. Those records link into the category
    # index instead, and the category index only lists zones that qualified.
    n_hub = 0
    thin = set()
    for (hub_slug, zone_key), recs in sorted(by_hub_zone.items()):
        if len(recs) >= MIN_HUB_LISTINGS:
            build_hub_page(hub_slug, zone_key, recs)
            n_hub += 1
        else:
            thin.add((hub_slug, zone_key))
    print(f"  hub x zone     : {n_hub} "
          f"({len(thin)} thin combos folded into category pages)")

    # 3. category, zone and home indexes
    zone_labels = {}
    for r in records:
        zone_labels.setdefault(r["zone"], r["zone_display"])

    hubs_by_zone = {z: [r for r in by_zone[z]] for z in by_zone}
    build_home(records, hubs_by_zone)
    build_categories_index(records)

    for hub_slug, recs in sorted(by_hub.items()):
        zones = sorted(
            ((z, zone_labels.get(z, z), sum(1 for r in recs if r["zone"] == z))
             for z in {r["zone"] for r in recs}),
            key=lambda x: -x[2])
        build_hub_index(HUB_BY_SLUG[hub_slug], zones, records)

    for z, recs in by_zone.items():
        build_zone_index(z, zone_labels.get(z, z), recs)
    build_zone_index_page(
        sorted(((z, zone_labels.get(z, z), len(recs)) for z, recs in by_zone.items()),
               key=lambda x: -x[2]))
    print(f"  index pages    : {2 + len(by_hub) + len(by_zone) + 1}")

    # 4. conversion landings
    no_hours = [r for r in records if not r.get("opening_hours")]
    guess_only = [r for r in records
                  if r.get("hours_confidence") == "default"]
    unreviewed = [r for r in records if r["tier"] == "A"]

    build_landing(
        records, "needs-a-website", "Free listings",
        "A free page for your business: hours, map, phone and directions.",
        "Email us to claim your page",
        extra="".join(
            f"""<div class="sib"><h3><a href="{SITE_URL}/{e(r['path'])}/">
{e(r['name'])}</a></h3><div class="meta">{e(r['zone_display'])} &middot;
{e(r['hub_title'])}</div></div>"""
            for r in sorted(unreviewed, key=lambda x: x["name"])[:60]))

    build_landing(
        records, "hours-not-published",
        "Businesses with no published opening hours",
        "Being open when someone searches is now a confirmed local ranking "
        "factor. These listings have no hours yet.",
        "Add your hours",
        extra="".join(
            f"""<div class="sib"><h3><a href="{SITE_URL}/{e(r['path'])}/">
{e(r['name'])}</a></h3><div class="meta">{e(r['zone_display'])} &middot;
{e(r['hub_title'])}</div></div>"""
            for r in sorted(no_hours, key=lambda x: x["name"])[:60]))

    print(f"  landings       : 2 (needs-a-website, hours-not-published)")

    # 5. 404 + robots
    write("404.html", page(
        "Page not found | Sandton Index",
        "That page does not exist.",
        '<div class="hero"><div class="wrap"><h1>Page not found</h1>'
        '<p>Try the <a href="/">homepage</a> or browse '
        '<a href="/categories/">by category</a>.</p></div></div>',
        f"{SITE_URL}/404.html"))

    for base in (SITE,):
        with open(os.path.join(base, "robots.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write("User-agent: *\nAllow: /\nSitemap: "
                     f"{SITE_URL}/sitemap.xml\n")

    # 6. sitemap over everything written
    written = []
    for root, _dirs, files in os.walk(SITE):
        for f in files:
            if f == "index.html":
                rel = os.path.relpath(os.path.join(root, f), SITE)
                written.append(rel.replace("\\", "/"))
    build_sitemap(sorted(written))
    print(f"  sitemap urls   : {len(written)}")
    print("=" * 62)


if __name__ == "__main__":
    main()
