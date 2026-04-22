"""
Ceremonial-bill filter.

A bill's synopsis passes if it does NOT match any exclude pattern AND it DOES
match at least one include pattern. The rules live in data/reference/category_rules.yml
so they can be refined without touching code.
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


def is_ceremonial(synopsis: str) -> bool:
    """
    True iff the synopsis looks like a ceremonial designation bill.

    Runs exclusions first so a bill like "designates Attorney General as chief
    election official" never even reaches the include patterns.
    """
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


def filter_reason(synopsis: str) -> str:
    """
    Explain why is_ceremonial returned False. Used for audit logging so a
    human reviewer can see what tripped each dropped bill.
    """
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
    """For tests that mutate category_rules.yml at runtime."""
    _rules.cache_clear()
    _compiled_excludes.cache_clear()
    _compiled_includes.cache_clear()
