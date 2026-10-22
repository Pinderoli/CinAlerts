"""Vista OCAPI: Odeon and Curzon.

Each site embeds a short-lived bearer token in its homepage, which the public API accepts.
"""

from __future__ import annotations

import datetime as dt
import re

from .. import http
from ..models import Cinema, Film, Screening

CHAINS = {
    "odeon": {
        "home": "https://www.odeon.co.uk/",
        "cinema_url": "https://www.odeon.co.uk/cinemas/{slug}/",
    },
    "curzon": {
        "home": "https://www.curzon.com/",
        "cinema_url": "https://www.curzon.com/venues/{slug}/",
    },
}
SITES_PER_REQUEST = 20


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _text(v) -> str:
    return (v or {}).get("text") or "" if isinstance(v, dict) else (v or "")


def scan(chain: str, days: int) -> tuple[list[Cinema], list[Screening]]:
    cfg = CHAINS[chain]
    s = http.session()
    home = http.request(s, "GET", cfg["home"]).text
    token = re.search(r'"authToken"\s*:\s*"([^"]+)"', home).group(1)
    api = re.search(r'"apiUrl"\s*:\s*"([^"]+)"', home).group(1).rstrip("/") + "/ocapi/v1"
    headers = {"Authorization": f"Bearer {token}"}

    cinemas = []
    for site in http.get_json(s, f"{api}/sites", headers=headers)["sites"]:
        name = _text(site["name"])
        addr = (site.get("contactDetails") or {}).get("address") or {}
        loc = site.get("location") or {}
        cinemas.append(
            Cinema(
                id=f"{chain}:{site['id']}",
                chain=chain,
                name=name,
                city=addr.get("city") or "",
                lat=loc.get("latitude"),
                lon=loc.get("longitude"),
                url=cfg["cinema_url"].format(slug=_slug(name)),
            )
        )
    by_id = {c.id: c for c in cinemas}
    site_ids = [c.id.split(":", 1)[1] for c in cinemas]

    screenings: list[Screening] = []
    films: dict[str, Film] = {}
    today = dt.date.today()
    for d in range(days):
        date = (today + dt.timedelta(days=d)).isoformat()
        for i in range(0, len(site_ids), SITES_PER_REQUEST):
            batch = site_ids[i : i + SITES_PER_REQUEST]
            data = http.get_json(
                s,
                f"{api}/showtimes/by-business-date/{date}",
                params=[("siteIds", sid) for sid in batch],
                headers=headers,
            )
            rel = data.get("relatedData") or {}
            genres = {g["id"]: _text(g["name"]) for g in rel.get("genres") or []}
            people = {}
            for p in rel.get("castAndCrew") or []:
                n = p.get("name") or {}
                people[p["id"]] = " ".join(x for x in (n.get("givenName"), n.get("familyName")) if x)
            for f in rel.get("films") or []:
                if f["id"] in films:
                    continue
                roles = [(people.get(c["castAndCrewMemberId"]), c.get("roles") or []) for c in f.get("castAndCrew") or []]
                films[f["id"]] = Film(
                    title=_text(f["title"]),
                    release_date=(f.get("releaseDate") or "")[:10] or None,
                    genres=[genres[g] for g in f.get("genreIds") or [] if g in genres],
                    cast=[n for n, r in roles if n and "Actor" in r],
                    directors=[n for n, r in roles if n and "Director" in r],
                )
            for st in data.get("showtimes") or []:
                film = films.get(st["filmId"])
                cid = f"{chain}:{st['siteId']}"
                if not film or cid not in by_id:
                    continue
                screenings.append(
                    Screening(
                        cinema_id=cid,
                        film=film,
                        start=st["schedule"]["startsAt"][:19],
                        url=by_id[cid].url,
                    )
                )
    return cinemas, screenings
