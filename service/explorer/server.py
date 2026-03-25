#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request
from urllib.parse import urlparse


STATIC_DIR = Path(__file__).with_name("static")


class Handler(BaseHTTPRequestHandler):
    indexer_base_url: str = ""

    def _send_json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_static(self, name: str) -> None:
        path = STATIC_DIR / name
        if not path.exists():
            self.send_error(404)
            return
        payload = path.read_bytes()
        ctype = "text/html" if name.endswith(".html") else "application/javascript"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            return self._send_static("index.html")
        if path == "/app.js":
            return self._send_static("app.js")
        if path == "/health":
            return self._send_json(200, {"ok": True})
        if path.startswith("/api/"):
            target = self.indexer_base_url.rstrip("/") + path.replace("/api", "", 1)
            try:
                with request.urlopen(target, timeout=10) as resp:
                    body = resp.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            except Exception as e:  # noqa: BLE001
                return self._send_json(502, {"error": f"indexer upstream error: {e}"})
        self.send_error(404)


def main() -> None:
    parser = argparse.ArgumentParser(description="Paramutuel explorer web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--indexer-base-url", default="http://127.0.0.1:8090")
    args = parser.parse_args()

    Handler.indexer_base_url = args.indexer_base_url
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Explorer listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
