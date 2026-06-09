import logging
import os
import unittest
from unittest.mock import patch

from sony_poller.adb import TvPowerState, parse_media_session, parse_power_state
from sony_poller.config import Config
from sony_poller.home_assistant import icon_for_state
from sony_poller.main import Poller
from sony_poller.health import HealthState


class DummyAdb:
    def __init__(self, states):
        self.states = list(states)

    def playback_state(self):
        return self.states.pop(0)

    def power_state(self):
        return TvPowerState("on", "ON", "Awake")


class DummyPowerAwareAdb:
    def __init__(self, power_states, playback_states):
        self.power_states = list(power_states)
        self.playback_states = list(playback_states)
        self.playback_calls = 0

    def power_state(self):
        return self.power_states.pop(0)

    def playback_state(self):
        self.playback_calls += 1
        return self.playback_states.pop(0)


class DummyHa:
    def __init__(self):
        self.calls = []

    def update_state(self, state, attributes=None):
        self.calls.append((state, attributes or {}))


class SonyPollerTests(unittest.TestCase):
    def test_parse_playing_state(self):
        output = "Sessions Stack - PlaybackState {state=3, position=123}"
        self.assertEqual(parse_media_session(output), "playing")

    def test_parse_paused_state(self):
        output = "Sessions Stack - PlaybackState {state=2, position=123}"
        self.assertEqual(parse_media_session(output), "paused")

    def test_parse_idle_state(self):
        output = "Sessions Stack - PlaybackState {state=1, position=123}"
        self.assertEqual(parse_media_session(output), "idle")

    def test_parse_buffering_as_playing(self):
        output = "Sessions Stack - PlaybackState {state=6, position=123}"
        self.assertEqual(parse_media_session(output), "playing")

    def test_parse_unknown_state(self):
        self.assertEqual(parse_media_session("no useful media session"), "unknown")

    def test_parse_power_state_off_from_display_state(self):
        power = parse_power_state("mWakefulness=Asleep\nDisplay State=OFF\nmState=OFF")
        self.assertEqual(power.power, "off")
        self.assertEqual(power.display_state, "OFF")
        self.assertEqual(power.wakefulness, "Asleep")

    def test_parse_power_state_on_from_awake_display(self):
        power = parse_power_state("mWakefulness=Awake\nDisplay State=ON\nmState=ON")
        self.assertEqual(power.power, "on")
        self.assertEqual(power.display_state, "ON")
        self.assertEqual(power.wakefulness, "Awake")

    def test_icons(self):
        self.assertEqual(icon_for_state("playing"), "mdi:play-circle")
        self.assertEqual(icon_for_state("paused"), "mdi:pause-circle")
        self.assertEqual(icon_for_state("off"), "mdi:television-off")
        self.assertEqual(icon_for_state("unknown"), "mdi:help-circle")

    @patch.dict(
        os.environ,
        {
            "TV_ADB_HOST": "tv.example.test:5555",
            "HA_URL": "http://ha.local:8123/",
            "HA_TOKEN": "token",
            "POLL_INTERVAL": "2",
            "UPDATE_ON_CHANGE_ONLY": "true",
        },
        clear=True,
    )
    def test_config_from_env(self):
        config = Config.from_env()
        self.assertEqual(config.tv_adb_host, "tv.example.test:5555")
        self.assertEqual(config.ha_url, "http://ha.local:8123")
        self.assertEqual(config.poll_interval, 2.0)
        self.assertTrue(config.update_on_change_only)

    def test_poller_only_posts_changes(self):
        config = Config(
            tv_adb_host="tv:5555",
            ha_url="http://ha",
            ha_token="token",
            ha_entity_id="sensor.sony",
            update_on_change_only=True,
        )
        ha = DummyHa()
        poller = Poller(DummyAdb(["playing", "playing", "paused"]), ha, HealthState(), config)
        poller.tick()
        poller.tick()
        poller.tick()
        self.assertEqual([call[0] for call in ha.calls], ["playing", "paused"])

    def test_poller_publishes_off_when_tv_power_is_off_without_checking_playback(self):
        config = Config(
            tv_adb_host="tv:5555",
            ha_url="http://ha",
            ha_token="token",
            ha_entity_id="sensor.sony",
            update_on_change_only=True,
        )
        ha = DummyHa()
        adb = DummyPowerAwareAdb([TvPowerState("off", "OFF", "Asleep")], ["playing"])
        poller = Poller(adb, ha, HealthState(), config)  # type: ignore[arg-type]

        poller.tick()

        self.assertEqual([call[0] for call in ha.calls], ["off"])
        self.assertEqual(adb.playback_calls, 0)
        self.assertEqual(ha.calls[0][1]["tv_power_state"], "off")
        self.assertEqual(ha.calls[0][1]["display_state"], "OFF")
        self.assertEqual(ha.calls[0][1]["wakefulness"], "Asleep")

    def test_poller_keeps_idle_when_tv_power_is_on(self):
        config = Config(
            tv_adb_host="tv:5555",
            ha_url="http://ha",
            ha_token="token",
            ha_entity_id="sensor.sony",
            update_on_change_only=True,
        )
        ha = DummyHa()
        adb = DummyPowerAwareAdb([TvPowerState("on", "ON", "Awake")], ["idle"])
        poller = Poller(adb, ha, HealthState(), config)  # type: ignore[arg-type]

        poller.tick()

        self.assertEqual([call[0] for call in ha.calls], ["idle"])
        self.assertEqual(ha.calls[0][1]["tv_power_state"], "on")
        self.assertEqual(ha.calls[0][1]["display_state"], "ON")
        self.assertEqual(ha.calls[0][1]["wakefulness"], "Awake")

    def test_unknown_published_after_threshold(self):
        config = Config(
            tv_adb_host="tv:5555",
            ha_url="http://ha",
            ha_token="token",
            ha_entity_id="sensor.sony",
            update_on_change_only=True,
            unknown_after_failures=2,
        )
        ha = DummyHa()
        poller = Poller(DummyAdb(["unknown", "unknown"]), ha, HealthState(), config)  # type: ignore[arg-type]
        poller.tick()
        poller.tick()
        self.assertEqual([call[0] for call in ha.calls], ["unknown"])

    def test_transient_unknown_does_not_warn_or_publish(self):
        config = Config(
            tv_adb_host="tv:5555",
            ha_url="http://ha",
            ha_token="token",
            ha_entity_id="sensor.sony",
            update_on_change_only=True,
            unknown_after_failures=3,
        )
        ha = DummyHa()
        poller = Poller(DummyAdb(["unknown", "playing"]), ha, HealthState(), config)  # type: ignore[arg-type]
        logger = logging.getLogger("sony_poller.main")
        records = []

        class Handler(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Handler(level=logging.WARNING)
        logger.addHandler(handler)
        try:
            poller.tick()
            poller.tick()
        finally:
            logger.removeHandler(handler)

        self.assertEqual([call[0] for call in ha.calls], ["playing"])
        self.assertEqual([r for r in records if r.levelno >= logging.WARNING], [])

    def test_sustained_unknown_logs_warning_at_threshold(self):
        config = Config(
            tv_adb_host="tv:5555",
            ha_url="http://ha",
            ha_token="token",
            ha_entity_id="sensor.sony",
            update_on_change_only=True,
            unknown_after_failures=2,
        )
        ha = DummyHa()
        poller = Poller(DummyAdb(["unknown", "unknown"]), ha, HealthState(), config)  # type: ignore[arg-type]
        with self.assertLogs("sony_poller.main", level="WARNING") as captured:
            poller.tick()
            poller.tick()
        self.assertIn("publishing unknown", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
