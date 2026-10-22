"""The daily job: scan every chain, find re-runs, write the website data, send alerts."""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from . import genres as genre_map
from . import notify
from .config import Config
from .identify import Identifier
from .models import Cinema, Screening
from .sources import CHAIN_NAMES, SOURCES
from .titles import clean_title, has_rerun_marker, norm

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE_DATA = ROOT / "docs" / "data"
MAX_SEPARATE_ALERTS = 6
# Festival premieres often come a year or more before the UK release. If a chain's own release
# date is within this gap of the film's earliest release anywhere, it's a new release, not a re-run.
NEW_RELEASE_GAP_DAYS = 730


def scan_all(chains: list[str], days: int) -> tuple[list[Cinema], list[Screening], dict]:
    cinemas: list[Cinema] = []
    screenings: list[Screening] = []
    status = {}

    def one(chain):
        t = time.monotonic()
        try:
            c, s = SOURCES[chain](chain, days)
            return chain, c, s, {"ok": True, "cinemas": len(c), "screenings": len(s), "seconds": round(time.monotonic() - t)}
        except Exception as e:
            log.exception("Scanning %s failed", chain)
            return chain, [], [], {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}

    with ThreadPoolExecutor(len(chains) or 1) as pool:
        for chain, c, s, st in pool.map(one, chains):
            log.info("%-12s %s", chain, st)
            cinemas += c
            screenings += s
            status[chain] = st
    return cinemas, screenings, status


def find_reruns(screenings: list[Screening], ident: Identifier, cfg: Config) -> list[dict]:
    today = dt.date.today()
    cutoff = (today - dt.timedelta(days=round(365.25 * cfg.min_years_old))).isoformat()
    screenings = [sc for sc in screenings if not cfg.title_excluded(sc.film.title)]

    # Identify each distinct listing once.
    listings: dict[int, tuple] = {}
    for sc in screenings:
        if id(sc.film) not in listings:
            listings[id(sc.film)] = (sc.film, [])
        listings[id(sc.film)][1].extend(sc.tags)
    ids: dict[int, dict | None] = {}
    for key, (film, tags) in listings.items():
        ids[key] = ident.identify(film, tags)
    ident.enrich(sorted({i["imdb"] for i in ids.values() if i}))

    groups: dict[str, dict] = {}
    for sc in screenings:
        film = sc.film
        match = ids[id(film)]
        key = match["imdb"] if match else "t:" + norm(clean_title(film.title))
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "key": key,
                "imdb": match["imdb"] if match else None,
                "title": match["title"] if match else clean_title(film.title),
                "year": match["year"] if match else None,
                "dates": set(),
                "listing_dates": set(),
                "raw_genres": [],
                "poster": None,
                "marker": False,
                "listed_as": set(),
                "showings": defaultdict(set),
            }
            if match:
                wd = ident.wikidata(match["imdb"])
                if wd["released"]:
                    g["dates"].add(wd["released"])
                g["raw_genres"] += wd["genres"]
        if film.release_trusted and film.release_date:
            g["dates"].add(film.release_date)
        elif film.release_date:
            g["listing_dates"].add(film.release_date)
        g["raw_genres"] += film.genres
        g["poster"] = g["poster"] or film.poster or (match or {}).get("poster")
        g["marker"] |= has_rerun_marker(film.title, sc.tags)
        g["listed_as"].add(film.title)
        g["showings"][sc.cinema_id].add((sc.start, sc.url))

    reruns = []
    for g in groups.values():
        released = min(g["dates"]) if g["dates"] else (f"{g['year']}-12-31" if g["year"] else None)
        if released:
            if released > cutoff:
                continue
            if g["listing_dates"] and not g["marker"]:
                gap = dt.date.fromisoformat(min(g["listing_dates"])) - dt.date.fromisoformat(released)
                if gap.days < NEW_RELEASE_GAP_DAYS:
                    continue
            reason = "date"
        elif g["marker"]:
            reason = "marker"  # unidentified, but the cinema calls it a re-release/anniversary/etc.
        else:
            continue
        age = (today - dt.date.fromisoformat(released)).days / 365.25 if released else None
        reruns.append(
            {
                "key": g["key"],
                "imdb": g["imdb"],
                "title": g["title"],
                "year": int(released[:4]) if released else g["year"],
                "released": released,
                "age_years": round(age, 1) if age is not None else None,
                "reason": reason,
                "genres": genre_map.normalise(g["raw_genres"]),
                "poster": g["poster"],
                "listed_as": sorted(g["listed_as"]),
                "showings": {cid: sorted(v) for cid, v in sorted(g["showings"].items())},
            }
        )
    reruns.sort(key=lambda r: (min(s[0][0] for s in r["showings"].values()), r["title"]))
    return reruns


def write_site(cinemas: list[Cinema], reruns: list[dict], status: dict, cfg: Config) -> None:
    """One file per chain, written only when that chain scanned OK.

    A machine that can't reach a chain (e.g. GitHub Actions vs. Cloudflare) leaves its file alone, so
    several runners can each contribute the chains they can reach. The site merges the files.
    """
    out = SITE_DATA / "chains"
    out.mkdir(parents=True, exist_ok=True)
    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for chain, st in status.items():
        if not st.get("ok"):
            continue
        films = []
        for f in reruns:
            showings = {cid: s for cid, s in f["showings"].items() if cid.split(":", 1)[0] == chain}
            if showings:
                films.append({**f, "showings": showings})
        (out / f"{chain}.json").write_text(
            json.dumps(
                {
                    "chain": chain,
                    "name": CHAIN_NAMES[chain],
                    "generated": generated,
                    "days_ahead": cfg.days_ahead,
                    "min_years_old": cfg.min_years_old,
                    "cinemas": [asdict(c) for c in sorted(cinemas, key=lambda c: c.name) if c.chain == chain],
                    "films": films,
                },
                ensure_ascii=False,
            )
        )


def _fmt(start: str) -> str:
    d = dt.datetime.fromisoformat(start)
    return d.strftime("%a %-d %b %H:%M")


def send_alerts(reruns: list[dict], cinemas: dict[str, dict], scanned: list[str], cfg: Config, dry_run: bool) -> int:
    # Alert history is stored per chain (data/alerted/<chain>.json) for the same reason as the site data.
    state_dir = DATA / "alerted"
    state: dict = {}
    for f in state_dir.glob("*.json"):
        state.update(json.loads(f.read_text()))
    today = dt.date.today()
    realert_before = (today - dt.timedelta(days=cfg.realert_after_days)).isoformat()
    wanted = set(cfg.cinemas)
    want_genres = {g.lower() for g in cfg.genres}

    fresh = []  # (film, {cinema_id: showings})
    for film in reruns:
        if cfg.title_excluded(film["title"]) or any(cfg.title_excluded(t) for t in film["listed_as"]):
            continue
        if want_genres and film["genres"] and not want_genres & {g.lower() for g in film["genres"]}:
            continue
        new_here = {}
        for cid, shows in film["showings"].items():
            if cid not in wanted:
                continue
            pair = f"{film['key']}|{cid}"
            prev = state.get(pair)
            if prev is None or prev["last_seen"] < realert_before:
                new_here[cid] = shows
                state[pair] = {"alerted": today.isoformat(), "last_seen": today.isoformat()}
            else:
                prev["last_seen"] = today.isoformat()
        if new_here:
            fresh.append((film, new_here))

    def label(film):
        return f"{film['title']} ({film['year']})" if film.get("year") else film["title"]

    site = cfg.site_url.rstrip("/")
    if len(fresh) > MAX_SEPARATE_ALERTS:
        lines = [f"• {label(f)}: {', '.join(cinemas.get(c, {}).get('name', c) for c in where)}" for f, where in fresh]
        msg = "\n".join(lines)
        log.info("Summary alert:\n%s", msg)
        if not dry_run:
            notify.send(f"{len(fresh)} re-runs near you", msg, click=site or None)
    for film, where in fresh if len(fresh) <= MAX_SEPARATE_ALERTS else []:
        parts = []
        for cid, shows in where.items():
            c = cinemas.get(cid, {})
            name = f"{CHAIN_NAMES.get(c.get('chain'), '')} {c.get('name', cid)}".strip()
            times = ", ".join(_fmt(s) for s, _ in shows[:4]) + (f" +{len(shows) - 4} more" if len(shows) > 4 else "")
            parts.append(f"{name}: {times}")
        age = f"{film['age_years']:.0f} years old · " if film.get("age_years") else ""
        msg = age + " · ".join(film["genres"]) + "\n" + "\n".join(parts)
        first_url = next(iter(where.values()))[0][1]
        log.info("Alert: %s\n%s", label(film), msg)
        if not dry_run:
            notify.send(
                f"Back in cinemas: {label(film)}",
                msg.strip(),
                click=f"{site}/#{film['key']}" if site else first_url,
                actions=[{"action": "view", "label": "Book", "url": first_url}] if first_url else None,
            )

    # Forget pairs not seen for a long time.
    prune_before = (today - dt.timedelta(days=cfg.realert_after_days * 4)).isoformat()
    state = {k: v for k, v in state.items() if v["last_seen"] >= prune_before}
    if not dry_run:
        state_dir.mkdir(parents=True, exist_ok=True)
        for chain in scanned:
            part = {k: v for k, v in state.items() if k.split("|", 1)[1].split(":", 1)[0] == chain}
            (state_dir / f"{chain}.json").write_text(json.dumps(part, indent=1, sort_keys=True))
    return len(fresh)


def run(cfg: Config, notify_enabled: bool = True, chains: list[str] | None = None, write: bool = True) -> list[dict]:
    chains = chains or cfg.chains
    cinemas, screenings, status = scan_all(chains, cfg.days_ahead)
    ident = Identifier(DATA / "films.json")
    reruns = find_reruns(screenings, ident, cfg)
    log.info("%d screenings, %d re-run films", len(screenings), len(reruns))
    if write:
        ident.save()
        write_site(cinemas, reruns, status, cfg)
    if cfg.cinemas:
        scanned = [c for c, st in status.items() if st.get("ok")]
        all_cinemas = {c.id: asdict(c) for c in cinemas}
        n = send_alerts(reruns, all_cinemas, scanned, cfg, dry_run=not (notify_enabled and write))
        log.info("%d new re-runs at your cinemas", n)
    else:
        log.info("No cinemas configured in config.toml, so no alerts sent")
    failed = [c for c, st in status.items() if not st.get("ok")]
    if failed:
        log.warning("Couldn't reach %s from here; their existing data was left as it was", ", ".join(failed))
    return reruns
