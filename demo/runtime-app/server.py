from __future__ import annotations

import json
import os
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REQUESTS = 0
ERRORS = 0
LOCK = threading.Lock()
ERROR_FRACTION = float(os.getenv("DEMO_ERROR_FRACTION", "0.8"))
CONTROL_TOKEN = os.getenv("DEMO_CONTROL_TOKEN", "runtime-demo-control-token")


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()


def generate_traffic() -> None:
    global ERRORS, REQUESTS
    while True:
        with LOCK:
            REQUESTS += 10
            ERRORS += round(10 * ERROR_FRACTION)
        time.sleep(1)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/metrics":
            with LOCK:
                body = (
                    "# HELP demo_http_requests_total Simulated HTTP requests.\n"
                    "# TYPE demo_http_requests_total counter\n"
                    f'demo_http_requests_total{{service="runtime-demo"}} {REQUESTS}\n'
                    "# HELP demo_http_errors_total Simulated HTTP 5xx responses.\n"
                    "# TYPE demo_http_errors_total counter\n"
                    f'demo_http_errors_total{{service="runtime-demo"}} {ERRORS}\n'
                    "# HELP demo_configured_error_fraction Active failure injection ratio.\n"
                    "# TYPE demo_configured_error_fraction gauge\n"
                    f'demo_configured_error_fraction{{service="runtime-demo"}} {ERROR_FRACTION}\n'
                ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
        elif self.path == "/health":
            with LOCK:
                healthy = ERROR_FRACTION <= 0.01
                body = json_bytes(
                    {
                        "status": "healthy" if healthy else "degraded",
                        "error_fraction": ERROR_FRACTION,
                    }
                )
            self.send_response(200 if healthy else 503)
            self.send_header("Content-Type", "application/json")
        elif self.path.startswith("/diagnostics/logs"):
            with LOCK:
                fraction = ERROR_FRACTION
            now = datetime.now(UTC).isoformat()
            body = json_bytes(
                {
                    "service": "runtime-demo",
                    "records": [
                        {
                            "timestamp": now,
                            "level": "ERROR",
                            "event": "request_failed",
                            "message": (
                                "Requests are rejected by the active failure-injection "
                                "configuration"
                            ),
                            "configured_error_fraction": fraction,
                            "config_source": "runtime_override",
                        },
                        {
                            "timestamp": now,
                            "level": "INFO",
                            "event": "remediation_hint",
                            "message": "Rollback runtime_override to the safe error fraction 0.0",
                            "rollback_target": 0.0,
                        },
                    ],
                }
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        else:
            body = b"runtime incident fixture\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        global ERROR_FRACTION
        if self.path != "/admin/rollback":
            self.send_error(404)
            return
        if self.headers.get("Authorization") != f"Bearer {CONTROL_TOKEN}":
            self.send_error(401)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self.send_error(400)
            return
        if payload.get("service") != "runtime-demo" or payload.get("target_error_fraction") != 0.0:
            self.send_error(422)
            return
        with LOCK:
            previous = ERROR_FRACTION
            ERROR_FRACTION = 0.0
        body = json_bytes(
            {
                "status": "applied",
                "service": "runtime-demo",
                "previous_error_fraction": previous,
                "current_error_fraction": ERROR_FRACTION,
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


if __name__ == "__main__":
    threading.Thread(target=generate_traffic, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
