# NJ Legislature API — reverse-engineering notes

The NJ Legislature runs a Next.js app at `https://www.njleg.state.nj.us`. There is no public API documentation, but the browser app makes plain JSON calls to endpoints under `/api/`. None of the endpoints we use require authentication or a reCAPTCHA token.

This file exists so future-you (or future-us) can rebuild the scraper if the API shape changes.

## Endpoints

### `GET /api/advancedSearch/sessions`

Returns the list of biennial sessions the site knows about.

```json
[
  {"display": "2026-2027 Session", "value": 2026},
  {"display": "2024-2025 Session", "value": 2024},
  …
  {"display": "2000-2001 Session", "value": 2000}
]
```

Fourteen sessions total at time of writing (April 2026). The `value` is the starting year and is what every other endpoint expects as the session identifier.

### `GET /api/advancedSearch/searchFields`

Returns a five-element array of dictionaries used to populate the advanced-search form:

```
[years, sponsors, govActions, committees, subjects]
```

`govActions` is especially useful — it is the complete set of governor-action codes with human labels:

| Code | Description |
|------|-------------|
| AV   | Absolute Veto |
| APP  | Approved |
| CV   | Conditional Veto |
| FSS  | Filed with Secretary of State |
| LIV  | Line Item Veto |
| PV   | Pocket Veto |
| WOA  | Without Approval |

`subjects` holds ~658 subject codes. `sponsors` is a full roster across all sessions.

### `POST /api/advancedSearch/search`

The keyword search endpoint. **Critical quirk:** the browser state holds arrays for `years`, `sponsors`, `committees`, `subjects`, `govActions`, but before POSTing they are `.join(",")` to comma-separated strings. Sending actual JSON arrays returns HTTP 200 with `{"message":"Advanced Search Results did not work"}`. Sending empty strings means "no filter on this field." To match all sessions, send `years: ""` (the code sets this when the user picks `ALL`).

Working body:

```json
{
  "billNumber": "",
  "keyWords": "Designates",
  "ldoaStart": "",
  "ldoaEnd": "",
  "years": "2024",
  "sponsors": "",
  "govActions": "",
  "committees": "",
  "subjects": ""
}
```

Response: array of bill records. Example field shapes:

```json
{
  "Bill": "A444   ",                            // trailing spaces; trim before use
  "Synopsis": "Designates \"New Jersey State Song\" as State song.",
  "LIS_Value": 2024,
  "CurrentStatus": "ASL",                       // opaque; see status codes note below
  "LDOA": "2024-01-09T00:00:00.000Z",
  "GovernorAction": null,                       // null or one of the codes above
  "BillType": "A  ",                            // trim before use
  "BillNumber": 444,
  "IdenticalBillNumber": null,                  // companion bill, same session
  "LastSessionFullBillNumber": "A380",          // space-separated reintroductions
  "NumberPrimeSponsors": 1
}
```

### `GET /api/billDetail/{resource}/{BILL}/{SESSION}` and `/api/billDetailHist/...`

Per-bill detail. The site switches between the two endpoints based on whether the session is current or closed. For our scraper:

- `billDetail/...` for the current session value (check `/api/advancedSearch/sessions` for the latest `value`).
- `billDetailHist/...` for every prior session.

Resources: `billSponsors`, `billDescription`, `billHistory`, `billText`, `sessionVotes`.

Example: `GET /api/billDetail/billSponsors/A444/2024` returns

```json
[
  [ { "Full_Name": "Venezia, Michael", "SponsorDescription": " as Primary Sponsor", "BioLink": "/legislative-roster/492/..." } ],
  [ { "Full_Name": "Morales, Carmen Theresa", "SponsorDescription": " as Co-Sponsor", "BioLink": "/legislative-roster/491/..." } ]
]
```

A two-element array: `[primarySponsors, coSponsors]`. `BioLink` may be null for legislators no longer serving.

One gotcha: `billDetail/billDescription/A444/2024` sometimes returns data for the **current live** version of a bill number, not the 2024 version specifically. Use `billDetailHist/...` for anything before the current session.

## Status codes (`CurrentStatus`) — undocumented

The `searchFields` endpoint documents only the seven governor actions above. Bill-level `CurrentStatus` codes (e.g. `ASL`, `AHU`, `AEN`, `WAPP`, `SIN`, `AIR`) are not documented by any endpoint we've found. We maintain a hand-curated decoder at `data/reference/status_codes.csv`, seeded with values derived empirically from `billHistory` responses. Unknown codes are surfaced to the reader as the raw code with "Meaning not documented" rather than fabricated.

## Rate and etiquette

No documented rate limits. We default to 1 request/second with jitter, honest User-Agent, no concurrency. This is an OLS-hosted site on a public API — don't hammer it.

## Known URLs

- Bill detail page: `https://www.njleg.state.nj.us/bill-search/{SESSION}/{BILL}`
- Legislator bio: `https://www.njleg.state.nj.us{BioLink}` (relative paths in API responses)
