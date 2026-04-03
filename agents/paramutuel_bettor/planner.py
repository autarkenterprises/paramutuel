from __future__ import annotations

import json
import time
from typing import Any

from . import calldata as calldata_mod
from .indexer_client import IndexerClient
from . import odds as odds_mod
from .policy import pick_outcome, summarize_list_row


def recommend(
    client: IndexerClient,
    *,
    strategy: str,
    bet_amount_raw: int,
    scan_limit: int = 30,
    min_total_pot_raw: int = 0,
    proposition_contains: str | None = None,
    top: int = 5,
) -> dict[str, Any]:
    rows = client.list_wagers(state="OPEN", limit=scan_limit, order="desc")
    filtered: list[dict[str, Any]] = []
    needle = (proposition_contains or "").strip().lower()
    for row in rows:
        pot = int(str(row.get("total_pot") or "0"))
        if pot < min_total_pot_raw:
            continue
        prop = str(row.get("proposition") or "").lower()
        if needle and needle not in prop:
            continue
        filtered.append(row)

    recs: list[dict[str, Any]] = []
    errors: list[str] = []
    for row in filtered:
        addr = str(row.get("wager_address") or "").strip()
        if not addr:
            continue
        try:
            detail = client.get_wager(addr)
            pick = pick_outcome(strategy=strategy, wager_detail=detail, bet_amount=bet_amount_raw)
            oi = int(pick["outcome_index"])
            od = pick["odds"]
            post = od.get("post_bet_payout_multiple")
            score = float(post) if isinstance(post, (int, float)) else float("-inf")
            wager = detail.get("wager") or {}
            collateral = str(wager.get("collateral_token") or "").strip()
            quote = calldata_mod.build_quote_like_payload(
                wager_address=addr,
                collateral_token=collateral,
                outcome_index=oi,
                amount=bet_amount_raw,
                odds=od,
                betting_open=bool(pick["betting_open"]),
                revert_hint=str(pick["revert_hint"] or ""),
            )
            recs.append(
                {
                    "score": score,
                    "summary": summarize_list_row(row),
                    "chosen_outcome_index": oi,
                    "strategy": strategy,
                    "bet_amount_raw": bet_amount_raw,
                    "pick": pick,
                    "quote": quote,
                    "disclaimer": "Informational only; verify on-chain and with your own risk policy before signing.",
                }
            )
        except (ValueError, RuntimeError, json.JSONDecodeError, TypeError, KeyError) as exc:
            errors.append(f"{addr}: {exc}")

    recs.sort(key=lambda x: x["score"], reverse=True)
    return {
        "indexer_url": client.base_url,
        "candidates_scanned": len(filtered),
        "recommendations": recs[: max(1, top)],
        "errors_sample": errors[:10],
    }


def quote_wager(
    client: IndexerClient,
    *,
    wager_address: str,
    outcome_index: int,
    bet_amount_raw: int,
) -> dict[str, Any]:
    detail = client.get_wager(wager_address)
    wager = detail.get("wager") or {}
    totals_meta = detail.get("totals") or {}
    outcome_rows = detail.get("outcomes") or []

    total_pot = int(totals_meta.get("total_pot", 0) or 0) if totals_meta else int(wager.get("total_pot", 0) or 0)
    total_fee_bps = int(totals_meta.get("total_fee_bps", 0) or 0) if totals_meta else int(wager.get("total_fee_bps", 0) or 0)

    now_ts = int(time.time())
    betting_open, revert_hint = odds_mod.betting_open_status(wager, now_ts=now_ts)

    otot = None
    for row in outcome_rows:
        if int(row.get("outcome_index", -1)) == int(outcome_index):
            otot = int(row.get("outcome_total", 0) or 0)
            break
    if otot is None:
        raise ValueError(f"outcome_index {outcome_index} not found on wager")

    od = odds_mod.compute_odds(
        total_pot=total_pot,
        outcome_total=otot,
        total_fee_bps=total_fee_bps,
        bet_amount=bet_amount_raw,
    )
    collateral = str(wager.get("collateral_token") or "").strip()
    quote = calldata_mod.build_quote_like_payload(
        wager_address=wager_address.strip(),
        collateral_token=collateral,
        outcome_index=int(outcome_index),
        amount=int(bet_amount_raw),
        odds=od,
        betting_open=betting_open,
        revert_hint=revert_hint,
    )
    return {
        "wager_address": wager_address,
        "outcome_index": outcome_index,
        "bet_amount_raw": bet_amount_raw,
        "outcome_total_raw": otot,
        "total_pot_raw": total_pot,
        "quote": quote,
    }
