"""Picturehouse: picturehouses.com (Laravel) AJAX endpoints. Needs the XSRF cookie from the homepage."""

from __future__ import annotations

import datetime as dt
import logging
import urllib.parse

from .. import http
from ..models import Cinema, Film, Screening

log = logging.getLogger(__name__)
BASE = "https://www.picturehouses.com"


def scan(chain: str, days: int) -> tuple[list[Cinema], list[Screening]]:
    s = http.session()
    http.request(s, "GET", BASE + "/")
    headers = {
        "X-XSRF-TOKEN": urllib.parse.unquote(s.cookies.get("XSRF-TOKEN") or ""),
        "X-Requested-With": "XMLHttpRequest",
        "Referer": BASE + "/",
    }

    cinemas = []
    for c in http.post_json(s, f"{BASE}/ajax-cinema-list", headers=headers)["cinema_list"]:
        cinemas.append(
            Cinema(
                id=f"picturehouse:{c['cinema_id']}",
                chain="picturehouse",
                name=c["name"],
                city=c.get("address2") or c.get("city") or "",
                lat=float(c["latitude"]) if c.get("latitude") else None,
                lon=float(c["longitude"]) if c.get("longitude") else None,
                url=f"{BASE}/cinema/{c['slug']}",
            )
        )

    last_day = (dt.date.today() + dt.timedelta(days=days)).isoformat()
    films: dict[str, Film] = {}
    screenings = []
    failures = 0
    for cinema in cinemas:
        try:
            data = http.post_json(
                s, f"{BASE}/api/scheduled-movies-ajax", data={"cinema_id": cinema.id.split(":", 1)[1]}, headers=headers
            )
        except Exception as e:
            log.warning("Picturehouse cinema %s failed: %s", cinema.id, e)
            failures += 1
            continue
        for m in data.get("movies") or []:
            film = films.setdefault(m["ScheduledFilmId"], Film(title=m.get("Title") or "", poster=m.get("image_url")))
            for st in m.get("show_times") or []:
                start = st.get("Showtime") or ""
                if not start or start[:10] >= last_day:
                    continue
                screenings.append(
                    Screening(
                        cinema_id=cinema.id,
                        film=film,
                        start=start[:19],
                        url=cinema.url,
                        tags=st.get("SessionAttributesNames") or [],
                    )
                )
    if failures == len(cinemas):
        raise RuntimeError("every Picturehouse cinema request failed")
    return cinemas, screenings
