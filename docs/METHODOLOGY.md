# Methodology

This project catalogues ceremonial designation bills introduced in the New Jersey Legislature. This file explains exactly which bills are included, which are not, and why.

## What counts as ceremonial

A bill is "ceremonial" if its synopsis indicates its purpose is one of:

- Creating or renaming a state symbol — the state muffin, state sport, state native pollinator, state song, state slogan. Anything the legislature has made or tried to make "official."
- Establishing a public holiday, commemorative day, week, weekend, or month. Awareness days, remembrance days, heritage months.
- Naming or renaming a piece of road infrastructure — a highway, bridge, interchange, rest area, or overpass. Often these honor a person (a veteran, a public official, a local figure).
- Naming or renaming a civic place — a rail station, park, welcome center, plaza, or preserved landscape.
- Commemorating an anniversary, founding, independence, or event through a resolution.

## What does not count

The word "designates" appears in hundreds of bills that are not ceremonial. This project excludes:

- **Administrative designations.** Bills that designate a government officer or agency to perform a role — "Designates the Attorney General as chief election official" — are organizational, not ceremonial. The rule uses a regex that drops any bill whose synopsis begins with "designates" followed by a governmental title.
- **Regulatory classifications.** Bills like "Designates sweepstakes casinos as internet gaming" are policy, not commemoration.
- **Legal or workforce classifications.** "Designates open water lifeguards as first responders" changes a legal status and is excluded.
- **Renaming administrative bodies.** "Renames Juvenile Justice Commission as Youth Justice Commission" is organizational.
- **Statutory program naming.** "Designates drug court program as the 'special probation recovery court program' in statutes" changes the name of a program within the statutory code but is not a ceremonial act.

## How categorization works

Every included bill receives a primary category and zero or more secondary tags. Categories:

- `state_symbol` — state X bills and bills designating official state colors, gems, or emblems.
- `holiday_observance` — days, weeks, months, weekends, years, and commemorative resolutions.
- `road_naming` — highways, bridges, interchanges, rest areas, overpasses.
- `place_naming` — rail stations, parks, welcome centers, preserved lands.

When a bill matches more than one category, `holiday_observance` wins over `state_symbol` (because a bill like "Designates September 11 as State and public holiday" is primarily a holiday bill), and both win over road and place namings.

Subcategories are keyword-based and narrower. `state_symbol` subs include `food`, `nature`, `culture`, `geology`. Subcategories are hints for readers, not ground truth.

## Where the rules live

Everything is in `data/reference/category_rules.yml`. Edit that file, run `python -m scraper build --session 2024` again, and the rules are applied. The test fixtures in `tests/fixtures/` catch regressions.

A companion file, `data/reference/overrides.yml`, lets a human reviewer add explicit include, exclude, or category decisions for specific bills when the regex can't be made both correct and readable.

## How completeness is verified

- The scraper runs multiple keyword searches per session (`Designates`, `Renames`, `Commemorates`) and deduplicates the union. Ceremonial road-naming bills sometimes use "Renames" rather than "Designates", so a single-keyword search would miss them silently.
- Every bill the scraper pulls is logged to `data/raw/sessions/<year>/search_<keyword>.json` before any filtering happens. The filter and categorizer only read those files — they never hit the API. A re-run with the same raw produces the same output.
- Every dropped bill is written to `data/processed/audit_rejected.csv` with the rule that rejected it. A human can scan that file to look for false negatives.
- A sample of accepted bills is hand-reviewed per session. Decisions are logged in `docs/audit_log.md`.

## Status codes

The NJ Legislature's API returns a `CurrentStatus` code for every bill (e.g. `ASL`, `AHU`, `WAPP`, `APP`). These codes are not documented by any API endpoint. The mapping in `data/reference/status_codes.csv` is hand-curated from the NJ Legislature glossary and from cross-referencing the `billHistory` endpoint. Unknown codes are surfaced to readers as the raw code with "Meaning not documented" rather than an invented label.

## Known limits

- **Sponsor party and district are not in the search endpoint.** We have names and biographical links but would need to scrape the legislative roster to report on party or geographic patterns reliably.
- **Older sessions may have different synopsis formats.** The 2000–2005 sessions have not yet been scraped; we expect to need additional patterns.
- **A bill reintroduced in multiple sessions appears once per session.** We compute a `bill_family_id` to cluster reintroductions but the default view does not deduplicate across sessions. Toggle-based cross-session deduplication is a future enhancement.
- **Geocoding road namings is deferred.** A map view is planned but requires mapping freeform text like "the bridge on Route 18 over the Navesink River" to coordinates, which is nontrivial.

## Replicating

Start with a clean checkout. Everything is deterministic given the same raw API responses. Raw files are not committed but snapshot tarballs at publication milestones are committed to `data/raw/snapshots/`. See `README.md` for the full replication steps.
