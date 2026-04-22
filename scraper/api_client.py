"""
Thin, polite HTTP client for the NJ Legislature API.

Enforces rate limiting, retry with exponential backoff on transient failures,
and optional on-disk caching keyed by URL + body hash. No concurrency by
design — the API is undocumented and we don't want to hammer it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from pathlib import Path
from typing import Any

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from scraper.config import (
    BASE_URL,
    REQUEST_DELAY_SECONDS,
    REQUEST_JITTER_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
)

log = logging.getLogger(__name__)


class NJLegAPIError(RuntimeError):
    """Raised when the NJ Leg API returns a non-success response we can't recover from."""


class TransientError(RuntimeError):
    """Raised on transient failures so tenacity will retry."""


def _sleep():
    time.sleep(REQUEST_DELAY_SECONDS + random.uniform(0, REQUEST_JITTER_SECONDS))


def _cache_key(method: str, path: str, body: dict | None) -> str:
    raw = f"{method}:{path}:{json.dumps(body, sort_keys=True) if body else ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class Client:
    """
    Polite wrapper around the undocumented NJ Leg JSON API. Create one and reuse it;
    the session object keeps TCP connections warm for free.

    ``cache_dir``: if provided, successful responses are memoized to disk. Intended
    for long historical backfills where we may re-run the scraper many times.
    Cache is bypassed when ``force_refresh=True`` is passed to the call sites.
    """

    def __init__(self, cache_dir: Path | None = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/advanced-search",
        })
        self.cache_dir = cache_dir
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)

    @retry(
        retry=retry_if_exception_type(TransientError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=30),
        reraise=True,
    )
    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        url = f"{BASE_URL}{path}"
        try:
            resp = self.session.request(
                method=method,
                url=url,
                json=body if method == "POST" else None,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as e:
            log.warning("network error on %s %s: %s", method, path, e)
            raise TransientError(str(e)) from e

        if resp.status_code in (429, 500, 502, 503, 504):
            log.warning("transient status %s on %s %s", resp.status_code, method, path)
            raise TransientError(f"{resp.status_code} on {path}")

        if not resp.ok:
            raise NJLegAPIError(f"{resp.status_code} {resp.reason} on {method} {path}: {resp.text[:200]}")

        try:
            return resp.json()
        except ValueError as e:
            raise NJLegAPIError(f"non-JSON response on {method} {path}: {resp.text[:200]}") from e

    def get(self, path: str, force_refresh: bool = False) -> Any:
        cached = self._cache_read("GET", path, None, force_refresh)
        if cached is not None:
            return cached
        _sleep()
        log.info("GET %s", path)
        result = self._request("GET", path)
        self._cache_write("GET", path, None, result)
        return result

    def post(self, path: str, body: dict, force_refresh: bool = False) -> Any:
        cached = self._cache_read("POST", path, body, force_refresh)
        if cached is not None:
            return cached
        _sleep()
        log.info("POST %s", path)
        result = self._request("POST", path, body)
        self._cache_write("POST", path, body, result)
        return result

    def _cache_path(self, method: str, path: str, body: dict | None) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"{_cache_key(method, path, body)}.json"

    def _cache_read(self, method: str, path: str, body: dict | None, force: bool) -> Any | None:
        if force:
            return None
        p = self._cache_path(method, path, body)
        if p is None or not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def _cache_write(self, method: str, path: str, body: dict | None, payload: Any) -> None:
        p = self._cache_path(method, path, body)
        if p is None:
            return
        try:
            p.write_text(json.dumps(payload))
        except OSError as e:
            log.warning("cache write failed: %s", e)


# ---- Typed wrappers around the specific endpoints we use ----

def search_bills(client: Client, session: int, keyword: str, force_refresh: bool = False) -> list[dict]:
    """
    POST /api/advancedSearch/search

    The quirk that burned us during reverse-engineering: array-typed fields
    must be sent as comma-separated strings, not JSON arrays. An empty string
    means "no filter on that field."
    """
    body = {
        "billNumber": "",
        "keyWords": keyword,
        "ldoaStart": "",
        "ldoaEnd": "",
        "years": str(session),
        "sponsors": "",
        "govActions": "",
        "committees": "",
        "subjects": "",
    }
    result = client.post("/api/advancedSearch/search", body, force_refresh=force_refresh)
    if isinstance(result, dict) and "message" in result:
        raise NJLegAPIError(f"search API returned: {result['message']}")
    return result


def fetch_sponsors(client: Client, bill: str, session: int, is_current: bool,
                   force_refresh: bool = False) -> list[list[dict]]:
    """
    GET /api/billDetail/billSponsors/{bill}/{session}   for current session
    GET /api/billDetailHist/billSponsors/{bill}/{session} for closed sessions

    Returns [primary_sponsors, cosponsors] (each a list of dicts).
    """
    base = "billDetail" if is_current else "billDetailHist"
    return client.get(f"/api/{base}/billSponsors/{bill}/{session}", force_refresh=force_refresh)


def fetch_sessions(client: Client) -> list[dict]:
    """GET /api/advancedSearch/sessions → [{"display": "...", "value": 2024}, ...]"""
    return client.get("/api/advancedSearch/sessions")


def fetch_search_fields(client: Client) -> list[list[dict]]:
    """GET /api/advancedSearch/searchFields → [years, sponsors, govActions, committees, subjects]"""
    return client.get("/api/advancedSearch/searchFields")
