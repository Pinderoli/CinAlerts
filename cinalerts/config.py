from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .sources import SOURCES


@dataclass
class Config:
    min_years_old: float = 1
    days_ahead: int = 14
    cinemas: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    exclude_titles: list[str] = field(default_factory=list)
    chains: list[str] = field(default_factory=lambda: list(SOURCES))
    site_url: str = ""
    realert_after_days: int = 30

    def title_excluded(self, title: str) -> bool:
        return any(re.search(p, title, re.I) for p in self.exclude_titles)


def load(path: Path) -> Config:
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    known = Config.__dataclass_fields__
    unknown = set(data) - set(known)
    if unknown:
        raise ValueError(f"Unknown config keys in {path}: {', '.join(sorted(unknown))}")
    cfg = Config(**data)
    bad = [c for c in cfg.chains if c not in SOURCES]
    if bad:
        raise ValueError(f"Unknown chains {bad}; choose from {list(SOURCES)}")
    return cfg
