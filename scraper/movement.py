"""
Compute the weekly "what moved this week" feed from per-bill action history.

Reads each ceremonial bill's history list (already shaped at fetch time by
fetch_bill_details._shape_history), filters to a recent window, classifies
each event into a bucket, and joins enough bill metadata for the site to
render a usable ticker.

Buckets
-------
- governor   : signed, vetoed, filed with Secretary of State, withdrawn
               because the identical bill was signed
- floor      : passed by either chamber, or passed both houses
- committee  : reported out of committee (with or without amendments)
- transfer   : received in the other chamber
- other      : substituted for/by, anything we haven't classified

The "introduced" event is *not* a bucket. We skip those because the
"what's new" panel already covers freshly-introduced bills, and including
intros here would double-report them every week.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)


# Ordered most-specific-first; first match wins.
#
# The NJ Leg API returns HistoryAction as English prose written by clerks, so
# we match on lowercased substrings rather than trying to lock down exact
# wording. Patterns observed empirically against the 2024 and 2026 sessions.
_CLASSIFIERS: list[tuple[str, re.Pattern]] = [
    # Governor actions (laws, vetoes, withdrawals because identical signed)
    ("governor", re.compile(r"\bapproved p\.l\.", re.IGNORECASE)),
    ("governor", re.compile(r"\bapproved by (the )?governor\b", re.IGNORECASE)),
    ("governor", re.compile(r"\bfiled with secretary of state\b", re.IGNORECASE)),
    ("governor", re.compile(r"\b(absolute|conditional|line item|pocket) veto\b", re.IGNORECASE)),
    ("governor", re.compile(r"\bwithout approval\b", re.IGNORECASE)),
    ("governor", re.compile(r"\bwithdrawn because approved\b", re.IGNORECASE)),
    # Floor passage in either chamber, or final passage of both
    ("floor",    re.compile(r"\bpassed (by the )?(assembly|senate)\b", re.IGNORECASE)),
    ("floor",    re.compile(r"\bpassed both houses\b", re.IGNORECASE)),
    # Reported out of committee — substantive committee action
    ("committee", re.compile(r"\breported (out of|from) (the )?(assembly|senate) committee\b", re.IGNORECASE)),
    ("committee", re.compile(r"\breported from committee\b", re.IGNORECASE)),
    ("committee", re.compile(r"\breported with amendments\b", re.IGNORECASE)),
    # Cross-chamber transfer
    ("transfer",  re.compile(r"\breceived in the (assembly|senate)\b", re.IGNORECASE)),
    # Substitutions and other procedural shuffling we don't have a special bucket for
    ("other",     re.compile(r"\bsubstituted (for|by)\b", re.IGNORECASE)),
    ("other",     re.compile(r"\bwithdrawn\b", re.IGNORECASE)),  # withdrawn for non-approval reasons
]


# Initial-introduction events. These are *deliberately excluded* from the
# movement feed because the site's "what's new" panel already surfaces newly
# introduced bills. Surfacing them again here would double-report.
_INTRODUCED = re.compile(
    r"^\s*introduced\b",  # most intros start with "Introduced, Referred to..."
    re.IGNORECASE,
)


# "Filed with Secretary of State" is the ambiguous event that can mean either
# (a) the governor has signed a bill/JR and it's been recorded as law, or
# (b) a single-chamber resolution (AR/SR) has been adopted and recorded.
# We disambiguate by checking whether both chambers have actually passed the
# legislation — only then does it count as a governor action.
_FILED_WITH_SOS = re.compile(r"\bfiled with secretary of state\b", re.IGNORECASE)

# Floor-passage patterns used by the both-chambers check. Mirrors the floor
# classifier above but split into per-chamber matchers so we can require one
# of each before promoting "filed with SoS" to the governor bucket.
_PASSED_ASSEMBLY = re.compile(
    r"\bpassed (by the )?assembly\b|\bresolution passed assembly\b",
    re.IGNORECASE,
)
_PASSED_SENATE = re.compile(
    r"\bpassed (by the )?senate\b|\bresolution passed senate\b|\bpassed both houses\b",
    re.IGNORECASE,
)


def _passed_both_chambers(events: list[dict], companion_events: list[dict] | None = None) -> bool:
    """True if the bill or its companion shows floor passage in BOTH chambers.

    Joint Resolutions and Bills need both Assembly and Senate to pass before
    they can reach the governor; companion bills (linked via IdenticalBillNumber)
    are how the same legislation moves through each chamber in parallel, so
    we union the two histories.
    """
    actions = [(e.get("action") or "") for e in events]
    if companion_events:
        actions.extend((e.get("action") or "") for e in companion_events)
    passed_assembly = any(_PASSED_ASSEMBLY.search(a) for a in actions)
    passed_senate = any(_PASSED_SENATE.search(a) for a in actions)
    return passed_assembly and passed_senate


# Bucket sort order when multiple events share a date — most consequential first.
_BUCKET_PRIORITY = {
    "governor": 0,
    "floor": 1,
    "committee": 2,
    "transfer": 3,
    "other": 4,
}


def classify(action: str) -> str | None:
    """Return the bucket for an action string, or None if it's an initial
    introduction (which we deliberately drop from the movement feed).

    Anything we can't classify still returns 'other' rather than None — only
    introductions are silently skipped.
    """
    if not action:
        return "other"
    if _INTRODUCED.search(action):
        return None
    for bucket, pattern in _CLASSIFIERS:
        if pattern.search(action):
            return bucket
    return "other"


def _parse_iso(date_str: str | None) -> dt.date | None:
    if not date_str:
        return None
    try:
        return dt.date.fromisoformat(date_str)
    except ValueError:
        return None


def compute_movement(
    records: Iterable[dict],
    history_dir: Path,
    window_days: int = 7,
    today: dt.date | None = None,
) -> dict:
    """Build the movement feed for one session's worth of bill records.

    Parameters
    ----------
    records : iterable of bill record dicts produced by build_site_data
        (must include `bill_id`, `full_number`, `session`, `synopsis`, etc.).
    history_dir : Path
        Directory containing per-bill detail JSON (e.g. data/raw/bill_details/2026).
        Each file is expected to carry a `history` list as written by
        fetch_bill_details. Bills whose file is missing or lacks history are
        silently skipped — no events contributed.
    window_days : int
        Number of days back from `today` to include. The window is inclusive
        on both ends.
    today : datetime.date, optional
        Anchor for the window. Defaults to UTC today. Exposed for testing.

    Returns
    -------
    dict with shape:
        {
          generated_at, window_start, window_end, window_days,
          counts_by_bucket: {bucket: int, ...},
          events: [event, ...]   # date desc, then bucket priority, then bill
        }
    """
    today = today or dt.datetime.utcnow().date()
    window_end = today
    window_start = today - dt.timedelta(days=window_days - 1)

    import json

    by_full: dict[tuple[str, str], dict] = {}
    for r in records:
        key = (str(r.get("session", "")), (r.get("full_number") or ""))
        by_full[key] = r

    # Read every bill's history once up front so we can cheaply look up a
    # companion bill's events when disambiguating "Filed with SoS" later.
    history_by_full: dict[tuple[str, str], list[dict]] = {}
    for (session, full_number) in by_full:
        if not full_number:
            continue
        history_path = history_dir / str(session) / f"{full_number}.json"
        if not history_path.exists():
            continue
        try:
            detail = json.loads(history_path.read_text())
        except (OSError, ValueError):
            continue
        history_by_full[(session, full_number)] = detail.get("history") or []

    events: list[dict] = []
    for (session, full_number), record in by_full.items():
        history_events = history_by_full.get((session, full_number))
        if history_events is None:
            continue

        # Look up companion bill's history if the record points to one.
        companion_full = (record.get("identical_bill") or "").strip() or None
        companion_events = (
            history_by_full.get((session, companion_full))
            if companion_full else None
        )

        for entry in history_events:
            action = (entry.get("action") or "").strip()
            action_date = _parse_iso(entry.get("action_date"))
            if not action_date or not action:
                continue
            if action_date < window_start or action_date > window_end:
                continue
            bucket = classify(action)
            if bucket is None:  # initial introduction — skip
                continue

            # "Filed with Secretary of State" only counts as a governor action
            # if the legislation has actually cleared both chambers (either
            # directly or via its identical companion). Otherwise it's a
            # single-chamber adoption record and the floor-passage event from
            # the same week already conveys it.
            if bucket == "governor" and _FILED_WITH_SOS.search(action):
                if not _passed_both_chambers(history_events, companion_events):
                    bucket = "other"

            events.append({
                "bill_id": record.get("bill_id"),
                "full_number": full_number,
                "session": str(session),
                "session_label": record.get("session_label"),
                "bill_type_label": record.get("bill_type_label"),
                "synopsis": record.get("synopsis"),
                "primary_category": record.get("primary_category"),
                "url": record.get("njleg_url"),
                "action_date": action_date.isoformat(),
                "action": action,
                "bucket": bucket,
            })

    events.sort(key=lambda e: (
        # Date desc, then bucket priority asc, then full bill number for stability
        -dt.date.fromisoformat(e["action_date"]).toordinal(),
        _BUCKET_PRIORITY.get(e["bucket"], 99),
        e["full_number"],
    ))

    counts: dict[str, int] = {}
    for e in events:
        counts[e["bucket"]] = counts.get(e["bucket"], 0) + 1

    return {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "window_days": window_days,
        "counts_by_bucket": counts,
        "events": events,
    }
