"""Map the many genre spellings (chain listings, Wikidata labels) onto one small set."""

from __future__ import annotations

import re

CANONICAL: dict[str, str] = {
    "Action": r"action|martial arts|superhero|swashbuckler",
    "Adventure": r"adventure",
    "Animation": r"animat|anime|stop-motion",
    "Comedy": r"comed|humou?r|satir|parody",
    "Crime": r"crime|gangster|heist|noir|mafia",
    "Documentary": r"documentar",
    "Drama": r"drama",
    "Family": r"family|children|kids",
    "Fantasy": r"fantasy|fairy",
    "History": r"histor|biograph|biopic|period",
    "Horror": r"horror|slasher|zombie|vampire|splatter",
    "Music": r"music|concert",
    "Mystery": r"myster|detective|whodunit",
    "Romance": r"romanc|romantic",
    "Sci-Fi": r"science fiction|sci-?fi|cyberpunk|dystopi|space opera",
    "Thriller": r"thriller|suspense|psychological",
    "War": r"\bwar\b",
    "Western": r"western",
}
_COMPILED = {name: re.compile(p, re.I) for name, p in CANONICAL.items()}


def normalise(raw: list[str] | str) -> list[str]:
    if isinstance(raw, str):
        raw = re.split(r"[,|/]", raw)
    out = set()
    for g in raw:
        for name, rx in _COMPILED.items():
            if rx.search(g):
                out.add(name)
    return sorted(out)
