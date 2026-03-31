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


def list_wagers(
    conn: sqlite3.Connection,
    state: str | None,
    limit: int,
    query_text: str | None,
    order: str,
    offset: int,
) -> list[dict]:
    base_query = """
        SELECT
            m.*,
            COALESCE(t.total_pot, '0') AS total_pot,
            COALESCE(t.total_fee_bps, '0') AS total_fee_bps,
            t.winning_outcome,
            t.total_winning_stake
        FROM wagers m
        LEFT JOIN wager_totals t ON t.wager_address = m.wager_address
    """
    clauses = []
    params: list = []
    if state:
        clauses.append("m.state = ?")
        params.append(state)
    if query_text and query_text.strip():
        needle = f"%{query_text.strip().lower()}%"
        clauses.append(
            "("
            "LOWER(m.wager_address) LIKE ? OR "
            "LOWER(m.factory_address) LIKE ? OR "
            "LOWER(m.proposer) LIKE ? OR "
            "LOWER(m.resolver) LIKE ? OR "
            "LOWER(m.betting_closer) LIKE ? OR "
            "LOWER(m.resolution_closer) LIKE ? OR "
            "LOWER(m.collateral_token) LIKE ? OR "
            "LOWER(m.proposition) LIKE ? OR "
            "LOWER(m.outcomes_json) LIKE ? OR "
            "LOWER(m.state) LIKE ? OR "
            "LOWER(CAST(m.betting_close_time AS TEXT)) LIKE ? OR "
            "LOWER(CAST(m.resolution_window AS TEXT)) LIKE ? OR "
            "LOWER(CAST(m.resolution_deadline AS TEXT)) LIKE ? OR "
            "LOWER(CAST(m.betting_closed_by_authority AS TEXT)) LIKE ? OR "
            "LOWER(CAST(m.betting_closed_at AS TEXT)) LIKE ? OR "
            "LOWER(CAST(m.resolution_window_closed AS TEXT)) LIKE ? OR "
            "LOWER(CAST(m.resolution_window_closed_at AS TEXT)) LIKE ? OR "
            "LOWER(CAST(m.created_block AS TEXT)) LIKE ? OR "
            "LOWER(m.created_tx_hash) LIKE ? OR "
            "LOWER(COALESCE(t.total_pot, '0')) LIKE ? OR "
            "LOWER(COALESCE(t.total_fee_bps, '0')) LIKE ? OR "
            "LOWER(COALESCE(t.winning_outcome, '')) LIKE ? OR "
            "LOWER(COALESCE(t.total_winning_stake, '')) LIKE ?"
            ")"
        )
        params.extend([needle] * 23)

    order_sql = "DESC" if order == "desc" else "ASC"

    query = base_query
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += f" ORDER BY m.created_block {order_sql}, m.created_tx_hash {order_sql} LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(query, tuple(params)).fetchall()
    return [row_to_dict(r) for r in rows]


def get_wager(conn: sqlite3.Connection, wager_address: str) -> dict | None:
    m = conn.execute("SELECT * FROM wagers WHERE wager_address = ?", (wager_address.lower(),)).fetchone()
    if not m:
        return None
    totals = conn.execute("SELECT * FROM wager_totals WHERE wager_address = ?", (wager_address.lower(),)).fetchone()
    outcomes = conn.execute(
        "SELECT outcome_index, outcome_total FROM wager_outcomes WHERE wager_address = ? ORDER BY outcome_index ASC",
        (wager_address.lower(),),
    ).fetchall()
    events = conn.execute(
        "SELECT event_name, block_number, tx_hash, log_index, payload_json FROM events_log WHERE wager_address = ? ORDER BY block_number ASC, log_index ASC",
        (wager_address.lower(),),
    ).fetchall()
    return {
        "wager": row_to_dict(m),
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        # Support both direct paths (/wagers) and explorer-style prefixed paths (/api/wagers).
        if path.startswith("/api/"):
            path = path[len("/api") :] or "/"

        if path in ("/", "/api", "/api/"):
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "paramutuel-indexer-api",
                    "endpoints": [
                        "/health",
                        "/wagers?limit=20&offset=0&order=desc",
                        "/wagers?limit=20&offset=0&order=asc&q=<text>",
                        "/wagers?q=<searches all indexed wager fields>",
                        "/wagers/{wager_address}",
                        "/sweeper/expire-candidates",
                    ],
                },
            )
            return

        if path == "/health":
            self._send_json(200, {"ok": True, "ts": int(time.time())})
            return

        if path == "/wagers":
            state = qs.get("state", [None])[0]
            query_text = qs.get("q", [None])[0]
            limit_raw = qs.get("limit", ["100"])[0]
            offset_raw = qs.get("offset", ["0"])[0]
            order = qs.get("order", ["desc"])[0].lower()
            try:
                limit = max(1, min(1000, int(limit_raw)))
            except ValueError:
                self._send_json(400, {"error": "invalid limit"})
                return
            try:
                offset = max(0, int(offset_raw))
            except ValueError:
                self._send_json(400, {"error": "invalid offset"})
                return
            if order not in ("desc", "asc"):
                self._send_json(400, {"error": "invalid order"})
                return
            self._send_json(
                200,
                {
                    "wagers": list_wagers(
                        self.conn,
                        state,
                        limit,
                        query_text,
                        order,
                        offset,
                    )
                },
            )
            return

        if path.startswith("/wagers/"):
            addr = path.split("/wagers/", 1)[1].lower()
            item = get_wager(self.conn, addr)
            if not item:
                self._send_json(404, {"error": "wager not found"})
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
                            "wager_address": r["wager_address"],
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

