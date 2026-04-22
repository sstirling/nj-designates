"""Unit tests for the API client — mocked so they never hit the real network."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scraper.api_client import Client, NJLegAPIError, search_bills


def _mock_response(payload, status=200):
    m = MagicMock()
    m.status_code = status
    m.ok = 200 <= status < 400
    m.reason = "OK" if m.ok else "Error"
    m.text = ""
    m.json.return_value = payload
    return m


def test_search_bills_sends_session_as_string_not_array(tmp_path: Path):
    """
    Regression for the 'arrays must be comma-joined strings' quirk.
    The request body we send to /api/advancedSearch/search must have
    'years' as a bare string, not a list — otherwise the server returns
    {"message":"Advanced Search Results did not work"}.
    """
    client = Client(cache_dir=tmp_path)
    with patch.object(client.session, "request", return_value=_mock_response([])) as mock:
        # sleep would otherwise burn a real second
        with patch("scraper.api_client._sleep"):
            search_bills(client, session=2024, keyword="Designates")

    assert mock.called
    kwargs = mock.call_args.kwargs
    body = kwargs["json"]
    assert body["years"] == "2024"
    assert isinstance(body["years"], str)
    # all the other array-shaped fields must be empty strings, not lists
    for k in ("sponsors", "govActions", "committees", "subjects"):
        assert body[k] == ""
    assert body["keyWords"] == "Designates"


def test_search_raises_on_did_not_work(tmp_path: Path):
    client = Client(cache_dir=tmp_path)
    bad = _mock_response({"message": "Advanced Search Results did not work"})
    with patch.object(client.session, "request", return_value=bad):
        with patch("scraper.api_client._sleep"):
            with pytest.raises(NJLegAPIError):
                search_bills(client, session=2024, keyword="Designates")


def test_cache_hit_skips_http(tmp_path: Path):
    client = Client(cache_dir=tmp_path)
    payload = [{"Bill": "A1   ", "Synopsis": "..."}]
    with patch.object(client.session, "request", return_value=_mock_response(payload)) as mock:
        with patch("scraper.api_client._sleep"):
            first = search_bills(client, 2024, "Designates")
            second = search_bills(client, 2024, "Designates")
    assert first == second == payload
    assert mock.call_count == 1  # second call hit the cache
