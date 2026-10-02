#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config.py -- Shared taxonomy, chain guard list and hours defaults.

Three concerns live here:
  1. HUB_GROUPS   -- collapses 115 raw category strings into ~24 SEO hub groups
  2. CHAIN_GUARD  -- brands that already have a website; blocks the "you have
                     no site" pitch and marks them as branch locations instead
  3. HOURS_DEFAULTS-- per-category fallback hours, used ONLY as a visibly
                     labelled estimate. Never emitted into JSON-LD schema.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SITE = os.path.join(ROOT, "site")
SRC_DB = r"C:\Users\molel\zk\ngo\output\sandton_b2b\dow_sandton_master_db.csv"


def load_env():
    """Read ROOT/.env into os.environ without overwriting real env vars.

    Hand-rolled rather than pulling in python-dotenv: the file format we need
    is three lines of parsing, and the build has no third-party dependencies
    worth adding a package for.

    Existing environment variables win, so CI (which sets secrets as real env
    vars) is never overridden by a developer's local file.
    """
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value:
                os.environ.setdefault(key, value)


load_env()

# G Maps Extractor bearer token for the Google Maps Scraper API.
# Optional: the pipeline completes without it, it only improves data quality.
# Read through config (never imported directly in scripts) so there is exactly
# one place that knows how the token is stored.
GMAPSEXTRACTOR_TOKEN = os.environ.get("GMAPSEXTRACTOR_TOKEN", "").strip()

SITE_NAME = "Sandton Index"

# Google Search Console site verification.
#
# This is the HTML meta-tag method rather than a DNS TXT record, because the
# site is served from <user>.github.io and that domain's DNS is owned by
# GitHub. If a real domain is ever pointed at this site, switch to the DNS TXT
# record and this becomes redundant -- 09_build_sites.py also writes the
# standalone google<token>.html file, which covers the file-based method.
#
# Override with SANDTON_GOOGLE_VERIFICATION in .env, or set it to "" to
# suppress the tag entirely.
GOOGLE_SITE_VERIFICATION = os.environ.get(
    "SANDTON_GOOGLE_VERIFICATION",
    "GE9Rw6RV6BChb2Q7l-jmgEtL5-rmEpxinsXmoiR9ziY",
).strip()

# Base URL for canonical tags, sitemap entries and internal links.
#
# Every internal link is absolute, so this must match where the site is
# actually served. The default points at the GitHub Pages project URL, which
# is the only host this is known to resolve on -- sandtonindex.co.za was never
# registered, and defaulting to it made every internal link a dead redirect.
#
# Override it once a real domain is live, either via the environment:
#
#   SANDTON_SITE_URL=https://sandtonindex.co.za python scripts/09_build_sites.py
#
# or by setting the SANDTON_SITE_URL repository variable, which the deploy
# workflow reads.
SITE_URL = os.environ.get(
    "SANDTON_SITE_URL", "https://skywalkingzulu1.github.io/sandton-index"
).rstrip("/")

SITE_DESCRIPTION = (
    "Every business in Sandton, Johannesburg, on one map. "
    "Opening hours, directions and contact details for shops, services and offices."
)

# Design tokens, taken from docsonwheels.co.za so the index reads as part of
# the same family. Blue carries structure, teal marks informational blocks and
# green marks the "good / open / confirmed" states.
PALETTE = {
    "primary": "#0052cc",
    "primary_dark": "#0747a6",
    "primary_darker": "#052d6e",
    "secondary": "#00a3bf",
    "accent": "#36b37e",
    "accent_dark": "#2a8f63",
    "text": "#1e293b",
    "muted": "#64748b",
    "border": "#e2e8f0",
    "light": "#f8fafc",
    "footer": "#0f172a",
    # Tier + state tints
    "tint_blue": "#eef4ff",
    "tint_green": "#e3fcef",
    "tint_teal": "#e6fcff",
    "tint_amber": "#fff8e1",
    "amber": "#f59e0b",
}

# --------------------------------------------------------------------------
# 1. HUB GROUPS
# Ordered by search volume potential. Each maps many raw category strings onto
# one hub page. Page slug + title are what Google indexes.
# --------------------------------------------------------------------------
HUB_GROUPS = [
    {
        "slug": "restaurants-takeaways",
        "title": "Restaurants & Takeaways",
        "singular": "restaurant",
        "raw": ["restaurant", "fast_food", "takeaway", "deli", "cafe", "café"],
    },
    {
        "slug": "supermarkets",
        "title": "Supermarkets & Grocers",
        "singular": "supermarket",
        "raw": ["supermarket", "greengrocer", "food", "health_food", "butcher",
                "seafood", "bakery", "pastry"],
    },
    {
        "slug": "convenience-liquor",
        "title": "Convenience & Liquor Stores",
        "singular": "convenience store",
        "raw": ["convenience", "alcohol", "wine", "winery", "liquor", "beverages",
                "tobacco", "newsagent", "lottery"],
    },
    {
        "slug": "clothing-fashion",
        "title": "Clothing & Fashion",
        "singular": "clothing store",
        "raw": ["clothes", "shoes", "fashion", "boutique", "tailor", "curio",
                "gift", "department_store", "toys", "party"],
    },
    {
        "slug": "beauty-hair",
        "title": "Beauty, Hair & Cosmetics",
        "singular": "beauty business",
        "raw": ["beauty", "hairdresser", "cosmetics", "massage", "tattoo",
                "nutrition_supplements", "sorbet"],
    },
    {
        "slug": "health-wellness",
        "title": "Health & Wellness",
        "singular": "health business",
        "raw": ["chemist", "pharmacy", "pharma", "clinic", "health", "optician",
                "hospital", "medical", "dental", "physio"],
    },
    {
        "slug": "hotels-accommodation",
        "title": "Hotels & Accommodation",
        "singular": "accommodation provider",
        "raw": ["hotel", "guest_house", "hostel", "motel", "lodge", "resort"],
    },
    {
        "slug": "home-furniture",
        "title": "Home, Furniture & Décor",
        "singular": "home business",
        "raw": ["furniture", "interior_decoration", "houseware", "kitchen",
                "bed", "mattress", "homeware", "carpet", "household_linen",
                "garden_centre", "florist", "art"],
    },
    {
        "slug": "doityourself-hardware",
        "title": "DIY, Hardware & Trade",
        "singular": "trade supplier",
        "raw": ["doityourself", "hardware", "builders", "trade", "paint", "tile"],
    },
    {
        "slug": "automotive",
        "title": "Automotive",
        "singular": "automotive business",
        "raw": ["car", "car_repair", "tyres", "motorcycle", "bicycle", "auto"],
    },
    {
        "slug": "professional-services",
        "title": "Professional & Business Services",
        "singular": "professional services firm",
        "raw": ["lawyer", "legal", "accounting", "consultants", "consulting",
                "financial", "financial_advisor", "financial services",
                "insurance", "estate_agent", "property", "recruitment",
                "bookkeeping", "tax"],
    },
    {
        "slug": "banks-financial",
        "title": "Banks & Financial Institutions",
        "singular": "financial institution",
        "raw": ["bank", "banking", "financial institutions", "financial markets",
                "asset management", "fintech", "atm"],
    },
    {
        "slug": "tech-it",
        "title": "Technology & IT Services",
        "singular": "technology company",
        "raw": ["it", "computer", "technology services", "technology consulting",
                "telecommunications", "software", "electronics", "mobile_phone",
                "hifi", "video"],
    },
    {
        "slug": "offices-coworking",
        "title": "Offices & Coworking",
        "singular": "office",
        "raw": ["office", "commercial", "company", "shared_office_space",
                "coworking", "headquarters", "hq", "flagship hq", "corp",
                "mining & industrial hq", "government", "diplomatic", "embassy"],
    },
    {
        "slug": "malls-shopping-centres",
        "title": "Malls & Shopping Centres",
        "singular": "shopping centre",
        "raw": ["mall", "shopping_centre", "centre", "plaza"],
    },
    {
        "slug": "fitness-sports",
        "title": "Fitness, Sport & Recreation",
        "singular": "fitness business",
        "raw": ["fitness_centre", "sports_centre", "sports", "golf_course", "gym",
                "yoga", "pilates", "park", "outdoor"],
    },
    {
        "slug": "services-home",
        "title": "Home Services",
        "singular": "home service",
        "raw": ["laundry", "dry_cleaning", "cleaning", "security", "locksmith",
                "hvac", "plumbing", "electrical", "pest_control", "storage_rental",
                "moving", "courier"],
    },
    {
        "slug": "education-training",
        "title": "Education & Training",
        "singular": "education provider",
        "raw": ["educational_institution", "school", "college", "training",
                "university", "tutor", "creche", "daycare"],
    },
    {
        "slug": "pets-animals",
        "title": "Pets & Animals",
        "singular": "pet business",
        "raw": ["pet", "pets", "animal", "vet", "veterinary", "pet_shop"],
    },
    {
        "slug": "media-printing",
        "title": "Media, Printing & Stationery",
        "singular": "media business",
        "raw": ["books", "stationery", "copyshop", "news", "printing",
                "publisher", "music", "musical_instrument", "photography", "photo"],
    },
    {
        "slug": "travel-tourism",
        "title": "Travel & Tourism",
        "singular": "travel business",
        "raw": ["travel_agency", "tourism", "tour", "safari"],
    },
    {
        "slug": "auctions-pawn",
        "title": "Auctions, Pawn & Cash",
        "singular": "pawnbroker",
        "raw": ["pawnbroker", "auction", "cash_buyer", "cash"],
    },
    {
        "slug": "cannabis",
        "title": "Cannabis & Alternative Products",
        "singular": "cannabis retailer",
        "raw": ["cannabis", "dispensary", "alternative"],
    },
    {
        "slug": "other",
        "title": "Other Sandton Businesses",
        "singular": "business",
        "raw": [],  # catch-all
    },
]

# Slug for the catch-all plus a few raw values that are data-quality noise
NOISE_CATEGORIES = {"yes", "channel 1", "channel 2", "channel 3", "channel 4"}

# --------------------------------------------------------------------------
# 2. CHAIN GUARD
# Brands that unquestionably have a website. A record matching one of these is
# never pitched "you have no website" regardless of the has_website flag --
# that flag came from OSM tag absence, not from checking.
#
# Matching rule: a guard entry matches only as a WHOLE-WORD SEQUENCE, not a
# bare substring. A naive `guard in name` would flag "Game Changers" as the
# retail chain Game, and "Gymnasium" as a fitness chain. Word-boundary
# matching keeps the guard precise at the cost of missing odd spellings,
# which is the correct trade for a list whose job is to avoid false positives.
# --------------------------------------------------------------------------
CHAIN_GUARD = [
    # Supermarkets & grocery
    "pick n pay", "pick n pay express", "pick n pay family", "pick n pay liquor",
    "pn p", "spar", "shoprite", "checkers", "liquorshop", "food lover",
    "market kokoro", "kokoro", "boxer", "quickshop", "makro", "cambridge",
    "okay", "nests",
    # Apparel
    "woolworths", "woolworths food", "mr price", "markham", "truth",
    "cotton on", "h&m", "zara", "asos", "takealot", "legacy",
    "fashion fusion", "sportscene", "matalan", "diesel", "eversham", "stutta",
    "side by side", "refinery", "outfitters", "nfinity", "edgars",
    "the wig", "truworths", "cotton trader",
    # Health & pharmacy
    "cna", "clicks", "dischem", "alpha pharmacies", "the alpha pharmacy",
    "sorbet", "lifemed", "siza", "medscheme", "itab", "hollard", "pps",
    "sanlam", "momentum", "santiam", "gpg",
    # Financial & insurance
    "discovery", "liberty", "standard bank", "absa", "nedbank", "fnb",
    "capitec", "investec", "sizes", "old mutual", "santafrican",
    # Fuel
    "shell", "shell select", "engen", "caltex", "total", "sasol", "astron",
    "petro", "bp",
    # Automotive
    "audi", "bmw", "mercedes", "mercedes benz", "toyota", "honda", "nissan",
    "ford", "vw", "volkswagen", "hyundai", "kia", "land rover", "range rover",
    "jaguar", "porsche", "firstcarhire", "tempest", "carlinks", "avis",
    "europcar", "hertz", "tiger wheel", "tiger wheel and tyre", "goodyear",
    "continental", "tiger",
    # Retail & food chains
    "builders", "builders warehouse", "croma", "steers", "spur",
    "mcdonald's", "mcdonalds", "nandos", "kfc", "debonairs", "fishaways",
    "crazy pizza", "news24", "iol", "timeslive", "citypress",
    "business day", "moneyweb",
    # Telecom
    "vodacom", "mtn", "telkom", "cell c", "rain",
    # Property & property services
    "jse", "liberty two degrees", "growthpoint", "attacq", "redm",
    "arrow", "bidvest", "sabre", "jhb", "pep", "pep stores", "cashbuild",
    "jhw", "jbg", "santafi", "afrimat", "mcp", "steinhoff", "eskom",
    "transnet", "sabc", "virgin active",
]

# Normalize guard entries once
CHAIN_GUARD_NORM = {c.lower().strip() for c in CHAIN_GUARD if c and c.strip()}

# --------------------------------------------------------------------------
# 3. HOURS DEFAULTS
# (open, close) per hub group slug. Used ONLY when a business has no scraped
# hours. Rendered to users as a visibly labelled estimate and never written
# into LocalBusiness JSON-LD, because publishing wrong opening hours as fact
# is the fastest way to lose a client's Google Business Profile.
# --------------------------------------------------------------------------
HOURS_DEFAULTS = {
    "restaurants-takeaways":     ("09:00", "21:00"),
    "supermarkets":             ("07:00", "21:00"),
    "convenience-liquor":       ("07:00", "22:00"),
    "clothing-fashion":         ("09:00", "18:00"),
    "beauty-hair":              ("09:00", "18:00"),
    "health-wellness":          ("08:00", "17:00"),
    "hotels-accommodation":     None,   # 24h reception is misleading to guess
    "home-furniture":           ("09:00", "18:00"),
    "doityourself-hardware":    ("08:00", "17:00"),
    "automotive":               ("08:00", "17:00"),
    "professional-services":    ("08:30", "17:00"),
    "banks-financial":          ("09:00", "16:00"),
    "tech-it":                  ("08:30", "17:00"),
    "offices-coworking":        ("08:00", "17:00"),
    "malls-shopping-centres":   ("09:00", "18:00"),
    "fitness-sports":           ("05:30", "21:00"),
    "services-home":            ("07:00", "18:00"),
    "education-training":       ("07:30", "16:00"),
    "pets-animals":             ("08:30", "17:30"),
    "media-printing":           ("08:30", "17:00"),
    "travel-tourism":           ("08:00", "17:00"),
    "auctions-pawn":            ("09:00", "17:00"),
    "cannabis":                 ("09:00", "20:00"),
    "other":                    ("09:00", "17:00"),
}

# Zone display names and the office/landmark they centre on, used for
# "near me" landing copy on each hub page.
ZONE_META = {
    "sandton_cbd":            ("Sandton CBD", "Sandton"),
    "rivonia_strip":          ("Rivonia", "Rivonia Road"),
    "illovo":                 ("Illovo", "Illovo"),
    "sandton_hq":             ("Sandton Office Park", "Sandton Office Park"),
    "sunninghill":            ("Sunninghill", "Sunninghill"),
    "marlboro_wynberg":       ("Marlboro Park & Wynberg", "Marlboro Park"),
    "bryanston_east":         ("Bryanston", "Bryanston"),
    "sandhurst":              ("Sandhurst", "Sandhurst"),
    "woodmead":               ("Woodmead", "Woodmead"),
    "northcliff_adj":         ("Northcliff", "Northcliff"),
}

# Branch name tokens stripped when normalizing a chain name for grouping
BRANCH_TOKENS = {
    "sandton", "jhb", "johannesburg", "rand", "the", "and", "branch", "store",
    "shop", "centre", "center", "south", "north", "east", "west", "express",
    "food", "market", "liquor", "family", "select", "petrol", "service",
    "services", "estate", "town", "local",
}

# Legal / trading suffixes stripped before brand normalization
LEGAL_SUFFIX_RE = re.compile(
    r"\b(pty|ltd|limited|inc|incorporated|cc|co|company|group|holdings|"
    r"the|and)\b\.?",
    re.IGNORECASE,
)
NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")
WS_RE = re.compile(r"\s+")


def normalize_brand(name):
    """Collapse a company name to a groupable brand key.

    Strips legal suffixes and branch-location tokens so that
    'Pick n Pay Express - Sandton' and 'Pick n Pay' produce the same key.
    """
    if not name:
        return ""
    n = str(name).lower()
    n = n.replace("&", " and ")
    n = LEGAL_SUFFIX_RE.sub(" ", n)
    n = NON_ALNUM_RE.sub(" ", n)
    tokens = [t for t in WS_RE.split(n) if t and t not in BRANCH_TOKENS]
    return " ".join(tokens).strip()


def is_known_chain(name):
    """True if the business is a national/franchise brand that has a website.

    Uses whole-word-sequence matching on the raw lowercase name so that
    'Pick n Pay Family' matches the 'pick n pay' entry, while 'Game Changers'
    and 'Gymnasium' do not match 'game' or 'gym'.
    """
    if not name:
        return False
    n = str(name).lower()
    n = NON_ALNUM_RE.sub(" ", n)
    n = WS_RE.sub(" ", n).strip()
    if not n:
        return False
    for guard in CHAIN_GUARD_NORM:
        if not guard:
            continue
        g = NON_ALNUM_RE.sub(" ", guard)
        g = WS_RE.sub(" ", g).strip()
        if not g:
            continue
        # word-boundary containment: guard tokens must appear contiguously
        if f" {g} " in f" {n} ":
            return True
    return False


def map_category_to_hub(raw_category):
    """Map a raw category string onto a hub slug."""
    if not raw_category:
        return "other"
    key = str(raw_category).strip().lower()
    if key in NOISE_CATEGORIES:
        return "other"
    norm = NON_ALNUM_RE.sub(" ", key)
    norm = WS_RE.sub(" ", norm).strip()

    # exact match first
    for hub in HUB_GROUPS:
        if hub["raw"] and key in hub["raw"]:
            return hub["slug"]
    # then containment in either direction
    for hub in HUB_GROUPS:
        for r in hub["raw"]:
            if r and (r in norm or norm in r):
                return hub["slug"]
    return "other"


def zone_meta(zone_raw):
    """Return (display_name, landmark) for a raw zone string."""
    if not zone_raw:
        return ("Sandton", "Sandton")
    key = str(zone_raw).strip().lower()
    if key in ZONE_META:
        return ZONE_META[key]
    cleaned = WS_RE.sub(" ", NON_ALNUM_RE.sub(" ", key)).strip()
    return (cleaned.title(), cleaned.title())


def slugify(value, max_len=60):
    """URL-safe slug. Stable and collision-resistant enough for this dataset.

    Whitespace must become a hyphen here. The shared NON_ALNUM_RE used for
    token normalization deliberately keeps spaces (name matching depends on
    them), so reusing it directly produced paths like "/werkmans attorneys/"
    -- a broken URL requiring percent-encoding on every internal link.
    """
    if not value:
        return "unknown"
    s = NON_ALNUM_RE.sub("-", str(value).lower())
    s = s.replace("_", "-")
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "unknown"


HUB_BY_SLUG = {h["slug"]: h for h in HUB_GROUPS}

# Minimum listings before a category x suburb page is worth publishing.
# Below this the page cannot outrank the big chains, offers a visitor nothing
# the category page does not, and reads as padding. Those records still
# appear on their category and suburb pages; they just do not get a dedicated
# near-me landing page.
MIN_HUB_LISTINGS = 3

# Bounding box for the Sandton cluster (Sandton CBD / Rivonia / Illovo).
# Shared by the opening-hours harvest (Overpass) and the property harvest
# (OSM /map API) so both cover exactly the same ground. Defined here rather
# than in either harvester because two copies of a geographic boundary is one
# more than there should be.
SANDTON_BBOX = {
    "south": -26.1800,
    "west": 27.9800,
    "north": -26.0200,
    "east": 28.1300,
}
