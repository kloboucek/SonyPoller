from __future__ import annotations

import logging
from typing import Any

import requests

log = logging.getLogger(__name__)


class HomeAssistantClient:
    def __init__(self, base_url: str, token: str, entity_id: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.entity_id = entity_id
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    def update_state(self, state: str, attributes: dict[str, Any] | None = None) -> None:
        payload = {
            "state": state,
            "attributes": {
                "friendly_name": "Sony TV Playback State",
                "icon": icon_for_state(state),
                **(attributes or {}),
            },
        }
        url = f"{self.base_url}/api/states/{self.entity_id}"
        response = self.session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        log.info("Updated %s => %s", self.entity_id, state)


def icon_for_state(state: str) -> str:
    if state == "playing":
        return "mdi:play-circle"
    if state == "paused":
        return "mdi:pause-circle"
    return "mdi:help-circle"
