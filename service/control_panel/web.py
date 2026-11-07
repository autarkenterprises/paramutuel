#!/usr/bin/env python3
"""Control panel — token-gated HTTP shell.

Mirrors the CLI commands behind a ``ThreadingHTTPServer``. Every endpoint builds a command and returns
a preview for operator review; sending ``"execute": true`` broadcasts it, which requires both
``--allow-execute`` and a valid token (``--auth-token`` / ``CONTROL_PANEL_TOKEN``, sent as
``Authorization: Bearer`` or ``X-Control-Token``). Previews need no token because they run nothing and
never contain the key.

The split between this service (operator-only, write-capable) and the public explorer
(:mod:`service.explorer.server`, read-only, public) is the surface boundary defined in ADR-0006. The
default bind address is localhost: this is not meant to be exposed publicly.
"""
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .commands import (
    build_create_freeform_wager_command,
    build_create_wager_command,
    build_wager_action_command,
    run_cast_send,
)
from .security import token_authorized


STATIC_DIR = Path(__file__).with_name("static")


class Handler(BaseHTTPRequestHandler):
    rpc_url: str = ""
    private_key: str = ""
    allow_execute: bool = False
    auth_token: str | None = None

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
        try:
            payload = json.loads(raw.decode() or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._send_json(400, {"error": "request body is not valid JSON"})
        if not isinstance(payload, dict):
            return self._send_json(400, {"error": "request body must be a JSON object"})
        zero = "0x0000000000000000000000000000000000000000"
        try:
            if path == "/api/preview/create-wager":
                cmd = build_create_wager_command(
                    factory=payload["factory"],
                    collateral=payload["collateral"],
                    proposition=payload["proposition"],
                    outcomes=payload["outcomes"],
                    betting_close_time=int(payload["bettingCloseTime"]),
                    resolution_window=int(payload["resolutionWindow"]),
                    resolver=payload.get("resolver", zero),
                    betting_closer=payload.get("bettingCloser", zero),
                    resolution_closer=payload.get("resolutionCloser", zero),
                    extra_recipients=payload.get("extraRecipients", []),
                    extra_bps=payload.get("extraBps", []),
                    payoff_policy=int(payload.get("payoffPolicy", 0)),
                    policy_param=int(payload.get("policyParam", 0)),
                    seed_outcome_indices=payload.get("seedOutcomeIndices", []),
                    seed_amounts=payload.get("seedAmounts", []),
                    min_new_ticket_stake=int(payload.get("minNewTicketStake", 0)),
                    rpc_url=self.rpc_url,
                    private_key=self.private_key,
                )
            elif path == "/api/preview/create-freeform-wager":
                cmd = build_create_freeform_wager_command(
                    factory=payload["factory"],
                    collateral=payload["collateral"],
                    proposition=payload["proposition"],
                    betting_close_time=int(payload["bettingCloseTime"]),
                    resolution_window=int(payload["resolutionWindow"]),
                    resolver=payload.get("resolver", zero),
                    betting_closer=payload.get("bettingCloser", zero),
                    resolution_closer=payload.get("resolutionCloser", zero),
                    extra_recipients=payload.get("extraRecipients", []),
                    extra_bps=payload.get("extraBps", []),
                    min_new_ticket_stake=int(payload.get("minNewTicketStake", 0)),
                    rpc_url=self.rpc_url,
                    private_key=self.private_key,
                )
            elif path == "/api/preview/action":
                cmd = build_wager_action_command(
                    wager=payload["wager"],
                    action=payload["action"],
                    winning_mask=payload.get("winningMask"),
                    protocol_version=payload.get("protocolVersion"),
                    winning_answer=payload.get("winningAnswer"),
                    rpc_url=self.rpc_url,
                    private_key=self.private_key,
                )
            else:
                return self._send_json(404, {"error": "not found"})
        except (KeyError, ValueError, TypeError, AttributeError) as e:
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
            result = run_cast_send(cmd.command)
            return self._send_json(
                200,
                {
                    **cmd.preview(),
                    "ok": result.ok,
                    "tx_hash": result.tx_hash,
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )
        return self._send_json(200, cmd.preview())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paramutuel control panel web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8092)
    parser.add_argument("--rpc-url", default=os.environ.get("RPC_URL", ""))
    parser.add_argument("--private-key", default=os.environ.get("PRIVATE_KEY", ""), help="Prefer the PRIVATE_KEY env var: flags are visible in process listings.")
    parser.add_argument("--allow-execute", action="store_true")
    parser.add_argument(
        "--auth-token",
        default=os.environ.get("CONTROL_PANEL_TOKEN") or None,
        help="Required bearer or X-Control-Token for execute requests (or CONTROL_PANEL_TOKEN).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.rpc_url or not args.private_key:
        raise SystemExit("RPC URL and private key are required (--rpc-url / RPC_URL, --private-key / PRIVATE_KEY)")

    Handler.rpc_url = args.rpc_url
    Handler.private_key = args.private_key
    Handler.allow_execute = args.allow_execute
    Handler.auth_token = args.auth_token
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Control panel listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
