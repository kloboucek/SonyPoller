from __future__ import annotations

import logging
import signal
import sys
import time
from dataclasses import dataclass

from .adb import AdbClient
from .config import Config
from .health import HealthState, start_health_server
from .home_assistant import HomeAssistantClient

log = logging.getLogger(__name__)


@dataclass
class Poller:
    adb: AdbClient
    ha: HomeAssistantClient
    health: HealthState
    config: Config
    last_sent_state: str | None = None
    consecutive_failures: int = 0

    def tick(self) -> None:
        self.health.update(polls=self.health.snapshot().get("polls", 0) + 1)
        state = self.adb.playback_state()
        if state == "unknown":
            self.consecutive_failures += 1
            self.health.update(
                ok=False,
                playback_state="unknown",
                consecutive_failures=self.consecutive_failures,
                last_error="Unable to determine playback state",
            )
            if self.consecutive_failures >= self.config.unknown_after_failures:
                self._send_state("unknown")
            return

        self.consecutive_failures = 0
        self.health.update(
            ok=True,
            playback_state=state,
            consecutive_failures=0,
            last_error=None,
        )
        self._send_state(state)

    def _send_state(self, state: str) -> None:
        if self.config.update_on_change_only and state == self.last_sent_state:
            log.debug("State unchanged (%s); skipping HA update", state)
            return
        self.ha.update_state(
            state,
            {
                "source": "SonyPoller",
                "tv_adb_host": self.config.tv_adb_host,
                "update_on_change_only": self.config.update_on_change_only,
            },
        )
        self.last_sent_state = state


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> int:
    config = Config.from_env()
    configure_logging(config.log_level)

    stop = False

    def _stop(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True
        log.info("Shutdown requested")

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    health = HealthState()
    server = start_health_server(config.health_port, health)
    adb = AdbClient(config.tv_adb_host, config.adb_timeout)
    ha = HomeAssistantClient(config.ha_url, config.ha_token, config.ha_entity_id)
    poller = Poller(adb=adb, ha=ha, health=health, config=config)

    log.info("Starting SonyPoller for %s -> %s", config.tv_adb_host, config.ha_entity_id)
    adb.connect()

    while not stop:
        try:
            poller.tick()
        except Exception as exc:  # noqa: BLE001 - daemon must keep running
            log.exception("Poll failed: %s", exc)
            health.update(ok=False, last_error=str(exc))
            adb.connect()
        time.sleep(config.poll_interval)

    server.shutdown()
    server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
