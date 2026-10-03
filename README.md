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
python scripts/build_all.py                  # everything, in order
```

Or one stage at a time while iterating:

```bash
python scripts/07_classify_and_group.py   # tier, hub, branch grouping
python scripts/08_harvest_hours.py        # OSM hours + category defaults
python scripts/13_harvest_properties.py   # OSM complexes
python scripts/15_harvest_cadastral.py    # Council for Geoscience parcels
python scripts/09_build_sites.py          # generate site/
python scripts/verify_build.py            # gate; exits 1 on unsafe output
```

The three harvest stages query free public endpoints that are frequently
overloaded, so `build_all.py` treats them as non-blocking: a failure warns and
the build continues on whatever is cached on disk.

## Build inputs

The stylesheet and script are **source files, not strings in the generator**.
`09_build_sites.py` copies them into `site/assets/` on every build and links
them from every page.

```
scripts/assets/sandton.css        design system -> site/assets/sandton.css
scripts/assets/sandton.js         behaviour     -> site/assets/sandton.js
```

This replaced roughly 15 KB of CSS inlined into each of 860 pages, which had
made the output 33 MB for 13 MB of content. One cacheable file is fetched once
per visitor, and a design change is one edit rather than 860 near-identical
diffs.

Neither asset is required to read the site. Every card, listing and opening
hour is server-rendered; the script only hides and reveals.

### Tests

```bash
python scripts/test_css_coverage.py     # every emitted class has a rule
node    scripts/test_search_js.js       # ranking ladder + escaping
node    scripts/test_search_render.js   # the real render path, via jsdom
```

`test_css_coverage.py` exists because the stylesheet is hand-written while the
markup is generated: nothing else notices when the two drift apart, and the
symptom is one unstyled component on one page type.

The two Node tests need `jsdom` (`npm i -D jsdom`) for the render test only.
`build_all.py` skips both when `node` is not on `PATH` -- the site itself has no
JavaScript toolchain requirement.

## Structure

```
scripts/config.py                 taxonomy, chain guard, hours defaults
scripts/07_classify_and_group.py  tier + hub + branch + URL assignment
scripts/08_harvest_hours.py       OSM hours harvest, name-verified matching
scripts/13_harvest_properties.py  OSM complexes via the /map API
scripts/15_harvest_cadastral.py   Council for Geoscience Erf layer
scripts/09_build_sites.py         page generators
scripts/assets/                   design system + behaviour (build inputs)
scripts/verify_build.py           publish gate
scripts/build_all.py              ordered pipeline
data/businesses.json              enriched dataset
data/chain_report.csv             guard reclassifications, for review
site/                             generated output (gitignored)
```

## Page types

| Type | URL | Ranks for | Purpose |
|---|---|---|---|
| Search | `/search/` | brand + category queries | Client-side index over all listings |
| Hub | `/{category}/{suburb}/` | "supermarket sandton" | Traffic + lead list |
| Brand/category index | `/{category}/` | "sandton supermarkets" | Suburb picker |
| Business | `/{brand}/` | long-tail branded | Free page, Maps, hours |
| Chain branch | `/{brand}/{suburb}-{category}/` | "woolworths sandton hours" | NAP + hours, no pitch |
| Property | `/properties/{complex}/` | "apartments for sale sandton" | Building, class, area |

Subdirectory URLs only -- one repo, one build, no per-client DNS.

Output: `site/` (859 pages, ~14 MB) and `data/businesses.json`.

## Publishing

`SITE_URL` must match where the site actually resolves. Every internal link,
canonical tag and sitemap entry is absolute, so a wrong value turns the whole
site into dead redirects.

**Default:** `https://skywalkingzulu1.github.io/sandton-index` — the GitHub
Pages project URL, the only host this is known to serve on.

`sandtonindex.co.za` was the original default and is **not a registered
domain**; it made every internal link a dead redirect, so it is no longer
referenced anywhere in the output.

To publish on a real domain, override per build:

```bash
SANDTON_SITE_URL=https://yourdomain.co.za python scripts/09_build_sites.py
```

Publishing is done by `scripts/publish_pages.py`, which builds, runs the gate,
and pushes `site/` to the `gh-pages` branch:

```bash
python scripts/publish_pages.py              # build, verify, publish, wait
python scripts/publish_pages.py --no-build   # republish site/ as-is
```

**There is deliberately no GitHub Actions workflow.** Pushing anything under
`.github/workflows/` requires the OAuth token to carry the `workflow` scope,
which a stock `gh auth login` does not grant, so the workflow could not be
pushed at all. Publishing from a branch needs only `repo` scope. An earlier
version of this README claimed `deploy.yml` existed and gated deploys; it never
did. The gate is real, it just runs locally before the push rather than on the
server.

## Design

The visual language is taken from [docsonwheels.co.za](https://docsonwheels.co.za)
so the index reads as part of the same family. The tokens live at the top of
`scripts/assets/sandton.css`:

| Token | Value | Use |
|---|---|---|
| `--brand-700` | `#0052cc` | Links, brand, structure |
| `--brand-900` | `#052d6e` | Gradient hero / CTA |
| `--teal` | `#00a3bf` | Gradient accent, informational |
| `--green` | `#36b37e` | "Open / confirmed / no website yet" |
| `--text` / `--muted` | `#1e293b` / `#64748b` | Copy hierarchy |
| `--border` | `#e2e8f0` | Card and divider lines |

Inter (400-900), 16px cards, 12px buttons, a 135 degree gradient hero with a
masked dot grid and drifting radial blobs, and stat cards that overlap the
hero edge. The amber "typical hours" notice deliberately breaks the blue/green
family so an unverified claim never looks like a verified one.

Beyond the original design:

- **Dark mode** via `prefers-color-scheme`, so the tokens have two definitions
- **`:focus-visible` rings** -- the site is keyboard-navigable end to end
- **A skip link** to the main content
- **Print styles** -- chrome drops out and every URL is spelled out
- **`prefers-reduced-motion`** disables the drifting hero blobs and every
  transition

## Data quality

Known gaps in the source data, not fixed by this pipeline:

- `street_address` present on 25% of records; `phone` on 23%
- `postcode` present on 47%
- 44 businesses have no hours at all and no category default
- 79 category x suburb combinations are too thin to publish as near-me pages

**Health categories are effectively absent.** "Health & Wellness" holds 14
records and there are no dentists, doctors or clinics in the dataset at all,
so a search for "dentist" returns nothing. This is an upstream harvest gap,
not a search defect; the search page says so plainly and points at the nearest
section rather than inventing a near miss. `scripts/test_search_render.js`
asserts the gap so that a later harvest which closes it is noticed.

Hours coverage is the weakest field and the highest-leverage one to improve.
Adding a Google Places key (`GOOGLE_MAPS_API_KEY`) would raise real coverage
well above OSM's 21%.
