"""Bet scout — top-level recommendation planner.

Composes the four lower-level modules (:mod:`indexer_client`, :mod:`odds`,
:mod:`policy`, :mod:`calldata`) into a single ``recommend(...)`` operation:
shortlist OPEN wagers, score outcomes against the agent's policy, build
the calldata an external signer would broadcast. The planner produces
JSON-only output and reads JSON-only input — that is the
stdin → stdout subagent contract documented in ``docs/BET-AGENT.md``.

Stateless by design: every invocation starts from indexer reads and ends
with calldata in the response, with nothing held between calls. The
caller's wallet (CLI, MCP-driven LLM, custom signer) decides whether to
broadcast.
"""
from __future__ import annotations

import json
import time
from typing import Any

from . import calldata as calldata_mod
from .indexer_client import IndexerClient
from . import odds as odds_mod
from .policy import _outcome_labels, odds_model_exact, pick_outcome, summarize_list_row


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
    # Wagers deliberately left out of the ranking, with the reason (ADR-0019):
    # the indexer's OPEN state survives the betting close, and the scout's
    # odds model only matches claim() math for SINGLE_WINNER / freeform.
    skipped: list[dict[str, str]] = []
    for row in filtered:
        addr = str(row.get("wager_address") or "").strip()
        if not addr:
            continue
        try:
            detail = client.get_wager(addr)
            pick = pick_outcome(strategy=strategy, wager_detail=detail, bet_amount=bet_amount_raw)
            if not pick["betting_open"]:
                skipped.append({"wager_address": addr, "reason": f"betting closed: {pick['revert_hint']}"})
                continue
            if not pick["odds_model_exact"]:
                policy = (detail.get("wager") or {}).get("payoff_policy")
                skipped.append(
                    {
                        "wager_address": addr,
                        "reason": f"payoff policy {policy}: single-pool odds model does not match claim() math",
                    }
                )
                continue
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
                protocol_version=str(wager.get("protocol_version") or "enumerated"),
                freeform_answer=pick.get("answer_text"),
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
        "skipped": skipped,
        "errors_sample": errors[:10],
    }


def quote_wager(
    client: IndexerClient,
    *,
    wager_address: str,
    outcome_index: int,
    bet_amount_raw: int,
    freeform_answer: str | None = None,
) -> dict[str, Any]:
    # With the answer text, ask for that answer's pool by id. The listing holds only the largest
    # pools, and `outcome_index` is a position in it that shifts as answers arrive, so taking the odds
    # from it described a different answer than the calldata (ADR-0021 U1). The indexer ignores
    # `answer_id` for enumerated wagers, so this is safe before the protocol is known.
    answer_id_hex: str | None = calldata_mod.freeform_answer_id_hex(freeform_answer) if freeform_answer else None
    detail = client.get_wager(wager_address, answer_id=answer_id_hex) if answer_id_hex else client.get_wager(wager_address)
    wager = detail.get("wager") or {}
    totals_meta = detail.get("totals") or {}
    # V3 indexer tags every wager as `enumerated` or `freeform`; default to
    # enumerated when the tag is missing.
    protocol_version = str(wager.get("protocol_version") or "enumerated").strip().lower()

    total_pot = int(totals_meta.get("total_pot", 0) or 0) if totals_meta else int(wager.get("total_pot", 0) or 0)
    total_fee_bps = int(totals_meta.get("total_fee_bps", 0) or 0) if totals_meta else int(wager.get("total_fee_bps", 0) or 0)

    now_ts = int(time.time())
    betting_open, revert_hint = odds_mod.betting_open_status(wager, now_ts=now_ts)

    if protocol_version != "freeform":
        labels = _outcome_labels(wager)
        if int(outcome_index) < 0 or (labels and int(outcome_index) >= len(labels)):
            raise ValueError(f"outcome_index {outcome_index} out of range: this wager has {len(labels)} outcomes")

    otot: int | None = None
    if protocol_version == "freeform" and answer_id_hex:
        otot = 0
        for tp in detail.get("ticket_pools") or []:
            if isinstance(tp, dict) and str(tp.get("ticket_mask") or "").strip().lower() == answer_id_hex:
                otot = int(tp.get("pool_total", 0) or 0)
                break
    elif protocol_version == "freeform":
        # No answer text: no calldata either, so this only reports the listed row at the index.
        pools = [p for p in (detail.get("ticket_pools") or []) if isinstance(p, dict)]
        pools.sort(key=lambda p: str(p.get("ticket_mask") or "").lower())
        oi = int(outcome_index)
        if oi < 0 or oi >= len(pools):
            raise ValueError(
                "freeform: outcome_index must be the row index into ticket_pools "
                "(sorted by answer id), as returned by recommend/pick_outcome"
            )
        row = pools[oi]
        otot = int(row.get("pool_total", 0) or 0)
        answer_id_hex = str(row.get("ticket_mask") or "").strip().lower()
    else:
        answer_id_hex = None  # an answer passed for an enumerated wager has no id to report
        mask = int(1) << int(outcome_index)
        key = str(mask)
        for tp in detail.get("ticket_pools") or []:
            if str(tp.get("ticket_mask")) == key:
                otot = int(tp.get("pool_total", 0) or 0)
                break
        if otot is None:
            otot = 0

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
        protocol_version=protocol_version,
        freeform_answer=freeform_answer,
    )
    # A new ticket below the wager's minimum reverts, so say so before anyone signs.
    minimum = int(wager.get("min_new_ticket_stake") or 0)
    if minimum and otot == 0 and bet_amount_raw < minimum:
        quote["execution_allowed"] = False
        quote["revert_hint"] = (
            f"This would open a new ticket, which needs at least minNewTicketStake={minimum} raw units."
        )
    out: dict[str, Any] = {
        "wager_address": wager_address,
        "outcome_index": outcome_index,
        "bet_amount_raw": bet_amount_raw,
        "outcome_total_raw": otot,
        "total_pot_raw": total_pot,
        "quote": quote,
        "odds_model_exact": odds_model_exact(wager),
    }
    if not out["odds_model_exact"]:
        out["odds_note"] = (
            "Odds use the single-winning-pool formula, which is the contract's payout only for "
            "SINGLE_WINNER and freeform wagers. This policy divides by the resolver-dependent winning "
            "units (docs/PAYOUT-CALCULATION.md Part B), so the multiple is not a payout estimate."
        )
    if answer_id_hex:
        out["answer_id_hex"] = answer_id_hex
    return out
