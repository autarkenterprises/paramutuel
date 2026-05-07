"""CLI / subagent entry point for the bet-scout package.

Two surfaces are exposed:

* Argparse subcommands (``health``, ``scan``, ``recommend``, ``quote``) for
  human/operator use at the shell.
* A ``json`` subcommand that reads exactly one JSON object from stdin and
  writes one JSON object on stdout. This is the stable contract used by
  higher-level agents that want to call the planner programmatically
  without parsing argparse strings.

Both surfaces share the same dispatch logic and emit the same shape of
result (``{"ok": true, ...}`` on success, ``{"ok": false, "error": str}``
on failure, written to stderr with a non-zero exit). The agent never
touches a private key — every command output describes calldata that the
caller must sign elsewhere.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .config import load_default_indexer_url
from .indexer_client import IndexerClient
from .planner import quote_wager, recommend
from .policy import summarize_list_row


def _client(args: argparse.Namespace) -> IndexerClient:
    base = (args.indexer_url or load_default_indexer_url()).strip().rstrip("/")
    return IndexerClient(base, timeout=args.timeout)


def _cmd_health(client: IndexerClient) -> dict[str, Any]:
    return {"ok": True, "health": client.health(), "indexer_url": client.base_url}


def _cmd_scan(client: IndexerClient, args: argparse.Namespace) -> dict[str, Any]:
    rows = client.list_wagers(state=args.state, limit=args.limit, order=args.order, q=args.q)
    return {
        "ok": True,
        "indexer_url": client.base_url,
        "count": len(rows),
        "wagers": [summarize_list_row(dict(r)) for r in rows],
    }


def _cmd_recommend(client: IndexerClient, args: argparse.Namespace) -> dict[str, Any]:
    out = recommend(
        client,
        strategy=args.strategy,
        bet_amount_raw=args.bet_amount_raw,
        scan_limit=args.scan_limit,
        min_total_pot_raw=args.min_total_pot_raw,
        proposition_contains=args.proposition_contains,
        top=args.top,
    )
    return {"ok": True, **out}


def _cmd_quote(client: IndexerClient, args: argparse.Namespace) -> dict[str, Any]:
    ff = getattr(args, "freeform_answer", None)
    ff_s = str(ff).strip() if ff is not None else ""
    q = quote_wager(
        client,
        wager_address=args.wager,
        outcome_index=args.outcome_index,
        bet_amount_raw=args.bet_amount_raw,
        freeform_answer=ff_s if ff_s else None,
    )
    return {"ok": True, **q}


def _dispatch_json(client: IndexerClient, payload: dict[str, Any]) -> dict[str, Any]:
    """Route one JSON request object to the matching planner call.

    The wire shape mirrors the argparse subcommands so a calling agent can
    learn the surface from the CLI ``--help`` and then use ``json`` for
    machine-to-machine I/O. Numeric fields use the ``_raw`` suffix to make
    it explicit that values are integer base units (no decimals applied).
    """
    op = str(payload.get("op") or "").strip().lower()
    if op == "health":
        return _cmd_health(client)
    if op == "scan":
        state = payload.get("state")
        limit = int(payload.get("limit") or 20)
        order = str(payload.get("order") or "desc")
        q = payload.get("q")
        rows = client.list_wagers(state=state, limit=limit, order=order, q=q)
        return {
            "ok": True,
            "indexer_url": client.base_url,
            "count": len(rows),
            "wagers": [summarize_list_row(dict(r)) for r in rows],
        }
    if op == "recommend":
        bet_amount_raw = int(payload.get("bet_amount_raw") or payload.get("bet_amount") or 0)
        if bet_amount_raw <= 0:
            raise ValueError("bet_amount_raw must be > 0")
        out = recommend(
            client,
            strategy=str(payload.get("strategy") or "best_post_multiple"),
            bet_amount_raw=bet_amount_raw,
            scan_limit=int(payload.get("scan_limit") or 30),
            min_total_pot_raw=int(payload.get("min_total_pot_raw") or 0),
            proposition_contains=payload.get("proposition_contains"),
            top=int(payload.get("top") or 5),
        )
        return {"ok": True, **out}
    if op == "quote":
        wager = str(payload.get("wager_address") or payload.get("wager") or "").strip()
        outcome_index = int(payload.get("outcome_index"))
        bet_amount_raw = int(payload.get("bet_amount_raw") or payload.get("bet_amount") or 0)
        if not wager or bet_amount_raw <= 0:
            raise ValueError("wager_address and bet_amount_raw required")
        ffa = payload.get("freeform_answer")
        q = quote_wager(
            client,
            wager_address=wager,
            outcome_index=outcome_index,
            bet_amount_raw=bet_amount_raw,
            freeform_answer=str(ffa).strip() if ffa is not None and str(ffa).strip() != "" else None,
        )
        return {"ok": True, **q}
    raise ValueError(f"unknown op: {op}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Paramutuel bet scout / planner (indexer + odds; no private keys).")
    p.add_argument("--indexer-url", default="", help="Indexer base URL (default: INDEXER_URL or deployments.json).")
    p.add_argument("--timeout", type=int, default=25)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="GET /health")

    sp = sub.add_parser("scan", help="List wagers (summary)")
    sp.add_argument("--state", default="OPEN")
    sp.add_argument("--limit", type=int, default=30)
    sp.add_argument("--order", default="desc", choices=("asc", "desc"))
    sp.add_argument("--q", default=None, help="Indexer search string")

    sp = sub.add_parser("recommend", help="Scan OPEN wagers and rank bet ideas")
    sp.add_argument("--strategy", default="best_post_multiple")
    sp.add_argument("--bet-amount-raw", type=int, required=True)
    sp.add_argument("--scan-limit", type=int, default=40)
    sp.add_argument("--min-total-pot-raw", type=int, default=0)
    sp.add_argument("--proposition-contains", default=None)
    sp.add_argument("--top", type=int, default=5)

    sp = sub.add_parser("quote", help="Quote one wager + outcome (fixed indices)")
    sp.add_argument("--wager", required=True)
    sp.add_argument("--outcome-index", type=int, required=True)
    sp.add_argument("--bet-amount-raw", type=int, required=True)
    sp.add_argument(
        "--freeform-answer",
        default="",
        help="Exact UTF-8 answer for placeBet(string,...) when protocol_version is freeform.",
    )

    sub.add_parser("json", help="Read one JSON object from stdin (subagent / tool bridge)")

    args = p.parse_args(argv)
    client = _client(args)

    if args.cmd == "json":
        raw = sys.stdin.read()
        payload = json.loads(raw or "{}")
        if not isinstance(payload, dict):
            raise ValueError("stdin JSON must be an object")
        out = _dispatch_json(client, payload)
    elif args.cmd == "health":
        out = _cmd_health(client)
    elif args.cmd == "scan":
        out = _cmd_scan(client, args)
    elif args.cmd == "recommend":
        out = _cmd_recommend(client, args)
    elif args.cmd == "quote":
        out = _cmd_quote(client, args)
    else:
        raise ValueError(f"unknown command: {args.cmd}")

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, json.JSONDecodeError, OSError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2), file=sys.stderr)
        raise SystemExit(1)
