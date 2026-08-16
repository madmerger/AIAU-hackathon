"""HTTP server for the hackathon monitoring dashboard (standard library only)."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import store
from aggregate import build_payload
from collector import Collector
from config import Config
from devin_api import DevinEnterpriseClient

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
logger = logging.getLogger(__name__)


def make_handler(config: Config, connection, collector: Collector):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            logger.debug("%s - %s", self.address_string(), format % args)

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def _send_static(self, relative_path: str) -> None:
            path = os.path.normpath(os.path.join(STATIC_DIR, relative_path))
            if not path.startswith(STATIC_DIR) or not os.path.isfile(path):
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
            with open(path, "rb") as handle:
                self._send(200, handle.read(), content_type)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send_static("index.html")
            elif path == "/api/data":
                state = {
                    "last_poll_at": collector.last_poll_at,
                    "last_error": collector.last_error,
                    "poll_interval": config.poll_interval,
                }
                self._send_json(200, build_payload(connection, config, state))
            elif path == "/api/health":
                self._send_json(200, {"ok": collector.last_error is None, "last_poll_at": collector.last_poll_at})
            elif path.startswith("/static/"):
                self._send_static(path[len("/static/") :])
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

    return Handler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = Config.from_env()
    connection = store.connect(config.db_path)
    client = DevinEnterpriseClient(config.api_base, config.api_key)
    collector = Collector(
        client,
        connection,
        org_refresh_interval=config.org_refresh_interval,
        summary_refresh_interval=config.summary_refresh_interval,
        consumption_refresh_interval=config.consumption_refresh_interval,
    )

    collector.poll()
    thread = threading.Thread(target=collector.run_forever, args=(config.poll_interval,), daemon=True)
    thread.start()

    server = ThreadingHTTPServer(("0.0.0.0", config.port), make_handler(config, connection, collector))
    logger.info("dashboard listening on http://localhost:%s", config.port)
    server.serve_forever()


if __name__ == "__main__":
    main()
