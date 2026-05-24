"""Tests for the weekly movement feed.

The movement feed surfaces bills that *advanced* in the last N days — passed
committee, passed a chamber, were signed into law, etc. The site's "what's
new" panel covers freshly-introduced bills, so initial introductions are
deliberately excluded from movement to avoid double-counting.

These tests pin down:
  - the HistoryAction → bucket classifier against the patterns we've seen
    in the wild,
  - that initial introductions are dropped,
  - that the date window is inclusive on both ends and excludes everything
    outside it,
  - that bills missing from the records list (e.g., dropped from the dataset
    because reclassified as non-ceremonial) contribute zero events,
  - that the output is ordered correctly so the site can render top-down.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from scraper.movement import classify, compute_movement


# --- classifier ---------------------------------------------------------

@pytest.mark.parametrize("action,expected", [
    # Governor actions — signed, vetoed, withdrawn-because-signed
    ("Approved P.L.2025, JR-17.", "governor"),
    ("Approved by Governor", "governor"),
    ("Approved by the Governor", "governor"),
    ("Filed with Secretary of State", "governor"),
    ("Absolute Veto", "governor"),
    ("Conditional Veto", "governor"),
    ("Line Item Veto", "governor"),
    ("Pocket Veto", "governor"),
    ("Without Approval", "governor"),
    ("Withdrawn Because Approved P.L.2025, JR-17.", "governor"),
    # Floor passage
    ("Passed by the Assembly (75-0-0)", "floor"),
    ("Passed by the Senate (38-0)", "floor"),
    ("Passed Senate (Passed Both Houses) (38-0)", "floor"),
    ("Passed Assembly", "floor"),
    # Committee action
    ("Reported out of Assembly Committee, 2nd Reading", "committee"),
    ("Reported out of Senate Committee with Amendments", "committee"),
    ("Reported from Assembly Committee", "committee"),
    ("Reported from Committee", "committee"),
    # Cross-chamber transfer
    ("Received in the Senate, Referred to Senate Environment and Energy Committee", "transfer"),
    ("Received in the Assembly without Reference, 2nd Reading", "transfer"),
    # Other procedural
    ("Substituted for SJR89 (1R)", "other"),
    ("Substituted by SJR89", "other"),
    ("Withdrawn from Consideration", "other"),
])
def test_classify_buckets(action, expected):
    assert classify(action) == expected


@pytest.mark.parametrize("action", [
    "Introduced, Referred to Assembly Tourism, Gaming and the Arts Committee",
    "Introduced in the Senate, Referred to Senate Environment and Energy Committee",
    "Introduced",
])
def test_classify_introductions_return_none(action):
    """Intros are silently dropped from the movement feed — the 'what's new'
    panel already covers them."""
    assert classify(action) is None


def test_classify_unknown_falls_back_to_other():
    """An action we don't recognise still counts as movement — better to
    surface it as 'other' than swallow it silently."""
    assert classify("Some clerk made up a new phrase") == "other"


# --- compute_movement end-to-end ---------------------------------------

def _record(full_number: str, session: str = "2026", **overrides) -> dict:
    base = {
        "bill_id": f"{session}-{full_number}",
        "full_number": full_number,
        "session": session,
        "session_label": "2026-27",
        "bill_type_label": "Assembly bill",
        "synopsis": f"Designates state thing for {full_number}.",
        "primary_category": "state_symbol",
        "njleg_url": f"https://example.test/{full_number}",
    }
    base.update(overrides)
    return base


def _write_history(tmp_path, session, full_number, events):
    """Write a per-bill detail file with the given history events."""
    session_dir = tmp_path / str(session)
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / f"{full_number}.json").write_text(json.dumps({
        "bill": full_number,
        "session": int(session),
        "ldoa": "2026-01-01T00:00:00.000Z",
        "sponsors": [[], []],
        "history": events,
    }))


def test_compute_movement_basic(tmp_path):
    """Events inside the window appear; introductions don't; output is ordered."""
    today = dt.date(2026, 5, 24)
    _write_history(tmp_path, "2026", "A1", [
        {"action_date": "2026-01-13", "action": "Introduced, Referred to Assembly Committee"},
        {"action_date": "2026-05-20", "action": "Reported out of Assembly Committee, 2nd Reading"},
        {"action_date": "2026-05-22", "action": "Passed by the Assembly (75-0-0)"},
    ])
    _write_history(tmp_path, "2026", "A2", [
        {"action_date": "2026-05-23", "action": "Approved P.L.2026, JR-1."},
    ])
    records = [_record("A1"), _record("A2")]

    feed = compute_movement(records, tmp_path, window_days=7, today=today)

    assert feed["window_start"] == "2026-05-18"
    assert feed["window_end"] == "2026-05-24"
    assert feed["window_days"] == 7

    # Three events: A1 reported (committee), A1 passed (floor), A2 signed (governor).
    # The intro is filtered out.
    actions = [(e["full_number"], e["bucket"]) for e in feed["events"]]
    assert ("A1", "committee") in actions
    assert ("A1", "floor") in actions
    assert ("A2", "governor") in actions
    assert len(feed["events"]) == 3

    # Sort: date desc, then bucket priority (governor < floor < committee).
    # 5/23 governor first, then 5/22 floor, then 5/20 committee.
    assert [e["action_date"] for e in feed["events"]] == [
        "2026-05-23", "2026-05-22", "2026-05-20"
    ]

    assert feed["counts_by_bucket"] == {"governor": 1, "floor": 1, "committee": 1}


def test_compute_movement_excludes_events_outside_window(tmp_path):
    today = dt.date(2026, 5, 24)
    _write_history(tmp_path, "2026", "A1", [
        # Way too old
        {"action_date": "2026-01-13", "action": "Passed by the Assembly"},
        # One day before the window starts (window = 5/18..5/24 inclusive)
        {"action_date": "2026-05-17", "action": "Passed by the Senate"},
        # One day inside the window — should appear
        {"action_date": "2026-05-18", "action": "Approved P.L.2026, JR-1."},
        # In the future — exclude
        {"action_date": "2026-06-01", "action": "Approved P.L.2026, JR-2."},
    ])
    feed = compute_movement([_record("A1")], tmp_path, window_days=7, today=today)
    assert [e["action_date"] for e in feed["events"]] == ["2026-05-18"]


def test_compute_movement_missing_history_file_is_safe(tmp_path):
    """A bill in the dataset with no detail file on disk contributes nothing
    and doesn't crash."""
    today = dt.date(2026, 5, 24)
    feed = compute_movement([_record("A999")], tmp_path, window_days=7, today=today)
    assert feed["events"] == []
    assert feed["counts_by_bucket"] == {}


def test_compute_movement_bill_not_in_records_is_excluded(tmp_path):
    """If a bill's history file exists but the bill isn't in the records list
    (e.g., reclassified out of scope), its events don't surface — we wouldn't
    have category/url metadata to render them anyway."""
    today = dt.date(2026, 5, 24)
    _write_history(tmp_path, "2026", "A_dropped", [
        {"action_date": "2026-05-20", "action": "Passed by the Assembly"},
    ])
    _write_history(tmp_path, "2026", "A_kept", [
        {"action_date": "2026-05-20", "action": "Passed by the Assembly"},
    ])

    feed = compute_movement([_record("A_kept")], tmp_path, window_days=7, today=today)
    nums = [e["full_number"] for e in feed["events"]]
    assert nums == ["A_kept"]


def test_compute_movement_event_metadata_joined_from_record(tmp_path):
    """Each event carries enough joined metadata for the site to render
    a link, category, and synopsis without re-fetching."""
    today = dt.date(2026, 5, 24)
    _write_history(tmp_path, "2026", "A42", [
        {"action_date": "2026-05-22", "action": "Approved P.L.2026, JR-1."},
    ])
    records = [_record(
        "A42",
        synopsis="Designates the official state muffin.",
        primary_category="state_symbol",
        njleg_url="https://www.njleg.state.nj.us/bill-search/2026/A42",
    )]

    feed = compute_movement(records, tmp_path, window_days=7, today=today)
    event = feed["events"][0]
    assert event["bill_id"] == "2026-A42"
    assert event["synopsis"] == "Designates the official state muffin."
    assert event["primary_category"] == "state_symbol"
    assert event["url"] == "https://www.njleg.state.nj.us/bill-search/2026/A42"
    assert event["bucket"] == "governor"


def test_filed_with_sos_demoted_when_single_chamber_only(tmp_path):
    """An AR/SR resolution that's been filed with the Secretary of State after
    passing one chamber should NOT show up as 'governor' — those bill types
    never go to the governor at all. The 'Filed with SoS' event in that case
    is just the formal record of the chamber's adoption.

    Regression: AR130/2026 passed Assembly and was filed with SoS the same
    day; its companion SR96 was still in Senate committee. We were calling
    that 'Governor's desk' even though no governor involvement was possible.
    """
    today = dt.date(2026, 5, 24)
    _write_history(tmp_path, "2026", "AR130", [
        {"action_date": "2026-05-18", "action": "Resolution Passed Assembly 76-1-0"},
        {"action_date": "2026-05-18", "action": "Filed with Secretary of State"},
    ])
    _write_history(tmp_path, "2026", "SR96", [
        {"action_date": "2026-05-11", "action": "Introduced in the Senate, Referred to committee"},
    ])
    records = [
        _record("AR130", identical_bill="SR96"),
        _record("SR96",  identical_bill="AR130"),
    ]

    feed = compute_movement(records, tmp_path, window_days=7, today=today)
    sos_events = [e for e in feed["events"] if "Filed with Secretary" in e["action"]]
    assert len(sos_events) == 1
    assert sos_events[0]["bucket"] == "other", \
        "Filed-with-SoS for a single-chamber resolution should not claim governor's-desk status"


def test_filed_with_sos_stays_governor_when_both_chambers_passed(tmp_path):
    """For a Joint Resolution that's cleared both chambers, the 'Filed with
    Secretary of State' event correctly represents the law being recorded.
    Don't demote in that case."""
    today = dt.date(2026, 5, 24)
    _write_history(tmp_path, "2026", "AJR42", [
        {"action_date": "2026-04-01", "action": "Passed by the Assembly (75-0-0)"},
        {"action_date": "2026-05-10", "action": "Passed by the Senate (38-0)"},
        {"action_date": "2026-05-20", "action": "Filed with Secretary of State"},
    ])
    feed = compute_movement([_record("AJR42")], tmp_path, window_days=7, today=today)
    sos = next(e for e in feed["events"] if "Filed with Secretary" in e["action"])
    assert sos["bucket"] == "governor"


def test_filed_with_sos_promoted_via_companion(tmp_path):
    """If the bill's own history only shows one chamber but its identical
    companion shows the other, the both-chambers test passes and 'Filed
    with SoS' stays in the governor bucket. Companion bills are how the
    same legislation moves through both chambers in parallel."""
    today = dt.date(2026, 5, 24)
    # Assembly side: passed Assembly + filed with SoS. No Senate event on
    # its own history.
    _write_history(tmp_path, "2026", "AJR1", [
        {"action_date": "2026-05-15", "action": "Passed by the Assembly (75-0-0)"},
        {"action_date": "2026-05-20", "action": "Filed with Secretary of State"},
    ])
    # Senate companion shows Senate floor passage.
    _write_history(tmp_path, "2026", "SJR1", [
        {"action_date": "2026-05-18", "action": "Passed by the Senate (38-0)"},
    ])
    records = [
        _record("AJR1", identical_bill="SJR1"),
        _record("SJR1", identical_bill="AJR1"),
    ]
    feed = compute_movement(records, tmp_path, window_days=7, today=today)
    sos = next(e for e in feed["events"] if e["full_number"] == "AJR1"
               and "Filed with Secretary" in e["action"])
    assert sos["bucket"] == "governor"


def test_approved_pl_stays_governor_regardless(tmp_path):
    """A bill explicitly carrying 'Approved P.L.' is inherently both-chambers-
    passed by definition — we don't second-guess that classification even if
    the same-bill history happens to look thin (API lag, etc.)."""
    today = dt.date(2026, 5, 24)
    _write_history(tmp_path, "2026", "AJR99", [
        {"action_date": "2026-05-22", "action": "Approved P.L.2026, JR-5."},
    ])
    feed = compute_movement([_record("AJR99")], tmp_path, window_days=7, today=today)
    assert feed["events"][0]["bucket"] == "governor"


def test_compute_movement_no_history_field_in_detail(tmp_path):
    """A detail file from before this feature shipped (no `history` key) is
    treated as 'no events' rather than crashing the build."""
    today = dt.date(2026, 5, 24)
    session_dir = tmp_path / "2026"
    session_dir.mkdir(parents=True)
    (session_dir / "A1.json").write_text(json.dumps({
        "bill": "A1", "session": 2026, "ldoa": "", "sponsors": [[], []],
        # no "history" key
    }))
    feed = compute_movement([_record("A1")], tmp_path, window_days=7, today=today)
    assert feed["events"] == []
