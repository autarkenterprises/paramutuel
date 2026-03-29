#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .commands import build_create_market_command, build_market_action_command
from .security import token_authorized


STATIC_DIR = Path(__file__).with_name("static")


class Handler(BaseHTTPRequestHandler):
    rpc_url: str = ""
    private_key: str = ""
    allow_execute: bool = False
    auth_token: str | None = None

    @staticmethod
    def _redact_command(cmd: list[str]) -> list[str]:
        out = list(cmd)
        for i, token in enumerate(out[:-1]):
            if token == "--private-key":
                out[i + 1] = "<redacted>"
        return out

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
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")) or 0)
        payload = json.loads(raw.decode() or "{}")
        try:
            if path == "/api/preview/create-market":
                cmd = build_create_market_command(
                    factory=payload["factory"],
                    collateral=payload["collateral"],
                    question=payload["question"],
                    outcomes=payload["outcomes"],
                    betting_close_time=int(payload["bettingCloseTime"]),
                    resolution_window=int(payload["resolutionWindow"]),
                    resolver=payload.get("resolver", "0x0000000000000000000000000000000000000000"),
                    betting_closer=payload.get("bettingCloser", "0x0000000000000000000000000000000000000000"),
                    resolution_closer=payload.get("resolutionCloser", "0x0000000000000000000000000000000000000000"),
                    extra_recipients=payload.get("extraRecipients", []),
                    extra_bps=payload.get("extraBps", []),
                    rpc_url=self.rpc_url,
                    private_key=self.private_key,
                )
            elif path == "/api/preview/action":
                cmd = build_market_action_command(
                    market=payload["market"],
                    action=payload["action"],
                    outcome_index=payload.get("outcomeIndex"),
                    rpc_url=self.rpc_url,
                    private_key=self.private_key,
                )
            else:
                return self._send_json(404, {"error": "not found"})
        except (KeyError, ValueError) as e:
            return self._send_json(400, {"error": str(e)})

        if payload.get("execute"):
            if not self.allow_execute:
                return self._send_json(403, {"error": "execution disabled"})
            if not token_authorized(
                expected_token=self.auth_token,
                auth_header=self.headers.get("Authorization"),
                x_token=self.headers.get("X-Control-Token"),
            ):
                return self._send_json(401, {"error": "unauthorized"})
            proc = subprocess.run(cmd.command, check=False, capture_output=True, text=True)
            return self._send_json(
                200,
                {
                    "command": self._redact_command(cmd.command),
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                },
            )
        return self._send_json(200, {"command": self._redact_command(cmd.command)})


def main() -> None:
    parser = argparse.ArgumentParser(description="Paramutuel control panel web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8092)
    parser.add_argument("--rpc-url", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--allow-execute", action="store_true")
    parser.add_argument("--auth-token", default=None, help="Required bearer or X-Control-Token for execute requests.")
    args = parser.parse_args()

    Handler.rpc_url = args.rpc_url
    Handler.private_key = args.private_key
    Handler.allow_execute = args.allow_execute
    Handler.auth_token = args.auth_token
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Control panel listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
