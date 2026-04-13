#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request
from urllib.parse import parse_qs, urlparse

from .logic import actionability_reason, normalize_address


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _json_response(handler: BaseHTTPRequestHandler, code: int, body: dict) -> None:
    payload = json.dumps(body).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(payload)


def _http_get_json(url: str, timeout: int = 20) -> dict:
    req = request.Request(url, headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _read_decisions(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict] = {}
    for k, v in data.items():
        if not isinstance(v, dict):
            continue
        out[normalize_address(k)] = v
    return out


def _extract_resolver_address(explicit: str, private_key: str) -> str:
    if explicit:
        return normalize_address(explicit)
    if not private_key:
        raise RuntimeError("resolver address required (RESOLUTION_SERVICE_ADDRESS or --private-key)")
    proc = subprocess.run(
        ["cast", "wallet", "address", "--private-key", private_key],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"failed to derive resolver address: {proc.stderr.strip()}")
    return normalize_address(proc.stdout.strip())


def _load_open_wagers(indexer_base_url: str, limit: int = 300) -> list[dict]:
    base = indexer_base_url.rstrip("/")
    body = _http_get_json(f"{base}/wagers?state=OPEN&limit={limit}&order=desc")
    return list(body.get("wagers") or [])


def _action_command(
    *,
    wager_address: str,
    action: str,
    rpc_url: str,
    private_key: str,
    protocol_version: str = "v1",
    resolve_uint256: int | None = None,
    winning_answer: str | None = None,
) -> list[str]:
    if action == "resolve":
        pv = (protocol_version or "v1").strip().lower()
        if pv in ("freeform", "v3_freeform"):
            ans = (winning_answer or "").strip()
            if not ans:
                raise ValueError(
                    "freeform/v3_freeform resolve requires decision.winningAnswer (exact UTF-8 string)"
                )
            return [
                "cast",
                "send",
                wager_address,
                "resolve(string)",
                ans,
                "--rpc-url",
                rpc_url,
                "--private-key",
                private_key,
            ]
        if resolve_uint256 is None:
            raise ValueError("resolve decision requires outcomeIndex or winningMask (v1/v2/v3_enum)")
        return [
            "cast",
            "send",
            wager_address,
            "resolve(uint256)",
            str(resolve_uint256),
            "--rpc-url",
            rpc_url,
            "--private-key",
            private_key,
        ]
    if action == "retract":
        return [
            "cast",
            "send",
            wager_address,
            "retract()",
            "--rpc-url",
            rpc_url,
            "--private-key",
            private_key,
        ]
    raise ValueError(f"unsupported decision action: {action}")


def evaluate_candidates(
    *,
    open_wagers: list[dict],
    decisions: dict,
    resolver_address: str,
    now_ts: int | None = None,
) -> list[dict]:
    out: list[dict] = []
    for row in open_wagers:
        wager = normalize_address(str(row.get("wager_address") or ""))
        reason = actionability_reason(row, resolver_address=resolver_address, now_ts=now_ts)
        decision = decisions.get(wager)
        candidate = {
            "wager_address": wager,
            "resolver": row.get("resolver"),
            "state": row.get("state"),
            "protocol_version": str(row.get("protocol_version") or "v1").strip().lower(),
            "betting_close_time": row.get("betting_close_time"),
            "resolution_window": row.get("resolution_window"),
            "resolution_window_closed": row.get("resolution_window_closed"),
            "decision": decision,
            "actionable": reason is None and decision is not None,
            "reason": reason,
        }
        if decision and "action" in decision:
            candidate["decision_action"] = decision.get("action")
            candidate["decision_outcome_index"] = decision.get("outcomeIndex")
            if decision.get("winningMask") is not None:
                candidate["decision_winning_mask"] = decision.get("winningMask")
            if decision.get("winningAnswer") is not None:
                candidate["decision_winning_answer"] = decision.get("winningAnswer")
        out.append(candidate)
    return out


class Handler(BaseHTTPRequestHandler):
    indexer_base_url: str = ""
    decisions_path: str = ""
    resolver_address: str = ""
    rpc_url: str = ""
    private_key: str = ""

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/health":
            decisions = _read_decisions(self.decisions_path)
            try:
                wagers = _load_open_wagers(self.indexer_base_url, limit=20)
                ok = True
                err = None
            except Exception as exc:
                wagers = []
                ok = False
                err = str(exc)
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "ts": int(time.time()),
                    "indexer_ok": ok,
                    "indexer_error": err,
                    "resolver_address": self.resolver_address,
                    "open_wagers_sampled": len(wagers),
                    "decision_entries": len(decisions),
                },
            )
            return

        if path == "/candidates":
            limit = int(qs.get("limit", ["300"])[0])
            open_wagers = _load_open_wagers(self.indexer_base_url, limit=max(1, min(1000, limit)))
            decisions = _read_decisions(self.decisions_path)
            candidates = evaluate_candidates(
                open_wagers=open_wagers,
                decisions=decisions,
                resolver_address=self.resolver_address,
                now_ts=int(time.time()),
            )
            _json_response(self, 200, {"candidates": candidates})
            return

        _json_response(self, 404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/run-once":
            _json_response(self, 404, {"error": "not found"})
            return
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")) or 0)
        payload = json.loads(raw.decode() or "{}")
        execute = bool(payload.get("execute", False))

        open_wagers = _load_open_wagers(self.indexer_base_url, limit=1000)
        decisions = _read_decisions(self.decisions_path)
        candidates = evaluate_candidates(
            open_wagers=open_wagers,
            decisions=decisions,
            resolver_address=self.resolver_address,
            now_ts=int(time.time()),
        )

        attempted = 0
        succeeded = 0
        failed = 0
        results: list[dict] = []
        for c in candidates:
            if not c.get("actionable"):
                continue
            decision = c.get("decision") or {}
            action = str(decision.get("action") or "").strip().lower()
            pv = str(c.get("protocol_version") or "v1").strip().lower()
            try:
                win = None
                win_ans = decision.get("winningAnswer")
                if win_ans is not None and not isinstance(win_ans, str):
                    win_ans = str(win_ans)
                if action == "resolve":
                    if pv in ("freeform", "v3_freeform"):
                        cmd = _action_command(
                            wager_address=c["wager_address"],
                            action=action,
                            rpc_url=self.rpc_url,
                            private_key=self.private_key,
                            protocol_version=pv,
                            resolve_uint256=None,
                            winning_answer=win_ans,
                        )
                    else:
                        win = decision.get("winningMask")
                        if win is None:
                            win = decision.get("outcomeIndex")
                        cmd = _action_command(
                            wager_address=c["wager_address"],
                            action=action,
                            rpc_url=self.rpc_url,
                            private_key=self.private_key,
                            protocol_version=pv,
                            resolve_uint256=int(win) if win is not None else None,
                            winning_answer=None,
                        )
                else:
                    cmd = _action_command(
                        wager_address=c["wager_address"],
                        action=action,
                        rpc_url=self.rpc_url,
                        private_key=self.private_key,
                        protocol_version=pv,
                        resolve_uint256=None,
                        winning_answer=None,
                    )
            except Exception as exc:
                failed += 1
                results.append({"wager": c["wager_address"], "ok": False, "error": str(exc)})
                continue
            attempted += 1
            if not execute:
                succeeded += 1
                results.append({"wager": c["wager_address"], "ok": True, "dry_run": True, "command": cmd})
                continue
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if proc.returncode == 0:
                succeeded += 1
                results.append({"wager": c["wager_address"], "ok": True, "stdout": proc.stdout})
            else:
                failed += 1
                results.append({"wager": c["wager_address"], "ok": False, "stderr": proc.stderr})

        _json_response(
            self,
            200,
            {
                "attempted": attempted,
                "succeeded": succeeded,
                "failed": failed,
                "execute": execute,
                "results": results,
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Paramutuel Resolution Service")
    parser.add_argument("--host", default=_env("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(_env("PORT", "8093")))
    parser.add_argument("--indexer-base-url", default=_env("INDEXER_BASE_URL"))
    parser.add_argument("--rpc-url", default=_env("RPC_URL_BASE_SEPOLIA") or _env("RPC_URL"))
    parser.add_argument("--private-key", default=_env("PRIVATE_KEY"))
    parser.add_argument("--resolver-address", default=_env("RESOLUTION_SERVICE_ADDRESS"))
    parser.add_argument(
        "--decisions-path",
        default=_env("RESOLUTION_DECISIONS_PATH", "config/resolution-decisions.base-sepolia.json"),
    )
    args = parser.parse_args()

    if not args.indexer_base_url:
        raise RuntimeError("INDEXER_BASE_URL is required")
    if not args.rpc_url:
        raise RuntimeError("RPC URL is required (RPC_URL_BASE_SEPOLIA or RPC_URL)")
    if not args.private_key:
        raise RuntimeError("PRIVATE_KEY is required for resolver execution")

    resolver = _extract_resolver_address(args.resolver_address, args.private_key)
    Handler.indexer_base_url = args.indexer_base_url.rstrip("/")
    Handler.decisions_path = args.decisions_path
    Handler.resolver_address = resolver
    Handler.rpc_url = args.rpc_url
    Handler.private_key = args.private_key

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Resolution service listening on http://{args.host}:{args.port}")
    print(f"Resolver address: {resolver}")
    print(f"Indexer API: {Handler.indexer_base_url}")
    print(f"Decisions file: {args.decisions_path}")
    server.serve_forever()


if __name__ == "__main__":
    main()
