"""
Failing-first tests for the ceremonial filter and category tagger.

The fixtures in tests/fixtures/ are hand-curated bills representing:
  - known_ceremonial.json    must be INCLUDED and tagged correctly
  - known_administrative.json must be EXCLUDED
  - known_false_negatives.json regression set — earlier regex dropped these

Every time we adjust data/reference/category_rules.yml, these tests catch drift.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scraper.filter_ceremonial import is_ceremonial, filter_reason
from scraper.categorize import categorize

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.parametrize("bill", load("known_ceremonial.json"))
def test_known_ceremonial_are_included(bill: dict) -> None:
    assert is_ceremonial(bill["synopsis"]), (
        f"{bill['full_number']} should have been kept. "
        f"Reason: {filter_reason(bill['synopsis'])}"
    )


@pytest.mark.parametrize("bill", load("known_ceremonial.json"))
def test_known_ceremonial_have_expected_primary_category(bill: dict) -> None:
    primary, _subs = categorize(bill["synopsis"])
    assert primary == bill["expected_primary_category"], (
        f"{bill['full_number']}: expected primary={bill['expected_primary_category']}, "
        f"got {primary}. Synopsis: {bill['synopsis']!r}"
    )


@pytest.mark.parametrize("bill", load("known_ceremonial.json"))
def test_known_ceremonial_subcategories_are_superset(bill: dict) -> None:
    """Every expected subcategory must be present (extra tags are fine)."""
    _primary, subs = categorize(bill["synopsis"])
    expected = set(bill.get("expected_subcategories", []))
    assert expected.issubset(set(subs)), (
        f"{bill['full_number']}: expected subs {expected}, got {subs}"
    )


@pytest.mark.parametrize("bill", load("known_administrative.json"))
def test_known_administrative_are_excluded(bill: dict) -> None:
    assert not is_ceremonial(bill["synopsis"]), (
        f"{bill['full_number']} should have been dropped. Synopsis: {bill['synopsis']!r}"
    )


@pytest.mark.parametrize("bill", load("known_false_negatives.json"))
def test_regression_false_negatives_are_included(bill: dict) -> None:
    assert is_ceremonial(bill["synopsis"]), (
        f"REGRESSION: {bill['full_number']} must not be dropped again. "
        f"Synopsis: {bill['synopsis']!r}"
    )
