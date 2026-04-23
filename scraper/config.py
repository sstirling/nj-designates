"""
Configuration for the NJ Legislature scraper.

The endpoints and payload shape are documented in docs/api_notes.md. Session
values are the starting year of each biennial session, matching what the
`/api/advancedSearch/sessions` endpoint returns.
"""

from __future__ import annotations

from pathlib import Path

BASE_URL = "https://www.njleg.state.nj.us"

# Identify the scraper honestly so OLS can reach us if they want to rate-limit.
# Contact is the repo's issue tracker; no personal email embedded.
USER_AGENT = (
    "nj-designates scraper/0.1 "
    "(+https://github.com/sstirling/nj-designates)"
)

# Seconds between any two HTTP requests. Jitter is added on top.
REQUEST_DELAY_SECONDS = 1.0
REQUEST_JITTER_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 30

# Multiple keyword passes broaden coverage — road/bridge dedications sometimes
# use "Renames", "Commemorates", or "Establishes X as" instead of "Designates".
# The filter deduplicates by (session, full_bill_number).
SEARCH_KEYWORDS = ["Designates", "Renames", "Commemorates"]

# Biennial sessions, starting year. Covers 2000 through the 2026–2027 session.
ALL_SESSIONS = [2000, 2002, 2004, 2006, 2008, 2010, 2012, 2014, 2016, 2018,
                2020, 2022, 2024, 2026]

# The session the NJ Leg treats as "current" for the billDetail vs billDetailHist
# endpoint split. Update when a new session starts.
CURRENT_SESSION = 2026

# Project paths
ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_REFERENCE = ROOT / "data" / "reference"
DATA_PROCESSED = ROOT / "data" / "processed"
SITE_DATA = ROOT / "data"


def session_label(session: int) -> str:
    """'2024' → '2024–2025' (an en-dash, matching NJ Leg style)."""
    return f"{session}–{session + 1}"


def is_current_session(session: int) -> bool:
    return session == CURRENT_SESSION


def bill_detail_base(session: int) -> str:
    """Current-session endpoint vs. closed-session endpoint."""
    return "billDetail" if is_current_session(session) else "billDetailHist"
