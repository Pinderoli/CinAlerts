"""BoxOffice (Webedia) Gatsby sites: Cineworld and Everyman."""

from __future__ import annotations

import datetime as dt

from .. import http
from ..models import Cinema, Film, Screening

CHAINS = {
    "cineworld": "https://www.cineworld.co.uk",
    "everyman": "https://www.everymancinema.com",
}
THEATERS_PER_REQUEST = 15
MOVIES_PER_REQUEST = 40


def _theaters(s, base: str) -> list[dict]:
    """The theatre list lives in a Gatsby static query whose hash changes between deploys."""
    page = http.get_json(s, f"{base}/page-data/index/page-data.json")
    for h in page.get("staticQueryHashes", []):
        data = http.get_json(s, f"{base}/page-data/sq/d/{h}.json").get("data") or {}
        nodes = (data.get("allTheater") or {}).get("nodes") or []
        if nodes and nodes[0].get("name"):  # other queries list theatres by id only
            return nodes
    raise RuntimeError(f"Couldn't find theatre list on {base}")


def scan(chain: str, days: int) -> tuple[list[Cinema], list[Screening]]:
    base = CHAINS[chain]
    s = http.session()

    cinemas = []
    tz = {}
    for t in _theaters(s, base):
        info = t.get("practicalInfo") or {}
        if not t.get("id") or not t.get("name") or info.get("closed") or ((t.get("country") or {}).get("iso31661A2") not in (None, "GB")):
            continue
        coords = info.get("coordinates") or {}
        cinemas.append(
            Cinema(
                id=f"{chain}:{t['id']}",
                chain=chain,
                name=t["name"],
                city=(info.get("location") or {}).get("city") or "",
                lat=coords.get("latitude"),
                lon=coords.get("longitude"),
                url=base + (t.get("path") or ""),
            )
        )
        tz[t["id"]] = t.get("timeZone") or "Europe/London"
    by_id = {c.id: c for c in cinemas}

    start = dt.date.today()
    end = start + dt.timedelta(days=days)
    raw: list[tuple[str, str, dict]] = []  # (theater id, movie id, showtime)
    ids = list(tz)
    for i in range(0, len(ids), THEATERS_PER_REQUEST):
        body = {
            "theaters": [{"id": t, "timeZone": tz[t]} for t in ids[i : i + THEATERS_PER_REQUEST]],
            "from": f"{start}T03:00:00",
            "to": f"{end}T03:00:00",
            "nin": [],
            "sin": [],
        }
        data = http.post_json(s, f"{base}/api/gatsby-source-boxofficeapi/schedule", json=body) or {}
        for theater_id, t in data.items():
            for movie_id, by_day in (t.get("schedule") or {}).items():
                for showtimes in by_day.values():
                    raw.extend((theater_id, movie_id, st) for st in showtimes)

    movie_ids = sorted({m for _, m, _ in raw})
    films: dict[str, Film] = {}
    for i in range(0, len(movie_ids), MOVIES_PER_REQUEST):
        batch = movie_ids[i : i + MOVIES_PER_REQUEST]
        for m in http.get_json(s, f"{base}/api/gatsby-source-boxofficeapi/movies", params=[("ids", x) for x in batch]) or []:
            locale = m.get("locale") or {}
            dates = sorted(r["releasedAt"][:10] for r in m.get("releases") or [] if r.get("releasedAt"))
            earliest = dates[0] if dates else None
            films[m["id"]] = Film(
                title=locale.get("title") or m.get("title") or "",
                release_date=earliest,
                # An old date here is reliable; a recent one may just be a re-release date.
                release_trusted=bool(earliest and earliest < str(start - dt.timedelta(days=365))),
                genres=[g.strip() for g in (m.get("genres") or "").split(",") if g.strip()],
                cast=m.get("casting") or [],
                directors=m.get("direction") or [],
                poster=(locale.get("poster") or {}).get("url") or m.get("poster"),
            )

    screenings = []
    for theater_id, movie_id, st in raw:
        cid = f"{chain}:{theater_id}"
        if movie_id not in films or cid not in by_id or st.get("isExpired"):
            continue
        url = by_id[cid].url
        for tk in (st.get("data") or {}).get("ticketing") or []:
            if tk.get("provider") == "default" and tk.get("urls"):
                url = tk["urls"][0]
                break
        screenings.append(
            Screening(cinema_id=cid, film=films[movie_id], start=st["startsAt"][:19], url=url, tags=st.get("tags") or [])
        )
    return cinemas, screenings
