# nj-designates

A data journalism project cataloguing every ceremonial "Designates X as" bill introduced in the New Jersey Legislature since 2000 — state symbols, public holidays, commemorative weeks, and highway, bridge, and building namings. The site is tongue-in-cheek about a genuine quirk of Trenton politics: how much of the legislative day gets spent making things official.

Data comes from the NJ Legislature's undocumented but public JSON API (see `docs/api_notes.md`). The scraper runs locally, writes a processed dataset, and builds a static site suitable for GitHub Pages.

**Status:** Phase 1 — 2024–2025 session only. Older sessions ship later.

## What's here

```
scraper/     Python scraper pipeline (fetch → filter → categorize → build)
tests/       Pytest suite with known-include / known-exclude fixtures
data/        Raw pulls (gitignored), reference files (committed), processed parquet
docs/        Methodology, provenance, API notes, audit log
site/        Static site served by GitHub Pages
```

## Replication

Requires Python 3.11+.

```bash
git clone https://github.com/sstirling/nj-designates.git
cd nj-designates
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the test suite
pytest

# Pull one session from the live API, then build site data
python -m scraper fetch --session 2024
python -m scraper build --session 2024

# Serve the site locally
python -m http.server -d site 8000
```

Open `http://localhost:8000`.

## Methodology and caveats

See `docs/METHODOLOGY.md` for the full inclusion rules. In short:

- Included: state symbols; public holidays; commemorative days, weeks, months; road, bridge, rest area, park, and rail-station dedications.
- Excluded: administrative designations ("designates the Attorney General as…"), regulatory definitions, and anything that fails the ceremonial test.
- Every bill in the final dataset traces back to a raw API response under `data/raw/`. Raw files are never edited.

## Sources

NJ Legislature bill search and detail endpoints (`https://www.njleg.state.nj.us/api/...`). The API is undocumented; our reverse-engineering notes are in `docs/api_notes.md` so the scrape remains reproducible if the API shape shifts.

## License

Code: MIT. Data derived from public records; attribution to the NJ Office of Legislative Services is included on every chart.
