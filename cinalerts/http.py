"""HTTP helpers. curl_cffi impersonates Chrome's TLS fingerprint, which several chains require."""

from __future__ import annotations

import logging
import time

from curl_cffi import requests

log = logging.getLogger(__name__)

TIMEOUT = 45


def session() -> requests.Session:
    return requests.Session(impersonate="chrome", timeout=TIMEOUT)


def request(s: requests.Session, method: str, url: str, retries: int = 3, **kw):
    """Make a request, retrying on network errors and 5xx/429 responses."""
    for attempt in range(retries):
        try:
            r = s.request(method, url, **kw)
            if r.status_code < 500 and r.status_code != 429:
                r.raise_for_status()
                return r
            log.debug("%s %s -> %s", method, url, r.status_code)
        except requests.exceptions.HTTPError:
            raise
        except Exception as e:  # network-level failure
            log.debug("%s %s failed: %s", method, url, e)
            if attempt == retries - 1:
                raise
        time.sleep(2 ** attempt)
    r.raise_for_status()
    return r


def get_json(s: requests.Session, url: str, **kw):
    return request(s, "GET", url, **kw).json()


def post_json(s: requests.Session, url: str, **kw):
    return request(s, "POST", url, **kw).json()
