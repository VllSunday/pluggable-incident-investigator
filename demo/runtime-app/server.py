from __future__ import annotations

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REQUESTS = 0
ERRORS = 0
LOCK = threading.Lock()
ERROR_FRACTION = float(os.getenv("DEMO_ERROR_FRACTION", "0.8"))


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
                ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
        elif self.path == "/health":
            body = b'{"status":"degraded"}'
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
        else:
            body = b"runtime incident fixture\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


if __name__ == "__main__":
    threading.Thread(target=generate_traffic, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
