"""Tests for build_sessions augment mode.

Reproduces the weekly-CI bug where `refresh --session 2026` rewrote meta.json
with totals for only the current session, dropping the historical archive.
The augment mode is the fix: it reads the committed bills.parquet as a seed,
drops rows for the rebuilt session(s), and writes the union back out.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scraper import build_site_data
from scraper.build_site_data import build_sessions


def _seed_record(session: str, idx: int, primary_category: str = "state_symbol") -> dict:
    """A schema-complete row matching what build_session_records would emit."""
    full = f"A{idx}"
    return {
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
        "primary_category": primary_category,
        "categories": [primary_category],
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


@pytest.fixture
def isolated_data_dirs(tmp_path, monkeypatch):
    """Redirect DATA_PROCESSED + SITE_DATA at a tmpdir so the test doesn't
    touch the committed data/ files."""
    processed = tmp_path / "processed"
    processed.mkdir()
    monkeypatch.setattr(build_site_data, "DATA_PROCESSED", processed)
    monkeypatch.setattr(build_site_data, "SITE_DATA", tmp_path)
    return tmp_path, processed


def test_augment_preserves_prior_sessions(isolated_data_dirs, monkeypatch):
    site, processed = isolated_data_dirs

    # Seed: 3 bills in 2022, 2 in 2024, 5 stale rows for 2026.
    seed_rows = (
        [_seed_record("2022", i) for i in range(1, 4)]
        + [_seed_record("2024", i) for i in range(1, 3)]
        + [_seed_record("2026", i) for i in range(1, 6)]
    )
    pd.DataFrame(seed_rows).to_parquet(processed / "bills.parquet", index=False)
    pd.DataFrame([
        {"bill_id": f"{s}-A999", "session": s, "full_number": "A999",
         "synopsis": "admin", "reason": "exclusion regex"}
        for s in (2022, 2024, 2026)
    ]).to_csv(processed / "audit_rejected.csv", index=False)

    # Pretend a fresh fetch shows 7 bills in 2026 (was 5).
    def fake_build_session_records(session: int):
        assert session == 2026, f"only 2026 should be rebuilt, got {session}"
        kept = [_seed_record("2026", i, "holiday_observance") for i in range(1, 8)]
        rejected = [{
            "bill_id": "2026-A999", "session": 2026, "full_number": "A999",
            "synopsis": "admin", "reason": "exclusion regex",
        }]
        return kept, rejected

    monkeypatch.setattr(build_site_data, "build_session_records",
                        fake_build_session_records)

    summary = build_sessions([2026], augment=True)

    # 2022 (3) + 2024 (2) + 2026 fresh (7) = 12.
    assert summary["kept"] == 12
    assert summary["sessions"] == [2022, 2024, 2026]
    assert summary["augment"] is True

    meta = json.loads((site / "meta.json").read_text())
    assert meta["total_bills"] == 12
    assert meta["sessions_covered"] == [2022, 2024, 2026]
    assert meta["earliest_session"] == 2022
    assert meta["latest_session"] == 2026
    assert meta["by_session"]["2026"] == 7
    assert meta["by_session"]["2022"] == 3
    assert meta["by_session"]["2024"] == 2

    # Audit CSV merges historical + freshly-rebuilt rejects.
    audit = pd.read_csv(processed / "audit_rejected.csv")
    assert sorted(audit["session"].astype(int).tolist()) == [2022, 2024, 2026]


def test_augment_with_no_existing_parquet_is_safe(isolated_data_dirs, monkeypatch):
    """First-ever augment run (no committed parquet yet) shouldn't crash."""
    monkeypatch.setattr(build_site_data, "build_session_records",
                        lambda s: ([_seed_record("2026", 1)], []))

    summary = build_sessions([2026], augment=True)
    assert summary["kept"] == 1
    assert summary["sessions"] == [2026]


def test_non_augment_build_unchanged(isolated_data_dirs, monkeypatch):
    """Existing local workflow (`build --all` without --augment) must keep
    rebuilding from scratch — augment is opt-in, not a behavior change."""
    site, processed = isolated_data_dirs

    # Even with stale parquet present, non-augment build ignores it.
    pd.DataFrame([_seed_record("2022", 1)]).to_parquet(
        processed / "bills.parquet", index=False
    )

    monkeypatch.setattr(build_site_data, "build_session_records",
                        lambda s: ([_seed_record("2026", 1)], []))

    summary = build_sessions([2026], augment=False)
    assert summary["kept"] == 1
    assert summary["sessions"] == [2026]

    meta = json.loads((site / "meta.json").read_text())
    assert meta["total_bills"] == 1
    assert meta["sessions_covered"] == [2026]
