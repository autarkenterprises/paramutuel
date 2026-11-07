#!/usr/bin/env python3
"""Operator-facing resolution daemon.

This is a small HTTP service (stdlib `http.server`, threaded) the
operator runs alongside the indexer. It periodically — or on demand
via `POST /run-once` — pulls open V3 wagers from the indexer, joins
each row against an operator-curated decisions JSON file keyed by
wager address, and either prints the `cast send` command (`execute=
False`, the default) or actually submits the transaction.

Neighbours:

  * `service/indexer/` — read-only HTTP source for `state=OPEN` wagers
    and the wager fields needed by `logic.actionability_reason`.
  * `service/control_panel/` — separate operator surface for
    create/close/withdraw transactions; this daemon only handles the
    resolve/retract phase.
  * `mcp_server/` — alternate path for an LLM agent to encode the same
    `resolve(uint256)` / `resolve(string)` / `retract()` calldata.

Decision JSON shape (one entry per wager address):

    {
      "0xabc...": {
        "action": "resolve" | "retract",
        # enumerated wagers:
        "outcomeIndex": 0,             # promoted to 1<<i if winningMask absent
        "winningMask": 5,              # raw bitmask, takes precedence
        # freeform wagers:
        "winningAnswer": "exact UTF-8 string"
      }
    }

`execute=False` is the safety default. `POST /run-once` is gated by a
bearer token (`RESOLUTION_SERVICE_TOKEN` / `--auth-token`, sent as
`Authorization: Bearer <t>` or `X-Token: <t>`) and fails closed when no
token is configured; the dry-run response redacts `--private-key`
(ADR-0019). `GET /health` stays open and `GET /candidates` shows full
decisions only with the token, because a decision written before betting
closes tells a reader the winner while they can still bet on it (ADR-0020).

Winning answers and masks reach the chain as ABI-encoded calldata, because
`cast` alters strings it parses: see `service/control_panel/abi.py`. A
transaction counts as successful only when its receipt says so, because
`cast send` exits 0 for a mined revert.

The container image (`Dockerfile.resolution`) includes `cast`, which signs and
broadcasts. `cast` takes the raw key only as a process argument, so run this
service alone in its container or on a host with no other local users.
"""
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

from service.control_panel.commands import build_wager_action_command, redact_argv, run_cast_send
from service.control_panel.security import token_authorized

from .logic import actionability_reason, normalize_address

# `numOptions <= 255` (factory `MAX_OUTCOMES`), so a valid outcome index is
# in [0, 254] and its single-bit mask `1 << i` always fits in uint256.
MAX_OUTCOME_INDEX = 254
# The indexer caps one /wagers page at this size.
INDEXER_PAGE_SIZE = 1000
# Stops a misbehaving indexer from looping forever; 50,000 open wagers is far beyond current scale.
MAX_INDEXER_PAGES = 50


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
    """Load the operator's decision file, keyed by normalized wager address.

    A missing file means no decisions. A file that exists but cannot be read raises (`OSError`, or
    `ValueError` for bad JSON or encoding) rather than reading as empty, so a typo in a hand-edited
    file is reported instead of looking like "nothing to do". See `_decisions_problem`.
    """
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


def _decisions_problem(exc: Exception) -> str:
    """Describe an unreadable decision file. `/candidates` and `/health` need no token, and pending
    decisions are insider information, so this reports where parsing failed and never the contents.
    `json.JSONDecodeError`'s message holds only a position; an `OSError` message would hold the path."""
    detail = exc.strerror if isinstance(exc, OSError) else str(exc)
    return f"decisions file unreadable: {detail}"


def _extract_resolver_address(explicit: str, private_key: str) -> str:
    """Resolve the address the daemon will compare against `wager.resolver`.

    Operators usually set `RESOLUTION_SERVICE_ADDRESS` explicitly so a
    typo in the private key cannot silently flip the daemon to a
    different address; if it is unset we derive it from the supplied
    private key via `cast wallet address` rather than reimplement
    secp256k1 here.
    """
    if explicit:
        return normalize_address(explicit)
    if not private_key:
        raise RuntimeError("resolver address required (RESOLUTION_SERVICE_ADDRESS or --private-key)")
    try:
        proc = subprocess.run(
            ["cast", "wallet", "address", "--private-key", private_key],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "`cast` not found on PATH: install Foundry or set RESOLUTION_SERVICE_ADDRESS explicitly"
        ) from None
    if proc.returncode != 0:
        raise RuntimeError(f"failed to derive resolver address: {proc.stderr.strip()}")
    return normalize_address(proc.stdout.strip())


def resolve_uint256_from_decision(decision: dict) -> int | None:
    """Map an enumerated decision row to the `resolve(uint256)` argument.

    `winningMask` (raw bitmask, must be > 0) takes precedence; otherwise
    `outcomeIndex` i is promoted to the single-bit mask `1 << i`, as the
    decision-file contract documents. Returns None when neither is set so
    the caller can surface "missing value". Rejects bools, non-integers,
    negative values and out-of-range indices with ValueError rather than
    letting a malformed decision reach the chain — before ADR-0019 the
    index was sent raw, so `outcomeIndex: 1` resolved outcome 0.
    """
    mask = decision.get("winningMask")
    if mask is not None:
        if isinstance(mask, bool) or not isinstance(mask, int) or mask <= 0:
            raise ValueError(f"winningMask must be a positive integer, got {mask!r}")
        return mask
    idx = decision.get("outcomeIndex")
    if idx is None:
        return None
    if isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx <= MAX_OUTCOME_INDEX:
        raise ValueError(f"outcomeIndex must be an integer in [0, {MAX_OUTCOME_INDEX}], got {idx!r}")
    return 1 << idx


def _load_open_wagers(indexer_base_url: str, limit: int | None = 300) -> list[dict]:
    """Fetch open wagers, oldest first; `limit=None` walks every page.

    Actionable wagers are the oldest: betting has closed and the window is running. Reading only the
    newest page would starve exactly those once more than one page of wagers was open.
    """
    base = indexer_base_url.rstrip("/")
    rows: list[dict] = []
    for page in range(MAX_INDEXER_PAGES):
        size = INDEXER_PAGE_SIZE if limit is None else min(INDEXER_PAGE_SIZE, limit - len(rows))
        offset = len(rows)
        body = _http_get_json(f"{base}/wagers?state=OPEN&limit={size}&offset={offset}&order=asc")
        batch = list(body.get("wagers") or [])
        rows.extend(batch)
        if len(batch) < size or (limit is not None and len(rows) >= limit):
            break
    return rows


def _action_command(
    *,
    wager_address: str,
    action: str,
    rpc_url: str,
    private_key: str,
    protocol_version: str = "enumerated",
    resolve_uint256: int | None = None,
    winning_answer: str | None = None,
) -> list[str]:
    """Translate a (wager, decision) pair into the `cast send` argv list.

    The caller has already verified the wager is actionable (see `logic.actionability_reason`) and
    looked up its decision row. The return value is a list, not a string, so it can be passed directly
    to a subprocess without shell quoting. Anything but `resolve` or `retract` is refused: the decision
    file must not be able to trigger other wager actions under the resolver's key.
    """
    if action not in ("resolve", "retract"):
        raise ValueError(f"unsupported decision action: {action}")
    pv = (protocol_version or "enumerated").strip().lower()
    if action == "resolve" and pv != "freeform" and resolve_uint256 is None:
        raise ValueError("enumerated resolve requires outcomeIndex or winningMask")
    if action == "resolve" and pv == "freeform" and not winning_answer:
        raise ValueError("freeform resolve requires decision.winningAnswer (exact UTF-8 string)")
    return build_wager_action_command(
        wager=wager_address,
        action=action,
        rpc_url=rpc_url,
        private_key=private_key,
        winning_mask=resolve_uint256,
        protocol_version=pv,
        winning_answer=winning_answer,
    ).command


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
            "protocol_version": str(row.get("protocol_version") or "enumerated").strip().lower(),
            "betting_close_time": row.get("betting_close_time"),
            "resolution_window": row.get("resolution_window"),
            "resolution_window_closed": row.get("resolution_window_closed"),
            "decision": decision,
            "decision_present": decision is not None,
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


def _without_decision_contents(candidate: dict) -> dict:
    """What an unauthenticated caller may see: that a decision exists, not what it says."""
    public = {k: v for k, v in candidate.items() if not k.startswith("decision_") or k == "decision_present"}
    public["decision"] = None
    return public


class Handler(BaseHTTPRequestHandler):
    indexer_base_url: str = ""
    decisions_path: str = ""
    resolver_address: str = ""
    rpc_url: str = ""
    private_key: str = ""
    # Bearer token for POST /run-once; None/empty fails closed.
    auth_token: str | None = None

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _authorized(self) -> bool:
        return token_authorized(
            expected_token=self.auth_token,
            auth_header=self.headers.get("Authorization"),
            x_token=self.headers.get("X-Token"),
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/health":
            decisions_error = None
            try:
                decisions = _read_decisions(self.decisions_path)
            except (OSError, ValueError) as exc:
                decisions = {}
                decisions_error = _decisions_problem(exc)
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
                    "decisions_ok": decisions_error is None,
                    "decisions_error": decisions_error,
                    "decision_entries": len(decisions),
                },
            )
            return

        if path == "/candidates":
            try:
                limit = int(qs.get("limit", ["300"])[0])
            except ValueError:
                _json_response(self, 400, {"error": "invalid limit"})
                return
            try:
                open_wagers = _load_open_wagers(self.indexer_base_url, limit=max(1, min(1000, limit)))
            except Exception as exc:
                _json_response(self, 502, {"error": f"indexer unavailable: {exc}"})
                return
            try:
                decisions = _read_decisions(self.decisions_path)
            except (OSError, ValueError) as exc:
                _json_response(self, 500, {"error": _decisions_problem(exc)})
                return
            candidates = evaluate_candidates(
                open_wagers=open_wagers,
                decisions=decisions,
                resolver_address=self.resolver_address,
                now_ts=int(time.time()),
            )
            if not self._authorized():
                candidates = [_without_decision_contents(c) for c in candidates]
            _json_response(self, 200, {"candidates": candidates})
            return

        _json_response(self, 404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/run-once":
            _json_response(self, 404, {"error": "not found"})
            return
        if not self._authorized():
            _json_response(self, 401, {"error": "unauthorized"})
            return
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")) or 0)
        try:
            payload = json.loads(raw.decode() or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            _json_response(self, 400, {"error": "request body is not valid JSON"})
            return
        if not isinstance(payload, dict):
            _json_response(self, 400, {"error": "request body must be a JSON object"})
            return
        execute = bool(payload.get("execute", False))

        try:
            open_wagers = _load_open_wagers(self.indexer_base_url, limit=None)
        except Exception as exc:
            _json_response(self, 502, {"error": f"indexer unavailable: {exc}"})
            return
        # Refuse the whole run: acting on part of a file the operator is mid-way through editing is
        # worse than doing nothing, and every path here can wait for the file to be fixed.
        try:
            decisions = _read_decisions(self.decisions_path)
        except (OSError, ValueError) as exc:
            _json_response(self, 500, {"error": _decisions_problem(exc)})
            return
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
            pv = str(c.get("protocol_version") or "enumerated").strip().lower()
            try:
                win = None
                win_ans = decision.get("winningAnswer")
                if win_ans is not None and not isinstance(win_ans, str):
                    win_ans = str(win_ans)
                if action == "resolve":
                    if pv == "freeform":
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
                        win = resolve_uint256_from_decision(decision)
                        cmd = _action_command(
                            wager_address=c["wager_address"],
                            action=action,
                            rpc_url=self.rpc_url,
                            private_key=self.private_key,
                            protocol_version=pv,
                            resolve_uint256=win,
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
                results.append(
                    {"wager": c["wager_address"], "ok": True, "dry_run": True, "command": redact_argv(cmd)}
                )
                continue
            result = run_cast_send(cmd)
            if result.ok:
                succeeded += 1
                results.append({"wager": c["wager_address"], "ok": True, "tx_hash": result.tx_hash, "stdout": result.stdout})
            else:
                failed += 1
                results.append({"wager": c["wager_address"], "ok": False, "tx_hash": result.tx_hash, "stderr": result.stderr})

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
    parser.add_argument(
        "--auth-token",
        default=_env("RESOLUTION_SERVICE_TOKEN"),
        help="Bearer token required by POST /run-once (unset = endpoint disabled).",
    )
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
    Handler.auth_token = args.auth_token or None
    if not Handler.auth_token:
        print("WARNING: RESOLUTION_SERVICE_TOKEN unset — POST /run-once will reject every request")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Resolution service listening on http://{args.host}:{args.port}")
    print(f"Resolver address: {resolver}")
    print(f"Indexer API: {Handler.indexer_base_url}")
    print(f"Decisions file: {args.decisions_path}")
    server.serve_forever()


if __name__ == "__main__":
    main()
