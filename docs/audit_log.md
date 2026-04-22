# Audit log

Every rule change, human-review decision, and data refresh that is worth recording for future-me.

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
