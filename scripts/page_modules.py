#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
page_modules.py -- SEO schema stack, Google Maps readiness module and the
cross-promotion coupon.

Kept out of 09_build_sites.py because that file is already the page templates;
this is the logic behind the three things the pages need to do beyond render.

Design constraints:

  * Never emit AggregateRating. Inventing a rating for a business that has
    not claimed its listing is an unsupported factual claim about a real
    business, and a manual-action risk on the whole domain. It is the single
    most common shortcut on directory pages and it is not taken here.

  * Never attach the coupon to the listed business. A "20% off consultations"
    offer on a page for a tyre shop or a supermarket is false structured
    data. The offer is marked up as its own thing, about its own product,
    from its own brand, and the listed business's LocalBusiness never
    references it.

  * Never put inferred opening hours in structured data. Only a scraped
    schedule is published as fact.
"""
import html
import json
from datetime import date

from data_overlay import hours_in_schema  # noqa: E402
from config import SITE_DESCRIPTION, SITE_NAME, SITE_URL
from seo_content import COUPON, coupon_url, seo_for

def coupon_strip():
    """Slim one-line coupon for the footer of every page.

    The full coupon block is heavy and belongs on business pages and category
    pages. Sitewide coverage is achieved with a single restrained line that
    states who the offer is from, so it can never be read as something the
    business being listed is offering.
    """
    if not COUPON.get("enabled"):
        return ""
    c = COUPON
    return f"""<div class="coupon-strip">
<div class="wrap">
<span class="coupon-strip-tag">Sponsored</span>
<span class="coupon-strip-offer">{e(c['offer'])} from {e(c['brand'])}</span>
<span class="coupon-strip-code">code <b>{e(c['code'])}</b></span>
<a class="coupon-strip-go" href="{coupon_url()}" target="_blank"
rel="sponsored noopener">Register &rarr;</a>
</div>
</div>"""


SCHEMA_CONTEXT = "https://schema.org"


def e(value):
    """HTML-escape. Duplicated from 09_build_sites rather than imported,
    because that module is a script, not a library, and importing it would
    execute the build."""
    return html.escape(str(value if value is not None else ""))

# Google Business Profile primary category, used both in the advice module
# and in the schema. Primary category is the top-weighted local pack factor,
# so it is the one field worth being precise about.
GBP_CATEGORY_REASON = (
    "Your primary category is the single strongest factor in local map "
    "results. Pick the most specific one that fits, not the broadest."
)


def _ld(obj):
    return (f'<script type="application/ld+json">'
            f'{json.dumps(obj, ensure_ascii=False, indent=None)}</script>')


# ---------------------------------------------------------------- schema
def schema_local_business(rec, enriched=None):
    """LocalBusiness with the full set of fields a Maps profile needs.

    Only verified data is asserted. A field we do not know is omitted rather
    than guessed, because a wrong value in structured data is a published
    claim about a real business.

    The rating is deliberately absent. See rating_badge() for why.
    """
    enriched = enriched or {}
    seo = seo_for(rec["hub"])
    data = {
        "@context": SCHEMA_CONTEXT,
        "@type": _schema_type(rec["hub"]),
        "name": rec["name"],
        "url": _absolute(rec["path"]),
        "address": _address(rec),
    }

    if rec.get("phone"):
        data["telephone"] = rec["phone"]
    if rec.get("lat") is not None and rec.get("lng") is not None:
        data["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": rec["lat"],
            "longitude": rec["lng"],
        }
        data["hasMap"] = maps_directions_url(rec)

    if rec.get("website"):
        data["sameAs"] = [rec["website"]]

    # openingHours only when corroborated by two independent sources, which
    # is the single gate this project uses to decide what may be stated as
    # fact. Google hours fail it: they are one third-party copy.
    confidence = enriched.get("confidence") or rec.get("hours_confidence")
    hours = enriched.get("hours") or rec.get("opening_hours") or {}
    if hours and hours_in_schema(confidence):
        data["openingHoursSpecification"] = _hours_spec(hours)

    if rec.get("street_address") or rec.get("building_name"):
        data["areaServed"] = [
            {"@type": "City", "name": "Sandton"},
            {"@type": "AdministrativeArea", "name": rec["zone_display"]},
        ]

    # priceRange is a GBP field, and category defaults are a safe assertion:
    # they describe the trade, not the individual business.
    if seo.get("price_range"):
        data["priceRange"] = seo["price_range"]

    if rec.get("tier") == "A":
        # These businesses have no site of their own, so this directory page
        # IS their canonical online presence. Saying so explicitly tells
        # Google which URL to attribute the entity to.
        data["mainEntityOfPage"] = {"@type": "WebPage",
                                    "@id": _absolute(rec["path"])}
        data["isAccessibleForFree"] = True

    return _ld(data)


def schema_breadcrumbs(rec, hub):
    """BreadcrumbList mirroring the visible breadcrumb, so the SERP shows a
    real hierarchy instead of a bare URL."""
    return _ld({
        "@context": SCHEMA_CONTEXT,
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home",
             "item": SITE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": hub["title"],
             "item": SITE_URL + "/" + rec["hub"] + "/"},
            {"@type": "ListItem", "position": 3,
             "name": rec["zone_display"],
             "item": SITE_URL + "/" + rec["hub"] + "/" + rec["zone"] + "/"},
            {"@type": "ListItem", "position": 4, "name": rec["name"],
             "item": _absolute(rec["path"])},
        ],
    })


def schema_faq(rec):
    """FAQPage for the category questions.

    Only rendered on pages that have a real FAQ, and the answers are advisory
    ("check with the business") rather than assertions about a specific
    business, so they stay true regardless of who claims the listing.
    """
    faqs = seo_for(rec["hub"])["faqs"]
    if not faqs:
        return ""
    return _ld({
        "@context": SCHEMA_CONTEXT,
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in faqs
        ],
    })


def schema_coupon():
    """The cross-promotion offer, as its own Offer entity.

    Deliberately standalone. It is not nested inside the listed business's
    LocalBusiness, so structured data never claims that a tyre shop sells
    discounted medical consultations.
    """
    if not COUPON.get("enabled"):
        return ""
    return _ld({
        "@context": SCHEMA_CONTEXT,
        "@type": "Offer",
        "name": f"{COUPON['offer']} at {COUPON['brand']}",
        "description": COUPON["note"],
        "brand": {"@type": "Brand", "name": COUPON["brand"]},
        "category": "Health care",
        "url": coupon_url(),
        "priceCurrency": "ZAR",
        "price": "0",
        "priceSpecification": {
            "@type": "UnitPriceSpecification",
            "price": "0",
            "priceCurrency": "ZAR",
            "valueAddedTaxIncluded": True,
        },
        "discount": {
            "@type": "Discount",
            "name": "20% off first consultation",
            "description": f"Use code {COUPON['code']} at checkout.",
        },
        "eligibleRegion": {"@type": "Country", "name": "South Africa"},
    })


def schema_itemlist(hub, zone_display, recs):
    """CollectionPage + ItemList for a category/zone page.

    The ItemList is what lets Google show a list of results rather than one
    blue link, which materially lifts click-through on a category SERP.
    """
    return _ld({
        "@context": SCHEMA_CONTEXT,
        "@type": "CollectionPage",
        "name": f"{hub['title']} in {zone_display}",
        "url": f"{SITE_URL}/{hub['slug']}/{recs[0]['zone'] if recs else ''}/",
        "about": {
            "@type": "Thing",
            "name": f"{hub['title']} in {zone_display}, Sandton",
        },
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(recs),
            "itemListOrder": "https://schema.org/ItemListUnordered",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i + 1,
                    "name": r["name"],
                    "url": SITE_URL + "/" + r["path"].strip("/") + "/",
                }
                for i, r in enumerate(recs[:100])
            ],
        },
    })


def schema_site():
    """WebSite + Organization for the site root.

    Declaring the publisher once, rather than repeating it on 767 pages, is
    what lets Google connect the whole domain to a single entity. It also
    gives the sitelinks search box its eligibility, which is real CTR on the
    branded and category queries.
    """
    return _ld({
        "@context": SCHEMA_CONTEXT,
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": SITE_URL + "/",
        "description": SITE_DESCRIPTION,
        "inLanguage": "en-ZA",
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": SITE_URL + "/",
            "areaServed": [
                {"@type": "City", "name": "Sandton"},
                {"@type": "AdministrativeArea", "name": "Gauteng"},
                {"@type": "Country", "name": "South Africa"},
            ],
        },
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": SITE_URL + "/search/?q={search_term_string}",
            },
            "query-input": "required name=search_term_string",
        },
    })


def schema_breadcrumb_path(trail):
    """BreadcrumbList for non-business pages, from an ordered list of
    (name, url) pairs."""
    items = [{"@type": "ListItem", "position": 1, "name": "Home",
              "item": SITE_URL + "/"}]
    for i, (name, url) in enumerate(trail, start=2):
        items.append({"@type": "ListItem", "position": i, "name": name,
                      "item": url})
    return _ld({"@context": SCHEMA_CONTEXT, "@type": "BreadcrumbList",
                "itemListElement": items})


def schema_faq_hub(hub_slug):
    """FAQPage for a category page. Same advisory wording as the business
    pages -- answers stay true whoever claims the listing."""
    faqs = seo_for(hub_slug)["faqs"]
    if not faqs:
        return ""
    return _ld({
        "@context": SCHEMA_CONTEXT,
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faqs
        ],
    })


DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday"]


def nap_html(rec, street=None):
    """Name-and-address block for copy-paste into a Google Business Profile.

    `street` is the already-normalised street component, passed in from the
    caller so the NAP shows exactly what the rest of the page shows. Escapes
    each part before joining, so the separator stays a real entity instead of
    being escaped into visible "&middot;" text.
    """
    if street is None:
        street = rec.get("street_address") or rec.get("building_name") or ""
    parts = []
    for v in [rec["name"], street, rec.get("zone_display", ""),
              rec.get("postcode", ""), rec.get("phone") or ""]:
        v = (v or "").strip()
        if not v:
            continue
        low = v.lower()
        # drop an exact repeat, and drop a component swallowed by a longer
        # one -- street_address is often just the suburb ("Sandton" inside
        # "Sandton CBD"), and repeating it makes the NAP look sloppy
        if any(low == p.lower() for p in parts):
            continue
        if any(low in p.lower() for p in parts):
            continue
        # also drop an earlier, shorter component the new one contains
        # ("Sandton" swallowed by "Sandton CBD")
        parts = [p for p in parts if p.lower() not in low]
        parts.append(v)
    return " &middot; ".join(e(p) for p in parts)


def hours_rows_html(rec):
    """Hours in Monday-first order.

    Sorted alphabetically this reads Friday, Monday, Saturday... which looks
    broken and reads worse to a business owner copying it into Maps.
    """
    days = rec.get("opening_hours") or {}
    out = []
    for key in DAY_ORDER:
        val = days.get(key)
        if not val:
            continue
        out.append(f"<b>{key.capitalize()}</b> &nbsp; {e(val)}")
    if days.get("_all") and not out:
        out.append(f"<b>Every day</b> &nbsp; {e(days['_all'])}")
    return "<br>".join(out)


def property_portal_module(rec, siblings, is_complex):
    """Tenant directory and visitor access for managed properties.

    Gated on the intent engine's is_complex flag -- an explicit check that the
    trading name signals a managed property ("Office Park", "Estate",
    "Sectional Title", "Gated").

    An earlier version gated on "has siblings OR is a property cluster", which
    put a Property portal heading on 334 pages including every branch of
    ordinary retail chains. Sibling branches are not tenants.

    The notice board and leasing module are honest about being unconfigured:
    a managed property that has not claimed its listing genuinely has no
    tenants, no rules and no vacancies here, and rendering invented ones
    would be fabricating facts about someone else's building.
    """
    if not is_complex:
        return ""

    tenant_rows = ""
    if siblings:
        items = "".join(
            f'<li><a href="{SITE_URL}/{e(s["path"])}/">{e(s["name"])}</a>'
            f'<span>{e(s.get("zone_display", ""))}</span></li>'
            for s in siblings[:24])
        tenant_rows = (f'<div class="portal-block"><h3>Also at this property</h3>'
                       f'<ul class="portal-list">{items}</ul></div>')

    return f"""<section class="portal">
<h2 class="sec">Property portal</h2>
<div class="portal-grid">
<div class="portal-block">
<h3>Visitor access</h3>
<p class="small">Exact location, gate coordinates and directions are below.
If you are visiting for an appointment, confirm entry arrangements with the
management office first.</p>
<p><a class="btn btn-2" href="{maps_directions_url(rec)}" target="_blank"
rel="noopener">Open in Google Maps</a></p>
</div>
<div class="portal-block">
<h3>Leasing &amp; space enquiries</h3>
<p class="small">This listing has not been claimed, so there is no live
leasing module or tenant notice board here yet. If you manage this property,
claiming the listing adds both.</p>
<a class="btn" href="{SITE_URL}/needs-a-website/?b={e(rec['id'])}">
Claim this property listing</a>
</div>
{tenant_rows}
</div>
</section>"""


def is_property_type(cluster_slug):
    return cluster_slug in ("housing-managed-complexes",
                            "commercial-industrial-hubs")


def rating_badge(enriched):
    """Google rating, shown with the date it was read.

    Two deliberate choices:

      1. NOT in JSON-LD. The standing rule for this project is no
         aggregateRating. A rating copied from Google is real data, but
         publishing it as a first-party claim about someone else's business
         is still a claim we cannot update ourselves, and it is the single
         most common way a directory earns a manual action.

      2. Always dated. A rating without a date goes stale silently and starts
         looking like a claim about the present. "4.6, as listed on Google in
         October 2026" is honest in a way "4.6" is not, and it ages visibly.
    """
    rating = enriched.get("rating")
    if not rating:
        return ""
    date_stamp = enriched.get("rating_date") or ""
    reviews = enriched.get("review_count")
    rev_html = ""
    if reviews:
        n = f"{reviews:,}"
        rev_html = (f'<span class="rate-rev">{n} review'
                    f'{"" if reviews == 1 else "s"}</span>')
    date_html = ""
    if date_stamp:
        # Rendered as a human month, not an ISO date: this is reassurance to
        # a visitor, not a machine-readable field.
        try:
            y, m, _ = date_stamp.split("-")
            months = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November",
                      "December"]
            date_html = f" as listed {months[int(m) - 1]} {y}"
        except (ValueError, IndexError):
            date_html = ""
    return (f'<div class="rate"><span class="rate-stars" aria-hidden="true">'
            f'&#9733;</span><span class="rate-num">{e(rating)}</span>'
            f'{rev_html}<span class="rate-src">on Google{date_html}</span></div>')


def open_status_pill(rec, enriched=None):
    """Live-looking open/closed pill -- but only when we can actually know.

    A green "OPEN NOW - closes 18:00" badge is the highest-value element on a
    local listing page and the easiest to fabricate. So the state machine is
    deliberately conservative and has exactly three outcomes:

      OPEN   scraped hours, and today's span says we are inside it
      CLOSED scraped hours, and today's span says we are outside it
      (nothing) anything else

    An inferred schedule or a Google snapshot NEVER produces a pill, because
    both can be wrong and a confidently wrong "CLOSED" sends a customer away
    from a shop that is open. Silence is the honest answer when we do not
    know, and "hours not published" is a useful answer too.

    Times are rendered in South African Standard Time (UTC+2). The server's
    own timezone is not consulted: publishing a Sandton business's status from
    a machine in another timezone would be wrong for two hours a day.
    """
    from datetime import datetime, timedelta, timezone

    enriched = enriched or {}
    confidence = enriched.get("confidence") or rec.get("hours_confidence")
    if confidence != "scraped":
        return ""

    hours = enriched.get("hours") or rec.get("opening_hours") or {}
    now = datetime.now(timezone(timedelta(hours=2)))
    key = ["monday", "tuesday", "wednesday", "thursday", "friday",
           "saturday", "sunday"][now.weekday()]
    span = hours.get(key)
    if not span or "-" not in span:
        return ""

    def mins(hhmm):
        try:
            h, m = hhmm.strip().split(":")
            return int(h) * 60 + int(m)
        except (ValueError, AttributeError):
            return None

    # only the first span of a split day; a lunch break mid-day means the
    # simple open/close test does not hold, so we decline to answer
    if "," in span:
        return ""
    op, cl = span.split("-", 1)
    op_m, cl_m = mins(op), mins(cl)
    if op_m is None or cl_m is None:
        return ""
    # a span that crosses midnight (24h, or a late bar) is handled explicitly
    if cl_m <= op_m:
        cl_m += 24 * 60
    cur = now.hour * 60 + now.minute
    if cl_m <= 24 * 60:
        is_open = op_m <= cur < cl_m
    else:
        # span crosses midnight: open late tonight, or still open past
        # midnight this morning
        is_open = cur >= op_m or cur < cl_m - 24 * 60

    if is_open:
        return (f'<span class="pill pill-open"><span class="dot"></span>'
                f'Open now &middot; closes {e(cl)}</span>')
    return (f'<span class="pill pill-closed"><span class="dot"></span>'
            f'Closed now &middot; opens {e(op)}</span>')


def dow_health_module(cluster_slug, rec=None, is_complex=False):
    """Cluster-aware Doctors on Wheels module.

    Placement is deliberate: DOW is a healthcare provider, so a single
    identical block on all 767 pages would be both ineffective and a
    credibility problem on pages for a post office or a tyre shop. The
    module is therefore keyed to the intent cluster, and for clusters where
    DOW is genuinely not a fit (civic services, home trades) nothing is
    rendered at all.

    Voucher codes are generated but marked PENDING APPROVAL. They are not
    presented as redeemable. No voucher code has been confirmed by Doctors on
    Wheels, and publishing "claim 15 free consultations with code ABCDE50"
    for a business that then receives no consultation is a commitment this
    project cannot make on DOW's behalf. The code field is there so the
    mechanism is built and reviewed, not so it can be switched on blindly.
    """
    roles = {
        "health-medical-urgent": {
            "role": "category_owner",
            "kicker": "Doctors on Wheels",
            "title": "Add mobile GP and screening days to what you offer",
            "body": ("If your patients in Sandton need a GP who comes to them, "
                     "or your own staff need occupational health screening, "
                     "Doctors on Wheels delivers both to premises across "
                     "Johannesburg."),
            "cta": "Discuss a partnership",
        },
        "commercial-industrial-hubs": {
            "role": "workforce_partner",
            "kicker": "Workplace health partner",
            "title": "On-site health screening for everyone working here",
            "body": ("Occupational health screenings, executive wellness days "
                     "and mobile GP visits for the tenants and staff in this "
                     "park. Delivered on site, so nobody loses a working day "
                     "to a clinic queue."),
            "cta": "Arrange a workplace screening day",
        },
        "housing-managed-complexes": {
            "role": "resident_benefit",
            "kicker": "Resident health benefit",
            "title": "Home healthcare and mobile GP visits for residents",
            "body": ("Residents of managed complexes can access 24/7 mobile GP "
                     "visits and home healthcare without travelling to a "
                     "practice."),
            "cta": "Register resident interest",
        },
        "education-family": {
            "role": "family_benefit",
            "kicker": "Family health",
            "title": "Mobile GP visits for staff and families",
            "body": ("On-site health days for school and creche staff, and "
                     "home visits for families who cannot easily get to a "
                     "practice during office hours."),
            "cta": "Talk about a health day",
        },
        "transport-logistics": {
            "role": "driver_welfare",
            "kicker": "Driver and shift-worker health",
            "title": "Occupational health that fits around shifts",
            "body": ("Driver licensing assessments, fit-for-work checks and "
                     "mobile GP visits scheduled around shift changes, for "
                     "fleet and logistics teams."),
            "cta": "Book an occupational health visit",
        },
        "recreation-lifestyle": {
            "role": "member_benefit",
            "kicker": "Member health",
            "title": "Health screenings for your members",
            "body": ("Screening days at your facility for members, plus access "
                     "to a mobile GP for anyone who cannot travel during the "
                     "week."),
            "cta": "Arrange a screening day",
        },
        "daily-retail-conveniences": {
            "role": "worker_welfare",
            "kicker": "Worker welfare",
            "title": "Free health screening vouchers for your staff",
            "body": ("Frontline and support staff at independent businesses can "
                     "receive primary care and health screening vouchers "
                     "through their employer's listing on this site."),
            "cta": "See how staff vouchers work",
        },
    }

    cfg = roles.get(cluster_slug)
    if not cfg:
        return ""

    pending = ""
    if cfg["role"] in ("resident_benefit", "worker_welfare"):
        pending = (
            '<p class="dow-pending">Voucher codes for this benefit are '
            '<b>pending approval by Doctors on Wheels</b> and are not yet '
            'redeemable. Nothing is claimed here that has not been agreed.</p>'
        )

    return f"""<section class="dow-card">
<div class="dow-in">
<p class="dow-kicker">{e(cfg['kicker'])}</p>
<h2 class="sec">{e(cfg['title'])}</h2>
<p class="dow-body">{e(cfg['body'])}</p>
{pending}
<a class="btn" href="{coupon_url()}" target="_blank" rel="sponsored noopener">
{e(cfg['cta'])}</a>
</div>
</section>"""


def maps_cta_rows(rec, enriched):
    """The Maps action buttons, branched on whether Google has a claimed
    listing for this business.

    Telling an already-claimed owner to "add a missing place" sends them to a
    flow for a listing they already have. Telling an unclaimed one to "manage
    your profile" sends them to a login they do not have credentials for.
    Both are dead ends, so the action is chosen from the data.
    """
    claimed = (enriched.get("claimed") or "").upper()
    add_url = maps_add_listing_url(rec)

    if claimed == "YES":
        return (
            '<a class="btn" href="' + maps_claim_url() + '" target="_blank" '
            'rel="noopener">Manage your Google profile</a>'
            '<span class="kit-flag">This business already has a Google '
            'listing &mdash; sign in to update its hours, photos and '
            'details.</span>'
        )
    if claimed == "NO":
        return (
            '<a class="btn" href="' + add_url + '" target="_blank" '
            'rel="noopener">Add this business to Google Maps</a>'
            '<span class="kit-flag">No Google listing found for this '
            'business yet. Adding one is the single biggest win available '
            '&mdash; it is how most nearby customers find you.</span>'
        )
    # Unknown: no Google match for this record at all
    return (
        '<a class="btn" href="' + add_url + '" target="_blank" '
        'rel="noopener">Add this business to Google Maps</a>'
        '<a class="btn btn-2" href="' + maps_claim_url() + '" '
        'target="_blank" rel="noopener">Already listed? Manage your '
        'profile</a>'
    )


def _schema_type(hub_slug):
    return {
        "restaurants-takeaways": "Restaurant",
        "supermarkets": "GroceryStore",
        "convenience-liquor": "ConvenienceStore",
        "clothing-fashion": "ClothingStore",
        "beauty-hair": "BeautySalon",
        "health-wellness": "MedicalClinic",
        "hotels-accommodation": "Hotel",
        "home-furniture": "FurnitureStore",
        "doityourself-hardware": "HardwareStore",
        "automotive": "AutoRepair",
        "professional-services": "ProfessionalService",
        "banks-financial": "Bank",
        "tech-it": "ProfessionalService",
        "offices-coworking": "CoworkingSpace",
        "malls-shopping-centres": "ShoppingMall",
        "fitness-sports": "ExerciseGym",
        "services-home": "HomeAndConstructionBusiness",
        "education-training": "EducationalOrganization",
        "pets-animals": "PetStore",
        "media-printing": "PrintShop",
        "travel-tourism": "TravelAgency",
        "auctions-pawn": "PawnShop",
        "cannabis": "Store",
    }.get(hub_slug, "LocalBusiness")


def _address(rec):
    parts = [
        rec.get("building_name") or "",
        rec.get("street_address") or "",
    ]
    # dedupe: building_name frequently repeats the trading name in this data
    street = ", ".join(p for p in parts
                       if p and p.lower() != rec["name"].lower())
    return {
        "@type": "PostalAddress",
        "streetAddress": street or rec["name"],
        "addressLocality": rec.get("zone_display", "Sandton"),
        "addressRegion": "Gauteng",
        "addressCountry": "ZA",
        "postalCode": rec.get("postcode", ""),
    }


def _hours_spec(days):
    """Convert our day->span map into OpeningHoursSpecification."""
    schema_days = {
        "monday": "Monday", "tuesday": "Tuesday", "wednesday": "Wednesday",
        "thursday": "Thursday", "friday": "Friday",
        "saturday": "Saturday", "sunday": "Sunday",
    }
    out = []
    for key, label in schema_days.items():
        span = days.get(key)
        if not span or "-" not in span:
            continue
        op, cl = span.split("-", 1)
        out.append({
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": f"https://schema.org/{label}",
            "opens": op,
            "closes": cl,
        })
    return out


def _absolute(path):
    return SITE_URL + "/" + path.strip("/") + "/"


# ---------------------------------------------------------------- maps
def maps_directions_url(rec):
    if rec.get("lat") is not None and rec.get("lng") is not None:
        return f"https://www.google.com/maps/dir/?api=1&destination={rec['lat']},{rec['lng']}"
    label = " ".join(x for x in [rec["name"], rec.get("street_address", ""),
                                 rec.get("zone_display", "")] if x)
    return f"https://www.google.com/maps/search/?api=1&query={label}"


def maps_add_listing_url(rec):
    """Deep link that opens Maps searching for this business.

    A business that does not exist on Google yet can be added from here in a
    couple of taps: Maps search -> Add a missing place. This is the highest
    value action on the page, because being absent from Maps loses far more
    customers than being absent from this directory.
    """
    label = " ".join(x for x in [rec["name"], rec.get("street_address", ""),
                                 rec.get("zone_display", ""), "Sandton"]
                     if x)
    return (f"https://www.google.com/maps/search/{label.replace(' ', '+')}")


def maps_claim_url():
    return "https://www.google.com/business/"


def maps_readiness_module(rec, street=None, enriched=None):
    """The 'get on Google Maps' block.

    Gives the owner the exact primary category to select, their NAP in
    copy-paste form, their hours, and the direct Maps link. Someone who has
    never set up a Business Profile does not know which category to pick, and
    the primary category is the highest-weighted local ranking factor -- so
    handing them the right answer is worth more than any on-page SEO.
    """
    enriched = enriched or {}
    from config import HOURS_DEFAULTS
    seo = seo_for(rec["hub"])
    confidence = enriched.get("confidence") or rec.get("hours_confidence")
    hours = enriched.get("hours") or rec.get("opening_hours") or {}
    hours_rows = hours_rows_html({"opening_hours": hours})

    if confidence == "scraped":
        hours_note = ("These hours were found in an open public data source. "
                      "Check them, then correct anything wrong.")
    elif confidence == "google":
        hours_note = (
            "Copied from this business's own Google profile. Google listings "
            "go stale, so check them &mdash; and if they are wrong, fix them "
            "at the source, because that is what nearby customers see.")
    elif hours:
        hours_note = (
            "<b>These are a guess</b>, not confirmed hours. If you work "
            "different hours, enter your real ones -- guessed hours actively "
            "hurt you in search, because being listed as closed when you are "
            "open removes you from results.")
    else:
        hours_rows = "<b>No hours on record</b>"
        hours_note = "Add your hours. They are the strongest single signal for 'open now' searches."

    nap = nap_html(rec, street)

    extra = "".join(
        f"<li>{e(c)}</li>" for c in seo["gbp_extra"][:4])

    return f"""<section class="maps-kit" id="google-maps">
<h2 class="sec">Get listed on Google Maps</h2>
<p class="kit-lead">Most people looking for a {e(seo['gbp_category'].lower())}
near you find it on Google Maps, not in a directory. Having a Maps listing is
what puts you in front of them &mdash; and it is free.</p>

<div class="kit-grid">
<div class="kit-card">
<h3>1. Choose this category</h3>
<p class="kit-note">{e(GBP_CATEGORY_REASON)}</p>
<p class="kit-pick"><span>Primary</span> {e(seo['gbp_category'])}</p>
<p class="kit-extra-label">Also add</p>
<ul class="kit-extra">{extra}</ul>
</div>

<div class="kit-card">
<h3>2. Copy your details</h3>
<p class="kit-note">Use this exactly as written everywhere you list the
business. Any difference between your website, Maps and other directories
hurts you in search results.</p>
<p class="kit-nap" id="nap-text">{nap}</p>
<p class="kit-hours-label">Opening hours</p>
<p class="kit-hours">{hours_rows}</p>
<p class="kit-note">{hours_note}</p>
</div>
</div>

<div class="kit-cta">{maps_cta_rows(rec, enriched)}</div>
</section>"""


# ---------------------------------------------------------------- coupon
def coupon_module(compact=False):
    """The cross-promotion block shown on every page.

    Rendered as a clearly separated sponsor module, below the business's own
    content and after the primary call to action, so it never reads as
    something the listed business is offering.
    """
    if not COUPON.get("enabled"):
        return ""
    c = COUPON
    return f"""<section class="coupon{' coupon-sm' if compact else ''}">
<div class="coupon-in">
<div class="coupon-mark">20<span>%</span></div>
<div class="coupon-body">
<p class="coupon-kicker">Sponsored offer &middot; {e(c['brand'])}</p>
<h3>{e(c['offer'])}</h3>
<p class="coupon-note">{e(c['note'])} Use code
<b class="coupon-code">{e(c['code'])}</b> when you register.</p>
</div>
<a class="btn" href="{coupon_url()}" target="_blank" rel="noopener"
rel="sponsored noopener">Get the discount</a>
</div>
</section>"""


