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
import math
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (  # noqa: E402
    DATA,
    GOOGLE_SITE_VERIFICATION,
    HUB_BY_SLUG,
    MIN_HUB_LISTINGS,
    SITE,
    SITE_DESCRIPTION,
    SITE_NAME,
    SITE_URL,
    slugify,
)
from data_overlay import enrich_record, hours_in_schema, load_overlay  # noqa
from page_modules import (  # noqa: E402
    coupon_module,
    coupon_strip,
    maps_readiness_module,
    schema_breadcrumbs,
    schema_coupon,
    schema_faq,
    dow_health_module,
    open_status_pill,
    property_portal_module,
    rating_badge,
    schema_local_business,
    schema_site,
    schema_faq_hub,
    schema_itemlist,
)
from seo_content import seo_for  # noqa: E402

DAY_LABELS = [
    ("monday", "Monday"), ("tuesday", "Tuesday"), ("wednesday", "Wednesday"),
    ("thursday", "Thursday"), ("friday", "Friday"), ("saturday", "Saturday"),
    ("sunday", "Sunday"),
]

# Enrichment sidecar, loaded once.
#
# Optional by design: the Maps API is quota-metered and can be absent,
# exhausted or mid-refresh. When data/google.json is missing or unreadable
# this is simply {}, every record falls back to its OSM hours or the category
# default, and the site builds exactly as it did before enrichment existed.
# No provider is allowed to be a single point of failure.
OVERLAY = load_overlay(DATA)

# Intent cluster assignment, produced by 11_intent_engine.py.
#
# Also optional. Without it every record falls back to no cluster, which
# simply means no DOW module and no property portal -- a plainer page, never a
# broken one. Same rule as the overlay: no single enrichment step is allowed
# to be a hard dependency of the build.
INTENT = load_overlay(DATA, "intent.json")

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
--r:16px;--r-lg:20px;--r-sm:12px;--r-xs:8px;
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
 justify-content:space-between;height:66px;position:relative}
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
/* buildings below the substance bar: named, mapped, but no page of their own */
.card .thin{color:var(--muted);font-weight:500;font-size:.82rem}

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

/* ===== BUSINESS PAGE ===== */
.hero-actions{display:flex;flex-wrap:wrap;gap:.7rem;margin-top:1.5rem}
.biz{padding-top:2rem;padding-bottom:3rem}
.biz-grid{display:grid;grid-template-columns:1fr 1fr;gap:2.2rem;
 align-items:start;margin-bottom:2.5rem}
.biz-panel{background:#fff;border:1px solid var(--border);border-radius:var(--r);
 padding:1.6rem 1.8rem}
.small{font-size:.88rem;color:var(--muted);line-height:1.6}
.rate{display:inline-flex;align-items:baseline;gap:.4rem;background:var(--tint-amber);
 border:1px solid #f5e2b0;border-radius:99px;padding:.3rem .8rem;
 margin-left:.5rem;vertical-align:middle;white-space:nowrap}
.rate-stars{color:#f59e0b;font-size:.9rem;line-height:1}
.rate-num{font-weight:800;color:var(--text);font-size:.92rem}
.rate-rev{font-size:.78rem;color:var(--muted)}
.rate-src{font-size:.72rem;color:var(--muted);opacity:.85}
.kit-flag{display:block;font-size:.8rem;color:var(--muted);line-height:1.6;
 margin-top:.7rem;flex-basis:100%}
.conflict{background:#fff7ed;border:1px solid #fed7aa;border-radius:var(--r);
 padding:.7rem .9rem;font-size:.83rem;color:#7c2d12;line-height:1.6;
 margin-top:.9rem}

/* ===== LIVE STATUS PILL =====
   Rendered ONLY from scraped hours. No hours evidence, no pill. */
.pill{display:inline-flex;align-items:center;gap:.4rem;margin-left:.6rem;
 padding:.22rem .7rem;border-radius:99px;font-size:.72rem;font-weight:700;
 letter-spacing:.02em;vertical-align:middle;white-space:nowrap}
.pill .dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.pill-open{background:var(--tint-green);color:#0f5132;border:1px solid #bbf0d4}
.pill-open .dot{background:var(--accent-dark);animation:pulse 2s ease-in-out infinite}
.pill-closed{background:#f1f5f9;color:#475569;border:1px solid var(--border)}
.pill-closed .dot{background:#94a3b8}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}

/* ===== DOW HEALTH MODULE ===== */
.dow-card{margin:2.5rem 0;padding:1.8rem;border-radius:var(--r-lg);
 background:linear-gradient(150deg,#f0fdf4 0%,#e8f6f1 55%,#e6f4f7 100%);
 border:1px solid #c7ead9}
.dow-kicker{margin:0 0 .4rem;font-size:.68rem;text-transform:uppercase;
 letter-spacing:.12em;font-weight:800;color:var(--accent-dark)}
.dow-card .sec{margin:0 0 .6rem}
.dow-body{font-size:.92rem;line-height:1.7;color:var(--text);max-width:62ch;
 margin:0 0 1.1rem}
.dow-pending{background:#fffbeb;border:1px solid #fde68a;border-radius:var(--r-sm);
 padding:.6rem .8rem;font-size:.8rem;color:#78350f;line-height:1.6;
 margin:0 0 1.1rem;max-width:62ch}

/* ===== PROPERTY PORTAL ===== */
.portal{margin:2.5rem 0;padding:1.8rem;border-radius:var(--r-lg);
 background:var(--tint_blue);border:1px solid #cfe0f7}
.portal .sec{margin-top:0}
.portal-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));
 gap:1.2rem}
.portal-block{background:#fff;border:1px solid #dbe9f6;border-radius:var(--r);
 padding:1.1rem 1.3rem}
.portal-block h3{margin:0 0 .5rem;font-size:.98rem;color:var(--primary-darker)}
.portal-list{list-style:none;padding:0;margin:0}
.portal-list li{display:flex;justify-content:space-between;gap:1rem;
 padding:.4rem 0;border-bottom:1px solid var(--light);font-size:.86rem}
.portal-list li:last-child{border-bottom:0}
.portal-list li span{color:var(--muted);font-size:.8rem;white-space:nowrap}
.chips{list-style:none;padding:0;margin:1rem 0;display:flex;flex-wrap:wrap;
 gap:.5rem}
.chips li a{display:inline-block;background:var(--light);border:1px solid var(--border);
 color:var(--primary-dark);padding:.4rem .85rem;border-radius:99px;
 font-size:.85rem;font-weight:600;transition:all .2s}
.chips li a:hover{background:var(--primary);color:#fff;border-color:var(--primary)}
.nearme{margin-top:.9rem;font-size:.86rem;color:rgba(255,255,255,.78);
 font-weight:500}
.nearme::before{content:"\1F4CD ";opacity:.9}
.faqs{display:grid;gap:.6rem;max-width:820px}
details.faq{background:#fff;border:1px solid var(--border);border-radius:var(--r);
 padding:.9rem 1.2rem}
details.faq summary{font-weight:600;cursor:pointer;font-size:.95rem;
 list-style:none;position:relative;padding-right:1.6rem}
details.faq summary::-webkit-details-marker{display:none}
details.faq summary::after{content:"+";position:absolute;right:0;top:0;
 color:var(--primary);font-weight:700;font-size:1.2rem;line-height:1.1}
details.faq[open] summary::after{content:"\2212"}
details.faq p{margin:.7rem 0 0;font-size:.9rem;color:var(--muted);line-height:1.65}

/* ===== GOOGLE MAPS KIT ===== */
.maps-kit{margin:3rem 0;padding:2.2rem;border-radius:var(--r-lg);
 background:linear-gradient(160deg,#f0f7ff 0%,#e6f4f7 100%);
 border:1px solid #cfe3f5}
.maps-kit .sec{margin-top:0}
.kit-lead{font-size:1rem;color:var(--text);max-width:64ch;margin:0 0 1.6rem}
.kit-grid{display:grid;grid-template-columns:1fr 1fr;gap:1.4rem}
.kit-card{background:#fff;border:1px solid #dbe9f6;border-radius:var(--r);
 padding:1.3rem 1.5rem}
.kit-card h3{margin:0 0 .5rem;font-size:1rem;color:var(--primary-darker)}
.kit-note{font-size:.83rem;color:var(--muted);line-height:1.6;margin:0 0 .8rem}
.kit-pick{background:var(--primary);color:#fff;padding:.6rem .9rem;
 border-radius:var(--r-sm);font-weight:700;font-size:.92rem;margin:0 0 .9rem}
.kit-pick span{display:block;font-size:.68rem;text-transform:uppercase;
 letter-spacing:.09em;opacity:.82;font-weight:700}
.kit-extra-label{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;
 color:var(--muted);font-weight:700;margin:0 0 .35rem}
.kit-extra{list-style:none;padding:0;margin:0}
.kit-extra li{font-size:.85rem;color:var(--text);padding:.16rem 0 .16rem .9rem;
 position:relative}
.kit-extra li::before{content:"";position:absolute;left:0;top:.62rem;width:4px;
 height:4px;border-radius:50%;background:var(--accent)}
.kit-nap{background:var(--light);border:1px dashed var(--border);padding:.7rem .9rem;
 border-radius:var(--r-sm);font-size:.86rem;line-height:1.6;margin:0 0 .9rem;
 user-select:all}
.kit-hours-label{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;
 color:var(--muted);font-weight:700;margin:0 0 .3rem}
.kit-hours{background:var(--light);border:1px dashed var(--border);padding:.7rem .9rem;
 border-radius:var(--r-sm);font-size:.83rem;line-height:1.85;margin:0 0 .8rem}
.kit-hours b{color:var(--primary-darker);min-width:4.4rem;display:inline-block}
.kit-cta{display:flex;flex-wrap:wrap;gap:.8rem;margin-top:1.5rem}
/* secondary/outline variant, always on a light surface */
.btn-2{background:#fff;color:var(--primary-dark);border:1px solid var(--primary)}
.btn-2:hover{background:var(--primary);color:#fff;border-color:var(--primary)}

/* ===== COUPON ===== */
.coupon{margin:3rem 0 0;padding:1.7rem;border-radius:var(--r-lg);
 background:linear-gradient(135deg,var(--primary-darker) 0%,var(--primary-dark) 55%,
 var(--primary) 100%);color:#fff}
.coupon-in{display:flex;align-items:center;gap:1.5rem;flex-wrap:wrap}
.coupon-mark{font-size:2.5rem;font-weight:900;line-height:1;flex-shrink:0;
 background:rgba(255,255,255,.13);padding:.9rem 1.1rem;border-radius:var(--r)}
.coupon-mark span{font-size:1.4rem;vertical-align:super}
.coupon-body{flex:1;min-width:250px}
.coupon-kicker{margin:0 0 .3rem;font-size:.68rem;text-transform:uppercase;
 letter-spacing:.12em;font-weight:700;color:var(--accent);opacity:.95}
.coupon-body h3{margin:0 0 .35rem;font-size:1.2rem;color:#fff}
.coupon-note{margin:0;font-size:.87rem;opacity:.9;line-height:1.6}
.coupon-code{background:rgba(255,255,255,.18);padding:.1rem .5rem;
 border-radius:4px;letter-spacing:.06em}
.coupon .btn{background:#fff;color:var(--primary-darker);flex-shrink:0}
.coupon .btn:hover{background:var(--accent);color:#fff}
.coupon-sm{padding:1.2rem 1.4rem;margin-top:2rem}
.coupon-sm .coupon-mark{font-size:1.8rem;padding:.7rem .85rem}
.coupon-sm .coupon-body h3{font-size:1.02rem}
.coupon-strip{background:var(--primary-darker);color:#fff;padding:.85rem 0;
 border-top:1px solid rgba(255,255,255,.12)}
.coupon-strip .wrap{display:flex;flex-wrap:wrap;align-items:center;gap:.7rem}
.coupon-strip-tag{background:var(--accent);color:#04241a;font-size:.62rem;
 text-transform:uppercase;letter-spacing:.11em;font-weight:800;padding:.24rem .5rem;
 border-radius:3px;flex-shrink:0}
.coupon-strip-offer{font-size:.88rem;font-weight:600}
.coupon-strip-code{font-size:.82rem;opacity:.8}
.coupon-strip-code b{background:rgba(255,255,255,.16);padding:.1rem .42rem;
 border-radius:3px;letter-spacing:.05em}
.coupon-strip-go{margin-left:auto;font-size:.82rem;font-weight:700;color:#fff;
 text-decoration:none;border-bottom:1px solid var(--accent);padding-bottom:1px;
 white-space:nowrap}
.coupon-strip-go:hover{color:var(--accent)}
@media(max-width:900px){.coupon-strip-go{margin-left:0}}

/* ===== RESPONSIVE ===== */
@media(max-width:900px){
.biz-grid,.kit-grid{grid-template-columns:1fr}
.coupon-in{flex-direction:column;align-items:flex-start}
.coupon .btn{width:100%}
}
.foot-grid{grid-template-columns:1fr 1fr}
}
@media(max-width:720px){
nav.site{gap:.8rem}
nav.site a:not(.nav-cta){display:none}
nav.site.open{display:flex;flex-direction:column;align-items:stretch;gap:0;
 position:absolute;top:66px;left:0;right:0;background:#fff;
 border-bottom:1px solid var(--border);box-shadow:var(--shadow-md);padding:.5rem}
nav.site.open a:not(.nav-cta){display:block;padding:.75rem 1.25rem;color:var(--text);
 font-size:.95rem}
nav.site.open a:not(.nav-cta):hover{background:var(--light);color:var(--primary)}
.nav-toggle{display:block}
.wrap{padding:0 1.25rem}
.grid{grid-template-columns:1fr}
.foot-grid{grid-template-columns:1fr}
.foot-bottom{flex-direction:column;text-align:center}
.hero{padding:3.2rem 0 3rem}
}
@media(max-width:480px){
.stats{grid-template-columns:1fr}
.btn{width:100%;max-width:290px;justify-content:center}
nav.site .nav-cta{padding:.45rem .85rem;font-size:.85rem}
.finder{padding:.6rem .75rem}
}
/* ===== MOBILE NAV TOGGLE =====
   Previously every nav link was display:none under 720px, leaving a header
   with a single orphaned button and no way to reach Categories or Suburbs. */
.nav-toggle{display:none;background:transparent;border:1px solid var(--border);
 border-radius:var(--r-xs);padding:.4rem .55rem;cursor:pointer;line-height:0;
 color:var(--text)}
.nav-toggle span,.nav-toggle span::before,.nav-toggle span::after{display:block;
 width:19px;height:2px;background:currentColor;border-radius:2px;
 transition:transform .25s,opacity .2s}
.nav-toggle span::before{content:'';transform:translateY(-6px)}
.nav-toggle span::after{content:'';transform:translateY(4px)}
.nav-toggle[aria-expanded="true"] span{background:transparent}
.nav-toggle[aria-expanded="true"] span::before{transform:rotate(45deg)}
.nav-toggle[aria-expanded="true"] span::after{transform:rotate(-45deg)}

/* ===== FINDER (client-side filter) =====
   Progressive enhancement only. Every card is server-rendered and visible
   with JS off; the script merely hides non-matching cards. */
.finder{display:flex;flex-wrap:wrap;align-items:center;gap:.8rem;margin:0 0 1.4rem;
 background:#fff;border:1px solid var(--border);border-radius:var(--r);
 padding:.7rem .9rem;box-shadow:var(--shadow-sm);position:relative;z-index:3}
.finder input[type=search]{flex:1;min-width:220px;border:0;outline:0;font:inherit;
 font-size:.98rem;color:var(--text);background:transparent;padding:.35rem .2rem}
.finder input[type=search]::-webkit-search-cancel-button{cursor:pointer}
.si-count{font-size:.8rem;color:var(--muted);font-weight:600;white-space:nowrap}
.si-none{background:var(--tint-amber);border:1px solid #fde68a;border-radius:10px;
 padding:.5rem .8rem;font-size:.85rem;color:#92400e;line-height:1.6;flex-basis:100%}
/* display:grid and display:flex both beat the UA [hidden] rule, so an
   emptied section would stay visible without these two lines */
.grid[hidden],h2.sec[hidden]{display:none}

@media(prefers-reduced-motion:reduce){
 *{animation:none!important;transition:none!important}
 .nav-toggle span,.nav-toggle span::before,.nav-toggle span::after{transition:none}
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


GENERIC_BUILDING_NAMES = {
    "commercial", "office", "retail", "industrial", "shop", "store",
    "unit", "building", "premises", "vacant",
}


def address_text(rec):
    """Full postal address: building, street, suburb, postcode.

    Components are de-duplicated by containment, not just by equality.
    street_address is frequently the bare suburb ("Sandton") while
    zone_display is the fuller form ("Sandton CBD"), and an exact-match dedupe
    leaves "Sandton, Sandton CBD, 2196" on the page.
    """
    out = []
    zone = (rec.get("zone_display") or "").strip()
    street = (rec.get("street_address") or "").strip()
    # street_address sometimes arrives as a full compound line that already
    # ends in the suburb ("138, Rivonia Road, Sandton, Sandton CBD"). The zone
    # is appended again below, so trim it off the street first.
    if zone and street.lower().endswith(zone.lower()):
        street = street[:len(street) - len(zone)].rstrip(" ,")
    # ...and then a trailing city/region token. The zone is more specific than
    # the city, so repeating it ("Rivonia Road, Sandton, Sandton CBD") is noise.
    if zone:
        parts = [x.strip() for x in street.split(",") if x.strip()]
        while parts and parts[-1].lower() in {"sandton", "johannesburg",
                                             "gauteng", "south africa"}:
            parts.pop()
        street = ", ".join(parts)
    for p in [rec.get("building_name", ""), street, zone]:
        p = (p or "").strip()
        # building_name often just repeats the trading name in this dataset,
        # and is sometimes a bare type word from the source column
        if not p or p.lower() == rec.get("name", "").lower():
            continue
        if p.lower() in GENERIC_BUILDING_NAMES:
            continue
        if any(p.lower() == q.lower() for q in out):
            continue
        # drop a component already named inside a longer one
        if any(p.lower() in q.lower() for q in out):
            continue
        # and drop a longer component that only adds a suffix already present
        if any(q.lower() in p.lower() for q in out):
            out = [q for q in out if q.lower() not in p.lower()]
        out.append(p)
    postcode = (rec.get("postcode") or "").strip()
    if postcode and postcode not in out:
        out.append(postcode)
    return ", ".join(out) or "Sandton, Johannesburg"


def street_line(rec):
    """The part of the address that adds information beyond the suburb.

    address_text() deliberately returns the full postal address, because the
    business page needs every component. On a listing card, though, that
    renders as "Sandton CBD · Sandton CBD, 2196" -- the suburb is already on
    the left of the separator, so it is repeated on the right. This returns
    only the street-level components, or "" when there are none.
    """
    zone = (rec.get("zone_display") or "").strip().lower()
    postcode = (rec.get("postcode") or "").strip()
    out = []
    for p in (rec.get("building_name", ""), rec.get("street_address", "")):
        p = (p or "").strip()
        if not p or p == postcode:
            continue
        if p.lower() == rec.get("name", "").lower():
            continue
        if p.lower() in GENERIC_BUILDING_NAMES:
            continue
        # a component that is just the suburb, or already names the suburb,
        # adds nothing next to it
        # skip if the component is just the suburb, or the two name each other
        if zone and (p.lower() in zone or zone in p.lower()):
            continue
        if p.lower() == zone:
            continue
        # drop a trailing city/region token -- the caller already shows the
        # suburb, and "Rivonia Road, Sandton, Sandton CBD" reads as a mistake
        segs = [x.strip() for x in p.split(",") if x.strip()]
        while segs and segs[-1].lower() in {"sandton", "johannesburg",
                                           "gauteng", "south africa"}:
            segs.pop()
        p = ", ".join(segs)
        if not p:
            continue
        if p not in out:
            out.append(p)
    return ", ".join(out)


def hours_block(rec, compact=False, enriched=None):
    """Render opening hours with an explicit confidence treatment.

    Scraped hours are shown as fact. Google hours carry a caveat because they
    are a third-party copy. Inferred hours carry the strongest warning,
    because printing a guess in the same visual weight as verified
    information is how a directory ends up sending customers to a closed door.
    """
    enriched = enriched or enrich_record(rec, {})
    days = enriched["hours"]
    confidence = enriched["confidence"]

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
    elif confidence == "google" and not compact:
        # Google's copy of the owner's published hours. Better than our guess,
        # but it is a third-party snapshot that can be months out of date, so
        # it is presented as "as listed on Google" and still worth confirming.
        out.append(
            '<div class="notice"><strong>As listed on Google, not confirmed '
            'directly.</strong> These are the hours this business publishes on '
            'its Google profile. They can go out of date, so call ahead if it '
            'matters &mdash; and if they are wrong, claim the listing to fix '
            'them.</div>'
        )
    return "".join(out)


def nearest_day_text(rec):
    """'Open today until 17:00' for the meta description.

    Only built from a scraped schedule. An inferred schedule is a guess, and
    a guess about whether a real business is open right now would be wrong
    often enough to be a bad trade even in a meta tag.
    """
    days = rec.get("opening_hours")
    if not days or rec.get("hours_confidence") != "scraped":
        return ""
    key = ["monday", "tuesday", "wednesday", "thursday", "friday",
           "saturday", "sunday"][datetime.now().weekday()]
    span = days.get(key)
    if not span or "-" not in span:
        return ""
    return f"until {span.split('-', 1)[1]}"


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


def finder_html(scope, placeholder, target=""):
    """Client-side filter over the .grid .card list already in the markup.

    Progressive enhancement, not a replacement: every card is server-rendered
    and readable with scripting off, so crawlers and no-JS visitors get the
    full list. The script in page() only toggles display on the same nodes.

    `target` scopes the filter to one grid by id. Pages holding two separate
    grids (home: suburbs then categories) pass their id, so typing filters the
    list the visitor is actually looking at rather than every card on the page.
    """
    return f"""<div class="finder">
<input type="search" class="si-q" data-target="{e(target)}"
 placeholder="{e(placeholder)}" aria-label="{e(scope)}">
<span class="si-count" aria-live="polite"></span>
<span class="si-none" hidden>No listings match that. Try a shorter word, or
<a href="{SITE_URL}/categories/">browse every category</a>.</span>
</div>"""


def tier_badge(rec):
    tier = rec.get("tier", "C")
    label = {"A": "No website yet", "B": "Chain location",
             "C": "Has website"}.get(tier, "")
    return f'<span class="badge b-{tier.lower()}">{e(label)}</span>'


def header_html():
    return f"""<header class="site"><div class="wrap">
<a class="brand" href="{SITE_URL}/"><span class="mark">SI</span>
<span>Sandton <b>Index</b></span></a>
<nav class="site" id="si-nav">
<a href="{SITE_URL}/">Home</a>
<a href="{SITE_URL}/categories/">Categories</a>
<a href="{SITE_URL}/zones/">Suburbs</a>
<a href="{SITE_URL}/intents/">Near me</a>
<a class="nav-cta" href="{SITE_URL}/needs-a-website/">Get listed free</a>
</nav>
<button class="nav-toggle" id="si-nav-toggle" type="button"
 aria-expanded="false" aria-controls="si-nav" aria-label="Open menu">
<span></span></button>
</div></header>"""


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

SITE_JS = """
(function(){
var b=document.getElementById("si-nav-toggle");
if(b){
 var n=document.getElementById("si-nav");
 b.addEventListener("click",function(){
  var open=n.className.indexOf("open")>-1;
  n.className=open?"site":"site open";
  b.setAttribute("aria-expanded",open?"false":"true");
 });
}
function bind(input){
 var sel=input.getAttribute("data-target");
 var root=sel?document.getElementById(sel):document;
 if(!root)return;
 var cards=root.querySelectorAll(".card");
 var grids=root.querySelectorAll(".grid");
 var box=input.parentNode;
 var cnt=box.querySelector(".si-count");
 var hint=box.querySelector(".si-none");
 var run=function(){
  var s=input.value.trim().toLowerCase();
  var shown=0;
  for(var i=0;i<cards.length;i++){
   var hit=s===""||cards[i].textContent.toLowerCase().indexOf(s)>-1;
   cards[i].style.display=hit?"":"none";
   if(hit)shown=shown+1;
  }
  if(cnt)cnt.textContent=cards.length?shown+" of "+cards.length+" shown":"";
  if(hint)hint.hidden=shown!==0;
  for(var g=0;g<grids.length;g=g+1){
   var kids=grids[g].querySelectorAll(".card");
   var any=false;
   for(var k=0;k<kids.length;k=k+1){
    if(kids[k].style.display!=="none")any=true;
   }
   grids[g].hidden=!any;
   var hd=grids[g].previousElementSibling;
   if(hd&&hd.tagName==="H2")hd.hidden=!any;
  }
 };
 input.addEventListener("input",run);
 run();
}
var qs=document.querySelectorAll(".si-q");
for(var z=0;z<qs.length;z=z+1)bind(qs[z]);
})();
""".strip()


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
<meta name="google-site-verification" content="{e(GOOGLE_SITE_VERIFICATION)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap">
{extra_head}
<style>{CSS}</style>
</head>
<body>
{header_html()}
{body}
{coupon_strip()}
{footer_html()}
<script>{SITE_JS}</script>
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

    street = street_line(rec)
    meta = (f'{e(rec["zone_display"])} &middot; {e(street)}' if street
            else e(rec["zone_display"]))

    return f"""<article class="card">
<div class="cat">{e(rec['hub_title'])}</div>
<h3><a href="{SITE_URL}/{e(rec['path'])}/">{e(rec['name'])}</a></h3>
<div class="meta">{meta}</div>
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

    seo = seo_for(hub_slug)

    facts = []
    if no_site:
        facts.append(f"{no_site} have no website yet")
    if no_hours:
        facts.append(f"{no_hours} have no published hours")

    fact_html = (" " + " and ".join(facts) + ".") if facts else ""

    # "Near me" copy. Built from real landmarks around this specific hub and
    # zone rather than a generic template, because a page that reads the same
    # on every suburb is a page that ranks for nothing.
    nearby = " &middot; ".join(e(n) for n in seo["nearby"][:4])
    service_html = "".join(f"<li>{e(s)}</li>" for s in seo["services"])
    faq_html = "".join(f"""<details class="faq"><summary>{e(q)}</summary>
<p>{e(a)}</p></details>""" for q, a in seo["faqs"])

    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="crumb"><a href="{SITE_URL}/">Home</a> /
<a href="{SITE_URL}/categories/">Categories</a> / {e(hub['title'])}</div>
<div class="hero-eyebrow"><span class="dot"></span>
{len(recs)} listings near {e(landmark)}</div>
<h1>{e(hub['title'])}<br>in <span class="grad">{e(zone_display)}</span></h1>
<p>Every {e(hub['singular'])} in {e(zone_display)}, Sandton, with opening
hours, directions and contact details.{fact_html}</p>
<p class="nearme">Near {nearby} &mdash; covering {e(zone_display)},
{e(recs[0]['hub_title']) if recs else 'Sandton'} and the wider Sandton area.</p>
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
<h2 class="sec">What people look for here</h2>
<ul class="chips">{service_html}</ul>
<h2 class="sec">All {len(recs)} in {e(zone_display)}</h2>
{finder_html("Search " + hub["singular"] + " in " + zone_display,
             "Filter by business name")}
<div class="grid">{cards}</div>
<div class="cta">
<h2>Running a {e(hub['singular'])} in {e(zone_display)}?</h2>
<p>Claim your free listing with your real hours, photos and contact details.</p>
<a class="btn" href="{SITE_URL}/needs-a-website/">Get a free listing</a>
</div>
<h2 class="sec">Common questions</h2>
<div class="faqs">{faq_html}</div>
{coupon_module(compact=True)}
</div>"""

    write(os.path.join(hub_slug, zone_key, "index.html"),
          page(title, desc, body, canonical,
               extra_head=schema_itemlist(hub, zone_display, recs)
               + schema_faq_hub(hub_slug)
               + schema_coupon()))


# ---------------------------------------------------------------- business
def build_business_page(rec, siblings, zone_count=0):
    """Full landing page for one business.

    Section order is deliberate and follows how a local customer decides:

      1. hero      -- what this is, where it is
      2. actions   -- call / directions, above the fold, no scrolling
      3. details   -- address, phone, hours
      4. map       -- because "near me" is the whole intent
      5. services  -- what they actually do, so the page matches the search
      6. FAQ       -- the questions asked before choosing
      7. Maps kit  -- how to get on Google Maps, the highest-value action
      8. siblings  -- other branches
      9. claim     -- conversion for a tier-A owner
     10. coupon    -- cross-promotion, last so it never reads as the
                      listed business's own offer
    """
    hub = HUB_BY_SLUG.get(rec["hub"], {"title": "Sandton Business",
                                       "singular": "business"})
    seo = seo_for(rec["hub"])
    enriched = enrich_record(rec, OVERLAY)
    intent = INTENT.get(rec["id"]) or {}

    title = (f"{rec['name']} &mdash; {seo['gbp_category']} in "
             f"{rec['zone_display']}, Sandton | {SITE_NAME}")
    desc = (
        f"{rec['name']} is a {seo['gbp_category'].lower()} in "
        f"{rec['zone_display']}, Sandton, Johannesburg. "
        f"{'Open today ' + nearest_day_text(rec) + '. ' if rec.get('opening_hours') else ''}"
        f"Address, phone and directions. "
        f"{'No website listed yet. ' if rec['tier'] == 'A' else ''}"
    )[:300]
    canonical = f"{SITE_URL}/{rec['path']}/"

    # ---- action row: the only two things a visitor wants --------------
    # phone comes from the overlay, not the raw record: a Google-supplied
    # number is a real, dialable number for a business we otherwise list
    # with no contact details at all, which is the entire reason to harvest it
    phone = enriched.get("phone") or rec.get("phone") or ""
    actions = []
    if phone:
        actions.append(
            f'<a class="btn" href="tel:{e(phone.replace(" ", ""))}">'
            f'Call {e(phone)}</a>')
    actions.append(
        f'<a class="btn{" btn-2" if phone else ""}" '
        f'href="{maps_link(rec)}" target="_blank" rel="noopener">Directions</a>')
    if rec.get("website"):
        actions.append(f'<a class="btn btn-2" href="{e(rec["website"])}" '
                       f'target="_blank" rel="noopener">Visit website</a>')
    action_html = "".join(actions)

    bits = []
    if phone:
        bits.append(f'<a href="tel:{e(phone.replace(" ", ""))}">'
                    f'{e(phone)}</a>')
    bits.append(f'<a href="{maps_link(rec)}" target="_blank" rel="noopener">'
                f'Directions &amp; map</a>')
    if rec.get("website"):
        bits.append(f'<a href="{e(rec["website"])}" target="_blank" '
                    f'rel="noopener">Website</a>')
    contact = " &middot; ".join(bits)

    # Where a Google number disagrees with the one we already had, say so on
    # the page rather than silently picking one. A customer dialling the wrong
    # number reaches a different business, and the only person who can resolve
    # it is whoever reads this page.
    conflict_html = ""
    if enriched.get("phone_conflict"):
        alt = (OVERLAY.get(rec["id"]) or {}).get("google_phone", "")
        conflict_html = (
            '<p class="conflict"><strong>Number to check.</strong> Google '
            f'lists this business as {e(alt)}, which differs from the number '
            'above. If you are the owner, claim the listing to correct it.'
            '</p>')

    claim = (f"""<div class="cta">
<h2>Is this your business?</h2>
<p>You have no website of your own yet. Claim this free page and we will set
up your real details, photos and opening hours properly &mdash; at no cost.</p>
<a class="btn" href="{SITE_URL}/needs-a-website/?b={e(rec['id'])}">Claim this listing free</a>
</div>""" if rec["tier"] == "A" else f"""<div class="cta">
<h2>Found a mistake in these details?</h2>
<p>Hours, address or phone out of date? Claim the listing to correct it
&mdash; accurate details are what local search rewards.</p>
<a class="btn" href="{SITE_URL}/needs-a-website/?b={e(rec['id'])}">Update these details</a>
</div>""")

    # ---- services: makes the page match a real search query ----------
    service_html = "".join(
        f'<li><a href="{SITE_URL}/{e(rec["hub"])}/'
        f'{e(rec["zone"])}/">{e(s)}</a></li>' for s in seo["services"])

    # ---- FAQ ---------------------------------------------------------
    faq_html = "".join(
        f"""<details class="faq"><summary>{e(q)}</summary>
<p>{e(a)}</p></details>""" for q, a in seo["faqs"])

    sib_html = ""
    if siblings:
        items = "".join(f"""<div class="sib">
<h3><a href="{SITE_URL}/{e(s['path'])}/">{e(s['name'])}</a></h3>
<div class="meta">{e(s['zone_display'])} &middot;
{e(s.get('street_address') or address_text(s))}</div>
</div>""" for s in siblings)
        label = "Other branches" if len(siblings) > 1 else "Nearby"
        sib_html = f"""<h2 class="sec">{e(label)}</h2>{items}"""

    hz = hub_zone_url(rec)
    crumb_hub = (f'<a href="{e(hz)}">{e(hub["title"])}</a>' if hz
                 else f'<a href="{SITE_URL}/{e(rec["hub"])}/">{e(hub["title"])}</a>')

    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="crumb"><a href="{SITE_URL}/">Home</a> /
{crumb_hub} / {e(rec['name'])}</div>
<div class="hero-eyebrow"><span class="dot"></span>
{e(seo['gbp_category'])} &middot; {e(rec['zone_display'])}
{open_status_pill(rec, enriched)}</div>
<h1>{e(rec['name'])}</h1>
<p>{e(address_text(rec))}.</p>
<div class="hero-actions">{action_html}</div>
</div></div>
<div class="wrap biz">
<div style="margin-bottom:1.6rem">{tier_badge(rec)}{rating_badge(enriched)}</div>

<div class="biz-grid">
<section class="biz-panel">
<h2 class="sec">Contact &amp; details</h2>
<p><strong>Address</strong><br>{e(address_text(rec))}<br>
Gauteng, South Africa</p>
<p><strong>Contact</strong><br>{contact}</p>
{conflict_html}
<p><strong>Category</strong><br>{e(seo['gbp_category'])}</p>
<h2 class="sec">Opening hours</h2>
{hours_block(rec, enriched=enriched)}
</section>

<section class="biz-panel">
<h2 class="sec">Where to find it</h2>
<iframe class="map" title="Map showing {e(rec['name'])}"
src="{maps_embed_url(rec)}" loading="lazy"
referrerpolicy="no-referrer-when-downgrade"></iframe>
<p class="small"><a href="{maps_link(rec)}" target="_blank" rel="noopener">
Open in Google Maps</a> &mdash; search results for nearby customers are
decided on Google Maps, so a listing there matters more than any page here.</p>
</section>
</div>

<h2 class="sec">What {e(rec['name'])} does</h2>
<p class="small">A {e(seo['gbp_category'].lower())} in {e(rec['zone_display'])}
covering {e(', '.join(seo['nearby'][:3]))} and the wider Sandton area. Looking
for something specific nearby?</p>
<ul class="chips">{service_html}</ul>
<p class="small">More {e(seo['gbp_category'].lower())} options in
{e(rec['zone_display'])}: <a href="{SITE_URL}/{e(rec['hub'])}/{e(rec['zone'])}/">
see all {zone_count}
</a> &middot; <a href="{SITE_URL}/{e(rec['hub'])}/">all Sandton</a></p>

<h2 class="sec">Common questions</h2>
<div class="faqs">{faq_html}</div>

{maps_readiness_module(rec, street_line(rec), enriched)}
{property_portal_module(rec, siblings, intent.get('is_complex'))}
{dow_health_module(intent.get('cluster'))}
{sib_html}
{claim}
{coupon_module()}
</div>"""

    head = (schema_local_business(rec, enriched)
            + schema_breadcrumbs(rec, hub)
            + schema_faq(rec)
            + schema_coupon())

    write(os.path.join(rec["path"], "index.html"),
          page(title, desc, body, canonical, extra_head=head))


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
{finder_html("Search suburbs", "Filter by suburb name", "si-zone-grid")}
<div class="grid" id="si-zone-grid">{zone_cards}</div>
<h2 class="sec">Browse by category</h2>
{finder_html("Search categories", "Filter by category name", "si-cat-grid")}
<div class="grid" id="si-cat-grid">
{cat_cards}
</div>
<div class="cta">
<h2>No website? Get a free listing.</h2>
<p>Hours, map, phone and directions on a page of your own. Free.</p>
<a class="btn" href="{SITE_URL}/needs-a-website/">Claim your business</a>
</div>
</div>"""
    write("index.html", page(title, desc, body, f"{SITE_URL}/",
                           extra_head=schema_site()))


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
{finder_html("Search categories", "Filter by category name")}
<div class="grid">{cards}</div></div>"""
    write(os.path.join("categories", "index.html"),
          page(f"Categories | {SITE_NAME}",
               "Browse Sandton businesses by category.", body,
               f"{SITE_URL}/categories/",
               extra_head=schema_site()))


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
{finder_html("Search suburbs", "Filter by suburb name")}
<div class="grid">{cards}</div></div>"""
    write(os.path.join(hub["slug"], "index.html"),
          page(f"{hub['title']} in Sandton | {SITE_NAME}",
               f"{hub['title']} across Sandton, Johannesburg.", body,
               f"{SITE_URL}/{hub['slug']}/",
               extra_head=schema_site() + schema_coupon()))


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
{finder_html("Search listings in " + label, "Filter by business name")}
{groups}</div>"""
    write(os.path.join("zones", zone_key, "index.html"),
          page(f"{label} businesses | {SITE_NAME}",
               f"Every listed business in {label}, Sandton, Johannesburg.",
               body, f"{SITE_URL}/zones/{zone_key}/",
               extra_head=schema_site()))


def build_intent_indexes(records):
    """One index page per intent cluster, listing every record in it.

    Thin clusters are skipped rather than published. A page with three
    listings cannot compete for "dentist sandton" and only adds a URL to
    crawl, so anything below MIN_HUB_LISTINGS folds into the clusters that do
    have depth.
    """
    try:
        from importlib import util as _util
        spec = _util.spec_from_file_location(
            "intent_engine", os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "11_intent_engine.py"))
        mod = _util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        clusters = mod.CLUSTERS
    except Exception as exc:  # noqa: BLE001
        print(f"  intent engine unavailable ({exc}); skipping intent pages")
        return 0

    by_cluster = defaultdict(list)
    for r in records:
        slug = (INTENT.get(r["id"]) or {}).get("cluster")
        if slug:
            by_cluster[slug].append(r)

    built = 0
    for c in clusters:
        recs = by_cluster.get(c["slug"], [])
        if len(recs) < MIN_HUB_LISTINGS:
            continue

        recs = sorted(recs, key=lambda r: (
            bool(r.get("phone")), bool(r.get("lat")), r.get("name", "")))
        cards = "".join(business_card(r) for r in recs[:120])
        zones = sorted({r["zone_display"] for r in recs})
        zone_links = " &middot; ".join(
            f'<a href="{SITE_URL}/zones/">{e(z)}</a>' for z in zones[:8])

        # the hub pages that back this cluster, so the two taxonomies link
        hubs = sorted({r["hub_title"] for r in recs})
        hub_links = " &middot; ".join(
            f'<a href="{SITE_URL}/categories/">{e(h)}</a>' for h in hubs[:8])

        title = f"{c['title']} in Sandton | {SITE_NAME}"
        desc = (f"{len(recs)} {c['singular']} options across Sandton, "
                f"Johannesburg. {c['intent']}. Hours, directions and contact "
                f"details on one map.")

        body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="crumb"><a href="{SITE_URL}/">Home</a> /
<a href="{SITE_URL}/intents/">Intents</a> / {e(c['title'])}</div>
<div class="hero-eyebrow"><span class="dot"></span> {len(recs)} listings</div>
<h1>{e(c['title'])}<br>in <span class="grad">Sandton</span></h1>
<p>{e(c['intent'])}. Every listing here is a real business in the Sandton
cluster with its own page, hours and directions.</p>
<p class="nearme">Across {zone_links} &mdash; and the wider Sandton area.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3">
<div class="stats">
<div class="stat"><div class="stat-ico ico-blue">&#127978;</div>
<b>{len(recs)}</b><span>Listings</span></div>
<div class="stat"><div class="stat-ico ico-green">&#128205;</div>
<b>{sum(1 for r in recs if r.get('phone'))}</b><span>With phone</span></div>
<div class="stat"><div class="stat-ico ico-teal">&#128337;</div>
<b>{sum(1 for r in recs if r.get('opening_hours'))}</b><span>Hours listed</span></div>
<div class="stat"><div class="stat-ico ico-amber">&#9889;</div>
<b>{sum(1 for r in recs if r['tier'] == 'A')}</b><span>No website</span></div>
</div>
<h2 class="sec">All {len(recs)} {e(c['singular'])} options</h2>
{finder_html("Search " + c["title"], "Filter by name or category")}
<div class="grid">{cards}</div>
<h2 class="sec">Also browse by category</h2>
<p class="small">{hub_links}</p>
<div class="cta">
<h2>Missing from this list?</h2>
<p>If you run a {e(c['singular'])} in Sandton and are not listed, your free
page is already built. Claim it and your details go live.</p>
<a class="btn" href="{SITE_URL}/needs-a-website/">Get a free listing</a>
</div>
{coupon_module(compact=True)}
</div>"""

        write(os.path.join("intents", c["slug"], "index.html"),
              page(title, desc, body, f"{SITE_URL}/intents/{c['slug']}/",
                   extra_head=schema_itemlist(
                       {"title": c["title"], "slug": "intents"}, "Sandton",
                       recs) + schema_site()))
        built += 1

    # index of the clusters that earned a page
    live = [c for c in clusters
            if len(by_cluster.get(c["slug"], [])) >= MIN_HUB_LISTINGS]
    cards = "".join(f"""<article class="card">
<div class="cat">{len(by_cluster.get(c['slug'], []))} listings</div>
<h3><a href="{SITE_URL}/intents/{e(c['slug'])}/">{e(c['title'])}</a></h3>
<div class="meta">{e(c['intent'])}</div>
<div class="acts"><a href="{SITE_URL}/intents/{e(c['slug'])}/">Browse &rarr;</a></div>
</article>""" for c in sorted(live, key=lambda x: -len(by_cluster[x["slug"]])))

    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> Search intents</div>
<h1>What are you<br>looking for <span class="grad">near you</span>?</h1>
<p>The same businesses, grouped by what people actually type into Google at
the moment they need one. Pick the situation, not the category.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<h2 class="sec">All intents</h2>
{finder_html("Search intents", "Filter by what you need")}
<div class="grid">{cards}</div>
{coupon_module(compact=True)}
</div>"""
    write(os.path.join("intents", "index.html"),
          page(f"What are you looking for near you? | {SITE_NAME}",
               "Sandton businesses grouped by search intent: health, "
               "workplaces, housing, retail, trades and more.",
               body, f"{SITE_URL}/intents/", extra_head=schema_site()))
    return built


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
<h2 class="sec">All {sum(c for _z, _l, c in all_zones)} listings</h2>
{finder_html("Search suburbs", "Filter by suburb name")}
<div class="grid">{cards}</div></div>"""
    write(os.path.join("zones", "index.html"),
          page(f"Suburbs | {SITE_NAME}",
               "Browse the Sandton Index by suburb.", body,
               f"{SITE_URL}/zones/",
               extra_head=schema_site()))


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
{coupon_module(compact=True)}
</div>"""
    write(os.path.join(slug, "index.html"),
          page(f"{heading} | {SITE_NAME}", blurb, body, f"{SITE_URL}/{slug}/",
               extra_head=schema_site()))


# ---------------------------------------------------------------- properties
CLASS_LABEL = {
    "residential": "Residential",
    "commercial": "Commercial",
    "industrial": "Industrial",
}
CLASS_TITLE = {
    "residential": "Residential complex",
    "commercial": "Commercial building",
    "industrial": "Industrial building",
}


def _haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres."""
    p = math.radians
    dlat = p(lat2 - lat1)
    dlon = p(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(p(lat1)) * math.cos(p(lat2)) * math.sin(dlon / 2) ** 2)
    return 6371000 * 2 * math.asin(math.sqrt(a))


def load_properties(records, zone_labels):
    """Load OSM complexes and decide what each one is entitled to.

    Two decisions matter here, and both are about honesty rather than volume.

    Area. There is no polygon data for the suburbs, so a property cannot be
    placed by boundary. It is placed by proximity to the businesses already
    indexed: whichever zone's listings sit closest is the area. That is a real
    geographic fact, but it is an inference, so a property further than 1.5 km
    from any indexed business is given no area at all rather than a wrong one.

    Substance. A page carrying a name and nothing else is thin, and 168 of
    them would be padding. A property earns its own page only if OSM carries an
    address, or a storey count, or enough mapped businesses sit nearby to say
    something genuinely useful about where it is. The rest are listed on index
    pages and nowhere else.
    """
    path = os.path.join(DATA, "properties.json")
    if not os.path.exists(path):
        return []

    with open(path, encoding="utf-8") as fh:
        props = json.load(fh)["records"]

    pts = [(r["lat"], r["lon"], r) for r in records
           if r.get("lat") and r.get("lon")]

    used = {}
    for prop in props:
        base = slugify(prop["name"]) or "building"
        key = f"properties/{base}"
        n = used.get(key, 0)
        used[key] = n + 1
        prop["path"] = key if n == 0 else f"{key}-{n}"

        near = []
        if prop.get("lat") and prop.get("lon"):
            for lat, lon, rec in pts:
                d = _haversine_m(prop["lat"], prop["lon"], lat, lon)
                if d <= 1200:
                    near.append((d, rec))
        near.sort(key=lambda x: x[0])
        prop["nearby_businesses"] = [r for _d, r in near[:8]]
        prop["nearby_business_count"] = len(near)

        zone = zone_dist = None
        if near:
            zone, zone_dist = near[0][1]["zone"], near[0][0]
        if zone and zone_dist is not None and zone_dist <= 1500:
            prop["area"] = zone
            prop["area_display"] = zone_labels.get(
                zone, zone.replace("-", " ").title())
        else:
            prop["area"] = ""
            prop["area_display"] = "Sandton"

        prop["has_address"] = bool(prop.get("street_address"))
        prop["has_levels"] = prop.get("levels") is not None
        prop["gets_page"] = (prop["has_address"] or prop["has_levels"]
                             or prop["nearby_business_count"] >= 3)

    props.sort(key=lambda p: (not p["gets_page"], p["name"].lower()))
    return props


def maps_directions_for(prop):
    return ("https://www.google.com/maps/dir/?api=1&destination="
            f"{prop['lat']},{prop['lon']}")


def property_card(prop):
    """Card for a building on an index page.

    Only links to a details page when one exists. 105 of the 168 complexes
    do not clear the substance bar and have no page, so an unconditional
    "Details" link would emit 105 dead internal links -- which the broken
    link gate would (correctly) fail the build on.
    """
    bits = [prop["area_display"]]
    if prop.get("street_address"):
        bits.append(prop["street_address"])
    if prop.get("levels"):
        bits.append(f"{prop['levels']} "
                    f"{'storey' if prop['levels'] == 1 else 'storeys'}")
    acts = []
    if prop["gets_page"]:
        acts.append(f'<a href="{SITE_URL}/{e(prop["path"])}/">Details</a>')
    else:
        acts.append('<span class="thin">No detail page yet</span>')
    acts.append(f'<a href="{maps_directions_for(prop)}" target="_blank" '
                'rel="noopener">Directions</a>')
    heading = (f'<a href="{SITE_URL}/{e(prop["path"])}/">{e(prop["name"])}</a>'
               if prop["gets_page"] else e(prop["name"]))
    return f"""<article class="card">
<div class="cat">{e(CLASS_LABEL.get(prop['class'], prop['class']))}</div>
<h3>{heading}</h3>
<div class="meta">{e(' · '.join(bits))}</div>
<div class="acts">{' '.join(acts)}</div>
</article>"""


def build_property_pages(props, zone_labels):
    """Property index pages, near-me pages and individual building pages."""
    from property_schema import (  # noqa: PLC0415
        schema_breadcrumbs, schema_itemlist, schema_property)

    published = [p for p in props if p["gets_page"]]
    n_ind = 0

    by_class = defaultdict(list)
    for p in props:
        by_class[p["class"]].append(p)

    for prop in published:
        rows = ""
        if prop.get("street_address"):
            rows += (f"<p><strong>Address</strong><br>"
                     f"{e(prop['street_address'])}<br>Gauteng, South Africa</p>")
        if prop.get("levels") is not None:
            rows += (f"<p><strong>Storeys</strong><br>{prop['levels']} "
                     f"{'storey' if prop['levels'] == 1 else 'storeys'}</p>")
        if prop.get("website"):
            rows += ('<p><strong>Website</strong><br>'
                     f'<a href="{e(prop["website"])}" target="_blank" '
                     f'rel="noopener">{e(prop["website"])}</a></p>')
        rows += f"<p><strong>Area</strong><br>{e(prop['area_display'])}</p>"

        near_biz = ""
        if prop["nearby_businesses"]:
            items = "".join(
                f'<li><a href="{SITE_URL}/{e(r["path"])}/">{e(r["name"])}</a>'
                f'<span>{e(r["zone_display"])}</span></li>'
                for r in prop["nearby_businesses"])
            near_biz = f"""<div class="portal-block">
<h3>Businesses mapped nearby</h3>
<p class="small">Businesses the index has mapped within walking distance of
this building. They are not presented as tenants: whether any of them
actually occupies this property is not something open mapping data can
verify.</p>
<ul class="portal-list">{items}</ul></div>"""

        others = [p for p in published
                  if p["path"] != prop["path"]
                  and _haversine_m(prop["lat"], prop["lon"],
                                   p["lat"], p["lon"]) <= 900]
        near_prop = ""
        if others:
            items = "".join(
                f'<li><a href="{SITE_URL}/{e(p["path"])}/">{e(p["name"])}</a>'
                f'<span>{e(p["area_display"])}</span></li>'
                for p in others[:10])
            near_prop = f"""<div class="portal-block">
<h3>Other buildings nearby</h3>
<ul class="portal-list">{items}</ul></div>"""

        crumb = (f'<div class="crumb"><a href="{SITE_URL}/">Home</a> / '
                 f'<a href="{SITE_URL}/properties/">Properties</a> / '
                 f'<a href="{SITE_URL}/properties/{e(prop["class"])}/">'
                 f'{e(CLASS_LABEL.get(prop["class"], prop["class"]))}</a>'
                 f' / {e(prop["name"])}</div>')

        body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
{crumb}
<div class="hero-eyebrow"><span class="dot"></span>
{e(CLASS_LABEL.get(prop['class'], prop['class']))}</div>
<h1>{e(prop['name'])}</h1>
<p>{e(CLASS_TITLE.get(prop['class'], 'Building'))} in
{e(prop['area_display'])}, Johannesburg. Location, directions and what is
mapped nearby.</p>
</div></div>
<div class="wrap biz">
<div class="biz-grid">
<section class="biz-panel">
<h2 class="sec">Details</h2>
{rows}
<h2 class="sec">How this data is sourced</h2>
<p class="small">Building details are mapped from OpenStreetMap contributors
and may be incomplete or out of date. Unit numbers, occupancy, amenities and
leasing status are not published here because they cannot be verified from
open mapping data. If you manage this building,
<a href="{SITE_URL}/needs-a-website/">claim the listing</a> to correct or
extend it.</p>
</section>
<section class="biz-panel">
<h2 class="sec">Where to find it</h2>
<iframe class="map" title="Map showing {e(prop['name'])}"
 src="https://www.openstreetmap.org/export/embed.html?bbox={prop['lon']-0.004:.5f}%2C{prop['lat']-0.004:.5f}%2C{prop['lon']+0.004:.5f}%2C{prop['lat']+0.004:.5f}&amp;layer=mapnik&amp;marker={prop['lat']:.5f}%2C{prop['lon']:.5f}"
 loading="lazy"></iframe>
<p class="small"><a href="{maps_directions_for(prop)}" target="_blank"
 rel="noopener">Open directions in Google Maps</a></p>
</section>
</div>
<div class="portal">
<h2 class="sec">Around this building</h2>
<div class="portal-grid">
{near_biz}
{near_prop}
</div>
</div>
<div class="cta">
<h2>Do you manage {e(prop['name'])}?</h2>
<p>Claim this free listing to publish your own details, correct the mapped
information and add a tenant directory.</p>
<a class="btn" href="{SITE_URL}/needs-a-website/">Claim this property</a>
</div>
</div>"""

        trail = [
            ("Home", f"{SITE_URL}/"),
            ("Properties", f"{SITE_URL}/properties/"),
            (CLASS_LABEL.get(prop["class"], prop["class"]),
             f"{SITE_URL}/properties/{e(prop['class'])}/"),
            (prop["name"], f"{SITE_URL}/{e(prop['path'])}/"),
        ]
        desc = (f"{prop['name']} is a "
                f"{CLASS_TITLE.get(prop['class'], 'building')} in "
                f"{prop['area_display']}, Johannesburg. Location, directions "
                "and mapped businesses nearby.")
        write(os.path.join(prop["path"], "index.html"),
              page(f"{prop['name']} | {SITE_NAME}", desc, body,
                   f"{SITE_URL}/{e(prop['path'])}/",
                   extra_head=schema_breadcrumbs(trail)
                   + schema_property(prop) + schema_site()))
        n_ind += 1

    n_cls = 0
    for cls, plist in sorted(by_class.items()):
        plist = sorted(plist, key=lambda p: p["name"].lower())
        label = CLASS_LABEL.get(cls, cls)
        title_word = CLASS_TITLE.get(cls, "Building")
        cards = "".join(property_card(p) for p in plist)
        body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="crumb"><a href="{SITE_URL}/">Home</a> /
<a href="{SITE_URL}/properties/">Properties</a> / {e(label)}</div>
<div class="hero-eyebrow"><span class="dot"></span> {len(plist)} mapped</div>
<h1>{e(label)} in Sandton</h1>
<p>{len(plist)} {e(title_word.lower())}s mapped across the Sandton area from
OpenStreetMap, each with its own page, location and directions.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<h2 class="sec">All {len(plist)} {e(title_word.lower())}s</h2>
{finder_html("Search " + label, "Filter by building name")}
<div class="grid">{cards}</div>
<div class="cta">
<h2>Missing your building?</h2>
<p>Most Sandton buildings are not mapped in open data. If you manage one,
claim a free page and add your own details.</p>
<a class="btn" href="{SITE_URL}/needs-a-website/">Add your building</a>
</div>
</div>"""
        write(os.path.join("properties", cls, "index.html"),
              page(f"{label} in Sandton | {SITE_NAME}",
                   f"{label} across Sandton, Johannesburg: locations, "
                   "directions and what is mapped nearby.", body,
                   f"{SITE_URL}/properties/{e(cls)}/",
                   extra_head=schema_itemlist(
                       f"{label} in Sandton", cls,
                       [p for p in plist if p["gets_page"]]) + schema_site()))
        n_cls += 1

        by_area = defaultdict(list)
        for p in plist:
            if p["area"]:
                by_area[p["area"]].append(p)
        for area, ap in sorted(by_area.items()):
            if len(ap) < MIN_HUB_LISTINGS:
                continue
            adisp = zone_labels.get(area, area.replace("-", " ").title())
            acards = "".join(property_card(p) for p in
                             sorted(ap, key=lambda p: p["name"].lower()))
            body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="crumb"><a href="{SITE_URL}/">Home</a> /
<a href="{SITE_URL}/properties/">Properties</a> /
<a href="{SITE_URL}/properties/{e(cls)}/">{e(label)}</a> / {e(adisp)}</div>
<div class="hero-eyebrow"><span class="dot"></span> {len(ap)} mapped</div>
<h1>{e(title_word)}s in {e(adisp)}</h1>
<p>{len(ap)} {e(title_word.lower())}s mapped in {e(adisp)}, Sandton. Pick
one for its location, directions and what is mapped nearby.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<h2 class="sec">All {len(ap)} in {e(adisp)}</h2>
{finder_html(f"Search {label} in " + adisp, "Filter by building name")}
<div class="grid">{acards}</div>
</div>"""
            write(os.path.join("properties", cls, area, "index.html"),
                  page(f"{title_word}s in {adisp} | {SITE_NAME}",
                       f"{title_word}s mapped in {adisp}, Sandton, "
                       "Johannesburg.", body,
                       f"{SITE_URL}/properties/{e(cls)}/{e(area)}/",
                       extra_head=schema_itemlist(
                           f"{title_word}s in {adisp}", cls, ap) + schema_site()))
            n_cls += 1

    groups = ""
    for cls, plist in sorted(by_class.items()):
        label = CLASS_LABEL.get(cls, cls)
        cards = "".join(property_card(p) for p in
                        sorted(plist, key=lambda p: p["name"].lower())[:40])
        groups += f"""<h2 class="sec"><a href="{SITE_URL}/properties/{e(cls)}/">
{e(label)}</a> <span style="font-weight:400;text-transform:none;
letter-spacing:0">({len(plist)})</span></h2>
<div class="grid">{cards}</div>"""

    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> {len(props)} mapped</div>
<h1>Residential, commercial<br>and industrial <span class="grad">buildings</span></h1>
<p>Every named building mapped in open data across the Sandton area, with
location, directions and the businesses indexed nearby. Source data is
OpenStreetMap, so coverage is partial by nature.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<div class="cta" style="margin-top:0">
<h2>Coverage is incomplete</h2>
<p>Most Sandton buildings are not mapped in open data, and unit numbers,
occupancy, amenities and leasing status are never published here because they
cannot be verified. If you manage a building, you can add it yourself.</p>
<a class="btn" href="{SITE_URL}/needs-a-website/">Add your building</a>
</div>
{groups}
</div>"""
    write(os.path.join("properties", "index.html"),
          page(f"Buildings in Sandton | {SITE_NAME}",
               "Residential, commercial and industrial buildings mapped across "
               "Sandton, Johannesburg, with location and directions.", body,
               f"{SITE_URL}/properties/", extra_head=schema_site()))

    return n_ind, n_cls


# Google processes only 500 URLs per sitemap file on the free tier, so a
# single flat sitemap silently truncates once the site passes that mark. 775
# URLs shipped as one file and Google only ever saw 500 of them. Shard into a
# sitemap index instead, which also scales without a code change.
SITEMAP_CHUNK = 500


def _urlset_xml(urls, lastmod):
    # lastmod is the crawl-priority signal Google actually uses. Every page is
    # regenerated on each build, so the build timestamp is the honest value.
    # Omitting it (as we did) is not fatal, but it removes the one field that
    # tells Google which of 775 URLs changed.
    body = "".join(
        f"<url><loc>{e(u)}</loc><lastmod>{lastmod}</lastmod></url>"
        for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}\n</urlset>\n")


def build_sitemap(paths):
    """Emit clean directory URLs, sharded behind a sitemap index.

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
    urls = sorted(set(urls))
    os.makedirs(SITE, exist_ok=True)
    lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    if len(urls) <= SITEMAP_CHUNK:
        with open(os.path.join(SITE, "sitemap.xml"), "w",
                  encoding="utf-8") as fh:
            fh.write(_urlset_xml(urls, lastmod))
        return len(urls)

    shards = [urls[i:i + SITEMAP_CHUNK]
              for i in range(0, len(urls), SITEMAP_CHUNK)]
    names = []
    for n, shard in enumerate(shards, start=1):
        name = f"sitemap-{n:03d}.xml"
        names.append(name)
        with open(os.path.join(SITE, name), "w", encoding="utf-8") as fh:
            fh.write(_urlset_xml(shard, lastmod))

    refs = "".join(
        f"<sitemap><loc>{e(SITE_URL)}/{e(n)}</loc></sitemap>" for n in names)
    index_xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<sitemapindex xmlns="http://www.sitemaps.org/schemas/'
                 'sitemap/0.9">\n'
                 f"{refs}\n</sitemapindex>\n")
    with open(os.path.join(SITE, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write(index_xml)
    return len(urls)


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
        build_business_page(rec, siblings,
                            len(by_hub_zone[(rec["hub"], rec["zone"])]))
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

    # 4b. intent cluster indexes
    #
    # A second taxonomy from HUB_GROUPS. The hub pages answer "what is this
    # business"; these answer "what is someone typing into Google right now"
    # -- "health clinic near me", "office park sandton". Same listings,
    # different query, and on this site the intent query is the one with a
    # realistic chance of ranking.
    n_intent = build_intent_indexes(records)
    print(f"  intent indexes : {n_intent}")

    print(f"  landings       : 2 (needs-a-website, hours-not-published)")

    # 4c. property pages (residential / commercial / industrial complexes)
    #
    # Harvested by 13_harvest_properties.py. Only complexes that clear the
    # substance bar get an individual page; the rest are listed on the index.
    props = load_properties(records, zone_labels)
    if props:
        n_prop, n_prop_cls = build_property_pages(props, zone_labels)
        n_with_page = sum(1 for p in props if p["gets_page"])
        print(f"  property builds: {len(props)} complexes, "
              f"{n_with_page} with their own page")
        print(f"  property pages : {n_prop + n_prop_cls + 1} "
              f"({n_prop} buildings, {n_prop_cls} category/area, 1 index)")
    else:
        print("  property builds: no properties.json -- run "
              "13_harvest_properties.py first")

    # 5. 404 + robots
    write("404.html", page(
        "Page not found | Sandton Index",
        "That page does not exist.",
        f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> 404</div>
<h1>That page is not<br>in the <span class="grad">index</span></h1>
<p>The link may be out of date, or the business page may have moved. Every
listing on the site is reachable from one of the four starting points below.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<h2 class="sec">Start here</h2>
<div class="grid">
<article class="card">
<div class="cat">{len(records)} businesses</div>
<h3><a href="{SITE_URL}/">Home</a></h3>
<div class="meta">Every business in Sandton, Johannesburg</div>
<div class="acts"><a href="{SITE_URL}/">Browse &rarr;</a></div>
</article>
<article class="card">
<div class="cat">By type of business</div>
<h3><a href="{SITE_URL}/categories/">Categories</a></h3>
<div class="meta">Offices, retail, health, automotive, trades and more</div>
<div class="acts"><a href="{SITE_URL}/categories/">Browse &rarr;</a></div>
</article>
<article class="card">
<div class="cat">By area</div>
<h3><a href="{SITE_URL}/zones/">Suburbs</a></h3>
<div class="meta">Sandton CBD, Rivonia, Illovo, Sunninghill and the rest</div>
<div class="acts"><a href="{SITE_URL}/zones/">Browse &rarr;</a></div>
</article>
<article class="card">
<div class="cat">By situation</div>
<h3><a href="{SITE_URL}/intents/">Near me</a></h3>
<div class="meta">What people actually search for when they need one</div>
<div class="acts"><a href="{SITE_URL}/intents/">Browse &rarr;</a></div>
</article>
</div>
<div class="cta">
<h2>Looking for a specific business?</h2>
<p>Search by name from the categories and suburb pages, or start from the
full index.</p>
<a class="btn" href="{SITE_URL}/categories/">Search the directory</a>
</div>
</div>""",
        f"{SITE_URL}/404.html"))

    for base in (SITE,):
        with open(os.path.join(base, "robots.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write("User-agent: *\nAllow: /\nSitemap: "
                     f"{SITE_URL}/sitemap.xml\n")

    # 5b. Search Console file verification
    #
    # The meta tag above is the method that works on GitHub Pages. This file is
    # Google's other file-based method, emitted so the property can also be
    # verified the moment a real domain is pointed here -- some setups prefer
    # a single static file over a tag on every page.
    if GOOGLE_SITE_VERIFICATION:
        with open(os.path.join(
                SITE, f"google{GOOGLE_SITE_VERIFICATION}.html"),
                "w", encoding="utf-8") as fh:
            fh.write(
                "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
                "<title>Site verification</title></head><body>"
                f"google-site-verification: {e(GOOGLE_SITE_VERIFICATION)}"
                "</body></html>\n")
        print(f"  gsc verification: meta tag + "
              f"google{GOOGLE_SITE_VERIFICATION}.html")
    else:
        print("  gsc verification: disabled (no token configured)")

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
