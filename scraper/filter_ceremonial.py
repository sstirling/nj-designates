"""
Ceremonial-bill filter.

A bill's synopsis passes if it does NOT match any exclude pattern AND it DOES
match at least one include pattern. The rules live in data/reference/category_rules.yml
so they can be refined without touching code.

Human-review overrides in data/reference/overrides.yml let a journalist force
specific bill_ids in or out of the dataset — used sparingly for edge cases
where regex can't be both correct and readable.
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
def _overrides() -> dict:
    p = DATA_REFERENCE / "overrides.yml"
    if not p.exists():
        return {"force_include": [], "force_exclude": []}
    data = yaml.safe_load(p.read_text()) or {}
    return {
        "force_include": set(data.get("force_include") or []),
        "force_exclude": set(data.get("force_exclude") or []),
    }


@functools.lru_cache(maxsize=1)
def _compiled_excludes() -> list[tuple[str, re.Pattern, str]]:
    return [
        (r["name"], re.compile(r["pattern"], re.IGNORECASE), r.get("reason", r["name"]))
        for r in _rules()["exclude"]
    ]


@functools.lru_cache(maxsize=1)
def _compiled_includes() -> list[tuple[str, re.Pattern]]:
    return [
        (r["name"], re.compile(r["pattern"], re.IGNORECASE))
        for r in _rules()["include"]
    ]


def is_ceremonial(synopsis: str, bill_id: str | None = None) -> bool:
    """
    True iff the synopsis looks like a ceremonial designation bill.

    Overrides win over rules. Exclusions run before includes so a bill like
    "designates Attorney General as chief election official" never reaches the
    include patterns.
    """
    if bill_id:
        overrides = _overrides()
        if bill_id in overrides["force_exclude"]:
            return False
        if bill_id in overrides["force_include"]:
            return True
    if not synopsis:
        return False
    text = synopsis.strip()
    for _name, pat, _reason in _compiled_excludes():
        if pat.search(text):
            return False
    for _name, pat in _compiled_includes():
        if pat.search(text):
            return True
    return False


def filter_reason(synopsis: str, bill_id: str | None = None) -> str:
    """Explain the filter decision. Used for audit logging."""
    if bill_id:
        overrides = _overrides()
        if bill_id in overrides["force_exclude"]:
            return "force_exclude override"
        if bill_id in overrides["force_include"]:
            return "force_include override"
    if not synopsis or not synopsis.strip():
        return "empty synopsis"
    text = synopsis.strip()
    for name, pat, reason in _compiled_excludes():
        if pat.search(text):
            return f"excluded: {name} ({reason})"
    for _name, pat in _compiled_includes():
        if pat.search(text):
            return "included"
    return "no include pattern matched"


def reload_rules() -> None:
    """For tests that mutate the YAML files at runtime."""
    _rules.cache_clear()
    _overrides.cache_clear()
    _compiled_excludes.cache_clear()
    _compiled_includes.cache_clear()
