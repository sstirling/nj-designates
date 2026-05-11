# CLAUDE.md — nj-designates

Project-specific guidance for Claude Code working in this repo. Pairs with the global instructions in `~/.claude/CLAUDE.md`; this file overrides them where they conflict.

## What this project is

A data journalism project cataloging every ceremonial "Designates X as" bill introduced in the New Jersey Legislature since 2000 — state symbols, named bridges, commemorative weeks, honorary highway signs. Static site on GitHub Pages at `sstirling.github.io/nj-designates/`. Live URL serves the repo root.

Reporting voice is tongue-in-cheek about a real quirk of Trenton politics: how much legislative time goes to making things official. Keep that tone in mind when writing copy, alt text, chart titles, or commit messages.

See `README.md` for the full pipeline overview and `docs/METHODOLOGY.md` for the long-form methodology.

## Scope: ceremonial only

The dataset is **ceremonial designations only**. In scope:

- State symbols (state muffin, state dinosaur, etc.)
- Public holidays, commemorative weeks/months/days
- Highway, bridge, building, and rail-station namings
- Other "Designates X as the official Y" bills with no regulatory effect

Out of scope, even when the bill literally contains "designate":

- Administrative designations ("designates the Attorney General as...")
- Regulatory designations ("designates X as a controlled substance," "designates as internet gaming")
- Land-use or zoning designations with legal effect

**Tone-driven scope on hard cases:** when a ceremonial bill is on a serious topic (9/11 memorials, military sexual trauma, mass-casualty events), let it drop rather than building keywords or overrides to keep it. The project's voice is tongue-in-cheek; surfacing the gravest topics as part of that joke is the wrong call. Don't argue this point — drop the bill and move on.

## Stack

- **Site:** vanilla HTML/CSS/JS at the repo root. No build step, no framework, no bundler. ES modules loaded directly from `js/`.
- **Pipeline:** Python 3.11+ in `scraper/`. CLI is `python -m scraper {fetch,build,refresh}`.
- **Data:** JSON for the site (`data/bills.json`, `data/meta.json`, `data/sessions.json`); parquet for the canonical processed dataset (`data/processed/bills.parquet`).
- **Tests:** pytest (`pytest` from the repo root). Fixtures in `tests/fixtures/` are the regression net for filter changes.

Always work inside the project venv (`.venv/`). If it doesn't exist, ask before choosing an alternative.

## Repo layout shortcuts

- Site code: `index.html`, `methodology.html`, `css/`, `js/`
- Pipeline code: `scraper/`
- Rule files (hand-curated, plain text): `data/reference/`
  - `category_rules.yml` — include/exclude/category regex
  - `overrides.yml` — per-bill force decisions; every entry needs a one-line *why*
  - `status_codes.csv` — decoder for opaque NJ Leg status codes
- Generated outputs: `data/bills.json`, `data/meta.json`, `data/processed/`
- Audit trail: `docs/audit_log.md` — every rule change goes here in chronological order
- API quirks: `docs/api_notes.md`

## Data rules

- Raw API responses in `data/raw/` are **immutable per run**. Never edit them; rerun the fetch instead.
- Every number on the site is generated from `data/meta.json`. Never hand-type counts into HTML, copy, or chart titles — wire them through the meta pipeline.
- After any rule edit (`category_rules.yml`, `overrides.yml`, `status_codes.csv`), run `pytest` before committing. The fixtures will catch known-ceremonial bills dropping out and known-admin bills slipping in.
- Don't round intermediate calculations. Don't present modeled or estimated figures as exact counts.
- Don't fabricate or backfill missing data. If a field is missing, surface that to the reader ("Meaning not documented") rather than inventing a label.

## NJ Legislature API

Undocumented JSON API at `njleg.state.nj.us/api/...`. Rate-limited to 1 req/sec with jitter via `scraper/api_client.py` — don't bypass that. POST search body fields that look like lists are actually comma-joined strings, not JSON arrays. See `docs/api_notes.md` for the full reverse-engineering notes.

## Site conventions

- URL state lives in `window.location.hash` as a querystring (`#category=...&q=...`). Every view is bookmarkable. `js/state.js` is the single source of truth; touch it carefully.
- Filter changes flow through `setState()` → `writeHash()` → subscribers. Don't mutate state directly.
- The site must remain readable at 320px. Test mobile before claiming a UI change is done.
- Colorblind-safe palettes (viridis, ColorBrewer); 4.5:1 contrast minimum; alt text on every visual.
- Chart titles in title case; everything else in sentence case (AP style).

## Workflow

- For non-trivial changes (3+ steps or any architectural decision), enter plan mode and get approval first.
- For UI changes, start a local server (`python -m http.server 8000`) and verify the change in a browser before reporting it done. Don't claim success on a frontend change you haven't loaded.
- For pipeline changes, run `pytest` and check the diff on `data/processed/bills.parquet` and `data/meta.json`. Commit the regenerated outputs in the same PR so the published site matches the repo.
- Bug fix workflow: write a failing test in `tests/` first, then fix, then verify the test passes.

## Writing style in this repo

Follow the global writing rules in `~/.claude/CLAUDE.md` (sentence case, AP style, banned-words list). Specific to this project:

- Don't drop the tongue-in-cheek tone in reader-facing copy, but keep it dry — no exclamation marks, no winking.
- Source line on every chart and map. Every bill on the site links to its official NJ Leg record.
- Commit messages: imperative mood, lowercase first word, no trailing period. Match the existing log style (`git log --oneline`).

## Do not

- Do not edit raw API responses in `data/raw/`.
- Do not commit credentials or `.env` files.
- Do not hand-type counts that should come from `meta.json`.
- Do not add overrides to keep a bill in scope when the tone test says drop it.
- Do not skip pre-commit hooks or test failures with `--no-verify`. Fix the underlying issue.
- Do not install a framework or bundler for the site. Vanilla JS is a deliberate choice.
