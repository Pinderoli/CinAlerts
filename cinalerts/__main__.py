"""
python -m cinalerts run                 scan, update the website data, send alerts
python -m cinalerts run --dry-run       scan and print, without writing files or notifying
python -m cinalerts cinemas [search]    list cinema IDs to put in config.toml
python -m cinalerts test-notify         send a test push notification
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from . import notify
from .config import load
from .run import ROOT, SITE_DATA, run


def main() -> None:
    p = argparse.ArgumentParser(prog="cinalerts", description="UK cinema re-run alerts")
    p.add_argument("--config", type=Path, default=ROOT / "config.toml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true", help="don't write files or send notifications")
    r.add_argument("--no-notify", action="store_true")
    r.add_argument("--chains", help="comma-separated subset, e.g. odeon,vue")
    r.add_argument("--days", type=int)
    c = sub.add_parser("cinemas")
    c.add_argument("search", nargs="?", default="")
    sub.add_parser("test-notify")
    args = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    cfg = load(args.config)

    if args.cmd == "run":
        if args.days:
            cfg.days_ahead = args.days
        reruns = run(
            cfg,
            notify_enabled=not args.no_notify,
            chains=args.chains.split(",") if args.chains else None,
            write=not args.dry_run,
        )
        if args.dry_run:
            for f in reruns:
                n = sum(len(v) for v in f["showings"].values())
                print(f"{f['year'] or '????'}  {f['title']:<45} {', '.join(f['genres']):<30} {len(f['showings']):>3} cinemas {n:>4} showings  [{f['reason']}]")
    elif args.cmd == "cinemas":
        files = sorted((SITE_DATA / "chains").glob("*.json"))
        if not files:
            raise SystemExit("No cinema list yet - run `python -m cinalerts run` first.")
        q = args.search.lower()
        for c in (c for f in files for c in json.loads(f.read_text())["cinemas"]):
            if q in f"{c['chain']} {c['name']} {c['city']}".lower():
                print(f"{c['id']:<22} {c['name']}  ({c['city']})")
    elif args.cmd == "test-notify":
        ok = notify.send("CinAlerts test", "If you can read this, notifications work.", click=cfg.site_url or None)
        print("Sent." if ok else "NTFY_TOPIC is not set.")


if __name__ == "__main__":
    main()
