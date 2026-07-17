from __future__ import annotations

import logging
import signal
import sys
import time
from dataclasses import dataclass

from .adb import AdbClient, TvPowerState
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
    last_sent_at: float = 0.0
    consecutive_failures: int = 0

    def tick(self) -> None:
        started = time.monotonic()
        self.health.update(polls=self.health.snapshot().get("polls", 0) + 1)
        state, power = self._read_adb_state()
        poll_duration_ms = round((time.monotonic() - started) * 1000, 1)
        attributes = self._power_attributes(power)
        if state == "unknown":
            self.consecutive_failures += 1
            self.health.update(
                ok=False,
                playback_state="unknown",
                tv_power_state=power.power,
                display_state=power.display_state,
                wakefulness=power.wakefulness,
                poll_duration_ms=poll_duration_ms,
                consecutive_failures=self.consecutive_failures,
                last_error="Unable to determine playback state",
            )
            if self.consecutive_failures == self.config.unknown_after_failures:
                log.warning(
                    "ADB playback state unknown for %s consecutive polls; publishing unknown",
                    self.consecutive_failures,
                )
            elif (
                self.consecutive_failures > self.config.unknown_after_failures
                and self.consecutive_failures % self.config.unknown_after_failures == 0
            ):
                log.warning(
                    "ADB playback state still unknown after %s consecutive polls",
                    self.consecutive_failures,
                )
            if (
                self.config.reconnect_after_failures > 0
                and self.consecutive_failures % self.config.reconnect_after_failures == 0
            ):
                log.info("Attempting ADB reconnect after %s failed poll(s)", self.consecutive_failures)
                self.adb.connect()
            if self.consecutive_failures >= self.config.unknown_after_failures:
                self._send_state("unknown", attributes)
            return

        if self.consecutive_failures:
            log.info("ADB playback state recovered after %s failed poll(s)", self.consecutive_failures)
        self.consecutive_failures = 0
        self.health.update(
            ok=True,
            playback_state=state,
            tv_power_state=power.power,
            display_state=power.display_state,
            wakefulness=power.wakefulness,
            poll_duration_ms=poll_duration_ms,
            consecutive_failures=0,
            last_error=None,
        )
        stable_state, stable_attributes = self._stable_state(state, attributes)
        if stable_state is not None:
            self._send_state(stable_state, stable_attributes)

    def _read_adb_state(self) -> tuple[str, TvPowerState]:
        power = self.adb.power_state()
        if power.power == "off":
            return "off", power
        return self.adb.playback_state(), power

    def _stable_state(
        self, state: str, attributes: dict[str, object]
    ) -> tuple[str | None, dict[str, object] | None]:
        if (
            not self.config.update_on_change_only
            or state == self.last_sent_state
            or self.config.state_stability_seconds <= 0
        ):
            return state, attributes

        time.sleep(self.config.state_stability_seconds)
        confirmed_state, confirmed_power = self._read_adb_state()
        if confirmed_state != state:
            log.info(
                "Ignoring transient ADB state %s -> %s after %.3fs stability check",
                state,
                confirmed_state,
                self.config.state_stability_seconds,
            )
            return None, None
        return state, self._power_attributes(confirmed_power)

    def _power_attributes(self, power: TvPowerState) -> dict[str, object]:
        return {
            "tv_power_state": power.power,
            "display_state": power.display_state,
            "wakefulness": power.wakefulness,
        }

    def _send_state(self, state: str, attributes: dict[str, object] | None = None) -> None:
        now = time.monotonic()
        unchanged = state == self.last_sent_state
        force_due = (
            self.config.force_update_interval > 0
            and self.last_sent_at > 0
            and now - self.last_sent_at >= self.config.force_update_interval
        )
        if self.config.update_on_change_only and unchanged and not force_due:
            log.debug("State unchanged (%s); skipping HA update", state)
            return
        if unchanged and force_due:
            log.info("Force-updating unchanged HA state %s after %.0fs", state, now - self.last_sent_at)
        merged_attributes = {
            "source": "SonyPoller",
            "tv_adb_host": self.config.tv_adb_host,
            "update_on_change_only": self.config.update_on_change_only,
            **(attributes or {}),
        }
        self.ha.update_state(state, merged_attributes)
        self.last_sent_state = state
        self.last_sent_at = now


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

    next_poll = time.monotonic()
    while not stop:
        try:
            poller.tick()
        except Exception as exc:  # noqa: BLE001 - daemon must keep running
            log.exception("Poll failed: %s", exc)
            health.update(ok=False, last_error=str(exc))
            adb.connect()
        next_poll += config.poll_interval
        sleep_for = max(0.0, next_poll - time.monotonic())
        if sleep_for == 0.0:
            next_poll = time.monotonic()
        time.sleep(sleep_for)

    server.shutdown()
    server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
