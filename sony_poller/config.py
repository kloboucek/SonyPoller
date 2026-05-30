from __future__ import annotations

import os
from dataclasses import dataclass


TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    tv_adb_host: str
    ha_url: str
    ha_token: str
    ha_entity_id: str
    poll_interval: float = 1.0
    adb_timeout: float = 5.0
    update_on_change_only: bool = True
    unknown_after_failures: int = 3
    health_port: int = 8080
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            tv_adb_host=require_env("TV_ADB_HOST"),
            ha_url=require_env("HA_URL").rstrip("/"),
            ha_token=require_env("HA_TOKEN"),
            ha_entity_id=os.getenv("HA_ENTITY_ID", "sensor.sony_tv_playback_state"),
            poll_interval=float(os.getenv("POLL_INTERVAL", "1")),
            adb_timeout=float(os.getenv("ADB_TIMEOUT", "5")),
            update_on_change_only=os.getenv("UPDATE_ON_CHANGE_ONLY", "true").lower() in TRUE_VALUES,
            unknown_after_failures=int(os.getenv("UNKNOWN_AFTER_FAILURES", "3")),
            health_port=int(os.getenv("HEALTH_PORT", "8080")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
