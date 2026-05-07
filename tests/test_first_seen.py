"""Tests for first_seen tracking in the build pipeline.

The site uses first_seen to power the "what's new this week" callout. The
contract is:

  - A bill already in last week's parquet WITH a first_seen value keeps it.
  - A bill in last week's parquet WITHOUT first_seen (legacy row from before
    this feature) stays null. We don't fabricate dates we don't know.
  - A bill that wasn't in last week's parquet is tagged with today's date.

Also verifies that previous_refresh_at on meta.json is captured BEFORE the
file is overwritten, since that timestamp anchors the callout's date range.
"""

from __future__ import annotations

import datetime as dt
import json

import pandas as pd
import pyarrow.parquet as pq
import pytest

from scraper import build_site_data
from scraper.build_site_data import build_sessions


def _seed_record(session: str, idx: int, first_seen: str | None = "__sentinel__") -> dict:
    """Schema-complete row. Pass first_seen=None to omit it (legacy rows);
    pass an ISO date to include it; default sentinel means "do not add the key
    at all" (mimics rows from a parquet that predates the feature)."""
    full = f"A{idx}"
    row = {
        "bill_id": f"{session}-{full}",
        "session": session,
        "session_label": f"{session}-{int(session) + 1}",
        "bill_type": "A",
        "bill_type_label": "Assembly bill",
        "bill_number": str(idx),
        "full_number": full,
        "synopsis": f"Designates state thing #{idx}.",
        "ldoa": "2024-01-01",
        "current_status_code": "100",
        "current_status_label": "Introduced",
        "governor_action_code": None,
        "governor_action_label": None,
        "became_law": False,
        "primary_category": "state_symbol",
        "categories": ["state_symbol"],
        "subcategories": [],
        "primary_sponsors": [],
        "cosponsors": [],
        "num_primary_sponsors": 0,
        "identical_bill": None,
        "last_session_bill": None,
        "bill_family_id": f"family-{session}-{full}",
        "njleg_url": "",
        "fetched_at": "2025-01-01T00:00:00Z",
    }
    if first_seen != "__sentinel__":
        row["first_seen"] = first_seen
    return row


@pytest.fixture
def isolated_data_dirs(tmp_path, monkeypatch):
    processed = tmp_path / "processed"
    processed.mkdir()
    monkeypatch.setattr(build_site_data, "DATA_PROCESSED", processed)
    monkeypatch.setattr(build_site_data, "SITE_DATA", tmp_path)
    return tmp_path, processed


def test_load_prior_bill_state_legacy_parquet(isolated_data_dirs):
    """Parquet without first_seen column → known set populated, fs map empty."""
    _, processed = isolated_data_dirs
    pd.DataFrame([_seed_record("2026", 1), _seed_record("2026", 2)]).to_parquet(
        processed / "bills.parquet", index=False
    )

    known, fs_map = build_site_data._load_prior_bill_state()
    assert known == {"2026-A1", "2026-A2"}
    assert fs_map == {}


def test_load_prior_bill_state_with_first_seen(isolated_data_dirs):
    """Mix of rows with and without first_seen → both maps populated correctly."""
    _, processed = isolated_data_dirs
    pd.DataFrame([
        _seed_record("2026", 1, first_seen="2026-04-27"),
        _seed_record("2026", 2, first_seen=None),       # legacy row, null
        _seed_record("2026", 3, first_seen="2026-05-04"),
    ]).to_parquet(processed / "bills.parquet", index=False)

    known, fs_map = build_site_data._load_prior_bill_state()
    assert known == {"2026-A1", "2026-A2", "2026-A3"}
    assert fs_map == {"2026-A1": "2026-04-27", "2026-A3": "2026-05-04"}


def test_load_prior_bill_state_no_parquet(isolated_data_dirs):
    """No prior parquet → empty results, no crash."""
    known, fs_map = build_site_data._load_prior_bill_state()
    assert known == set()
    assert fs_map == {}


def test_first_seen_three_way_merge(isolated_data_dirs, monkeypatch):
    """End-to-end via build_sessions(augment=True):

      - bill kept from prior parquet WITH date → preserved
      - bill kept from prior parquet WITHOUT date (legacy) → still null
      - bill new today → today's date
    """
    site, processed = isolated_data_dirs

    # Prior snapshot: A1 has a recorded first_seen, A2 is legacy (no field).
    pd.DataFrame([
        _seed_record("2026", 1, first_seen="2026-04-27"),
        _seed_record("2026", 2, first_seen=None),
    ]).to_parquet(processed / "bills.parquet", index=False)

    today = dt.datetime.utcnow().date().isoformat()

    def fake_build_session_records(session: int):
        # Pretend the scrape returned A1, A2 (still there), plus a brand-new A3.
        # build_session_records itself is what assigns first_seen; we replicate
        # its logic here by reading prior state — same merge function under test.
        prior_known, prior_fs = build_site_data._load_prior_bill_state()
        kept = []
        for idx in (1, 2, 3):
            bill_id = f"2026-A{idx}"
            if bill_id in prior_fs:
                fs = prior_fs[bill_id]
            elif bill_id in prior_known:
                fs = None
            else:
                fs = today
            kept.append(_seed_record("2026", idx, first_seen=fs))
        return kept, []

    monkeypatch.setattr(build_site_data, "build_session_records",
                        fake_build_session_records)

    summary = build_sessions([2026], augment=True)
    assert summary["kept"] == 3

    # Check bills.json — what the site actually consumes.
    bills = json.loads((site / "bills.json").read_text())
    by_id = {b["id"]: b for b in bills}
    assert by_id["2026-A1"]["first_seen"] == "2026-04-27"
    assert by_id["2026-A2"]["first_seen"] is None
    assert by_id["2026-A3"]["first_seen"] == today


def test_meta_added_this_refresh_count(isolated_data_dirs, monkeypatch):
    """meta.json reports how many bills were tagged today — drives the callout."""
    site, _ = isolated_data_dirs
    today = dt.datetime.utcnow().date().isoformat()

    def fake_build_session_records(session: int):
        return ([
            _seed_record("2026", 1, first_seen=today),
            _seed_record("2026", 2, first_seen=today),
            _seed_record("2026", 3, first_seen="2026-04-27"),  # carried over
        ], [])

    monkeypatch.setattr(build_site_data, "build_session_records",
                        fake_build_session_records)

    build_sessions([2026], augment=False)

    meta = json.loads((site / "meta.json").read_text())
    assert meta["added_this_refresh"] == 2
    assert meta["total_bills"] == 3


def test_previous_refresh_at_captured_before_overwrite(isolated_data_dirs, monkeypatch):
    """The prior meta.json's updated_at must be carried over as previous_refresh_at."""
    site, _ = isolated_data_dirs

    # Plant a previous meta.json — like a snapshot from last Sunday's run.
    (site / "meta.json").write_text(json.dumps({
        "updated_at": "2026-04-27T05:01:00Z",
        "total_bills": 999,
    }))

    monkeypatch.setattr(build_site_data, "build_session_records",
                        lambda s: ([_seed_record("2026", 1)], []))

    build_sessions([2026], augment=False)

    meta = json.loads((site / "meta.json").read_text())
    assert meta["previous_refresh_at"] == "2026-04-27T05:01:00Z"
    # And the new updated_at is something else (now).
    assert meta["updated_at"] != "2026-04-27T05:01:00Z"


def test_previous_refresh_at_null_on_first_run(isolated_data_dirs, monkeypatch):
    """No prior meta.json → previous_refresh_at is null, no crash."""
    site, _ = isolated_data_dirs

    monkeypatch.setattr(build_site_data, "build_session_records",
                        lambda s: ([_seed_record("2026", 1)], []))

    build_sessions([2026], augment=False)

    meta = json.loads((site / "meta.json").read_text())
    assert meta["previous_refresh_at"] is None
