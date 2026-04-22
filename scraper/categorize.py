"""
Assigns category and subcategory tags to ceremonial bills.

Bills get ALL matching category tags (multi-label). The priority list in
category_rules.yml decides the single "primary" category used for default
views on the site.

Subcategories are keyword-based — simple substring matches on a normalized
synopsis. These are coarser than full regex patterns on purpose: they're
editorial hints for the reader (is this a state FOOD symbol or a state
NATURE symbol), not ground truth.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

import yaml

from scraper.config import DATA_REFERENCE


@functools.lru_cache(maxsize=1)
def _rules(path: Path | None = None) -> dict:
    p = path or (DATA_REFERENCE / "category_rules.yml")
    return yaml.safe_load(p.read_text())


@functools.lru_cache(maxsize=1)
def _compiled_categories() -> list[tuple[str, list[re.Pattern], dict[str, list[str]]]]:
    cats = _rules()["categories"]
    out = []
    for name, cfg in cats.items():
        patterns = [re.compile(p, re.IGNORECASE) for p in cfg.get("patterns", [])]
        subs = cfg.get("subcategories", {}) or {}
        out.append((name, patterns, subs))
    return out


@functools.lru_cache(maxsize=1)
def _overrides(path: Path | None = None) -> dict:
    p = path or (DATA_REFERENCE / "overrides.yml")
    if not p.exists():
        return {"force_include": [], "force_exclude": [], "force_category": {}}
    return yaml.safe_load(p.read_text()) or {}


@functools.lru_cache(maxsize=1)
def _priority() -> list[str]:
    return list(_rules().get("priority", []))


def categorize(synopsis: str, bill_id: str | None = None) -> tuple[str | None, list[str]]:
    """
    Return (primary_category, subcategories).

    primary_category follows priority order from the rules file, falling back
    to 'other_ceremonial' if the bill matched the top-level include filter
    but fell through every category rule. Subcategories is a flat list.
    """
    text = (synopsis or "").strip()
    if not text:
        return None, []

    # Check for a hard-coded override by bill_id first.
    if bill_id:
        forced = _overrides().get("force_category", {})
        if bill_id in forced:
            return forced[bill_id][0], list(forced[bill_id][1:])

    matched_primary: list[str] = []
    all_subs: list[str] = []
    lowered = text.lower()

    for name, patterns, subs in _compiled_categories():
        if any(p.search(text) for p in patterns):
            matched_primary.append(name)
            for sub_name, keywords in subs.items():
                if any(kw in lowered for kw in keywords):
                    all_subs.append(sub_name)

    # Dedupe subs while preserving order.
    seen = set()
    deduped_subs = []
    for s in all_subs:
        if s not in seen:
            seen.add(s)
            deduped_subs.append(s)

    if not matched_primary:
        return "other_ceremonial", deduped_subs

    for cat in _priority():
        if cat in matched_primary:
            return cat, deduped_subs

    return matched_primary[0], deduped_subs


def all_category_tags(synopsis: str, bill_id: str | None = None) -> list[str]:
    """Every category whose patterns match (vs. categorize() which picks one primary)."""
    text = (synopsis or "").strip()
    if not text:
        return []
    if bill_id:
        forced = _overrides().get("force_category", {})
        if bill_id in forced:
            return list(forced[bill_id])
    hits = [name for name, patterns, _ in _compiled_categories()
            if any(p.search(text) for p in patterns)]
    return hits or ["other_ceremonial"]


def reload_rules() -> None:
    """For tests that mutate the YAML files at runtime."""
    _rules.cache_clear()
    _compiled_categories.cache_clear()
    _overrides.cache_clear()
    _priority.cache_clear()
