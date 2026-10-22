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

### Where the scan runs

Odeon, Curzon, Cineworld and Vue sit behind Cloudflare, which blocks data-centre IPs such as GitHub
Actions. Everyman and Picturehouse don't. So the scan is built to run from **any number of
machines**, each contributing the chains it can reach:

- Each chain's data is its own file (`docs/data/chains/<chain>.json`, `data/alerted/<chain>.json`).
  A runner only rewrites a chain's files if it reached that chain. The website merges the files and
  marks a chain as out of date if it hasn't updated in 36 hours.
- [`scripts/run-and-push.sh`](scripts/run-and-push.sh) is the whole job: pull, scan, alert, commit,
  push. It runs on anything with push access, such as a laptop, a Raspberry Pi or a VPS.

Current runners:

| Runner | Reaches | Setup |
| --- | --- | --- |
| GitHub Actions, daily 07:00 UTC ([`scan.yml`](.github/workflows/scan.yml)) | Everyman, Picturehouse (all chains with a proxy) | `NTFY_TOPIC` secret |
| A Mac on a home network, daily 09:00 | All chains | `scripts/macos/install.sh <ntfy-topic>` |

The Mac job uses its own clone in `~/.cinalerts` and never touches your working copy. If the Mac
was asleep at 09:00, it runs when it wakes. Logs go to `~/.cinalerts/scan.log`. Remove it with
`scripts/macos/uninstall.sh`.

**To stop depending on any one device**, add a `CINALERTS_PROXY` repo secret
(`http://user:pass@host:port`). Chain requests then go through it, and Actions alone can scan
everything. A residential proxy is needed, because data-centre proxies get blocked the same way.
IMDb, Wikidata and ntfy requests never use the proxy.

You get one alert per film per cinema. If a film stops showing there for 30 days and comes back,
you get alerted again.

## Towards a public app

What already supports public use:

- The website is static and needs no accounts. Cinema choices are stored in the visitor's browser.
- Scanning is decoupled from any device: proxy plus Actions, or any cheap always-on box.
- The data is plain JSON per chain, which an iOS app could read directly.

What's still personal: alerts come from `config.toml`, meaning one set of cinemas sent to one
ntfy topic. Options for per-user alerts:

1. **Per-cinema ntfy topics.** Publish each cinema's new re-runs to its own topic (e.g.
   `cinalerts-odeon-153`), and the site's picker shows "subscribe" links. No backend or accounts,
   but it needs a self-hosted ntfy server, since ntfy.sh limits daily messages.
2. **A small backend.** Store users' cinemas and genres, and send through Web Push or APNs. This is
   the route for an App Store app.

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
