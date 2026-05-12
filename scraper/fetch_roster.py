"""
Fetch the current NJ Legislature roster.

The official roster page at https://www.njleg.state.nj.us/legislative-roster
is server-rendered by Next.js and inlines the full roster as JSON inside a
single ``<script id="__NEXT_DATA__">`` block. There is no separate JSON
endpoint we could find (every /api/legislative-roster variant returns 404),
so we pull the page once and extract the embedded blob.

Output: ``data/active_legislators.json`` with the shape

    {
      "updated_at": "2026-05-12T...",
      "source_url": "https://www.njleg.state.nj.us/legislative-roster",
      "current_session": 2026,
      "legislators": [
        {
          "full_name": "Bramnick, Jon M.",
          "canonical_name": "bramnick,jon m",
          "last_name": "Bramnick",
          "first_name": "Jon",
          "middle_name": "M.",
          "suffix": null,
          "chamber": "Senate",
          "chamber_code": "S",
          "district": 21,
          "party": "R",
          "party_description": "Republican",
          "bio_url": "https://www.njleg.state.nj.us/legislative-roster/433/senator-bramnick"
        },
        ...
      ]
    }

The site reads this file to drive the "active legislator" filter and the
leaderboard badges. ``canonical_name`` is the form sponsor names from
``bills.json`` get normalized to before matching — see ``canonicalize_name``
below for the rule and ``js/sponsors.js`` for the JS counterpart.
"""

from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from scraper.config import (
    BASE_URL,
    CURRENT_SESSION,
    REQUEST_TIMEOUT_SECONDS,
    SITE_DATA,
    USER_AGENT,
)

log = logging.getLogger(__name__)

ROSTER_URL = f"{BASE_URL}/legislative-roster"
OUTPUT_PATH = SITE_DATA / "active_legislators.json"

# Match honorifics and generational suffixes wherever they appear in the name.
# The roster shoves "Jr." / "M.D." into the last-name slot ("Amato Jr., Carmen F.")
# while the bill-sponsors endpoint puts them after the first name
# ("Amato, Carmen F., Jr."). Dropping the tokens entirely on both sides
# resolves every observed mismatch in the 2000-2026 archive without producing
# any duplicate canonical keys across the current 120-member roster.
#
# A note on what's NOT in this regex: bare "V". Middle initials like
# "John V. Smith" appear constantly in NJ rosters, and a 5th-generation
# suffix ("Sampson V") essentially never does. Including a standalone "V"
# in the alternation would silently strip every "V." middle initial and
# create false matches. II/III/IV are multi-character so they don't
# collide with any common initials.
_HONORIFIC = re.compile(
    r"(?<!\w)(?:Jr|Sr|II|III|IV|M\.?\s*D|Ph\.?\s*D|Esq|Dr)\.?(?!\w)",
    re.IGNORECASE,
)
_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S,
)


class RosterParseError(RuntimeError):
    """Raised when the roster page shape doesn't match expectations."""


def canonicalize_name(name: str) -> str:
    """
    Reduce a legislator name to a comparable form by dropping honorifics
    (Jr., Sr., II–V, M.D., Ph.D., Esq., Dr.), all periods, and collapsing
    repeated commas/whitespace. Lowercased on the way out.

        "Amato Jr., Carmen F."  -> "amato,carmen f"
        "Amato, Carmen F., Jr." -> "amato,carmen f"
        "Donlon M.D., Margie"   -> "donlon,margie"
        "Donlon, Margie, M.D."  -> "donlon,margie"

    The JS counterpart in js/sponsors.js applies the same transform to
    bill sponsor names at runtime before checking membership.
    """
    n = _HONORIFIC.sub("", name or "")
    n = n.replace(".", "")
    n = re.sub(r"\s+", " ", n)
    n = re.sub(r"\s*,\s*", ",", n)
    n = re.sub(r",+", ",", n)
    return n.strip(" ,").lower()


def _fetch_page(url: str = ROSTER_URL) -> str:
    """One-off GET. No retry: if the roster page is down, we fail loudly so the
    operator can investigate rather than silently shipping a stale roster."""
    log.info("GET %s", url)
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.text


def _extract_next_data(page_html: str) -> dict:
    m = _NEXT_DATA.search(page_html)
    if not m:
        raise RosterParseError(
            "No __NEXT_DATA__ block found on the roster page. The site shape "
            "may have changed; inspect the page source and update this scraper."
        )
    try:
        return json.loads(html.unescape(m.group(1)))
    except json.JSONDecodeError as e:
        raise RosterParseError(f"__NEXT_DATA__ blob did not parse as JSON: {e}") from e


def parse_legislators(page_html: str) -> list[dict]:
    """
    Pull the legislator list out of a roster-page HTML response.

    ``legrosterData`` is a 3-element array — ``[legislators, towns, districts]``.
    We only want index 0. Vacant seats appear as entries with VacantSort != 0
    (or missing Full_Name); we drop them.
    """
    blob = _extract_next_data(page_html)
    try:
        legroster = blob["props"]["pageProps"]["legrosterData"]
        raw_legs = legroster[0]
    except (KeyError, IndexError, TypeError) as e:
        raise RosterParseError(
            "Expected blob.props.pageProps.legrosterData[0] to be the legislator "
            "list; the page shape may have changed."
        ) from e

    out = []
    for e in raw_legs:
        if not isinstance(e, dict):
            continue
        full_name = (e.get("Full_Name") or "").strip()
        if not full_name:
            continue  # vacant seats have no name
        if e.get("VacantSort") not in (0, None):
            # All currently-seated members have VacantSort=0; non-zero is the
            # legislature's marker for an empty seat awaiting appointment.
            continue
        bio = e.get("BioLink") or ""
        out.append({
            "full_name": full_name,
            "canonical_name": canonicalize_name(full_name),
            "last_name": (e.get("Last_Name") or "").strip() or None,
            "first_name": (e.get("First_Name") or "").strip() or None,
            "middle_name": (e.get("Middle_Name") or "").strip() or None,
            "suffix": (e.get("Suffix") or "").strip() or None,
            "chamber": (e.get("Roster_House") or "").strip() or None,
            "chamber_code": (e.get("RosterHouseCode") or "").strip() or None,
            "district": e.get("Roster_District"),
            "party": (e.get("Party") or "").strip() or None,
            "party_description": (e.get("PartyDescription") or "").strip() or None,
            "bio_url": f"{BASE_URL}{bio}" if bio.startswith("/") else (bio or None),
        })

    # Sort by chamber then last name for stable diffs in version control.
    out.sort(key=lambda r: ((r["chamber_code"] or "Z"),
                            (r["last_name"] or "").lower(),
                            (r["first_name"] or "").lower()))
    return out


def fetch_roster(output_path: Path = OUTPUT_PATH,
                 url: str = ROSTER_URL,
                 session: int = CURRENT_SESSION) -> dict:
    """Fetch, parse, and write the roster. Returns the document that was written."""
    html_body = _fetch_page(url)
    legislators = parse_legislators(html_body)
    doc = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_url": url,
        "current_session": session,
        "legislators": legislators,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(doc, indent=2) + "\n")
    log.info("wrote %d legislators to %s", len(legislators), output_path)
    return doc
