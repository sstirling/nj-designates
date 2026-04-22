"""
Phase 2: for every bill kept by the ceremonial filter, pull its sponsor list.

Uses an LDOA-based skip: if a bill's LDOA is unchanged from the previous run
AND a detail file already exists on disk, we don't refetch. Closed sessions
are cached forever unless --force-refresh is passed.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from scraper.api_client import Client, fetch_sponsors
from scraper.config import DATA_RAW, is_current_session

log = logging.getLogger(__name__)


def _manifest_path(session: int) -> Path:
    return DATA_RAW / "bill_details" / str(session) / "_manifest.json"


def _load_manifest(session: int) -> dict[str, str]:
    p = _manifest_path(session)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_manifest(session: int, manifest: dict[str, str]) -> None:
    p = _manifest_path(session)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def fetch_details(session: int, bills: list[dict],
                  client: Client | None = None, force_refresh: bool = False) -> list[dict]:
    """
    bills is the list of records returned by search_bills (for this session)
    that passed the ceremonial filter. Returns the same list with a
    '_detail' key merged in for each bill that we could fetch. Bills whose
    detail fetch fails keep '_detail' as None and are logged to errors.jsonl.
    """
    client = client or Client(cache_dir=DATA_RAW / ".cache")
    out_dir = DATA_RAW / "bill_details" / str(session)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest(session)
    errors_path = out_dir / "errors.jsonl"
    fetched = 0
    skipped = 0
    failed = 0

    for bill in bills:
        full_number = (bill.get("Bill") or "").strip()
        if not full_number:
            continue
        ldoa = bill.get("LDOA") or ""
        detail_path = out_dir / f"{full_number}.json"

        cache_hit = (
            not force_refresh
            and detail_path.exists()
            and manifest.get(full_number) == ldoa
        )
        if cache_hit:
            bill["_detail"] = json.loads(detail_path.read_text())
            skipped += 1
            continue

        try:
            sponsors = fetch_sponsors(
                client, full_number, session,
                is_current=is_current_session(session),
                force_refresh=force_refresh,
            )
        except Exception as e:
            bill["_detail"] = None
            failed += 1
            errors_path.open("a").write(
                json.dumps({"bill": full_number, "session": session,
                            "error": str(e),
                            "at": dt.datetime.utcnow().isoformat() + "Z"}) + "\n"
            )
            log.warning("detail fetch failed for %s: %s", full_number, e)
            continue

        detail = {
            "bill": full_number,
            "session": session,
            "ldoa": ldoa,
            "sponsors": sponsors,  # [primary[], cosponsors[]]
            "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
        }
        detail_path.write_text(json.dumps(detail, indent=2))
        manifest[full_number] = ldoa
        bill["_detail"] = detail
        fetched += 1

    _save_manifest(session, manifest)
    log.info("session=%s: %d fetched, %d skipped (cached), %d failed",
             session, fetched, skipped, failed)
    return bills
