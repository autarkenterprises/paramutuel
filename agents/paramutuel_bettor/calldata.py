"""ABI calldata encoders used by the planner to build tx-ready hints.

The encoders shell out to Foundry's ``cast calldata`` rather than depend on
a Python ABI library. This keeps the package's runtime requirements to the
standard library (the same posture as ``indexer_client`` using ``urllib``);
when ``cast`` is missing we return ``None`` and surface a note so the
caller can either install Foundry or route the encode through the MCP
server's encoders instead.

The recommend / quote pipeline ends in ``build_quote_like_payload``: that
function is the single source of truth for the JSON shape that downstream
tools rely on, including the ``placeBet.calldata`` hex and the
``approval_required`` block needed to pre-allow ERC-20 spend.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any


def _cast_calldata(signature: str, *args: Any) -> str | None:
    """Run ``cast calldata <sig> <args...>`` and return ``0x...`` on success.

    Returning ``None`` (rather than raising) lets the planner degrade
    gracefully when Foundry isn't installed: the JSON payload still
    carries odds and approval metadata, just without ready-to-broadcast
    placeBet calldata.
    """
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
    """Enumerated mode: first argument is a pre-shifted ticket bitmask.

    Callers pass the already-shifted ``1 << outcome_index`` value; the
    planner does that shift in ``build_quote_like_payload`` so this helper
    stays a thin pass-through to ``cast``.
    """
    return _cast_calldata("placeBet(uint256,uint256)", outcome_index, amount)


def encode_place_bet_freeform(answer: str, amount: int) -> str | None:
    """ADR-0009: `placeBet(string,uint256)`; answer bytes must match `resolve(string)` exactly."""
    return _cast_calldata("placeBet(string,uint256)", answer, amount)


def encode_resolve_freeform(winning_answer: str) -> str | None:
    """ADR-0009: resolver `resolve(string)`; must match a backed answer's UTF-8 bytes."""
    return _cast_calldata("resolve(string)", winning_answer)


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
    protocol_version: str = "enumerated",
    freeform_answer: str | None = None,
) -> dict[str, Any]:
    """Assemble the wire-shape JSON returned by ``recommend`` and ``quote``.

    The shape is intentionally stable: the MCP server, the dApp, and any
    downstream agent rely on the same field names so a recommendation can
    be handed to a wallet without further translation. ``execution_allowed``
    summarises gating (open + calldata available for freeform) so callers
    can surface a single boolean without re-deriving the rules.
    """
    # ADR-0010 recognises exactly two V3 protocol_version values:
    # `enumerated` (bitmask tickets, `placeBet(uint256,uint256)`) and
    # `freeform` (UTF-8 answer, `placeBet(string,uint256)`).
    pv = protocol_version.strip().lower()
    if pv == "freeform":
        place_data = (
            encode_place_bet_freeform(freeform_answer, amount)
            if freeform_answer is not None and str(freeform_answer).strip() != ""
            else None
        )
        calldata_note = None
        if place_data is None:
            calldata_note = (
                "Freeform wagers need the exact UTF-8 answer string (same bytes as on-chain). "
                "Pass `freeform_answer` in JSON `quote` or use MCP `encode_place_bet_freeform` / `quote_place_bet`."
            )
        first_u256 = int(outcome_index)
    else:
        first_u256 = int(1 << int(outcome_index))
        place_data = encode_place_bet(first_u256, amount)
        calldata_note = None if place_data else "Install Foundry `cast` or use MCP `quote_place_bet` for calldata."
    approve_data = encode_approve(wager_address, amount) if collateral_token else None
    body: dict[str, Any] = {
        "wager_address": wager_address,
        "collateral_token": collateral_token,
        "protocol_version": protocol_version,
        "outcome_index": outcome_index,
        "amount": amount,
        "betting_open": betting_open,
        "execution_allowed": betting_open and (pv != "freeform" or place_data is not None),
        "revert_hint": revert_hint,
        "odds": odds,
        "placeBet": {
            "to": wager_address,
            "calldata": place_data,
            "calldata_note": calldata_note,
            "approval_required": {
                "token": collateral_token,
                "spender": wager_address,
                "amount": amount,
                "approve_calldata": approve_data,
            },
        },
    }
    if pv == "freeform":
        body["freeform_answer_supplied"] = bool(
            freeform_answer is not None and str(freeform_answer).strip() != ""
        )
    else:
        body["ticket_mask"] = first_u256
    return body
