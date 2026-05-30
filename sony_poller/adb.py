from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

log = logging.getLogger(__name__)

PLAY_HINTS = ("state=PlaybackState", "state=3", "PLAYING", "mCurrentFocus")
PAUSE_HINTS = ("state=2", "PAUSED", "STOPPED", "state=1")


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
            log.warning("ADB media_session failed: %s", result.stderr.strip())
            return "unknown"
        return parse_media_session(result.stdout)


def parse_media_session(output: str) -> str:
    text = output.upper()
    # Android PlaybackState state=3 means playing. This is the strongest signal.
    if "STATE=PLAYBACKSTATE" in text and "STATE=3" in text:
        return "playing"
    if "PLAYBACKSTATE" in text and "STATE=3" in text:
        return "playing"
    if "PLAYING" in text:
        return "playing"
    if "STATE=2" in text or "PAUSED" in text or "STOPPED" in text or "STATE=1" in text:
        return "paused"
    return "unknown"
