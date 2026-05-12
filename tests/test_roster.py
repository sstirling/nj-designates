"""
Tests for the roster scraper.

The roster page is HTML, not JSON — every test here uses a fixture HTML
snippet shaped like the real __NEXT_DATA__ payload so we don't hit the network
and so a future shape change shows up as a deterministic test failure.
"""

from __future__ import annotations

import json
from textwrap import dedent

import pytest

from scraper.fetch_roster import (
    RosterParseError,
    canonicalize_name,
    parse_legislators,
)


def _wrap_in_html(next_data_obj: dict) -> str:
    """Build a minimal HTML doc with a __NEXT_DATA__ script block — the only
    part of the real page our parser cares about."""
    blob = json.dumps(next_data_obj)
    return (
        "<!doctype html><html><body>"
        '<script id="__NEXT_DATA__" type="application/json">'
        f"{blob}"
        "</script></body></html>"
    )


def _legrosterdata(legislators):
    """The real shape is [legislators, towns, districts]. Pad with empty arrays
    so the fixture stays minimal."""
    return {"props": {"pageProps": {"legrosterData": [legislators, [], []]}}}


# ---- canonicalize_name -------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        # The whole point: roster and bill-side suffix placement converges.
        ("Amato Jr., Carmen F.",          "amato,carmen f"),
        ("Amato, Carmen F., Jr.",         "amato,carmen f"),
        # Medical degree, same divergence.
        ("Donlon M.D., Margie",           "donlon,margie"),
        ("Donlon, Margie, M.D.",          "donlon,margie"),
        # Generational suffix in last-name slot.
        ("Sampson IV, William B.",        "sampson,william b"),
        ("Sampson, William B., IV",       "sampson,william b"),
        # Esquire, apostrophe preserved.
        ("O'Scanlon Jr., Declan J.",      "o'scanlon,declan j"),
        ("O'Scanlon, Declan J., Jr.",     "o'scanlon,declan j"),
        # Stacked honorifics.
        ("Azzariti Jr. M.D., John V.",    "azzariti,john v"),
        ("Azzariti Jr., John V., M.D.",   "azzariti,john v"),
        # Already-clean names should round-trip.
        ("Bramnick, Jon M.",              "bramnick,jon m"),
        ("Abdelaziz, Al",                 "abdelaziz,al"),
        # Whitespace and empty values.
        ("",                              ""),
        ("  ",                            ""),
        ("Foo,   Bar  ",                  "foo,bar"),
    ],
)
def test_canonicalize_name(raw, expected):
    assert canonicalize_name(raw) == expected


def test_canonicalize_name_does_not_eat_real_initials():
    """Single-letter middles like 'V.' must survive — only honorific tokens go."""
    # Last_Name "V" doesn't make sense, but a middle initial "V." appears in
    # plenty of real names and must not be confused with the generational "V".
    # The honorific regex uses (?<!\w)/(?!\w) boundaries so "V." inside a
    # multi-word string stays intact when it sits adjacent to other letters.
    assert canonicalize_name("Smith, John V.") == "smith,john v"


# ---- parse_legislators -------------------------------------------------------

def test_parse_legislators_extracts_basic_fields():
    page = _wrap_in_html(_legrosterdata([
        {
            "Full_Name": "Bramnick, Jon M.",
            "Last_Name": "Bramnick",
            "First_Name": "Jon",
            "Middle_Name": "M.",
            "Suffix": None,
            "RosterHouseCode": "S",
            "Roster_House": "Senate",
            "Roster_District": 21,
            "Party": "R",
            "PartyDescription": "Republican",
            "BioLink": "/legislative-roster/433/senator-bramnick",
            "VacantSort": 0,
        },
    ]))
    out = parse_legislators(page)
    assert len(out) == 1
    leg = out[0]
    assert leg["full_name"] == "Bramnick, Jon M."
    assert leg["canonical_name"] == "bramnick,jon m"
    assert leg["chamber"] == "Senate"
    assert leg["chamber_code"] == "S"
    assert leg["district"] == 21
    assert leg["party"] == "R"
    assert leg["bio_url"] == "https://www.njleg.state.nj.us/legislative-roster/433/senator-bramnick"


def test_parse_legislators_skips_vacant_seats():
    """A vacant seat is the legislature's marker that a district is unrepresented
    — drop it rather than ship a roster entry with no name."""
    page = _wrap_in_html(_legrosterdata([
        {"Full_Name": "Real Person, Test", "VacantSort": 0,
         "Last_Name": "Real Person", "First_Name": "Test",
         "Roster_House": "Assembly", "RosterHouseCode": "A",
         "Roster_District": 1, "Party": "D", "BioLink": ""},
        # Vacant: empty name.
        {"Full_Name": "",  "VacantSort": 0, "Roster_House": "Assembly",
         "RosterHouseCode": "A", "Roster_District": 99,
         "Last_Name": None, "First_Name": None, "Party": None, "BioLink": ""},
        # Vacant: marked by VacantSort.
        {"Full_Name": "[Vacant Seat]", "VacantSort": 1,
         "Roster_House": "Assembly", "RosterHouseCode": "A",
         "Roster_District": 40, "Party": None, "BioLink": "",
         "Last_Name": None, "First_Name": None},
    ]))
    out = parse_legislators(page)
    assert [l["full_name"] for l in out] == ["Real Person, Test"]


def test_parse_legislators_orders_by_chamber_then_lastname():
    """Stable order keeps the committed JSON diffable across runs."""
    page = _wrap_in_html(_legrosterdata([
        {"Full_Name": "Zeta, Anna", "Last_Name": "Zeta", "First_Name": "Anna",
         "RosterHouseCode": "A", "Roster_House": "Assembly",
         "Roster_District": 1, "Party": "D", "BioLink": "", "VacantSort": 0},
        {"Full_Name": "Alpha, Bob", "Last_Name": "Alpha", "First_Name": "Bob",
         "RosterHouseCode": "S", "Roster_House": "Senate",
         "Roster_District": 2, "Party": "R", "BioLink": "", "VacantSort": 0},
        {"Full_Name": "Beta, Carol", "Last_Name": "Beta", "First_Name": "Carol",
         "RosterHouseCode": "A", "Roster_House": "Assembly",
         "Roster_District": 3, "Party": "D", "BioLink": "", "VacantSort": 0},
    ]))
    out = parse_legislators(page)
    assert [(l["chamber_code"], l["last_name"]) for l in out] == [
        ("A", "Beta"),
        ("A", "Zeta"),
        ("S", "Alpha"),
    ]


def test_parse_legislators_handles_absolute_biolink():
    """If BioLink is already absolute we should not prepend BASE_URL twice."""
    page = _wrap_in_html(_legrosterdata([
        {"Full_Name": "Foo, Bar", "Last_Name": "Foo", "First_Name": "Bar",
         "RosterHouseCode": "S", "Roster_House": "Senate",
         "Roster_District": 1, "Party": "D",
         "BioLink": "https://example.org/profile/foo", "VacantSort": 0},
    ]))
    leg = parse_legislators(page)[0]
    assert leg["bio_url"] == "https://example.org/profile/foo"


def test_parse_legislators_raises_when_next_data_missing():
    with pytest.raises(RosterParseError, match="__NEXT_DATA__"):
        parse_legislators("<html><body>No script block here.</body></html>")


def test_parse_legislators_raises_when_shape_changes():
    """If the legrosterData path disappears, fail loudly so the operator knows
    to update the scraper rather than silently shipping zero legislators."""
    page = _wrap_in_html({"props": {"pageProps": {}}})
    with pytest.raises(RosterParseError, match="legrosterData"):
        parse_legislators(page)
