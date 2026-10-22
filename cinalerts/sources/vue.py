"""Vue: myvue.com's own JSON API."""

from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import logging

from .. import http
from ..models import Cinema, Film, Screening

log = logging.getLogger(__name__)
API = "https://www.myvue.com/api/microservice/showings"


def _cinema_films(cid: str, cookies: dict) -> list[dict] | None:
    s = http.session()
    params = {"minEmbargoLevel": 3, "includesSession": "true", "includeSessionAttributes": "true"}
    try:
        return http.get_json(s, f"{API}/cinemas/{cid}/films", params=params, cookies=cookies).get("result") or []
    except Exception as e:
        log.warning("Vue cinema %s failed: %s", cid, e)
        return None


def scan(chain: str, days: int) -> tuple[list[Cinema], list[Screening]]:
    s = http.session()
    # Loading any page sets the microservicesToken cookie the API requires.
    http.request(s, "GET", "https://www.myvue.com/whats-on")
    cookies = dict(s.cookies)
    cinemas = []
    for group in http.get_json(s, f"{API}/cinemas")["result"]:
        for c in group["cinemas"]:
            cinemas.append(
                Cinema(
                    id=f"vue:{c['cinemaId']}",
                    chain="vue",
                    name=c.get("fullName") or c["cinemaName"],
                    city=c["cinemaName"],
                    url=c.get("whatsOnUrl") or "",
                )
            )

    last_day = (dt.date.today() + dt.timedelta(days=days)).isoformat()
    films: dict[str, Film] = {}
    screenings = []
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda c: (c, _cinema_films(c.id.split(":", 1)[1], cookies)), cinemas))
    if all(r is None for _, r in results):
        raise RuntimeError("every Vue cinema request failed")
    for cinema, cinema_films in results:
        for f in cinema_films or []:
            film = films.get(f["filmId"])
            if film is None:
                film = films[f["filmId"]] = Film(
                    title=f.get("filmTitle") or f.get("originalTitle") or "",
                    release_date=(f.get("releaseDate") or "")[:10] or None,
                    genres=[g if isinstance(g, str) else g.get("name", "") for g in f.get("genres") or []],
                    cast=[x.strip() for x in (f.get("cast") or "").split(",") if x.strip()],
                    directors=[x.strip() for x in (f.get("director") or "").split(",") if x.strip()],
                    poster=f.get("posterImageSrc"),
                )
            for g in f.get("showingGroups") or []:
                for sess in g.get("sessions") or []:
                    start = sess.get("startTime") or ""
                    if not start or start[:10] >= last_day:
                        continue
                    url = sess.get("bookingUrl") or ""
                    screenings.append(
                        Screening(
                            cinema_id=cinema.id,
                            film=film,
                            start=start[:19],
                            url=("https://www.myvue.com" + url) if url.startswith("/") else (url or cinema.url),
                            tags=[a.get("name", "") for a in sess.get("attributes") or []],
                        )
                    )
    return cinemas, screenings
