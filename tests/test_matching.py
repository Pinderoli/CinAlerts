import pytest

from cinalerts.genres import normalise
from cinalerts.identify import pick_candidate
from cinalerts.models import Film
from cinalerts.titles import clean_title, has_rerun_marker, title_variants


@pytest.mark.parametrize(
    "raw, clean",
    [
        ("28 Days Later... (Re-release)", "28 Days Later..."),
        ("Pan's Labyrinth 4K + Discussion", "Pan's Labyrinth"),
        ("Paprika (20th Anniversary) + Panel Discussion", "Paprika"),
        ("Don't Look Now (35mm) + Q&A", "Don't Look Now"),
        ("Halloween 4K Restoration", "Halloween"),
        ("The Odyssey 35mm", "The Odyssey"),
        ("Alien (1979) (4K)", "Alien"),
        ("Film Club: Derek vs Derek", "Derek vs Derek"),
        ("Mission: Impossible - The Final Reckoning", "Mission: Impossible - The Final Reckoning"),
        ("Ocean's Eleven", "Ocean's Eleven"),
    ],
)
def test_clean_title(raw, clean):
    assert clean_title(raw) == clean


def test_title_variants_fallbacks():
    assert title_variants("Guillermo del Toro's Pan's Labyrinth")[-1] == "Pan's Labyrinth"
    assert title_variants("Harbour Highlights: Scream")[-1] == "Scream"
    assert title_variants("Ocean's Eleven") == ["Ocean's Eleven"]


def test_rerun_markers():
    assert has_rerun_marker("Jaws (50th Anniversary)")
    assert has_rerun_marker("Heat", ["Showtime.Event.BigScreenClassics"])
    assert not has_rerun_marker("The Odyssey 35mm")


SENSE = [
    {"id": "tt2", "l": "Sense and Sensibility", "y": 2026, "qid": "movie", "s": "Daisy Edgar-Jones, Esmé Creed-Miles", "rank": 21},
    {"id": "tt1", "l": "Sense and Sensibility", "y": 1995, "qid": "movie", "s": "Emma Thompson, Kate Winslet", "rank": 304},
]


def test_new_film_sharing_old_title_picks_new_by_cast():
    film = Film("Sense and Sensibility", release_date="2026-09-25", cast=["Daisy Edgar-Jones"])
    assert pick_candidate(SENSE, film, film.title, [])["y"] == 2026


def test_rerun_picks_old_by_cast():
    film = Film("Sense and Sensibility", release_date="2026-09-25", cast=["Emma Thompson", "Hugh Grant"])
    assert pick_candidate(SENSE, film, film.title, [])["y"] == 1995


def test_no_cast_prefers_listing_year_unless_marked_rerun():
    film = Film("Sense and Sensibility", release_date="2026-09-25")
    assert pick_candidate(SENSE, film, film.title, [])["y"] == 2026
    marked = Film("Sense and Sensibility (30th Anniversary)", release_date="2026-09-25")
    assert pick_candidate(SENSE, marked, marked.title, [])["y"] == 1995


def test_cast_mismatch_with_only_old_candidate_is_rejected():
    # A new film whose title matches an older one we know isn't it (different cast).
    film = Film("Sense and Sensibility", release_date="2026-09-25", cast=["Someone Else"])
    assert pick_candidate([SENSE[1]], film, film.title, []) is None


def test_genres_normalise():
    assert normalise(["science fiction film", "neo-noir", "drama film"]) == ["Crime", "Drama", "Sci-Fi"]
    assert normalise("Horror, Action, Detective") == ["Action", "Horror", "Mystery"]
