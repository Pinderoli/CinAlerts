"""Work out which real film a listing is, and when it was *originally* released.

Chains usually report the re-release date, and titles are ambiguous (a 2026 "Sense and
Sensibility" exists alongside the 1995 one), so we:
  1. search IMDb's public suggestion endpoint for the cleaned title,
  2. score exact-title candidates using cast/director overlap, years and re-run markers,
  3. look the winner up on Wikidata for its earliest release date and genres.
Results are cached in data/films.json so each title is only looked up once.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import re
import urllib.parse
from pathlib import Path

from . import http
from .models import Film
from .titles import clean_title, has_rerun_marker, norm, title_variants, title_year

log = logging.getLogger(__name__)

IMDB_SUGGEST = "https://v2.sg.media-imdb.com/suggestion/{first}/{query}.json"
WIKIDATA = "https://query.wikidata.org/sparql"
WIKIDATA_UA = "CinAlerts/1.0 (https://github.com/Pinderoli/CinAlerts)"
FILM_TYPES = {"movie", "tvMovie", "video", "short", "tvSpecial"}
RETRY_MISSES_AFTER = dt.timedelta(days=7)


def _surname_set(names: list[str]) -> set[str]:
    return {norm(n).split()[-1] for n in names if norm(n)}


def _year(date: str | None) -> int | None:
    return int(date[:4]) if date and re.match(r"\d{4}", date) else None


def score_candidate(c: dict, film: Film, raw_title: str, tags: list[str]) -> float:
    score = 0.0
    y = c.get("y")
    people = _surname_set(film.cast + film.directors)
    stars = _surname_set((c.get("s") or "").split(","))
    if people and stars & people:
        score += 100
    ty = title_year(raw_title)
    if ty and y:
        score += 200 if abs(y - ty) <= 1 else -50
    src_year = _year(film.release_date)
    if not src_year and y and has_rerun_marker(raw_title, tags):
        src_year = dt.date.today().year  # no listing date, but it's billed as a re-run: lean older
    if src_year and y:
        if film.release_trusted:
            score += 150 if abs(y - src_year) <= 1 else -50
        elif has_rerun_marker(raw_title, tags):
            score += 40 if y < src_year - 1 else -40
        elif abs(y - src_year) <= 1:
            score += 40  # most listings are new films
        if y > src_year + 1:
            score -= 100
    if c.get("qid") == "movie":
        score += 10
    rank = c.get("rank") or 10**6
    score += max(0.0, 20 - math.log2(rank))
    return score


def pick_candidate(cands: list[dict], film: Film, raw_title: str, tags: list[str], title: str | None = None) -> dict | None:
    target = norm(title or clean_title(raw_title))
    exact = [c for c in cands if c.get("qid") in FILM_TYPES and norm(c.get("l", "")) == target and c.get("y")]
    if not exact:
        return None
    best = max(exact, key=lambda c: score_candidate(c, film, raw_title, tags))
    # If we know the cast and nobody matches, a same-titled older film is probably a different
    # film (remake/namesake) - unless the listing itself signals a re-run.
    people = _surname_set(film.cast + film.directors)
    stars = _surname_set((best.get("s") or "").split(","))
    src_year = _year(film.release_date)
    if (
        people
        and stars
        and not (people & stars)
        and src_year
        and best["y"] < src_year - 1
        and not has_rerun_marker(raw_title, tags)
        and not film.release_trusted
    ):
        return None
    return best


class Identifier:
    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self.cache: dict = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        self.s = http.session(proxied=False)

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=1, sort_keys=True, ensure_ascii=False))

    @staticmethod
    def cache_key(film: Film) -> str:
        who = ",".join(sorted(_surname_set(film.cast[:3] + film.directors[:1])))
        return f"{norm(clean_title(film.title))}|{_year(film.release_date) or ''}|{who}"

    def _suggest(self, title: str) -> list[dict]:
        q = norm(title)[:60]
        if not q:
            return []
        url = IMDB_SUGGEST.format(first=q[0], query=urllib.parse.quote(q.replace(" ", "_")))
        try:
            return http.get_json(self.s, url).get("d") or []
        except Exception as e:
            log.warning("IMDb lookup failed for %r: %s", title, e)
            return []

    def identify(self, film: Film, tags: list[str]) -> dict | None:
        """Returns {imdb, title, year} or None. Cached."""
        key = self.cache_key(film)
        hit = self.cache.get(key)
        if hit is not None:
            if hit.get("imdb") or dt.datetime.fromisoformat(hit["checked"]) > dt.datetime.now() - RETRY_MISSES_AFTER:
                return hit if hit.get("imdb") else None
        best = None
        for variant in title_variants(film.title):
            best = pick_candidate(self._suggest(variant), film, film.title, tags, title=variant)
            if best:
                break
        entry = {"checked": dt.datetime.now().isoformat(timespec="seconds")}
        if best:
            entry.update(imdb=best["id"], title=best["l"], year=best["y"], poster=(best.get("i") or {}).get("imageUrl"))
        self.cache[key] = entry
        return entry if best else None

    def enrich(self, imdb_ids: list[str]) -> None:
        """Fetch earliest release date + genres from Wikidata for IMDb ids not yet enriched."""
        todo = [i for i in imdb_ids if f"wd|{i}" not in self.cache]
        for i in range(0, len(todo), 100):
            batch = todo[i : i + 100]
            values = " ".join(f'"{x}"' for x in batch)
            query = f"""
              SELECT ?imdb (MIN(?date) AS ?released) (GROUP_CONCAT(DISTINCT ?gl; separator="|") AS ?genres) WHERE {{
                VALUES ?imdb {{ {values} }}
                ?item wdt:P345 ?imdb.
                OPTIONAL {{ ?item wdt:P577 ?date }}
                OPTIONAL {{ ?item wdt:P136 ?g. ?g rdfs:label ?gl FILTER(lang(?gl) = "en") }}
              }} GROUP BY ?imdb"""
            try:
                data = http.get_json(
                    self.s, WIKIDATA, params={"query": query, "format": "json"}, headers={"User-Agent": WIKIDATA_UA}
                )
            except Exception as e:
                log.warning("Wikidata lookup failed: %s", e)
                continue
            found = set()
            for b in data["results"]["bindings"]:
                imdb = b["imdb"]["value"]
                found.add(imdb)
                self.cache[f"wd|{imdb}"] = {
                    "released": (b.get("released") or {}).get("value", "")[:10] or None,
                    "genres": [g for g in (b.get("genres") or {}).get("value", "").split("|") if g],
                }
            for imdb in set(batch) - found:
                self.cache[f"wd|{imdb}"] = {"released": None, "genres": []}

    def wikidata(self, imdb: str) -> dict:
        return self.cache.get(f"wd|{imdb}") or {"released": None, "genres": []}
