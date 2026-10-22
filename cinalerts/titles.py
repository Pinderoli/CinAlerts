"""Cleaning up cinema listing titles, e.g. "Film Club: Alien (4K Re-release)" -> "Alien"."""

from __future__ import annotations

import re
import unicodedata

# Words that suggest a screening is a re-run / repertory showing.
RERUN_MARKER = re.compile(
    r"re-?release|re-?issue|anniversary|\b4k\b|restor|remaster|classics?\b|retro|throwback|"
    r"rediscover|cult\b|back on the big screen|big ?screen ?classics|vintage|revival",
    re.I,
)

# Event-series words; a prefix like "<words>: " containing one of these is stripped.
_EVENT_WORDS = (
    r"season|club|classics?|presents|dochouse|retro|weekender|marathon|late|lates|cult|screening|festival|fest|"
    r"special|anniversary|rediscover|throwback|kids|kids'|family|parent|baby|toddler|autism|relaxed|"
    r"mini|matinee|members|preview|q ?& ?a|double bill|halloween|christmas|horror|ghibli|seniors|silver|"
    r"pride|women|lgbtq\+?|bfi|from the vault|sunday|saturday|throwback thursday|scared|sing-?a-?long"
)
_PREFIX = re.compile(rf"^\s*[^:]{{0,50}}\b(?:{_EVENT_WORDS})\b[^:]{{0,30}}[:|]\s+", re.I)

# Trailing bracketed bits like "(Re-release)", "[4K]", "(1982)", "(Subtitled)".
_SUFFIX_WORDS = (
    rf"{RERUN_MARKER.pattern}|\b(?:19|20)\d\d\b|imax|\b3d\b|\b2d\b|sub(?:titled|s)?\b|dubbed|\bcc\b|\bad\b|"
    r"parent|baby|autism|relaxed|hoh|sing-?a-?long|uncut|extended|director'?s cut|final cut|cut\b|"
    r"q ?& ?a|preview|intro|version|edition|\bpg\b|\b1[25]a?\b|\b18\b|\bu\b|dolby|screenx|4dx|laser|\b(?:35|70)\s?mm\b"
)
_BRACKET_SUFFIX = re.compile(rf"\s*[\(\[][^\)\]]*(?:{_SUFFIX_WORDS})[^\)\]]*[\)\]]\s*$", re.I)
_DASH_SUFFIX = re.compile(rf"\s+[-–—|:]\s+[^-–—|:]*(?:{_SUFFIX_WORDS})[^-–—|:]*$", re.I)
# Bare trailing markers with no separator, e.g. "Halloween 4K Restoration".
_BARE_SUFFIX = re.compile(
    r"\s+(?:\d+(?:st|nd|rd|th)\s+anniversary(?:\s+re-?release)?|4k(?:\s+(?:restoration|remaster(?:ed)?|re-?release))?|"
    r"re-?release|remastered|restored|restoration)\s*$",
    re.I,
)
# Add-ons like "+ Q&A", "+ Panel Discussion", "+ Intro by the Director".
_PLUS_EXTRA = re.compile(
    r"\s*\+\s*(?:[^+]*\b(?:q ?(?:&|\+|and) ?a|discussion|intro(?:duction|duced)?|panel|talk|conversation|"
    r"guest|live|director|cast|recorded|lecture|shorts?|party|quiz)\b[^+]*)$",
    re.I,
)
_FORMAT_SUFFIX = re.compile(r"\s+(?:in\s+)?(?:35|70)\s?mm\b.*$", re.I)
_POSSESSIVE_PREFIX = re.compile(r"^[A-Z][\w.\-]*\s(?:[\w.\-]+\s){0,2}[A-Z][\w.\-]*['’]s\s+(?=\S)")
_TITLE_YEAR = re.compile(r"[\(\[]\s*((?:19|20)\d\d)\s*[\)\]]")


def clean_title(raw: str) -> str:
    t = re.sub(r"\s+", " ", raw).strip()
    for _ in range(3):  # suffixes can be stacked, e.g. "Alien (1979) (4K)"
        new = _PLUS_EXTRA.sub("", t)
        new = _FORMAT_SUFFIX.sub("", _BRACKET_SUFFIX.sub("", new))
        new = _BARE_SUFFIX.sub("", _DASH_SUFFIX.sub("", new)).strip()
        if new == t:
            break
        t = new
    stripped = _PREFIX.sub("", t).strip()
    return stripped or t


def title_variants(raw: str) -> list[str]:
    """Cleaned title, then looser fallbacks to try if the first finds nothing."""
    base = clean_title(raw)
    out = [base]
    if ": " in base:  # "Harbour Highlights: Scream"
        out.append(clean_title(base.split(": ", 1)[1]))
    if m := _POSSESSIVE_PREFIX.match(base):  # "Guillermo del Toro's Pan's Labyrinth"
        out.append(base[m.end() :])
    if " + " in base:  # double bills: try the first film
        out.append(clean_title(base.split(" + ", 1)[0]))
    return list(dict.fromkeys(v for v in out if v))


def title_year(raw: str) -> int | None:
    m = _TITLE_YEAR.search(raw)
    return int(m.group(1)) if m else None


def has_rerun_marker(raw: str, tags: list[str] = ()) -> bool:
    return bool(RERUN_MARKER.search(raw) or any(RERUN_MARKER.search(t) for t in tags))


def norm(s: str) -> str:
    """Normalise a title for comparison."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"^(the|a|an) ", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()
