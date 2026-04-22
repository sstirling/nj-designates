# Audit log

Every rule change, human-review decision, and data refresh that is worth recording for future-me.

## 2026-04-22 — Phase 3 post-backfill rule tuning

Two audits on the full 13-session archive — the `other_ceremonial` bucket and a 25-bill random sample from 2000–2004. Found and fixed:

- **Abbreviation bug in category regexes.** `[^.]{0,80}` was stopping matches at any period, so synopses with "U.S.", "St.", "N.J." and similar abbreviations broke. Replaced with `.{0,80}` throughout.
- **N.J. prefix with periods.** State-symbol pattern assumed "NJ" without periods; added `n\.j\.\s+` alternative to all state_x patterns (include and category).
- **Building namings misclassified as admin.** "Designates the Department of Education Building as X" was excluded because "Department" hit the admin rule. Added a negative lookahead: admin_officer rule now exempts any synopsis where a place noun (building/center/hall/facility/complex/court/plaza) appears before "as".
- **Admin renames.** "Renames the State Parole Board as the State Parole Commission" slipped through because my renames_authority rule required the admin noun immediately after "renames". Broadened to allow modifier words between them, with the same place-noun exemption so building renames still pass.
- **Missing state-symbol taxonomy.** Added "mineral" to the enumerated official-X list; added a multi-word pattern for "official X of (the) State" (catches "official mineral of State of NJ" and "official Junior and Senior Ancient Fife and Drum Corps of New Jersey"); added a no-"as" pattern for "Designates six State songs" and "Designates State Song, State Anthem...".
- **Missing place-naming nouns**: added "street", "trail", "canal", "hall", "facility", and plain "center" (covers Trauma Center, Welcome Center, Technical Center, Community Center, etc.).
- **Commemoration scope.** Broadened the include rule so "Commemorates life and accomplishments of Chief Roy Crazy Horse" is caught alongside anniversary-style resolutions.

Net effect: **2,866 → 2,918 bills** (+52), `other_ceremonial` **33 → 2** (both are the "Miranda Vargas Act" — honorific naming of a substantive law, a genuine judgment call we've chosen to leave in `other_ceremonial` rather than force a category).

By category after the fixes:
- holiday_observance: 2,323
- road_naming: 267
- state_symbol: 258 (up from 216)
- place_naming: 68
- other_ceremonial: 2

All 60 tests still pass.

## 2026-04-22 — Phase 3 backfill 2022 back to 2000

- Ran the scraper sequentially for 12 biennial sessions. Wall-clock elapsed: 55:48. No retries needed, zero failed detail fetches.
- Dataset grew from 369 bills (2024 only) to **2,866 bills** across 13 sessions. 312 became law (10.9% pass rate across the full archive — noticeably higher than 2024 alone because older sessions have more time for bills to have made it through).
- Per-session bill counts confirm what the 2024 sample suggested: ceremonial designation bills have grown steadily. 89 in 2000–2001, 115 in 2002–2003, climbing to 341 in 2018–2019 and 369 in 2024–2025.
- Rejected bills across the archive: 341. Audit-review queue to revisit (~3% of the total kept volume), manageable.
- Top sponsor across the full period is Assemblywoman Angela V. McKnight with 194 primary sponsorships. Second is Valerie Vainieri Huttle (retired 2021) at 149.

## 2026-04-22 — Phase 2 design polish + accessibility

- Category palette darkened from ColorBrewer Set2 defaults so white text on the category pills clears WCAG AA (4.5:1). New values: `#0f6f55` state_symbol, `#9b4100` holiday, `#4a4583` road, `#9c1a60` place, `#565044` other. All white-on-color ratios now 6.1–8.5.
- Added monochrome SVG line-art icons (star-in-ribbon, calendar, highway shield, civic building) rendered inline in category chips and table cat-pills. No network requests; inherit current color.
- Wired sponsor bio links through the pipeline — `primary_sponsors[].bio_url` now flows to the site JSON; rendered as links in the table and sponsor leaderboard. 614/670 sponsors have bio URLs (the 56 gaps are legislators no longer serving; API returns null).
- Banned-words audit against CLAUDE.md style guide: no hits in site/ or docs/.
- Contrast audit on the cream palette: ink 15.76, muted 5.16, link 11.49, accent 6.06 — all pass normal-text AA. Category icon-tints 3.01–3.95 on cream (AA-large / decorative only, fine since they're aria-hidden).
- 320px structural audit: no unwanted fixed widths; the only `min-width` (40rem on the bill table) sits inside an `overflow-x: auto` wrapper. Long sponsor names have `word-break: break-word`. Masthead h1 is clamped and wraps.
- Semantic + ARIA check: one H1, one main landmark, skip link as first tabbable, HTML `lang="en"`, explicit `type` on every button, chart is `role="img"` with aria-label, external links carry `rel="external noopener"`.

## 2026-04-22 — Phase 2 editorial pass (2024 session)

- Wired `data/reference/overrides.yml` into the filter pipeline. `is_ceremonial()` now honors `force_include` / `force_exclude` when given a `bill_id`. Regression tests added in `tests/test_overrides.py`.
- Applied the six deferred overrides from Phase 1: AR24 (USS John Basilone christening), AR189 (Sikh Massacre), AJR65 (annual Lunar New Year), A3090 (pinelands rename), S4670 (Delaware Bay rename), S4923 (NJ tourism slogan).
- Post-overrides count: **369 bills** (+6), 26 became law, 17 remaining rejects — all confirmed genuine exclusions (administrative renames, regulatory classifications, legal workforce definitions).
- Stratified random sample of 25 accepted bills: every one correctly included and categorized. Holidays, state symbols, road namings, and place namings all read as expected.
- Full rejected list reviewed (17 bills); each is a legitimate admin / regulatory / legal designation. No false negatives found.

## 2026-04-22 — Phase 1 initial build

- First end-to-end run for the 2024–2025 session.
- 363 bills kept, 23 rejected, 26 became law (7.2% pass rate).
- Rule refinements during build:
  - Added negative lookahead on `state_symbol` pattern to stop "State Highway Route 71" from being tagged as a state symbol.
  - Added `\bdesignates?\b[^.]{0,120}\b(day|week|month)\b` include pattern to catch bills like "Designates March 30th of each year 'Menstrual Toxic Shock Syndrome Awareness Day.'" that don't use "as".
  - Added `\bdesignates?\s+\d{4}\s+as\b` for year-long observances ("Year of Black History").
  - Added `\b(commemorates?|celebrates?)\b...` include pattern for ceremonial resolutions.
  - Added `welcome center`, `visitor center`, `complex` to `place_naming` pattern and subs.
  - Reordered category priority: `holiday_observance` now beats `state_symbol` so "designates September 11 as State and public holiday" is classified as a holiday, not a symbol.
- Deferred to Phase 2 review (noted in `data/reference/overrides.yml`):
  - AR24 — USS John Basilone christening
  - AR189 — Sikh Massacre commemoration
  - AJR65 — annual Lunar New Year
  - A3090 — John McPhee pinelands renaming
  - S4670 — Delaware Bay to Bay of New Jersey rename
  - S4923 — state tourism slogan
