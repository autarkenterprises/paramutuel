#!/usr/bin/env python3
import argparse
import json
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .indexer import db_connect, get_expire_candidates, init_db


def row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def list_markets(conn: sqlite3.Connection, state: str | None, limit: int) -> list[dict]:
    if state:
        rows = conn.execute(
            "SELECT * FROM markets WHERE state = ? ORDER BY created_block DESC LIMIT ?",
            (state, limit),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM markets ORDER BY created_block DESC LIMIT ?", (limit,)).fetchall()
    return [row_to_dict(r) for r in rows]


def get_market(conn: sqlite3.Connection, market_address: str) -> dict | None:
    m = conn.execute("SELECT * FROM markets WHERE market_address = ?", (market_address.lower(),)).fetchone()
    if not m:
        return None
    totals = conn.execute("SELECT * FROM market_totals WHERE market_address = ?", (market_address.lower(),)).fetchone()
    outcomes = conn.execute(
        "SELECT outcome_index, outcome_total FROM market_outcomes WHERE market_address = ? ORDER BY outcome_index ASC",
        (market_address.lower(),),
    ).fetchall()
    events = conn.execute(
        "SELECT event_name, block_number, tx_hash, log_index, payload_json FROM events_log WHERE market_address = ? ORDER BY block_number ASC, log_index ASC",
        (market_address.lower(),),
    ).fetchall()
    return {
        "market": row_to_dict(m),
        "totals": row_to_dict(totals) if totals else None,
        "outcomes": [row_to_dict(o) for o in outcomes],
        "events": [
            {
                **row_to_dict(e),
                "payload_json": json.loads(e["payload_json"]),
            }
            for e in events
        ],
    }


class Handler(BaseHTTPRequestHandler):
    conn: sqlite3.Connection = None  # type: ignore

    def _send_json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/health":
            self._send_json(200, {"ok": True, "ts": int(time.time())})
            return

        if path == "/markets":
            state = qs.get("state", [None])[0]
            limit_raw = qs.get("limit", ["100"])[0]
            try:
                limit = max(1, min(1000, int(limit_raw)))
            except ValueError:
                self._send_json(400, {"error": "invalid limit"})
                return
            self._send_json(200, {"markets": list_markets(self.conn, state, limit)})
            return

        if path.startswith("/markets/"):
            addr = path.split("/markets/", 1)[1].lower()
            item = get_market(self.conn, addr)
            if not item:
                self._send_json(404, {"error": "market not found"})
                return
            self._send_json(200, item)
            return

        if path == "/sweeper/expire-candidates":
            now_raw = qs.get("now", [None])[0]
            now_ts = int(now_raw) if now_raw is not None else int(time.time())
            candidates = get_expire_candidates(self.conn, now_ts=now_ts)
            self._send_json(
                200,
                {
                    "now": now_ts,
                    "candidates": [
                        {
                            "market_address": r["market_address"],
                            "resolver": r["resolver"],
                            "resolution_window": r["resolution_window"],
                            "resolution_deadline": r["resolution_deadline"],
                            "betting_closed_at": r["betting_closed_at"],
                            "resolution_window_closed": bool(r["resolution_window_closed"]),
                        }
                        for r in candidates
                    ],
                },
            )
            return

        self._send_json(404, {"error": "not found"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Paramutuel indexer API")
    parser.add_argument("--db-path", default="service/indexer/indexer.db")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    conn = db_connect(args.db_path)
    init_db(conn)
    Handler.conn = conn
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Indexer API listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

