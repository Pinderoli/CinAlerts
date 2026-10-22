"""Push notifications via ntfy (https://ntfy.sh): install the app, subscribe to your topic."""

from __future__ import annotations

import logging
import os

from . import http

log = logging.getLogger(__name__)


def send(title: str, message: str, click: str | None = None, actions: list[dict] | None = None) -> bool:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        log.warning("NTFY_TOPIC not set; would have sent: %s\n%s", title, message)
        return False
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {}
    if token := os.environ.get("NTFY_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    body = {"topic": topic, "title": title, "message": message, "tags": ["film_projector"]}
    if click:
        body["click"] = click
    if actions:
        body["actions"] = actions
    http.request(http.session(proxied=False), "POST", server, json=body, headers=headers)
    return True
