#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from service.control_panel.security import token_authorized

from . import db as dbm
from . import dispatch as dispatchm
from . import ingest


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _json_response(handler: BaseHTTPRequestHandler, code: int, body: dict) -> None:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(payload)


def _load_deployments_factory(root: Path) -> str:
    path = root / "config" / "deployments.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        net = str(data.get("defaultNetwork") or "baseSepolia").strip()
        return str((data.get(net) or {}).get("factoryAddress") or "").strip()
    except (json.JSONDecodeError, TypeError):
        return ""


STATIC_DIR = Path(__file__).resolve().with_name("static")
SCHEMA_PATH = Path(__file__).resolve().with_name("schema.sql")


class Handler(BaseHTTPRequestHandler):
    db_path: str = ""
    sources_path: Path = Path()
    auth_token: str | None = None
    repo_root: Path = Path()
    factory: str = ""
    collateral: str = ""
    rpc_url: str = ""
    private_key: str = ""
    betting_close_offset: int = 7 * 24 * 3600
    resolution_window: int = 3 * 24 * 3600
    resolver: str = ""
    betting_closer: str = ""
    resolution_closer: str = ""
    extra_recipients: list[str] = []
    extra_bps: list[int] = []
    allow_execute: bool = False

    def _authorized(self) -> bool:
        return token_authorized(
            expected_token=self.auth_token,
            auth_header=self.headers.get("Authorization"),
            x_token=self.headers.get("X-Proposition-Token"),
        )

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Proposition-Token")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            return self._send_static("index.html")
        if path == "/app.js":
            return self._send_static("app.js")
        if path == "/style.css":
            return self._send_static("style.css")
        if path == "/health":
            return _json_response(
                self,
                200,
                {
                    "ok": True,
                    "ts": int(time.time()),
                    "db_path": self.db_path,
                    "factory_configured": bool(self.factory),
                },
            )
        if path == "/api/config":
            if not self._authorized():
                return _json_response(self, 401, {"error": "unauthorized"})
            return _json_response(
                self,
                200,
                {
                    "factory": self.factory,
                    "collateral": self.collateral,
                    "rpc_url_set": bool(self.rpc_url),
                    "private_key_set": bool(self.private_key),
                    "betting_close_offset_sec": self.betting_close_offset,
                    "resolution_window_sec": self.resolution_window,
                    "resolver": self.resolver,
                    "betting_closer": self.betting_closer,
                    "resolution_closer": self.resolution_closer,
                    "allow_execute": self.allow_execute,
                },
            )
        if path == "/api/sources":
            if not self._authorized():
                return _json_response(self, 401, {"error": "unauthorized"})
            if not self.sources_path.exists():
                return _json_response(self, 200, {"sources": []})
            cfg = ingest.load_sources_config(self.sources_path)
            return _json_response(self, 200, {"sources": cfg})
        if path == "/api/proposals":
            if not self._authorized():
                return _json_response(self, 401, {"error": "unauthorized"})
            qs = parse_qs(urlparse(self.path).query)
            status = qs.get("status", [None])[0]
            limit = int(qs.get("limit", ["100"])[0])
            conn = dbm.connect(self.db_path)
            rows = dbm.list_proposals(conn, status=status, limit=limit)
            conn.close()
            out = []
            for r in rows:
                out.append(dispatchm.proposal_to_preview_dict(r))
            return _json_response(self, 200, {"proposals": out})
        self.send_error(404)

    def do_PATCH(self) -> None:  # noqa: N802
        if not self._authorized():
            return _json_response(self, 401, {"error": "unauthorized"})
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "proposals":
            try:
                pid = int(parts[2])
            except ValueError:
                return _json_response(self, 400, {"error": "bad id"})
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")) or 0)
            try:
                payload = json.loads(raw.decode() or "{}")
            except json.JSONDecodeError:
                return _json_response(self, 400, {"error": "invalid json"})
            prop = str(payload.get("proposition") or "").strip()
            outs = payload.get("outcomes")
            if not prop or not isinstance(outs, list) or len(outs) < 2:
                return _json_response(self, 400, {"error": "proposition and outcomes[] required"})
            outs = [str(x) for x in outs]
            conn = dbm.connect(self.db_path)
            ok = dbm.update_proposal_content(conn, pid, proposition=prop, outcomes=outs)
            conn.close()
            if not ok:
                return _json_response(self, 400, {"error": "only pending proposals are editable"})
            return _json_response(self, 200, {"ok": True})
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/ingest":
            if not self._authorized():
                return _json_response(self, 401, {"error": "unauthorized"})
            qs = parse_qs(parsed.query)
            include_calendar = qs.get("calendar", ["0"])[0] in ("1", "true", "yes")
            conn = dbm.connect(self.db_path)
            summary = ingest.run_ingest(
                conn=conn,
                sources_path=self.sources_path,
                include_calendar=include_calendar,
            )
            conn.close()
            return _json_response(self, 200, summary)

        if path.startswith("/api/proposals/"):
            if not self._authorized():
                return _json_response(self, 401, {"error": "unauthorized"})
            tail = path[len("/api/proposals/") :].strip("/")
            segs = tail.split("/")
            if len(segs) != 2 or segs[1] not in ("approve", "reject", "dispatch"):
                return _json_response(self, 404, {"error": "not found"})
            try:
                pid = int(segs[0])
            except ValueError:
                return _json_response(self, 400, {"error": "bad id"})
            action = segs[1]
            conn = dbm.connect(self.db_path)
            row = dbm.get_proposal(conn, pid)
            if not row:
                conn.close()
                return _json_response(self, 404, {"error": "not found"})

            if action == "approve":
                if row["status"] != "pending":
                    conn.close()
                    return _json_response(self, 400, {"error": "not pending"})
                dbm.update_proposal_status(conn, pid, status="approved")
                conn.close()
                return _json_response(self, 200, {"ok": True})

            if action == "reject":
                if row["status"] != "pending":
                    conn.close()
                    return _json_response(self, 400, {"error": "not pending"})
                dbm.update_proposal_status(conn, pid, status="rejected")
                conn.close()
                return _json_response(self, 200, {"ok": True})

            if action == "dispatch":
                if row["status"] != "approved":
                    conn.close()
                    return _json_response(self, 400, {"error": "must approve before dispatch"})
                if not self.allow_execute:
                    conn.close()
                    return _json_response(self, 403, {"error": "execute disabled on server"})
                if not self.private_key or not self.rpc_url or not self.factory or not self.collateral:
                    conn.close()
                    return _json_response(self, 400, {"error": "missing factory/collateral/rpc/key env"})
                outcomes = json.loads(row["outcomes_json"] or "[]")
                close_ts = int(time.time()) + int(self.betting_close_offset)
                result = dispatchm.dispatch_proposal(
                    proposition=row["proposition"],
                    outcomes=outcomes,
                    factory=self.factory,
                    collateral=self.collateral,
                    rpc_url=self.rpc_url,
                    private_key=self.private_key,
                    betting_close_time=close_ts,
                    resolution_window=int(self.resolution_window),
                    resolver=self.resolver or "0x0000000000000000000000000000000000000000",
                    betting_closer=self.betting_closer or "0x0000000000000000000000000000000000000000",
                    resolution_closer=self.resolution_closer or "0x0000000000000000000000000000000000000000",
                    extra_recipients=list(self.extra_recipients),
                    extra_bps=list(self.extra_bps),
                    dry_run=False,
                )
                if result.get("ok"):
                    dbm.update_proposal_status(
                        conn,
                        pid,
                        status="dispatched",
                        tx_hint=(result.get("stdout") or "")[:4000],
                    )
                else:
                    dbm.update_proposal_status(
                        conn,
                        pid,
                        status="dispatch_failed",
                        tx_hint=(result.get("stdout") or "")[:2000],
                        dispatch_error=(result.get("stderr") or "dispatch failed")[:4000],
                    )
                conn.close()
                return _json_response(self, 200, result)

        self.send_error(404)

    def _send_static(self, name: str) -> None:
        path = STATIC_DIR / name
        if not path.exists():
            self.send_error(404)
            return
        data = path.read_bytes()
        ctype = "text/plain"
        if name.endswith(".html"):
            ctype = "text/html; charset=utf-8"
        elif name.endswith(".js"):
            ctype = "application/javascript; charset=utf-8"
        elif name.endswith(".css"):
            ctype = "text/css; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Paramutuel Proposition Service")
    parser.add_argument("--host", default=_env("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(_env("PORT", "8094")))
    parser.add_argument("--db-path", default=_env("PROPOSITION_DB_PATH", str(root / "service" / "proposition" / "data" / "propositions.db")))
    parser.add_argument(
        "--sources-config",
        default=_env("PROPOSITION_SOURCES_PATH", str(root / "config" / "proposition-sources.json")),
    )
    parser.add_argument("--auth-token", default=_env("PROPOSITION_PANEL_TOKEN"))
    parser.add_argument("--factory", default=_env("FACTORY_ADDRESS") or _env("PROPOSITION_FACTORY"))
    parser.add_argument("--collateral", default=_env("PROPOSITION_COLLATERAL_TOKEN"))
    parser.add_argument("--rpc-url", default=_env("RPC_URL_BASE_SEPOLIA") or _env("RPC_URL"))
    parser.add_argument("--private-key", default=_env("PRIVATE_KEY") or _env("PROPOSITION_PRIVATE_KEY"))
    _ae = _env("PROPOSITION_ALLOW_EXECUTE").lower()
    parser.add_argument(
        "--allow-execute",
        action="store_true",
        default=_ae in ("1", "true", "yes"),
    )
    parser.add_argument("--betting-close-offset", type=int, default=int(_env("PROPOSITION_BETTING_CLOSE_OFFSET_SEC", str(7 * 24 * 3600))))
    parser.add_argument("--resolution-window", type=int, default=int(_env("PROPOSITION_RESOLUTION_WINDOW_SEC", str(3 * 24 * 3600))))
    parser.add_argument("--resolver", default=_env("PROPOSITION_RESOLVER"))
    parser.add_argument("--betting-closer", default=_env("PROPOSITION_BETTING_CLOSER"))
    parser.add_argument("--resolution-closer", default=_env("PROPOSITION_RESOLUTION_CLOSER"))
    args = parser.parse_args()

    factory = args.factory.strip() or _load_deployments_factory(root)
    auth = (args.auth_token or "").strip()
    if not auth:
        raise SystemExit("PROPOSITION_PANEL_TOKEN (or --auth-token) is required")

    conn = dbm.connect(args.db_path)
    dbm.init_schema(conn, SCHEMA_PATH)
    conn.close()

    Handler.db_path = args.db_path
    Handler.sources_path = Path(args.sources_config)
    Handler.auth_token = auth
    Handler.repo_root = root
    Handler.factory = factory
    Handler.collateral = args.collateral.strip()
    Handler.rpc_url = args.rpc_url.strip()
    Handler.private_key = args.private_key.strip()
    Handler.betting_close_offset = max(60, args.betting_close_offset)
    Handler.resolution_window = max(60, args.resolution_window)
    Handler.resolver = args.resolver.strip()
    Handler.betting_closer = args.betting_closer.strip()
    Handler.resolution_closer = args.resolution_closer.strip()
    Handler.allow_execute = bool(args.allow_execute)

    er = _env("PROPOSITION_EXTRA_FEE_RECIPIENTS")
    eb = _env("PROPOSITION_EXTRA_FEE_BPS")
    if er and eb:
        Handler.extra_recipients = [x.strip() for x in er.split(",") if x.strip()]
        Handler.extra_bps = [int(x.strip()) for x in eb.split(",") if x.strip()]
        if len(Handler.extra_recipients) != len(Handler.extra_bps):
            raise SystemExit("PROPOSITION_EXTRA_FEE_RECIPIENTS and PROPOSITION_EXTRA_FEE_BPS length mismatch")

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Proposition service http://{args.host}:{args.port}")
    print(f"DB: {args.db_path}")
    print(f"Sources: {Handler.sources_path}")
    print(f"Execute: {Handler.allow_execute}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
