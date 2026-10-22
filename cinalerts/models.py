from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Cinema:
    id: str  # "<chain>:<chain's own id>", e.g. "odeon:017"
    chain: str
    name: str
    city: str = ""
    lat: float | None = None
    lon: float | None = None
    url: str = ""


@dataclass
class Film:
    """A film as one chain describes it. Different chains describe the same film differently."""

    title: str
    release_date: str | None = None  # whatever date the chain reports, often the *re*-release date
    release_trusted: bool = False  # True when the chain's date is known to be the original release
    genres: list[str] = field(default_factory=list)
    cast: list[str] = field(default_factory=list)
    directors: list[str] = field(default_factory=list)
    poster: str | None = None


@dataclass
class Screening:
    cinema_id: str
    film: Film
    start: str  # local ISO datetime
    url: str = ""
    tags: list[str] = field(default_factory=list)
