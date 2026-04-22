"""
Transform raw API pulls into the processed dataset and the site's JSON.

Pipeline per session:
  1. Read raw search files from data/raw/sessions/<year>/search_*.json.
  2. Apply the ceremonial filter; log rejects to data/processed/audit_rejected.csv.
  3. Read per-bill details from data/raw/bill_details/<year>/<bill>.json.
  4. Categorize; build a slim per-bill record.
  5. Write data/processed/bills.parquet (columnar, for future analysis) and
     site/data/bills.json + meta.json + sessions.json (for the web app).

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


def build_session_records(session: int) -> tuple[list[dict], list[dict]]:
    """
    Returns (kept_records, rejected_records). Rejected are bills the filter
    dropped, with a reason — used for audit_rejected.csv so a human can spot-check.
    """
    session_dir = DATA_RAW / "sessions" / str(session)
    if not session_dir.exists():
        raise FileNotFoundError(f"No raw pull found at {session_dir}. "
                                f"Run `python -m scraper fetch --session {session}` first.")

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

        if not is_ceremonial(synopsis):
            rejected.append({
                "bill_id": bill_id,
                "session": session,
                "full_number": full_number,
                "synopsis": synopsis,
                "reason": filter_reason(synopsis),
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

        kept.append({
            "bill_id": bill_id,
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


def write_outputs(all_records: list[dict], all_rejected: list[dict],
                  sessions_covered: list[int]) -> None:
    """Write processed parquet + site JSON files."""
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    SITE_DATA.mkdir(parents=True, exist_ok=True)

    # Processed dataset — committed to git so drift is visible in diffs.
    df = pd.DataFrame(all_records)
    df.to_parquet(DATA_PROCESSED / "bills.parquet", index=False)

    # Audit trail — committed, so every rule change shows up as a diff.
    pd.DataFrame(all_rejected).to_csv(
        DATA_PROCESSED / "audit_rejected.csv", index=False
    )

    # Site JSON — consumed directly by site/js/app.js.
    site_rows = _slim_for_site(all_records)
    (SITE_DATA / "bills.json").write_text(json.dumps(site_rows))

    (SITE_DATA / "sessions.json").write_text(json.dumps([
        {"value": s, "label": session_label(s)} for s in sorted(sessions_covered, reverse=True)
    ]))

    (SITE_DATA / "meta.json").write_text(json.dumps(_build_meta(all_records, sessions_covered)))

    log.info("wrote %d bills (%d rejected) across sessions %s",
             len(all_records), len(all_rejected), sessions_covered)


def _slim_for_site(records: list[dict]) -> list[dict]:
    """Trim what the browser doesn't need. Keeps the JSON small for GH Pages."""
    out = []
    for r in records:
        out.append({
            "id": r["bill_id"],
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
                {"name": s["name"], "role": s["role"]}
                for s in r["primary_sponsors"]
            ],
            "cosponsor_count": len(r["cosponsors"]),
            "bill_family_id": r["bill_family_id"],
            "url": r["njleg_url"],
        })
    return out


def _build_meta(records: list[dict], sessions_covered: list[int]) -> dict:
    now = dt.datetime.utcnow().isoformat() + "Z"
    if not records:
        return {
            "updated_at": now,
            "total_bills": 0,
            "sessions_covered": sessions_covered,
        }
    df = pd.DataFrame(records)
    by_category = df["primary_category"].value_counts().to_dict()
    by_session = df.groupby("session").size().to_dict()
    became_law = int(df["became_law"].sum())
    return {
        "updated_at": now,
        "total_bills": int(len(df)),
        "sessions_covered": sessions_covered,
        "earliest_session": min(sessions_covered) if sessions_covered else None,
        "latest_session": max(sessions_covered) if sessions_covered else None,
        "by_primary_category": {k: int(v) for k, v in by_category.items()},
        "by_session": {str(k): int(v) for k, v in by_session.items()},
        "total_became_law": became_law,
        "pass_rate": round(became_law / len(df), 4) if len(df) else 0.0,
    }


def build_sessions(sessions: Iterable[int]) -> dict[str, Any]:
    """Run the full build for one or more sessions. Returns a summary dict."""
    all_records: list[dict] = []
    all_rejected: list[dict] = []
    sessions_covered: list[int] = []

    for s in sessions:
        try:
            kept, rejected = build_session_records(s)
        except FileNotFoundError as e:
            log.warning("skipping session %s: %s", s, e)
            continue
        all_records.extend(kept)
        all_rejected.extend(rejected)
        sessions_covered.append(s)

    write_outputs(all_records, all_rejected, sessions_covered)
    return {
        "sessions": sessions_covered,
        "kept": len(all_records),
        "rejected": len(all_rejected),
    }
