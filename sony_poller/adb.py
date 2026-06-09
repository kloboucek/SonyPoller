from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass

log = logging.getLogger(__name__)

PLAYING_STATES = {3, 6, 8}  # PLAYING, BUFFERING, CONNECTING
PAUSED_STATES = {2}
IDLE_STATES = {0, 1}  # NONE, STOPPED


@dataclass
class AdbResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""


class AdbClient:
    def __init__(self, host: str, timeout: float = 5.0) -> None:
        self.host = host
        self.timeout = timeout

    def run(self, *args: str) -> AdbResult:
        cmd = ["adb", "-s", self.host, *args]
        try:
            completed = subprocess.run(
                cmd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
                check=False,
            )
            return AdbResult(completed.returncode == 0, completed.stdout, completed.stderr)
        except subprocess.TimeoutExpired as exc:
            return AdbResult(False, exc.stdout or "", f"ADB timeout after {self.timeout}s")

    def connect(self) -> bool:
        try:
            completed = subprocess.run(
                ["adb", "connect", self.host],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            log.warning("ADB connect timed out for %s", self.host)
            return False
        output = f"{completed.stdout}\n{completed.stderr}".lower()
        ok = completed.returncode == 0 and ("connected" in output or "already connected" in output)
        if not ok:
            log.warning("ADB connect failed: %s", output.strip())
        return ok

    def playback_state(self) -> str:
        """Return playing/paused/unknown using Android media-session output."""
        result = self.run("shell", "dumpsys", "media_session")
        if not result.ok:
            log.debug("ADB media_session failed: %s", result.stderr.strip())
            return "unknown"
        return parse_media_session(result.stdout)


def parse_media_session(output: str) -> str:
    state = extract_playback_state(output)
    if state in PLAYING_STATES:
        return "playing"
    if state in PAUSED_STATES:
        return "paused"
    if state in IDLE_STATES:
        return "idle"

    text = output.upper()
    if "PLAYING" in text:
        return "playing"
    if "PAUSED" in text:
        return "paused"
    if "STOPPED" in text or "STATE_NONE" in text:
        return "idle"
    return "unknown"


def extract_playback_state(output: str) -> int | None:
    """Extract Android PlaybackState numeric state from dumpsys media_session output."""
    matches = re.findall(r"PlaybackState\s*\{[^}]*state=(\d+)", output, flags=re.IGNORECASE)
    if not matches:
        matches = re.findall(r"state=(\d+)", output, flags=re.IGNORECASE)
    if not matches:
        return None
    return int(matches[0])
