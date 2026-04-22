"""
Decode the opaque CurrentStatus and GovernorAction codes the NJ Leg API returns.

Status codes are NOT documented by any API endpoint. The mapping lives in
data/reference/status_codes.csv — hand-curated. Unknown codes are returned
as-is so the site can surface them as "Meaning not documented" rather than
fabricate a label.
"""

from __future__ import annotations

import csv
import functools
from pathlib import Path

from scraper.config import DATA_REFERENCE


@functools.lru_cache(maxsize=1)
def _status_map() -> dict[str, str]:
    p = DATA_REFERENCE / "status_codes.csv"
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    with p.open() as f:
        for row in csv.DictReader(f):
            code = (row.get("code") or "").strip()
            label = (row.get("label") or "").strip()
            if code:
                out[code] = label
    return out


# Governor actions are documented by /api/advancedSearch/searchFields but we
# hard-code them since there are only seven and they never change.
GOVERNOR_ACTION_LABELS = {
    "AV": "Absolute veto",
    "APP": "Approved",
    "CV": "Conditional veto",
    "FSS": "Filed with Secretary of State",
    "LIV": "Line-item veto",
    "PV": "Pocket veto",
    "WOA": "Became law without approval",
}

LAW_ACTION_CODES = {"APP", "FSS", "WOA"}


def status_label(code: str | None) -> str | None:
    """Human label, or None if we genuinely don't know."""
    if not code:
        return None
    return _status_map().get(code.strip())


def governor_action_label(code: str | None) -> str | None:
    if not code:
        return None
    return GOVERNOR_ACTION_LABELS.get(code.strip())


def became_law(governor_action: str | None) -> bool:
    if not governor_action:
        return False
    return governor_action.strip() in LAW_ACTION_CODES
