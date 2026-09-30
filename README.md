# Sandton Index

A static directory of every business in Sandton, Johannesburg, with opening
hours, maps and contact details. Built from an existing OSM harvest.

Two audiences:

- **Businesses with no website** get a free page they can claim, and a
  listing on the relevant "near me" page.
- **Everyone else** gets a directory that answers local queries
  (`supermarket sandton`, `open now near me`).

## Why the pages look the way they do

Three findings from the data drove the design. Each one is enforced by a
check, not just a convention.

**Chains were mislabelled as having no website.** The source DB's
`has_website` flag came from OpenStreetMap tag absence, not from checking
the web, so 60 records for brands like Woolworths, CNA and Discovery were
flagged `has_website=False`. Approaching CNA with "you have no website" ends
the conversation. `CHAIN_GUARD` in `scripts/config.py` matches whole-word
brand sequences and reclassifies these to tier B, which is never pitched that
line. Guard matching is deliberately strict: substring matching flagged
"Acrylic Game" as the retail chain Game, and "Vape Crazy" as a pizza brand.

**Opening hours are a ranking factor, and were entirely absent.** Being open
when someone searches is now a confirmed local-pack ranking factor
(#5 in Whitespark's 2026 study), and "open now near me" is among the fastest
growing local queries. The source data had no hours field at all.
`08_harvest_hours.py` scrapes OpenStreetMap, which covers only ~21% of
records, and infers the rest from category.

Inferred hours are rendered as **"Typical hours, not confirmed"** and are
**excluded from JSON-LD**. Structured data is what Google publishes; putting
an unverified opening time in it makes a false claim about a real business,
and sending customers to a closed door costs you the account.

**Proximity matching handed businesses their neighbours' hours.** The first
version matched OSM elements within 120m and hit 90% of records -- a
jewellery store inherited a restaurant's hours, and 59 records picked up
24/7 from nearby office towers. Sandton's CBD is too dense for coordinates
alone. Matching now requires the OSM name to resolve to the same core tokens
as the record name, within 150m.

## Pipeline

```bash
python scripts/07_classify_and_group.py   # tier, hub, branch grouping
python scripts/08_harvest_hours.py        # OSM hours + category defaults
python scripts/09_build_sites.py          # generate site/
python scripts/verify_build.py            # gate; exits 1 on unsafe output
```

Output: `site/` (767 pages, ~12 MB) and `data/businesses.json`.

## Structure

```
scripts/config.py              taxonomy, chain guard, hours defaults
scripts/07_classify_and_group.py  tier + hub + branch + URL assignment
scripts/08_harvest_hours.py     OSM hours harvest, name-verified matching
scripts/09_build_sites.py       page templates
scripts/verify_build.py         publish gate
data/businesses.json            enriched dataset
data/chain_report.csv           guard reclassifications, for review
site/                           generated output
```

## Page types

| Type | URL | Ranks for | Purpose |
|---|---|---|---|
| Hub | `/{category}/{suburb}/` | "supermarket sandton" | Traffic + lead list |
| Brand/category index | `/{category}/` | "sandton supermarkets" | Suburb picker |
| Business | `/{brand}/` | long-tail branded | Free page, Maps, hours |
| Chain branch | `/{brand}/{suburb}-{category}/` | "woolworths sandton hours" | NAP + hours, no pitch |

Subdirectory URLs only -- one repo, one build, no per-client DNS.

## Publishing

`SITE_URL` must match where the site actually resolves. Every internal link,
canonical tag and sitemap entry is absolute, so a wrong value turns the whole
site into dead redirects.

**Default:** `https://skywalkingzulu1.github.io/sandton-index` — the GitHub
Pages project URL, the only host this is known to serve on.

`sandtonindex.co.za` was the original default and is **not a registered
domain**; it made every internal link a dead redirect, so it is no longer
referenced anywhere in the output.

To publish on a real domain, set the `SANDTON_SITE_URL` repository variable
(the deploy workflow reads it) or override per build:

```bash
SANDTON_SITE_URL=https://yourdomain.co.za python scripts/09_build_sites.py
```

`.github/workflows/deploy.yml` builds and deploys to GitHub Pages on push to
`main`. It runs `verify_build.py` before publishing and fails the deploy if
any check trips.

## Design

The visual language is taken from [docsonwheels.co.za](https://docsonwheels.co.za)
so the index reads as part of the same family:

| Token | Value | Use |
|---|---|---|
| `--primary` | `#0052cc` | Links, brand, structure |
| `--primary-darker` | `#052d6e` | Gradient hero / CTA |
| `--secondary` | `#00a3bf` | Gradient accent, informational |
| `--accent` | `#36b37e` | "Open / confirmed / no website yet" |
| `--text` / `--muted` | `#1e293b` / `#64748b` | Copy hierarchy |
| `--border` | `#e2e8f0` | Card and divider lines |

Inter (400–900), 16px cards, 12px buttons, a 135° gradient hero with dot grid
and drifting radial blobs, and stat cards that overlap the hero edge. The
amber "typical hours" notice deliberately breaks the blue/green family so an
unverified claim never looks like a verified one.

## Data quality

Known gaps in the source data, not fixed by this pipeline:

- `street_address` present on 25% of records; `phone` on 23%
- `postcode` present on 47%
- 44 businesses have no hours at all and no category default
- 79 category x suburb combinations are too thin to publish as near-me pages

Hours coverage is the weakest field and the highest-leverage one to improve.
Adding a Google Places key (`GOOGLE_MAPS_API_KEY`) would raise real coverage
well above OSM's 21%.
