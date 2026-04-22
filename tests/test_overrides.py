"""
Tests for human-review overrides in data/reference/overrides.yml.

Overrides let a journalist force specific bill_ids in or out of the dataset,
regardless of what the rule-based filter would say. Tests write a throwaway
overrides YAML and reload the filter's cache so they're hermetic.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scraper import filter_ceremonial
from scraper.filter_ceremonial import (
    filter_reason,
    is_ceremonial,
    reload_rules,
)


@pytest.fixture
def overrides_file(monkeypatch, tmp_path: Path):
    """Swap DATA_REFERENCE to a tmpdir with copies of the real rule files."""
    from scraper import config
    src_ref = config.DATA_REFERENCE
    tmp_ref = tmp_path / "reference"
    tmp_ref.mkdir()
    (tmp_ref / "category_rules.yml").write_text((src_ref / "category_rules.yml").read_text())

    monkeypatch.setattr(config, "DATA_REFERENCE", tmp_ref)
    monkeypatch.setattr(filter_ceremonial, "DATA_REFERENCE", tmp_ref)
    reload_rules()

    def write(overrides: dict) -> None:
        (tmp_ref / "overrides.yml").write_text(yaml.safe_dump(overrides))
        reload_rules()

    yield write
    reload_rules()


def test_force_include_overrides_exclusion(overrides_file):
    # Synopsis would normally be excluded by the administrative_officer rule.
    admin_synopsis = "Designates Attorney General as chief election official."
    assert not is_ceremonial(admin_synopsis)
    overrides_file({"force_include": ["2024-AX999"], "force_exclude": []})
    assert is_ceremonial(admin_synopsis, bill_id="2024-AX999")
    assert filter_reason(admin_synopsis, bill_id="2024-AX999") == "force_include override"


def test_force_exclude_overrides_include(overrides_file):
    syn = "Designates blueberry muffin as State Muffin."
    assert is_ceremonial(syn)
    overrides_file({"force_include": [], "force_exclude": ["2024-A3611"]})
    assert not is_ceremonial(syn, bill_id="2024-A3611")
    assert filter_reason(syn, bill_id="2024-A3611") == "force_exclude override"


def test_overrides_do_not_affect_other_bills(overrides_file):
    admin = "Designates Attorney General as chief election official."
    overrides_file({"force_include": ["2024-AX999"], "force_exclude": []})
    # Different bill id: rule-based decision still applies.
    assert not is_ceremonial(admin, bill_id="2024-OTHER")


def test_missing_bill_id_ignores_overrides(overrides_file):
    admin = "Designates Attorney General as chief election official."
    overrides_file({"force_include": ["2024-AX999"], "force_exclude": []})
    # No bill_id passed — filter must rely on rules only.
    assert not is_ceremonial(admin)
