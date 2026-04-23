# Provenance

Where every field in the processed dataset comes from.

## Source

New Jersey Office of Legislative Services (OLS), bill search and detail API at `https://www.njleg.state.nj.us`. The API is undocumented; `docs/api_notes.md` explains the endpoints we use and how we found them.

## Data flow

```
NJ Leg API                    raw              processed                   site
─────────                     ───              ─────────                   ────
advancedSearch/search  ─────► data/raw/sessions/<year>/search_<keyword>.json
                                         │
                                         ▼
                              scraper/filter_ceremonial.py
                              scraper/categorize.py
                                         │
billDetail/billSponsors ───► data/raw/bill_details/<year>/<bill>.json
                                         │
                                         ▼
                              scraper/build_site_data.py
                                         │
                              ┌──────────┴──────────┐
                              ▼                     ▼
                   data/processed/bills.parquet   data/bills.json
                   data/processed/audit_rejected.csv  data/meta.json
                                                  data/sessions.json
```

Raw files are immutable once written. Filter and category rules are applied in the build step; re-running the build with the same raw produces the same output.

## Field-by-field

| Field on site | Source | Transformation |
|---|---|---|
| `id` | derived | `{session}-{full_number}` |
| `session` | `LIS_Value` from search | stringified |
| `session_label` | derived | `{year}–{year+1}` with en-dash |
| `bill_type` | prefix of `Bill` | A, S, AJR, SJR, ACR, SCR, AR, SR |
| `bill_type_label` | derived | "Assembly bill", "Senate joint resolution", etc. |
| `full_number` | `Bill` from search | trimmed |
| `synopsis` | `Synopsis` from search | trimmed |
| `ldoa` | `LDOA` from search | ISO datetime → date |
| `status_code` | `CurrentStatus` from search | trimmed, nullable |
| `status_label` | `data/reference/status_codes.csv` | lookup; null if undocumented |
| `gov_action_code` | `GovernorAction` from search | nullable |
| `gov_action_label` | hard-coded dict | 7 known codes from `/api/advancedSearch/searchFields` |
| `became_law` | derived from `gov_action_code` | true iff code ∈ {APP, FSS, WOA} |
| `primary_category` | `data/reference/category_rules.yml` | rules + priority ordering |
| `categories` | `data/reference/category_rules.yml` | all matching category tags |
| `subcategories` | `data/reference/category_rules.yml` | keyword tags on lowercased synopsis |
| `primary_sponsors` | `billDetail/billSponsors` element [0] | `{name, role}` only; bio link kept in processed parquet |
| `cosponsor_count` | `billDetail/billSponsors` element [1] | length |
| `bill_family_id` | `LastSessionFullBillNumber` | clusters reintroductions |
| `url` | derived | `https://www.njleg.state.nj.us/bill-search/{session}/{full_number}` |

## Audit artifacts

- `data/processed/bills.parquet` — the full processed dataset, committed to git so drift is visible in diffs.
- `data/processed/audit_rejected.csv` — every bill the filter dropped, with the rule that dropped it. Committed.
- `data/raw/snapshots/YYYY-MM-DD.tar.gz` — tarball of raw files at each publication milestone. Committed. Raw files themselves are gitignored.

## Caveats

Read `METHODOLOGY.md` first — it explains what "ceremonial" means in this project and what is excluded on purpose.
