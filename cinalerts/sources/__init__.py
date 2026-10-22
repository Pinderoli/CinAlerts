from __future__ import annotations

from typing import Callable

from ..models import Cinema, Screening
from . import boxoffice, picturehouse, vista, vue

Scanner = Callable[[str, int], tuple[list[Cinema], list[Screening]]]

SOURCES: dict[str, Scanner] = {
    "odeon": vista.scan,
    "curzon": vista.scan,
    "cineworld": boxoffice.scan,
    "everyman": boxoffice.scan,
    "vue": vue.scan,
    "picturehouse": picturehouse.scan,
}

CHAIN_NAMES = {
    "odeon": "Odeon",
    "curzon": "Curzon",
    "cineworld": "Cineworld",
    "everyman": "Everyman",
    "vue": "Vue",
    "picturehouse": "Picturehouse",
}
