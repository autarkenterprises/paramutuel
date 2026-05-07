"""Bet scout — odds and expected-payout helpers.

Mirrors the math used by the dApp (``dapp/logic.js``) and the MCP server
so all three surfaces produce the same number for a given wager / outcome /
bet size. Drift between them would mislead an agent that hops between
surfaces (e.g. an LLM reading MCP odds and calling the bet scout to plan).
All values are raw token units; the caller is responsible for any
human-scale formatting.
"""
from __future__ import annotations

from typing import Any


def compute_odds(
    *,
    total_pot: int,
    outcome_total: int,
    total_fee_bps: int,
    bet_amount: int,
) -> dict[str, Any]:
    """Parimutuel implied multiples and expected payout (raw token units). Mirrors MCP logic."""
    if bet_amount <= 0:
        raise ValueError("bet_amount must be > 0")
    bps_denom = 10_000
    net_before = total_pot - (total_pot * total_fee_bps // bps_denom)
    current_multiple = round(net_before / outcome_total, 4) if outcome_total > 0 else None

    pot_after = total_pot + bet_amount
    net_after = pot_after - (pot_after * total_fee_bps // bps_denom)
    outcome_after = outcome_total + bet_amount
    post_bet_multiple = round(net_after / outcome_after, 4) if outcome_after > 0 else None
    expected_payout = (bet_amount * net_after) // outcome_after if outcome_after > 0 else 0
    expected_profit = expected_payout - bet_amount

    return {
        "current_payout_multiple": current_multiple,
        "post_bet_payout_multiple": post_bet_multiple,
        "expected_payout_raw": expected_payout,
        "expected_profit_raw": expected_profit,
        "net_pot_after": net_after,
        "total_pot_after": pot_after,
    }


def betting_open_status(wager_row: dict[str, Any], *, now_ts: int) -> tuple[bool, str]:
    state = str(wager_row.get("state", "")).upper()
    if state != "OPEN":
        return False, "wager.state != OPEN"
    if int(wager_row.get("betting_closed_by_authority", 0) or 0) == 1:
        return False, "betting was closed by authority"
    betting_close_time = int(wager_row.get("betting_close_time", 0) or 0)
    if betting_close_time == 0:
        return True, ""
    if now_ts >= betting_close_time:
        return False, "betting_close_time has passed"
    return True, ""
