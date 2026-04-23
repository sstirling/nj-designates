"""
Command-line interface.

Examples:
  python -m scraper fetch --session 2024
  python -m scraper build --session 2024
  python -m scraper refresh --session 2024     # fetch + build
  python -m scraper refresh --all              # every session in ALL_SESSIONS
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Iterable

from scraper.build_site_data import build_sessions
from scraper.config import ALL_SESSIONS
from scraper.fetch_bill_details import fetch_details
from scraper.fetch_sessions import fetch_session
from scraper.filter_ceremonial import is_ceremonial


def _sessions_from_args(args) -> list[int]:
    if args.all:
        return list(ALL_SESSIONS)
    if args.session:
        return [int(s) for s in args.session]
    raise SystemExit("error: pass --session YYYY (repeatable) or --all")


def cmd_fetch(args) -> int:
    sessions = _sessions_from_args(args)
    for s in sessions:
        raw_bills = fetch_session(s, force_refresh=args.force)
        # Apply ceremonial filter up front so we only fetch detail pages for
        # bills that might matter. Pass bill_id so force_include overrides
        # are honored — otherwise overridden bills wouldn't get sponsors.
        kept = []
        for b in raw_bills:
            full = (b.get("Bill") or "").strip()
            bill_id = f"{s}-{full}" if full else None
            if is_ceremonial(b.get("Synopsis") or "", bill_id=bill_id):
                kept.append(b)
        logging.info("session %s: %d / %d bills pass filter — fetching details", s, len(kept), len(raw_bills))
        fetch_details(s, kept, force_refresh=args.force)
    return 0


def cmd_build(args) -> int:
    sessions = _sessions_from_args(args)
    summary = build_sessions(sessions)
    print(f"built {summary['kept']} bills across sessions {summary['sessions']}; "
          f"{summary['rejected']} rejected")
    return 0


def cmd_refresh(args) -> int:
    cmd_fetch(args)
    cmd_build(args)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m scraper")
    p.add_argument("--verbose", action="store_true")

    sub = p.add_subparsers(dest="command", required=True)

    def add_session_args(sp):
        sp.add_argument("--session", action="append", type=int,
                        help="session start year (repeatable), e.g. --session 2024")
        sp.add_argument("--all", action="store_true", help="every session in ALL_SESSIONS")
        sp.add_argument("--force", action="store_true", help="ignore on-disk caches")

    fetch_p = sub.add_parser("fetch", help="pull raw API data into data/raw/")
    add_session_args(fetch_p)
    fetch_p.set_defaults(func=cmd_fetch)

    build_p = sub.add_parser("build", help="transform raw → data/ + data/processed/")
    add_session_args(build_p)
    build_p.set_defaults(func=cmd_build)

    refresh_p = sub.add_parser("refresh", help="fetch + build in one shot")
    add_session_args(refresh_p)
    refresh_p.set_defaults(func=cmd_refresh)

    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
