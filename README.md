# CinAlerts

Get a push notification when a UK cinema near you puts on a re-run: Interstellar, Blade Runner,
Pan's Labyrinth, anything first released more than a year ago (configurable).

There's no central listing for this, so CinAlerts scans every cinema of six chains once a day,
works out which films are old, publishes them to a website and pings your phone.

**Website:** https://pinderoli.github.io/CinAlerts

## Chains covered

| Chain | Source |
| --- | --- |
| Odeon | Vista OCAPI (token taken from odeon.co.uk) |
| Curzon | Vista OCAPI (token taken from curzon.com) |
| Cineworld | BoxOffice API behind cineworld.co.uk |
| Everyman | BoxOffice API behind everymancinema.com |
| Vue | myvue.com showings API |
| Picturehouse | picturehouses.com AJAX endpoints |

None of these are official public APIs. They're what the chains' own websites use, so expect one
to break occasionally. The website footer says which chains failed in the latest scan.

## How "is this a re-run?" works

Cinemas list re-runs with the *re-release* date, and titles are ambiguous (there's a 2026
*Sense and Sensibility* as well as the 1995 one). So for each listing CinAlerts:

1. Cleans the title (`"Film Club: Alien (4K Re-release) + Q&A"` → `Alien`).
2. Searches IMDb's public suggestion endpoint and picks the best exact-title match, using
   cast/director overlap, years and re-run markers ("anniversary", "4K", "re-release", …).
3. Gets the film's earliest release date and genres from Wikidata.
4. Counts it as a re-run if that date is at least `min_years_old` ago. It skips films whose UK
   release is within two years of a festival premiere, since those are new releases.

Lookups are cached in `data/films.json`.

## Setup

### Phone notifications

1. Install **ntfy** ([iOS](https://apps.apple.com/app/ntfy/id1625396347) /
   [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)).
2. Subscribe to your topic name (it's the `NTFY_TOPIC` repo secret). Anyone who knows the topic
   can read it, so keep it random.

### Pick your cinemas

Open the website, click **Choose cinemas**, tick yours, then **Copy for config.toml**. Paste the
result over `cinemas = []` in [`config.toml`](config.toml) and commit. You can also list IDs from the
command line:

```sh
python -m cinalerts cinemas leicester
```

`config.toml` also has genre filters, the age threshold, title exclusions and the chain list.

### Schedule

[`.github/workflows/scan.yml`](.github/workflows/scan.yml) runs daily at 07:00 UTC. It scans the
cinemas, sends alerts, then commits `docs/data` (the website) and `data/` (the lookup cache and
which alerts were already sent). You can also run it any time from the **Actions** tab.

You get one alert per film per cinema. If a film stops showing there for 30 days and comes back,
you get alerted again.

## Running locally

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m cinalerts run --dry-run           # scan and print, change nothing
.venv/bin/python -m cinalerts run --dry-run --chains odeon --days 3
NTFY_TOPIC=your-topic .venv/bin/python -m cinalerts test-notify
.venv/bin/python -m pytest
```

Preview the website with `python3 -m http.server -d docs`.

## Layout

```
cinalerts/
  sources/      one scraper per backend (vista, boxoffice, vue, picturehouse)
  titles.py     title cleaning and re-run markers
  identify.py   IMDb + Wikidata matching, cached
  run.py        scan → find re-runs → write site data → alert
docs/           the GitHub Pages site (static HTML/JS reading docs/data/*.json)
data/           lookup cache and alert history
```
