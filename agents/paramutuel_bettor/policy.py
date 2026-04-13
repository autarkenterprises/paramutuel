from __future__ import annotations

import json
import time
from typing import Any

from . import odds as odds_mod


def _outcome_labels(wager_row: dict[str, Any]) -> list[str]:
    raw = wager_row.get("outcomes_json") or "[]"
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def _ticket_pool_total(ticket_pools: list[Any], mask: int) -> int:
    key = str(mask)
    for row in ticket_pools:
        if not isinstance(row, dict):
            continue
        if str(row.get("ticket_mask")) == key:
            return int(row.get("pool_total", 0) or 0)
    return 0


def pick_outcome(
    *,
    strategy: str,
    wager_detail: dict[str, Any],
    bet_amount: int,
) -> dict[str, Any]:
    """Choose an outcome index; includes diagnostics and betting-open status."""
    wager = wager_detail.get("wager") or {}
    totals_meta = wager_detail.get("totals") or {}
    outcome_rows = wager_detail.get("outcomes") or []

    total_pot = int(totals_meta.get("total_pot", 0) or 0) if totals_meta else int(wager.get("total_pot", 0) or 0)
    total_fee_bps = int(totals_meta.get("total_fee_bps", 0) or 0) if totals_meta else int(wager.get("total_fee_bps", 0) or 0)

    now_ts = int(time.time())
    betting_open, revert_hint = odds_mod.betting_open_status(wager, now_ts=now_ts)

    per_outcome: list[dict[str, Any]] = []
    protocol_version = str(wager.get("protocol_version") or "v1").strip().lower()

    if protocol_version in ("v2", "v3_enum"):
        labels = _outcome_labels(wager)
        ticket_pools = wager_detail.get("ticket_pools") or []
        for idx in range(len(labels)):
            mask = 1 << idx
            otot = _ticket_pool_total(ticket_pools, mask)
            od = odds_mod.compute_odds(
                total_pot=total_pot,
                outcome_total=otot,
                total_fee_bps=total_fee_bps,
                bet_amount=bet_amount,
            )
            post = od.get("post_bet_payout_multiple")
            per_outcome.append(
                {
                    "outcome_index": idx,
                    "outcome_total_raw": otot,
                    "ticket_mask": mask,
                    "odds": od,
                    "score": post if isinstance(post, (int, float)) else -1.0,
                }
            )
    elif protocol_version in ("freeform", "v3_freeform"):
        raw_pools = wager_detail.get("ticket_pools") or []
        ticket_pools = [p for p in raw_pools if isinstance(p, dict)]
        ticket_pools.sort(key=lambda p: str(p.get("ticket_mask") or "").lower())
        for idx, row in enumerate(ticket_pools):
            aid = str(row.get("ticket_mask") or "").strip().lower()
            otot = int(row.get("pool_total", 0) or 0)
            od = odds_mod.compute_odds(
                total_pot=total_pot,
                outcome_total=otot,
                total_fee_bps=total_fee_bps,
                bet_amount=bet_amount,
            )
            post = od.get("post_bet_payout_multiple")
            per_outcome.append(
                {
                    "outcome_index": idx,
                    "outcome_total_raw": otot,
                    "answer_id_hex": aid,
                    "odds": od,
                    "score": post if isinstance(post, (int, float)) else -1.0,
                }
            )
    else:
        for row in outcome_rows:
            idx = int(row.get("outcome_index", -1))
            if idx < 0:
                continue
            otot = int(row.get("outcome_total", 0) or 0)
            od = odds_mod.compute_odds(
                total_pot=total_pot,
                outcome_total=otot,
                total_fee_bps=total_fee_bps,
                bet_amount=bet_amount,
            )
            post = od.get("post_bet_payout_multiple")
            per_outcome.append(
                {
                    "outcome_index": idx,
                    "outcome_total_raw": otot,
                    "odds": od,
                    "score": post if isinstance(post, (int, float)) else -1.0,
                }
            )

    if not per_outcome:
        raise ValueError("no outcomes on wager detail payload")

    st = strategy.strip().lower()
    if st in ("best_post_multiple", "max_post_multiple", "value"):
        best = max(per_outcome, key=lambda x: float(x["score"] if x["score"] is not None else -1))
    elif st in ("min_liquidity", "contrarian", "longshot"):
        best = min(per_outcome, key=lambda x: x["outcome_total_raw"])
    else:
        raise ValueError(f"unknown strategy: {strategy}")

    out: dict[str, Any] = {
        "outcome_index": int(best["outcome_index"]),
        "odds": dict(best["odds"]),
        "per_outcome": per_outcome,
        "betting_open": betting_open,
        "revert_hint": revert_hint,
    }
    if protocol_version == "freeform":
        out["answer_id_hex"] = str(best.get("answer_id_hex") or "")
        out["freeform_note"] = (
            "Indexer stores answer ids (bytes32), not plaintext. To sign `placeBet`, you need the exact "
            "UTF-8 string that hashes to this id, or use MCP `encode_place_bet_freeform` with that string."
        )
    elif protocol_version == "v3_freeform":
        out["answer_id_hex"] = str(best.get("answer_id_hex") or "")
        out["freeform_note"] = (
            "v3_freeform: ticket id = keccak256(abi.encodePacked(bytes1(0x03), bytes(answer))) — not legacy "
            "freeform. Indexer stores ids only; pass the exact UTF-8 answer in `quote.freeform_answer` or use MCP."
        )
    return out


def summarize_list_row(row: dict[str, Any]) -> dict[str, Any]:
    labels = _outcome_labels(row)
    pv = str(row.get("protocol_version") or "v1").strip().lower()
    return {
        "wager_address": row.get("wager_address"),
        "state": row.get("state"),
        "protocol_version": row.get("protocol_version") or "v1",
        "proposition": (row.get("proposition") or "")[:500],
        "collateral_token": row.get("collateral_token"),
        "total_pot_raw": str(row.get("total_pot") or "0"),
        "total_fee_bps": str(row.get("total_fee_bps") or "0"),
        "outcome_count": len(labels),
        "outcome_labels_preview": labels[:8],
        "freeform": pv in ("freeform", "v3_freeform"),
        "v3": pv.startswith("v3_"),
    }
