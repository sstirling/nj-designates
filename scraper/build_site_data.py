"""
Transform raw API pulls into the processed dataset and the site's JSON.

Pipeline per session:
  1. Read raw search files from data/raw/sessions/<year>/search_*.json.
  2. Apply the ceremonial filter; log rejects to data/processed/audit_rejected.csv.
  3. Read per-bill details from data/raw/bill_details/<year>/<bill>.json.
  4. Categorize; build a slim per-bill record.
  5. Write data/processed/bills.parquet (columnar, for future analysis) and
     data/bills.json + meta.json + sessions.json (for the web app).

Every quantitative value the site displays comes from meta.json, which this
script generates. Nothing is hand-typed in site copy.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from scraper.categorize import all_category_tags, categorize
from scraper.config import (
    BASE_URL,
    DATA_PROCESSED,
    DATA_RAW,
    SITE_DATA,
    session_label,
)
from scraper.decode_status import (
    became_law,
    governor_action_label,
    status_label,
)
from scraper.filter_ceremonial import filter_reason, is_ceremonial
from scraper.movement import compute_movement

log = logging.getLogger(__name__)


def _bill_type_label(raw: str) -> str:
    code = (raw or "").strip()
    return {
        "A": "Assembly bill",
        "S": "Senate bill",
        "AJR": "Assembly joint resolution",
        "SJR": "Senate joint resolution",
        "ACR": "Assembly concurrent resolution",
        "SCR": "Senate concurrent resolution",
        "AR": "Assembly resolution",
        "SR": "Senate resolution",
    }.get(code, code or "Unknown")


def _parse_bill_prefix(full_number: str) -> str:
    """A444 → 'A'; AJR57 → 'AJR'; S310 → 'S'."""
    i = 0
    while i < len(full_number) and full_number[i].isalpha():
        i += 1
    return full_number[:i]


def _sponsor_dicts(sponsors_raw: list[list[dict]] | None) -> tuple[list[dict], list[dict]]:
    if not sponsors_raw or len(sponsors_raw) < 2:
        return [], []
    primaries = sponsors_raw[0] or []
    cosponsors = sponsors_raw[1] or []

    def shape(lst: list[dict], default_role: str) -> list[dict]:
        out = []
        for s in lst:
            bio = (s.get("BioLink") or "").strip() or None
            if bio and not bio.startswith("http"):
                bio = f"{BASE_URL}{bio}"
            out.append({
                "name": (s.get("Full_Name") or "").strip(),
                "role": (s.get("SponsorDescription") or default_role).strip(),
                "bio_url": bio,
            })
        return out

    return shape(primaries, "as Primary Sponsor"), shape(cosponsors, "as Co-Sponsor")


def _family_id(bill: dict, session: int) -> str:
    """
    Cluster reintroductions. A bill is the head of its family unless it
    explicitly points to a prior session version.
    """
    last = (bill.get("LastSessionFullBillNumber") or "").strip()
    if last:
        # pick the first bill number out of the space-separated list
        first = last.split()[0]
        return f"family-{first}"
    return f"family-{session}-{(bill.get('Bill') or '').strip()}"


def _ldoa_to_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _load_prior_bill_state() -> tuple[set[str], dict[str, str]]:
    """Inspect the committed parquet for (known_bill_ids, first_seen_by_id).

    - known_bill_ids: every bill_id present in the prior snapshot, regardless
      of whether it had a first_seen value. A bill in this set was already in
      the archive last week, so it is NOT new today.
    - first_seen_by_id: bill_id -> ISO date for rows that already carry a
      first_seen value (rows written after this feature shipped).

    The split matters on the first run after this feature: the prior parquet
    has the bills but no first_seen column. Without the known-set, we'd mark
    every existing bill "first seen today" — fabrication. With it, those bills
    correctly stay null (we know they're not new, but we don't know when they
    actually first appeared).
    """
    bills_parquet = DATA_PROCESSED / "bills.parquet"
    if not bills_parquet.exists():
        return set(), {}
    try:
        import pyarrow.parquet as pq
        table = pq.read_table(bills_parquet)
    except Exception:
        return set(), {}
    known: set[str] = set()
    fs_map: dict[str, str] = {}
    has_first_seen = "first_seen" in table.column_names
    for row in table.to_pylist():
        bid = row.get("bill_id")
        if not bid:
            continue
        known.add(bid)
        if has_first_seen:
            fs = row.get("first_seen")
            if fs:
                fs_map[bid] = fs
    return known, fs_map


def build_session_records(session: int) -> tuple[list[dict], list[dict]]:
    """
    Returns (kept_records, rejected_records). Rejected are bills the filter
    dropped, with a reason — used for audit_rejected.csv so a human can spot-check.
    """
    session_dir = DATA_RAW / "sessions" / str(session)
    if not session_dir.exists():
        raise FileNotFoundError(f"No raw pull found at {session_dir}. "
                                f"Run `python -m scraper fetch --session {session}` first.")

    prior_known, prior_first_seen = _load_prior_bill_state()
    today = dt.datetime.utcnow().date().isoformat()

    # Dedupe across keyword search files by full bill number.
    by_full_number: dict[str, dict] = {}
    for fp in sorted(session_dir.glob("search_*.json")):
        payload = json.loads(fp.read_text())
        for b in payload:
            full = (b.get("Bill") or "").strip()
            if full:
                by_full_number.setdefault(full, b)

    kept: list[dict] = []
    rejected: list[dict] = []

    for full_number, bill in by_full_number.items():
        synopsis = (bill.get("Synopsis") or "").strip()
        bill_id = f"{session}-{full_number}"

        if not is_ceremonial(synopsis, bill_id=bill_id):
            rejected.append({
                "bill_id": bill_id,
                "session": session,
                "full_number": full_number,
                "synopsis": synopsis,
                "reason": filter_reason(synopsis, bill_id=bill_id),
            })
            continue

        primary, subs = categorize(synopsis, bill_id=bill_id)
        tags = all_category_tags(synopsis, bill_id=bill_id)

        detail_path = DATA_RAW / "bill_details" / str(session) / f"{full_number}.json"
        detail = None
        if detail_path.exists():
            try:
                detail = json.loads(detail_path.read_text())
            except json.JSONDecodeError:
                detail = None

        primary_sponsors, cosponsors = _sponsor_dicts(
            detail.get("sponsors") if detail else None
        )

        prefix = _parse_bill_prefix(full_number)
        status_code = (bill.get("CurrentStatus") or "").strip() or None
        gov_code = (bill.get("GovernorAction") or "").strip() or None

        # Three-way first_seen logic:
        # - known prior date → preserve it
        # - bill was in last week's snapshot but has no recorded date → null
        #   (legacy row from before this feature; we don't fabricate a date)
        # - bill was NOT in last week's snapshot → today (genuinely new)
        if bill_id in prior_first_seen:
            first_seen = prior_first_seen[bill_id]
        elif bill_id in prior_known:
            first_seen = None
        else:
            first_seen = today

        kept.append({
            "bill_id": bill_id,
            "first_seen": first_seen,
            "session": str(session),
            "session_label": session_label(session),
            "bill_type": prefix,
            "bill_type_label": _bill_type_label(prefix),
            "bill_number": bill.get("BillNumber"),
            "full_number": full_number,
            "synopsis": synopsis,
            "ldoa": _ldoa_to_date(bill.get("LDOA")),
            "current_status_code": status_code,
            "current_status_label": status_label(status_code),
            "governor_action_code": gov_code,
            "governor_action_label": governor_action_label(gov_code),
            "became_law": became_law(gov_code),
            "primary_category": primary,
            "categories": tags,
            "subcategories": subs,
            "primary_sponsors": primary_sponsors,
            "cosponsors": cosponsors,
            "num_primary_sponsors": bill.get("NumberPrimeSponsors"),
            "identical_bill": (bill.get("IdenticalBillNumber") or "").strip() or None,
            "last_session_bill": (bill.get("LastSessionFullBillNumber") or "").strip() or None,
            "bill_family_id": _family_id(bill, session),
            "njleg_url": f"{BASE_URL}/bill-search/{session}/{full_number}",
            "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
        })

    return kept, rejected


def _read_prior_meta_updated_at() -> str | None:
    """Pull `updated_at` from the existing meta.json before we overwrite it.

    The site uses this as `previous_refresh_at` so the "what's new" callout
    can frame counts relative to the last refresh ("4 new since April 27").
    """
    meta_path = SITE_DATA / "meta.json"
    if not meta_path.exists():
        return None
    try:
        prior = json.loads(meta_path.read_text())
        return prior.get("updated_at")
    except Exception:
        return None


def write_outputs(all_records: list[dict], all_rejected: list[dict],
                  sessions_covered: list[int]) -> None:
    """Write processed parquet + site JSON files."""
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    SITE_DATA.mkdir(parents=True, exist_ok=True)

    # Capture before any overwrite — we use this to anchor the "what's new"
    # callout's date range on the previous refresh, not the current one.
    previous_refresh_at = _read_prior_meta_updated_at()

    # Processed dataset — committed to git so drift is visible in diffs.
    df = pd.DataFrame(all_records)
    df.to_parquet(DATA_PROCESSED / "bills.parquet", index=False)

    # Audit trail — committed, so every rule change shows up as a diff.
    pd.DataFrame(all_rejected).to_csv(
        DATA_PROCESSED / "audit_rejected.csv", index=False
    )

    # Site JSON — consumed directly by js/app.js.
    site_rows = _slim_for_site(all_records)
    (SITE_DATA / "bills.json").write_text(json.dumps(site_rows))

    (SITE_DATA / "sessions.json").write_text(json.dumps([
        {"value": s, "label": session_label(s)} for s in sorted(sessions_covered, reverse=True)
    ]))

    # Weekly "what moved" feed. Closed sessions are filtered out naturally
    # because their history events never fall inside the recent date window.
    movement = compute_movement(all_records, DATA_RAW / "bill_details")
    (SITE_DATA / "movement.json").write_text(json.dumps(movement))

    (SITE_DATA / "meta.json").write_text(json.dumps(
        _build_meta(all_records, sessions_covered, previous_refresh_at, movement)
    ))

    log.info("wrote %d bills (%d rejected) across sessions %s; "
             "%d movement events in last %d days",
             len(all_records), len(all_rejected), sessions_covered,
             len(movement["events"]), movement["window_days"])


def _slim_for_site(records: list[dict]) -> list[dict]:
    """Trim what the browser doesn't need. Keeps the JSON small for GH Pages."""
    out = []
    for r in records:
        out.append({
            "id": r["bill_id"],
            "first_seen": r.get("first_seen"),
            "session": r["session"],
            "session_label": r["session_label"],
            "bill_type": r["bill_type"],
            "bill_type_label": r["bill_type_label"],
            "full_number": r["full_number"],
            "synopsis": r["synopsis"],
            "ldoa": r["ldoa"],
            "status_code": r["current_status_code"],
            "status_label": r["current_status_label"],
            "gov_action_code": r["governor_action_code"],
            "gov_action_label": r["governor_action_label"],
            "became_law": r["became_law"],
            "primary_category": r["primary_category"],
            "categories": r["categories"],
            "subcategories": r["subcategories"],
            "primary_sponsors": [
                {"name": s["name"], "role": s["role"], "bio_url": s.get("bio_url")}
                for s in r["primary_sponsors"]
            ],
            "cosponsor_count": len(r["cosponsors"]),
            "bill_family_id": r["bill_family_id"],
            "url": r["njleg_url"],
        })
    return out


def _build_meta(records: list[dict], sessions_covered: list[int],
                previous_refresh_at: str | None = None,
                movement: dict | None = None) -> dict:
    now = dt.datetime.utcnow().isoformat() + "Z"
    today = dt.datetime.utcnow().date().isoformat()
    moved_this_refresh = len((movement or {}).get("events") or [])
    if not records:
        return {
            "updated_at": now,
            "previous_refresh_at": previous_refresh_at,
            "total_bills": 0,
            "sessions_covered": sessions_covered,
            "added_this_refresh": 0,
            "moved_this_refresh": moved_this_refresh,
        }
    df = pd.DataFrame(records)
    by_category = df["primary_category"].value_counts().to_dict()
    by_session = df.groupby("session").size().to_dict()
    became_law = int(df["became_law"].sum())
    # Bills the scraper tagged with today's date — i.e., didn't exist in last
    # week's snapshot. Drives the "what's new" callout on the site.
    added_this_refresh = int(
        df["first_seen"].fillna("").eq(today).sum()
    ) if "first_seen" in df.columns else 0
    return {
        "updated_at": now,
        "previous_refresh_at": previous_refresh_at,
        "total_bills": int(len(df)),
        "sessions_covered": sessions_covered,
        "earliest_session": min(sessions_covered) if sessions_covered else None,
        "latest_session": max(sessions_covered) if sessions_covered else None,
        "by_primary_category": {k: int(v) for k, v in by_category.items()},
        "by_session": {str(k): int(v) for k, v in by_session.items()},
        "total_became_law": became_law,
        "pass_rate": round(became_law / len(df), 4) if len(df) else 0.0,
        "added_this_refresh": added_this_refresh,
        "moved_this_refresh": moved_this_refresh,
    }


def build_sessions(sessions: Iterable[int], augment: bool = False) -> dict[str, Any]:
    """Run the build for one or more sessions. Returns a summary dict.

    If augment=True, preserves rows in the existing committed bills.parquet and
    audit_rejected.csv for sessions NOT being rebuilt. The CI weekly job uses
    this so refreshing only the current session doesn't drop the historical
    archive — the runner has no raw API data for closed sessions, so the
    committed parquet is the source of truth for them.
    """
    refresh_targets = [int(s) for s in sessions]
    refresh_str = {str(s) for s in refresh_targets}

    all_records: list[dict] = []
    all_rejected: list[dict] = []
    sessions_covered: list[int] = []

    if augment:
        bills_parquet = DATA_PROCESSED / "bills.parquet"
        if bills_parquet.exists():
            # pyarrow.to_pylist() returns native Python lists/dicts; pandas
            # read_parquet returns numpy ndarrays for list columns, which then
            # break json.dumps when bills.json is written.
            import pyarrow.parquet as pq
            table = pq.read_table(bills_parquet)
            preserved_sessions: set[str] = set()
            for row in table.to_pylist():
                if str(row.get("session")) not in refresh_str:
                    all_records.append(row)
                    preserved_sessions.add(str(row["session"]))
            sessions_covered.extend(int(s) for s in sorted(preserved_sessions))
            log.info("augment: preserved %d records from %d prior sessions",
                     len(all_records), len(preserved_sessions))

        rejected_csv = DATA_PROCESSED / "audit_rejected.csv"
        if rejected_csv.exists():
            existing_rej = pd.read_csv(rejected_csv)
            kept_rej = existing_rej[
                ~existing_rej["session"].astype(str).isin(refresh_str)
            ]
            all_rejected.extend(kept_rej.to_dict("records"))

    for s in refresh_targets:
        try:
            kept_records, rejected_records = build_session_records(s)
        except FileNotFoundError as e:
            log.warning("skipping session %s: %s", s, e)
            continue
        all_records.extend(kept_records)
        all_rejected.extend(rejected_records)
        if s not in sessions_covered:
            sessions_covered.append(s)

    write_outputs(all_records, all_rejected, sorted(sessions_covered))
    return {
        "sessions": sorted(sessions_covered),
        "kept": len(all_records),
        "rejected": len(all_rejected),
        "augment": augment,
    }
