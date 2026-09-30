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
:root{
--primary:#0052cc;--primary-dark:#0747a6;--primary-darker:#052d6e;
--secondary:#00a3bf;--accent:#36b37e;--accent-dark:#2a8f63;
--text:#1e293b;--muted:#64748b;--border:#e2e8f0;--light:#f8fafc;
--footer:#0f172a;--white:#fff;
--tint-blue:#eef4ff;--tint-green:#e3fcef;--tint-teal:#e6fcff;
--tint-amber:#fff8e1;--amber:#f59e0b;
--shadow-sm:0 1px 3px rgba(0,0,0,.08);
--shadow-md:0 4px 20px rgba(0,0,0,.08);
--shadow-lg:0 10px 40px rgba(0,0,0,.12);
--shadow-glow:0 0 30px rgba(0,82,204,.15);
--r:16px;--r-sm:12px;--r-xs:8px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;font:16px/1.6 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",
Roboto,Helvetica,Arial,sans-serif;color:var(--text);background:var(--white);
-webkit-font-smoothing:antialiased}
a{color:var(--primary);text-decoration:none}
a:hover{text-decoration:none}
.wrap{max-width:1100px;margin:0 auto;padding:0 2rem}

/* ===== NAVBAR (transparent over the gradient hero, solid once scrolled) ===== */
header.site{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.9);
backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
border-bottom:1px solid var(--border);box-shadow:var(--shadow-sm)}
header.site .wrap{display:flex;align-items:center;gap:1rem;
justify-content:space-between;height:66px}
.brand{font-weight:800;font-size:1.22rem;color:var(--text);letter-spacing:-.5px;
display:flex;align-items:center;gap:.55rem}
.brand .mark{width:32px;height:32px;border-radius:9px;display:grid;place-items:center;
background:linear-gradient(135deg,var(--primary),var(--secondary));color:#fff;
font-size:.95rem;box-shadow:0 2px 8px rgba(0,82,204,.3)}
.brand b{color:var(--primary);font-weight:800}
nav.site{display:flex;align-items:center;gap:1.9rem}
nav.site a{color:var(--muted);font-weight:500;font-size:.9rem;
letter-spacing:.01em;transition:color .2s}
nav.site a:hover{color:var(--primary)}
.nav-cta{background:var(--primary);color:#fff!important;padding:.5rem 1.05rem;
border-radius:var(--r-xs);font-weight:600!important;box-shadow:var(--shadow-sm)}
.nav-cta:hover{background:var(--primary-dark)}

/* ===== HERO ===== */
.hero{position:relative;overflow:hidden;
background:linear-gradient(135deg,var(--primary-darker) 0%,var(--primary-dark) 40%,
var(--primary) 100%);color:#fff;padding:4.5rem 0 4rem;margin-bottom:-3rem}
.hero::before{content:'';position:absolute;width:620px;height:620px;border-radius:50%;
background:radial-gradient(circle,rgba(0,163,191,.28) 0%,transparent 70%);
top:-180px;right:-160px;animation:blob 17s ease-in-out infinite}
.hero::after{content:'';position:absolute;width:420px;height:420px;border-radius:50%;
background:radial-gradient(circle,rgba(54,179,126,.20) 0%,transparent 70%);
bottom:-140px;left:-110px;animation:blob 22s ease-in-out infinite reverse}
@keyframes blob{0%,100%{transform:translate(0,0) scale(1)}33%{transform:translate(30px,-30px) scale(1.05)}
66%{transform:translate(-20px,20px) scale(.95)}}
.hero-grid{position:absolute;inset:0;pointer-events:none;
background-image:radial-gradient(rgba(255,255,255,.06) 1px,transparent 1px);
background-size:40px 40px}
.hero .wrap{position:relative;z-index:2}
.hero h1{margin:0 0 1rem;font-size:clamp(2.1rem,4.6vw,3.5rem);font-weight:900;
line-height:1.1;letter-spacing:-1.4px;max-width:19ch}
.hero h1 .grad{background:linear-gradient(135deg,#4fc3f7,#5ce0a0);
-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.hero p{margin:0;color:rgba(255,255,255,.78);font-size:1.05rem;max-width:62ch;
line-height:1.7}
.hero-eyebrow{display:inline-flex;align-items:center;gap:.5rem;margin-bottom:1.1rem;
background:rgba(54,179,126,.15);border:1px solid rgba(54,179,126,.32);
color:#5ce0a0;padding:.35rem .95rem;border-radius:50px;font-size:.78rem;
font-weight:600}
.hero-eyebrow .dot{width:6px;height:6px;border-radius:50%;background:#5ce0a0;
animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}

/* ===== BREADCRUMB (sits below the hero) ===== */
.crumb{position:relative;z-index:2;padding-top:3.6rem;font-size:.82rem;
color:rgba(255,255,255,.62)}
.crumb a{color:rgba(255,255,255,.8)}
.crumb a:hover{color:#fff;text-decoration:underline}

/* ===== STAT CARDS (overlap the hero) ===== */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:1.1rem;
margin:0 0 2.5rem;position:relative;z-index:3}
.stat{background:#fff;border:1px solid var(--border);border-radius:var(--r);
padding:1.4rem 1.1rem;text-align:center;box-shadow:var(--shadow-lg);
transition:transform .3s,box-shadow .3s}
.stat:hover{transform:translateY(-4px);box-shadow:var(--shadow-lg),var(--shadow-glow)}
.stat-ico{width:42px;height:42px;border-radius:11px;margin:0 auto .7rem;
display:grid;place-items:center;font-size:1.05rem}
.ico-blue{background:var(--tint-blue);color:var(--primary)}
.ico-green{background:var(--tint-green);color:var(--accent)}
.ico-teal{background:var(--tint-teal);color:var(--secondary)}
.ico-amber{background:var(--tint-amber);color:var(--amber)}
.stat b{display:block;font-size:1.75rem;font-weight:900;line-height:1;
letter-spacing:-.8px;color:var(--text)}
.stat span{font-size:.72rem;color:var(--muted);font-weight:700;
text-transform:uppercase;letter-spacing:.06em;margin-top:.3rem;display:block}

/* ===== SECTIONS ===== */
h2.sec{font-size:.78rem;text-transform:uppercase;letter-spacing:.09em;
color:var(--muted);font-weight:700;margin:2.4rem 0 1rem;
display:flex;align-items:center;gap:.6rem}
h2.sec::after{content:'';flex:1;height:1px;background:var(--border)}
.badge-cat{display:inline-flex;align-items:center;gap:.4rem;background:var(--tint-blue);
color:var(--primary);padding:.3rem .85rem;border-radius:50px;font-size:.72rem;
font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-bottom:.7rem}
h1.body{font-size:clamp(1.6rem,3.2vw,2.2rem);font-weight:800;letter-spacing:-.7px;
margin:0 0 .5rem;color:var(--text);line-height:1.15}
.lede{color:var(--muted);font-size:1.02rem;max-width:64ch;margin:0}

/* ===== GRID + CARDS ===== */
.grid{display:grid;gap:1.25rem;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.card{background:#fff;border:1px solid var(--border);border-radius:var(--r);
padding:1.4rem 1.5rem;display:flex;flex-direction:column;gap:.5rem;
position:relative;overflow:hidden;transition:transform .3s,box-shadow .3s,border-color .3s}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;
background:linear-gradient(90deg,var(--primary),var(--secondary));opacity:0;
transition:opacity .3s}
.card:hover{transform:translateY(-6px);box-shadow:var(--shadow-lg);border-color:transparent}
.card:hover::before{opacity:1}
.card h3{margin:0;font-size:1.05rem;line-height:1.3;font-weight:700}
.card h3 a{color:var(--text)}
.card h3 a:hover{color:var(--primary)}
.card .meta{font-size:.85rem;color:var(--muted)}
.card .cat{font-size:.72rem;font-weight:700;color:var(--primary);
text-transform:uppercase;letter-spacing:.05em}
.card .acts{margin-top:auto;padding-top:.6rem;display:flex;flex-wrap:wrap;gap:1rem;
font-size:.85rem;font-weight:600}
.card .acts a{color:var(--primary)}
.card .acts a:hover{text-decoration:underline}

/* ===== TIER BADGES ===== */
.badge{display:inline-flex;align-items:center;gap:.35rem;font-size:.7rem;
font-weight:700;letter-spacing:.05em;padding:.28rem .7rem;border-radius:50px;
text-transform:uppercase}
.b-a{background:var(--tint-green);color:var(--accent-dark)}
.b-b{background:var(--tint-blue);color:var(--primary)}
.b-c{background:#f1f5f9;color:var(--muted)}

/* ===== HOURS ===== */
.hrs{font-size:.86rem;color:var(--muted)}
.hrs .row{display:flex;justify-content:space-between;gap:1rem;padding:.12rem 0}
.hrs .row.today{color:var(--primary);font-weight:700}
.hrs strong{color:var(--text);display:block;margin-bottom:.35rem;font-size:.8rem;
text-transform:uppercase;letter-spacing:.06em}
.notice{background:var(--tint-amber);border:1px solid #fde68a;border-radius:10px;
padding:.8rem 1rem;font-size:.84rem;color:#92400e;margin-top:.75rem;line-height:1.55}
.notice strong{color:#78350f}

/* ===== MAP ===== */
.map{width:100%;height:300px;border:0;border-radius:var(--r);display:block;
border:1px solid var(--border);box-shadow:var(--shadow-sm)}

/* ===== CTA ===== */
.cta{background:linear-gradient(135deg,var(--primary-darker) 0%,var(--primary-dark) 50%,
var(--primary) 100%);color:#fff;border-radius:var(--r);padding:2.6rem 2rem;
margin:3rem 0 1rem;text-align:center;position:relative;overflow:hidden}
.cta::before{content:'';position:absolute;width:420px;height:420px;border-radius:50%;
background:radial-gradient(circle,rgba(54,179,126,.16) 0%,transparent 70%);
top:-180px;right:-90px}
.cta>*{position:relative;z-index:2}
.cta h2{color:#fff;margin:0 0 .6rem;font-size:1.45rem;font-weight:800;
letter-spacing:-.4px}
.cta p{color:rgba(255,255,255,.75);margin:0 0 1.4rem;font-size:1rem}
.btn{display:inline-flex;align-items:center;gap:.5rem;background:#fff;
color:var(--primary);padding:.7rem 1.6rem;border-radius:var(--r-sm);font-weight:700;
font-size:.92rem;box-shadow:0 4px 20px rgba(0,0,0,.15);transition:transform .25s,
box-shadow .25s;letter-spacing:.01em}
.btn:hover{transform:translateY(-2px);box-shadow:0 8px 30px rgba(0,0,0,.22);
text-decoration:none}
.btn-2{background:rgba(255,255,255,.1);color:#fff;box-shadow:none;
border:1px solid rgba(255,255,255,.22)}
.btn-2:hover{background:rgba(255,255,255,.16)}

/* ===== FOOTER ===== */
footer.site{background:var(--footer);color:rgba(255,255,255,.5);
padding:2.6rem 0 1.6rem;margin-top:3.5rem}
.foot-grid{display:grid;grid-template-columns:1.6fr 1fr 1fr 1fr;gap:1.8rem}
.foot-brand h4{color:#fff;font-size:1.05rem;margin:0 0 .6rem;display:flex;
align-items:center;gap:.5rem}
.foot-brand .mark{width:26px;height:26px;border-radius:7px;display:grid;
place-items:center;background:linear-gradient(135deg,var(--primary),var(--secondary));
color:#fff;font-size:.8rem}
.foot-brand p{font-size:.85rem;line-height:1.65;margin:0}
.foot-col h5{color:#fff;font-size:.72rem;font-weight:700;text-transform:uppercase;
letter-spacing:.08em;margin:0 0 .9rem}
.foot-col a{display:block;color:rgba(255,255,255,.5);font-size:.85rem;
padding:.22rem 0;transition:color .2s}
.foot-col a:hover{color:#fff}
.foot-bottom{margin-top:1.8rem;padding-top:1.3rem;
border-top:1px solid rgba(255,255,255,.08);display:flex;justify-content:space-between;
align-items:center;font-size:.78rem;gap:1rem;flex-wrap:wrap}

.empty{color:var(--muted);padding:2rem 0;font-size:.95rem}
.sib{background:#fff;border:1px solid var(--border);border-radius:var(--r);
padding:1.1rem 1.3rem;margin-bottom:.7rem;transition:all .3s}
.sib:hover{box-shadow:var(--shadow-md);transform:translateX(3px)}
.sib h3{margin:0 0 .25rem;font-size:1rem}
.sib h3 a{color:var(--text)}
.sib h3 a:hover{color:var(--primary)}
.sib .meta{font-size:.84rem;color:var(--muted)}

/* ===== RESPONSIVE ===== */
@media(max-width:900px){
.stats{grid-template-columns:repeat(2,1fr)}
.foot-grid{grid-template-columns:1fr 1fr}
}
@media(max-width:720px){
nav.site{gap:1rem}
nav.site a:not(.nav-cta){display:none}
.wrap{padding:0 1.25rem}
.grid{grid-template-columns:1fr}
.foot-grid{grid-template-columns:1fr}
.foot-bottom{flex-direction:column;text-align:center}
.hero{padding:3.2rem 0 3rem}
}
@media(max-width:480px){
.stats{grid-template-columns:1fr}
.btn{width:100%;max-width:290px;justify-content:center}
}
@media(prefers-reduced-motion:reduce){
*{animation:none!important;transition:none!important}
html{scroll-behavior:auto}
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
            '<div class="notice"><strong>Typical hours, not confirmed.</strong> '
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
<a class="brand" href="{SITE_URL}/"><span class="mark">SI</span>
<span>Sandton <b>Index</b></span></a>
<nav class="site">
<a href="{SITE_URL}/">Home</a>
<a href="{SITE_URL}/categories/">Categories</a>
<a href="{SITE_URL}/zones/">Suburbs</a>
<a class="nav-cta" href="{SITE_URL}/needs-a-website/">Get listed free</a>
</nav></div></header>"""


def footer_html():
    return f"""<footer class="site"><div class="wrap">
<div class="foot-grid">
<div class="foot-brand">
<h4><span class="mark">SI</span> Sandton Index</h4>
<p>A directory of businesses across Sandton, Johannesburg &mdash; opening
hours, directions and contact details, on one map.</p>
</div>
<div class="foot-col">
<h5>Browse</h5>
<a href="{SITE_URL}/categories/">All categories</a>
<a href="{SITE_URL}/zones/">All suburbs</a>
<a href="{SITE_URL}/supermarkets/">Supermarkets</a>
<a href="{SITE_URL}/restaurants-takeaways/">Restaurants</a>
</div>
<div class="foot-col">
<h5>For business</h5>
<a href="{SITE_URL}/needs-a-website/">Get a free listing</a>
<a href="{SITE_URL}/hours-not-published/">Publish your hours</a>
</div>
<div class="foot-col">
<h5>Sandton</h5>
<a href="{SITE_URL}/zones/sandton-cbd/">Sandton CBD</a>
<a href="{SITE_URL}/zones/rivonia-strip/">Rivonia</a>
<a href="{SITE_URL}/zones/illovo/">Illovo</a>
<a href="{SITE_URL}/zones/sunninghill/">Sunninghill</a>
</div>
</div>
<div class="foot-bottom">
<span>&copy; 2026 Sandton Index. Map data &copy; OpenStreetMap contributors.</span>
<span>Hours are indicative &mdash; confirm before travelling.</span>
</div>
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
<meta name="theme-color" content="#0052cc">
<meta name="geo.region" content="ZA-GT">
<meta name="geo.placename" content="Sandton, Johannesburg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap">
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
<div class="cat">{e(rec['hub_title'])}</div>
<h3><a href="{SITE_URL}/{e(rec['path'])}/">{e(rec['name'])}</a></h3>
<div class="meta">{e(rec['zone_display'])} &middot; {e(address_text(rec))}</div>
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
        facts.append(f"{no_site} have no website yet")
    if no_hours:
        facts.append(f"{no_hours} have no published hours")

    fact_html = (" " + " and ".join(facts) + ".") if facts else ""

    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="crumb"><a href="{SITE_URL}/">Home</a> /
<a href="{SITE_URL}/categories/">Categories</a> / {e(hub['title'])}</div>
<div class="hero-eyebrow"><span class="dot"></span>
{len(recs)} listings near {e(landmark)}</div>
<h1>{e(hub['title'])}<br>in <span class="grad">{e(zone_display)}</span></h1>
<p>Every {e(hub['singular'])} in {e(zone_display)}, Sandton, with opening
hours, directions and contact details.{fact_html}</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3">
<div class="stats">
<div class="stat"><div class="stat-ico ico-blue">&#127978;</div>
<b>{len(recs)}</b><span>Listings here</span></div>
<div class="stat"><div class="stat-ico ico-green">&#128205;</div>
<b>{sum(1 for r in recs if r.get('phone'))}</b><span>With phone</span></div>
<div class="stat"><div class="stat-ico ico-teal">&#128337;</div>
<b>{sum(1 for r in recs if r.get('opening_hours'))}</b><span>Hours listed</span></div>
<div class="stat"><div class="stat-ico ico-amber">&#9889;</div>
<b>{no_site}</b><span>No website</span></div>
</div>
<h2 class="sec">All {len(recs)} in {e(zone_display)}</h2>
<div class="grid">{cards}</div>
<div class="cta">
<h2>Running a {e(hub['singular'])} in {e(zone_display)}?</h2>
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
<a class="btn" href="{SITE_URL}/needs-a-website/?b={e(rec['id'])}">Claim this listing</a>
</div>"""
    else:
        claim = f"""<div class="cta">
<h2>Found a mistake in these details?</h2>
<p>Hours, address or phone out of date? Claim the listing to correct it
&mdash; accurate details are what local search rewards.</p>
<a class="btn" href="{SITE_URL}/needs-a-website/?b={e(rec['id'])}">Update these details</a>
</div>"""

    sib_html = ""
    if siblings:
        items = "".join(f"""<div class="sib">
<h3><a href="{SITE_URL}/{e(s['path'])}/">{e(s['name'])}</a></h3>
<div class="meta">{e(s['zone_display'])} &middot;
{e(s.get('street_address') or address_text(s))}</div>
</div>""" for s in siblings)
        label = ("Other branches" if len(siblings) > 1 else "Nearby")
        sib_html = f"""<h2 class="sec">{e(label)} of {e(rec['brand_slug'].replace('-', ' '))}</h2>
{items}"""

    hz = hub_zone_url(rec)
    crumb_hub = (f'<a href="{e(hz)}">{e(hub["title"])}</a>' if hz
                 else f'<a href="{SITE_URL}/{e(rec["hub"])}/">{e(hub["title"])}</a>')

    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="crumb"><a href="{SITE_URL}/">Home</a> /
{crumb_hub} / {e(rec['name'])}</div>
<div class="hero-eyebrow"><span class="dot"></span>
{e(rec['hub_title'])} &middot; {e(rec['zone_display'])}</div>
<h1>{e(rec['name'])}</h1>
<p>{e(address_text(rec))}, Sandton, Johannesburg.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<div style="margin-bottom:1.4rem">{tier_badge(rec)}</div>
<div class="grid" style="grid-template-columns:1fr 1fr;align-items:start">
<div>
<h2 class="sec">Details</h2>
<p><strong>Address</strong><br>{e(address_text(rec))}<br>Sandton,
{('2196' if rec.get('postcode') else 'Johannesburg, Gauteng')}, South Africa</p>
<p><strong>Contact</strong><br>{contact}</p>
<h2 class="sec">Opening hours</h2>
{hours_block(rec)}
</div>
<div>
<h2 class="sec">Find it</h2>
<iframe class="map" title="Map showing {e(rec['name'])}"
src="{maps_embed_url(rec)}" loading="lazy"
referrerpolicy="no-referrer-when-downgrade"></iframe>
<p style="font-size:.85rem;color:var(--muted);margin-top:.9rem">
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
<div class="cat">{len(hubs_by_zone[z])} businesses</div>
<h3><a href="{SITE_URL}/zones/{e(z)}/">{e(z.replace('-', ' ').title())}</a></h3>
<div class="acts"><a href="{SITE_URL}/zones/{e(z)}/">Browse &rarr;</a></div>
</article>""" for z in zones)

    title = f"{SITE_NAME} | Every business in Sandton, Johannesburg"
    desc = SITE_DESCRIPTION
    cat_cards = "".join(
        f"""<article class="card">
<div class="cat">{sum(1 for r in records if r['hub'] == h['slug'])} listings</div>
<h3><a href="{SITE_URL}/{h['slug']}/">{e(h['title'])}</a></h3>
<div class="meta">{e(h['singular'].capitalize())} across Sandton</div>
<div class="acts"><a href="{SITE_URL}/{h['slug']}/">Browse &rarr;</a></div>
</article>""" for h in HUB_BY_SLUG.values()
        if any(r['hub'] == h['slug'] for r in records))

    with_phone = sum(1 for r in records if r.get('phone'))
    with_hours = sum(1 for r in records if r.get('opening_hours'))

    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> Sandton, Johannesburg</div>
<h1>Every business in Sandton,<br><span class="grad">on one map</span></h1>
<p>{total} businesses across {len(zones)} suburbs &mdash; opening hours,
directions and contact details. {no_site} have no website yet and can claim a
free page here.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<div class="stats">
<div class="stat"><div class="stat-ico ico-blue">&#127978;</div>
<b>{total}</b><span>Businesses</span></div>
<div class="stat"><div class="stat-ico ico-teal">&#128337;</div>
<b>{with_hours}</b><span>Hours listed</span></div>
<div class="stat"><div class="stat-ico ico-green">&#128222;</div>
<b>{with_phone}</b><span>With phone</span></div>
<div class="stat"><div class="stat-ico ico-amber">&#9889;</div>
<b>{no_site}</b><span>No website</span></div>
</div>
<h2 class="sec">Browse by suburb</h2>
<div class="grid">{zone_cards}</div>
<h2 class="sec">Browse by category</h2>
<div class="grid">
{cat_cards}
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
<div class="cat">{counts.get(h['slug'], 0)} listings</div>
<h3><a href="{SITE_URL}/{h['slug']}/">{e(h['title'])}</a></h3>
<div class="meta">{e(h['singular'].capitalize())} across Sandton</div>
<div class="acts"><a href="{SITE_URL}/{h['slug']}/">Browse &rarr;</a></div>
</article>""" for h in HUB_BY_SLUG.values() if counts.get(h["slug"], 0))

    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span>
{sum(counts.values())} listings</div>
<h1>Categories</h1>
<p>Every category of business listed in the Sandton Index. Pick a category,
then a suburb.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<h2 class="sec">All categories</h2>
<div class="grid">{cards}</div></div>"""
    write(os.path.join("categories", "index.html"),
          page(f"Categories | {SITE_NAME}",
               "Browse Sandton businesses by category.", body,
               f"{SITE_URL}/categories/"))


def build_hub_index(hub, zones, records):
    # Only list suburbs that earned their own page. A zone whose listing count
    # is below MIN_HUB_LISTINGS has no page to link to, and linking to a
    # non-existent near-me page would be a dead end for both crawler and user.
    cards = "".join(f"""<article class="card">
<div class="cat">{n} listings</div>
<h3><a href="{SITE_URL}/{e(hub['slug'])}/{e(z)}/">{e(label)}</a></h3>
<div class="meta">{e(hub['singular'].capitalize())} in {e(label)}</div>
<div class="acts"><a href="{SITE_URL}/{e(hub['slug'])}/{e(z)}/">Browse &rarr;</a></div>
</article>"""
                    for z, label, n in zones if n >= MIN_HUB_LISTINGS)
    if not cards:
        cards = ('<p class="empty">No suburb has enough listings yet for its '
                 'own page. Browse all listings by suburb instead.</p>')

    total = sum(c for _z, _l, c in zones)
    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="crumb"><a href="{SITE_URL}/">Home</a> /
<a href="{SITE_URL}/categories/">Categories</a></div>
<div class="hero-eyebrow"><span class="dot"></span> {total} listings in Sandton</div>
<h1>{e(hub['title'])}</h1>
<p>Pick your suburb to see {e(hub['singular'])} options near you.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<h2 class="sec">Choose a suburb</h2>
<div class="grid">{cards}</div></div>"""
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
    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="crumb"><a href="{SITE_URL}/">Home</a> /
<a href="{SITE_URL}/zones/">Suburbs</a></div>
<div class="hero-eyebrow"><span class="dot"></span> {len(recs)} businesses</div>
<h1>{e(label)}</h1>
<p>Every listed business in {e(label)}, Sandton, grouped by category.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
{groups}</div>"""
    write(os.path.join("zones", zone_key, "index.html"),
          page(f"{label} businesses | {SITE_NAME}",
               f"Every listed business in {label}, Sandton, Johannesburg.",
               body, f"{SITE_URL}/zones/{zone_key}/"))


def build_zone_index_page(all_zones):
    cards = "".join(f"""<article class="card">
<div class="cat">{n} businesses</div>
<h3><a href="{SITE_URL}/zones/{e(z)}/">{e(label)}</a></h3>
<div class="acts"><a href="{SITE_URL}/zones/{e(z)}/">Browse &rarr;</a></div>
</article>"""
                    for z, label, n in all_zones)
    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span>
{sum(c for _z, _l, c in all_zones)} businesses</div>
<h1>Sandton suburbs</h1>
<p>Browse the index by area.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<div class="grid">{cards}</div></div>"""
    write(os.path.join("zones", "index.html"),
          page(f"Suburbs | {SITE_NAME}",
               "Browse the Sandton Index by suburb.", body,
               f"{SITE_URL}/zones/"))


def build_landing(records, slug, heading, blurb, cta_label, rows=()):
    tier_a = [r for r in records if r["tier"] == "A"]
    if slug == "needs-a-website":
        extra_rows = "".join(
            f"""<div class="sib">
<h3><a href="{SITE_URL}/{e(r['path'])}/">{e(r['name'])}</a></h3>
<div class="meta">{e(r['hub_title'])} &middot; {e(r['zone_display'])}</div>
</div>""" for r in rows)
        body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> Free, no obligation</div>
<h1>Get a free page for<br><span class="grad">your Sandton business</span></h1>
<p>{e(blurb)}</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<div class="cta" style="margin-top:0">
<h2>{len(tier_a)} Sandton businesses have no website yet</h2>
<p>If that is you, a page with your hours, map, phone and directions costs you
nothing. It is the minimum for showing up when someone searches for what you
do.</p>
<a class="btn" href="mailto:hello@{SITE_URL.split('//')[1]}?subject=Claim%20my%20Sandton%20listing">{e(cta_label)}</a>
</div>
<h2 class="sec">Businesses looking for a page</h2>
{extra_rows}
</div>"""
    else:
        extra_rows = "".join(
            f"""<div class="sib">
<h3><a href="{SITE_URL}/{e(r['path'])}/">{e(r['name'])}</a></h3>
<div class="meta">{e(r['hub_title'])} &middot; {e(r['zone_display'])}</div>
</div>""" for r in rows)
        body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> Opening hours matter</div>
<h1>{e(heading)}</h1>
<p>{e(blurb)}</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<h2 class="sec">Listings missing hours</h2>
{extra_rows}
</div>"""
    write(os.path.join(slug, "index.html"),
          page(f"{heading} | {SITE_NAME}", blurb, body, f"{SITE_URL}/{slug}/"))


# ---------------------------------------------------------------- sitemap
def build_sitemap(paths):
    """Emit clean directory URLs.

    Pages are written as <dir>/index.html, but every canonical tag and
    internal link uses the directory form, so the sitemap must match.
    Listing /shop/index.html alongside a canonical of /shop/ asks a search
    engine to treat two URLs as one page, which is exactly the duplicate
    this index must avoid.
    """
    urls = []
    for p in paths:
        if p == "index.html":
            urls.append(f"{SITE_URL}/")
            continue
        clean = p[:-len("index.html")] if p.endswith("index.html") else p
        urls.append(f"{SITE_URL}/{clean}")
    body = "".join(f"<url><loc>{e(u)}</loc></url>" for u in sorted(set(urls)))
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f"{body}\n</urlset>\n")
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
        rows=sorted(unreviewed, key=lambda x: x["name"])[:60])

    build_landing(
        records, "hours-not-published",
        "Businesses with no published opening hours",
        "Being open when someone searches is now a confirmed local ranking "
        "factor. These listings have no hours yet.",
        "Add your hours",
        rows=sorted(no_hours, key=lambda x: x["name"])[:60])

    print(f"  landings       : 2 (needs-a-website, hours-not-published)")

    # 5. 404 + robots
    write("404.html", page(
        "Page not found | Sandton Index",
        "That page does not exist.",
        f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> 404</div>
<h1>Page not found</h1>
<p>That page is not in the index. Try the <a href="{SITE_URL}/">homepage</a>
or browse <a href="{SITE_URL}/categories/">by category</a>.</p>
</div></div>""",
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
