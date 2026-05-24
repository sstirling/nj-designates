# Audit log

Every rule change, human-review decision, and data refresh that is worth recording for future-me.

## 2026-05-24 — Added weekly "on the move" tracking

Shipped a new feature: each weekly refresh now also pulls the per-bill action history from `/api/billDetail/billHistory/{BILL}/{SESSION}`, classifies events into buckets (governor / floor / committee / transfer / other), and emits a `data/movement.json` feed of everything that happened in the last 7 days. The site renders this as a new "On the move" panel below the existing "What's new" panel.

Design decisions worth recording:

- **Window:** fixed 7-day window anchored to UTC today at build time. Considered anchoring to `meta.json`'s `previous_refresh_at` for self-correction on missed cron runs, but the fixed window is simpler and a missed week is a rare enough edge case that the empty-panel signal is itself useful editorially.
- **Initial introductions are excluded.** The HistoryAction `"Introduced, Referred to ..."` (and variants) is silently dropped by `scraper.movement.classify()`. The site's "What's new" panel already surfaces newly-introduced bills via `first_seen`; surfacing them again here would double-report. Movement = post-introduction progress.
- **Classifier is regex-based on the HistoryAction prose.** Clerks write the action text in English, so the classifier matches lowercased substrings. Patterns and test fixtures cover everything observed in the 2024 + 2026 sessions; unrecognized actions fall through to the `other` bucket rather than being dropped silently, so a wording change at NJ Leg's end degrades gracefully.
- **`CurrentStatus` vs `billHistory` can disagree.** Spot-checked SJR43/2026, which had `CurrentStatus=SEN` ("Senate enacted") but only a single intro event in its history. The API can lag. We treat `billHistory` as authoritative for events and dates; `CurrentStatus` remains the authoritative *current state* shown on bill cards. They're shown independently.
- **Cache strategy.** `fetch_bill_details.py` now requires the cached detail file to carry a `history` key for a cache hit, alongside the existing LDOA match. Existing detail files written before this feature ship will be treated as cache misses on the first run after deploy, triggering a one-time backfill — roughly 2–3 minutes of extra API time at 1 req/sec.
- **"Filed with Secretary of State" is ambiguous and must be disambiguated by bill type + both-chamber passage.** The phrase appears for two distinct events:
  1. A Bill or Joint Resolution that's been signed by the governor and is now law (the genuine "governor's desk" arrival).
  2. A single-chamber Resolution (AR/SR) being formally recorded after one chamber adopted it — no governor involvement possible, since AR/SR don't go to the governor at all.

  Both come back from the API with the same `Filed with Secretary of State` HistoryAction text. We disambiguate by checking whether the bill (or its identical companion via `IdenticalBillNumber`) shows floor passage in BOTH chambers. If it does, the event stays in the `governor` bucket. If not, it's demoted to `other`. Caught this against AR130/2026 (NJ-Taiwan recognition): passed Assembly, filed with SoS the same day, but companion SR96 was still in Senate committee — the panel was falsely claiming governor's-desk status. `Approved P.L.` events are unambiguous and stay in `governor` regardless.

## 2026-05-07 — Re-added "Honors" and "Recognizes" to search keywords

Reversing the May-4 decision to keep `Honors`/`Recognizes` out. The earlier reasoning leaned on aggregate hit-counts; an actual inspection of the 21 bills currently in the dataset whose synopses start with those verbs showed the signal is much higher than the search-volume number suggested.

Of the 21 `Honors` + `Recognizes` bills currently kept (across all sessions), about 13 are unambiguously ceremonial and would otherwise be lost on the next refresh. Examples:

- **Honors** — "Honors life of Congressman William J. Pascrell, Jr." (SR53); "Honors 40th anniversary of Jersey Fresh program" (SCR20); "Honors life of Charles 'Charlie' Kirk" (AR43).
- **Recognizes** — "Recognizes 138th anniversary of Knights of Columbus" (ACR44); "Recognizes Prince Hall as Revolutionary Era activist" (ACR116/SCR105); "Recognizes 30th Anniversary of Srebrenica genocide and Dayton Accords" (ACR120/SCR109); "Recognizes and celebrates April 10 as Dolores Huerta's birthday" (AR71/SR12); "Recognizes contributions of Special Olympics" (AR98); "Recognizes NJ-Taiwan sister-state relationship" (AR130/SR96).

These are exactly the kind of honoring/anniversary/sister-state resolutions the project tracks. The `is_ceremonial` filter catches the bulk of substantive `Honors X program / Recognizes X regulation` noise, so the per-week churn is bounded.

`Establishes` stays out. Inspecting the 48 `Establishes` bills in the current dataset confirmed the May-4 reasoning was right for that verb specifically: nearly all are substantive policy (grant programs, study commissions, reimbursement rates) that the categorize step mis-tags as ceremonial. Two genuine ceremonial `Establishes` bills will be lost on the next refresh as a result — A3296 ("Establishes State holiday on September 11") and SJR72 ("Establishes April as Military Sexual Trauma Awareness Month"). We deliberately did **not** add a recovery mechanism (narrow phrase search or special-case fetch) for those two: both bills sit on serious topics (mass-casualty memorial; sexual trauma awareness) that don't fit the project's tongue-in-cheek register. Cataloguing them next to state-vegetable resolutions would misread the tone. The cleaner outcome is to let them drop with the rest of the `Establishes` noise.

New `SEARCH_KEYWORDS`: `["Designates", "Renames", "Commemorates", "Honors", "Recognizes", "official State"]`. Effect on the dataset is forward-only — the change takes effect on the next fetch (Sunday's CI run or a manual workflow_dispatch).

## 2026-05-04 — Added "official State" phrase to search keywords

While verifying the new weekly auto-refresh job, found that S4120 ("Establishes 'Freedom Flag' as official State flag.") wasn't being captured. Its synopsis uses "Establishes" rather than "Designates", and the keyword list was `["Designates", "Renames", "Commemorates"]`. The ceremonial filter accepts the synopsis when given it directly — the gap was at the search-discovery layer, not the filter.

First attempted fix was to add the verbs `Establishes`, `Honors`, `Recognizes` to `SEARCH_KEYWORDS`. Live-API measurements for session 2026 showed `Establishes` alone returns 1,766 hits with only 58 ceremonial — a 30:1 noise ratio against the filter. The cost (1,708 substantive bills churning through the filter every weekly run, plus a ballooning audit_rejected.csv, plus the risk of false-positive ceremonial classifications) outweighed the gain for what is mostly an edge-case verb.

Reverted that change and instead added the single phrase **`"official State"`**. The NJ Leg search API treats multi-word `keyWords` as phrase queries, so this is highly targeted — it returns only 3 bills in session 2026, all 3 ceremonial:
- A2698, S1184: "Designates 9/11 Heart Symbol flag as official State flag…" (already caught by `Designates`; deduplicated)
- S4120: "Establishes 'Freedom Flag' as official State flag."

Net effect on the next refresh: +1 ceremonial bill in session 2026 (S4120). Historical sessions are unchanged — applied forward only. If the same `"X as official State Y"` pattern appears with non-`Designates` verbs in older sessions, those bills are still missed; a future full backfill (`python -m scraper refresh --all`) would close that gap if needed. Verbs other than `Designates`/`Renames`/`Commemorates` (like `Establishes`/`Honors`/`Recognizes` for non-state-symbol bills) remain out of scope by design — too noisy to be worth catching in this archive.

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
