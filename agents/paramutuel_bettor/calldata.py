from __future__ import annotations

import shutil
import subprocess
from typing import Any


def _cast_calldata(signature: str, *args: Any) -> str | None:
    cast = shutil.which("cast")
    if not cast:
        return None
    cmd = [cast, "calldata", signature, *[str(a) for a in args]]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    return out if out.startswith("0x") else None


def encode_place_bet(outcome_index: int, amount: int) -> str | None:
    return _cast_calldata("placeBet(uint256,uint256)", outcome_index, amount)


def encode_approve(spender: str, amount: int) -> str | None:
    return _cast_calldata("approve(address,uint256)", spender, amount)


def build_quote_like_payload(
    *,
    wager_address: str,
    collateral_token: str,
    outcome_index: int,
    amount: int,
    odds: dict[str, Any],
    betting_open: bool,
    revert_hint: str,
) -> dict[str, Any]:
    place_data = encode_place_bet(outcome_index, amount)
    approve_data = encode_approve(wager_address, amount) if collateral_token else None
    return {
        "wager_address": wager_address,
        "collateral_token": collateral_token,
        "outcome_index": outcome_index,
        "amount": amount,
        "betting_open": betting_open,
        "execution_allowed": betting_open,
        "revert_hint": revert_hint,
        "odds": odds,
        "placeBet": {
            "to": wager_address,
            "calldata": place_data,
            "calldata_note": None if place_data else "Install Foundry `cast` or use MCP `quote_place_bet` for calldata.",
            "approval_required": {
                "token": collateral_token,
                "spender": wager_address,
                "amount": amount,
                "approve_calldata": approve_data,
            },
        },
    }
