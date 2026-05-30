from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

log = logging.getLogger(__name__)


class HealthState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state: dict[str, Any] = {
            "ok": False,
            "playback_state": "starting",
            "last_error": None,
            "polls": 0,
            "consecutive_failures": 0,
        }

    def update(self, **kwargs: Any) -> None:
        with self._lock:
            self.state.update(kwargs)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self.state)


def start_health_server(port: int, health: HealthState) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib API
            if self.path not in ("/healthz", "/readyz", "/"):
                self.send_response(404)
                self.end_headers()
                return
            payload = health.snapshot()
            payload["alive"] = True
            # /healthz is liveness for Docker: the process is up even if the TV is temporarily offline.
            # /readyz is readiness: last poll succeeded and Home Assistant was reachable.
            status = 200 if self.path in ("/healthz", "/") or payload.get("ok") else 503
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: Any) -> None:
            log.debug("healthcheck: " + fmt, *args)

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info("Health endpoint listening on :%s/healthz", port)
    return server
