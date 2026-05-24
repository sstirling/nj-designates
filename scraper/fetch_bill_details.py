"""
Phase 2: for every bill kept by the ceremonial filter, pull its sponsor list
and action history.

Uses an LDOA-based skip: if a bill's LDOA is unchanged from the previous run
AND a detail file already exists on disk, we don't refetch. Closed sessions
are cached forever unless --force-refresh is passed.

Schema-evolution note: the detail file gained a `history` field after
sponsors. Existing files without it are treated as cache misses even when
LDOA hasn't moved, so the first run after deployment backfills history.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from scraper.api_client import Client, fetch_history, fetch_sponsors
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


def _normalize_action_date(raw: str | None) -> str | None:
    """Convert ActionDate from the API's M/D/YYYY format to ISO YYYY-MM-DD.

    Returns None for falsy or unparseable values rather than fabricating a
    date — downstream code must handle missing dates explicitly.
    """
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        return dt.datetime.strptime(s, "%m/%d/%Y").date().isoformat()
    except ValueError:
        log.warning("could not parse ActionDate %r", raw)
        return None


def _shape_history(raw: list[dict] | None) -> list[dict]:
    """Turn the API's [{ActionDate, HistoryAction}, ...] into our internal
    [{action_date, action}, ...] with ISO dates. Drops entries with no date
    and no action text.
    """
    if not raw:
        return []
    out = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        action_date = _normalize_action_date(entry.get("ActionDate"))
        action = (entry.get("HistoryAction") or "").strip()
        if not action and not action_date:
            continue
        out.append({"action_date": action_date, "action": action})
    return out


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

    is_current = is_current_session(session)

    for bill in bills:
        full_number = (bill.get("Bill") or "").strip()
        if not full_number:
            continue
        ldoa = bill.get("LDOA") or ""
        detail_path = out_dir / f"{full_number}.json"

        # Cache hit requires the file to exist AND match LDOA AND already
        # carry the history field — the latter forces a one-time backfill
        # of history into pre-existing detail files written before this
        # feature shipped.
        cached_detail = None
        if not force_refresh and detail_path.exists() and manifest.get(full_number) == ldoa:
            try:
                cached_detail = json.loads(detail_path.read_text())
            except json.JSONDecodeError:
                cached_detail = None
        if cached_detail is not None and "history" in cached_detail:
            bill["_detail"] = cached_detail
            skipped += 1
            continue

        try:
            sponsors = fetch_sponsors(
                client, full_number, session,
                is_current=is_current,
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
            log.warning("sponsor fetch failed for %s: %s", full_number, e)
            continue

        # History fetch is allowed to fail independently — we still want the
        # sponsor data on file. Bills with a failed history fetch get an
        # empty list, which compute_movement() handles gracefully.
        try:
            history_raw = fetch_history(
                client, full_number, session,
                is_current=is_current,
                force_refresh=force_refresh,
            )
            history = _shape_history(history_raw)
        except Exception as e:
            history = []
            errors_path.open("a").write(
                json.dumps({"bill": full_number, "session": session,
                            "endpoint": "billHistory",
                            "error": str(e),
                            "at": dt.datetime.utcnow().isoformat() + "Z"}) + "\n"
            )
            log.warning("history fetch failed for %s: %s", full_number, e)

        detail = {
            "bill": full_number,
            "session": session,
            "ldoa": ldoa,
            "sponsors": sponsors,  # [primary[], cosponsors[]]
            "history": history,    # [{action_date, action}, ...]
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
