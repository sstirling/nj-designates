"""
Phase 1 of the pipeline: pull raw keyword-search results for a session.

Runs multiple keywords per session (configured in scraper/config.py) because
some ceremonial bills use "Renames" or "Commemorates" rather than "Designates"
in the synopsis. Deduplicates by (session, full_bill_number).

Raw response is written to data/raw/sessions/<year>/search_<keyword>.json
verbatim. The filter/categorize step runs against these files — the raw API
payload is never mutated.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from scraper.api_client import Client, search_bills
from scraper.config import DATA_RAW, SEARCH_KEYWORDS

log = logging.getLogger(__name__)


def fetch_session(session: int, keywords: list[str] | None = None,
                  client: Client | None = None, force_refresh: bool = False) -> list[dict]:
    """
    Run each keyword against /api/advancedSearch/search for one session, write
    each raw response to disk, return the deduplicated union.
    """
    client = client or Client(cache_dir=DATA_RAW / ".cache")
    keywords = keywords or SEARCH_KEYWORDS

    out_dir = DATA_RAW / "sessions" / str(session)
    out_dir.mkdir(parents=True, exist_ok=True)

    by_full_number: dict[str, dict] = {}

    for keyword in keywords:
        log.info("searching session=%s keyword=%r", session, keyword)
        try:
            bills = search_bills(client, session, keyword, force_refresh=force_refresh)
        except Exception as e:
            (out_dir / f"errors.jsonl").open("a").write(
                json.dumps({"keyword": keyword, "error": str(e),
                            "at": dt.datetime.utcnow().isoformat() + "Z"}) + "\n"
            )
            log.warning("search failed for keyword=%r: %s", keyword, e)
            continue

        # Raw dump — immutable record of what the API returned. Provenance.
        (out_dir / f"search_{keyword.lower()}.json").write_text(
            json.dumps(bills, indent=2)
        )

        for b in bills:
            full_number = (b.get("Bill") or "").strip()
            if not full_number:
                continue
            # First keyword wins on duplicates — the search API returns the same
            # record regardless of keyword, and later keywords are broader nets.
            by_full_number.setdefault(full_number, b)

    (out_dir / "fetched_at.txt").write_text(
        dt.datetime.utcnow().isoformat() + "Z\n"
    )

    log.info("session=%s: %d unique bills across %d keywords",
             session, len(by_full_number), len(keywords))
    return list(by_full_number.values())
