"""ABI calldata encoders used by the planner to build tx-ready hints.

Standard library only, so the package keeps zero runtime dependencies. These once shelled out to
``cast calldata``, which made calldata depend on Foundry being installed and, worse, was not exact:
``cast`` strips trailing whitespace and surrounding quotes from string arguments, so an agent could be
handed calldata for a different freeform answer than the one it was told about (ADR-0020).

The recommend / quote pipeline ends in ``build_quote_like_payload``: that function is the single source
of truth for the JSON shape that downstream tools rely on, including the ``placeBet.calldata`` hex and
the ``approval_required`` block needed to pre-allow ERC-20 spend.
"""

from __future__ import annotations

from typing import Any

from .keccak import keccak256

# `ParamutuelWagerV3._answerId` hashes a domain byte before the answer, so a freeform answer id can
# never collide with an enumerated ticket mask.
FREEFORM_ANSWER_DOMAIN = b"\x03"

# keccak256(signature)[:4]. Python's standard library has no keccak, so these are pinned, and
# `tests/test_adr0020.py` recomputes each one.
SELECTORS: dict[str, str] = {
    "placeBet(uint256,uint256)": "0x4afe62b5",
    "placeBet(string,uint256)": "0xd76f2a1e",
    "resolve(string)": "0x461a4478",
    "approve(address,uint256)": "0x095ea7b3",
}


def freeform_answer_id_hex(answer: str) -> str:
    """``keccak256(0x03 || utf8(answer))``: the id the contract and the indexer key this answer by.

    The scout asks the indexer for this id directly (``/wagers/{addr}?answer_id=``), because the
    wager listing holds only the largest pools (ADR-0021 U1).
    """
    return "0x" + keccak256(FREEFORM_ANSWER_DOMAIN + answer.encode("utf-8")).hex()


def _word(value: int) -> str:
    return f"{value:064x}"


def _encode_string_tail(text: str) -> str:
    """ABI tail of a dynamic string: its byte length, then its bytes padded to a 32-byte boundary."""
    raw = text.encode("utf-8")
    padded = raw.hex().ljust((len(raw) + 31) // 32 * 64, "0")
    return _word(len(raw)) + padded


def encode_place_bet(ticket_mask: int, amount: int) -> str:
    """Enumerated mode. The first argument is the ticket bitmask, so ``1 << i`` backs outcome ``i``."""
    return SELECTORS["placeBet(uint256,uint256)"] + _word(ticket_mask) + _word(amount)


def encode_place_bet_freeform(answer: str, amount: int) -> str:
    """ADR-0009: `placeBet(string,uint256)`. Sent byte for byte, since the answer matches exactly."""
    head = _word(64) + _word(amount)  # offset of the string, past the two head words
    return SELECTORS["placeBet(string,uint256)"] + head + _encode_string_tail(answer)


def encode_resolve_freeform(winning_answer: str) -> str:
    """ADR-0009: resolver `resolve(string)`; must match a backed answer's bytes exactly."""
    return SELECTORS["resolve(string)"] + _word(32) + _encode_string_tail(winning_answer)


def encode_approve(spender: str, amount: int) -> str:
    return SELECTORS["approve(address,uint256)"] + _word(int(spender, 16)) + _word(amount)


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
        place_data = encode_place_bet_freeform(freeform_answer, amount) if freeform_answer else None
        calldata_note = None
        if place_data is None:
            calldata_note = (
                "Freeform wagers need the exact UTF-8 answer string (same bytes as on-chain). "
                "Pass `freeform_answer` in JSON `quote`, or read `answer_text` from the indexer's `ticket_pools`."
            )
        first_u256 = int(outcome_index)
    else:
        first_u256 = int(1 << int(outcome_index))
        place_data = encode_place_bet(first_u256, amount)
        calldata_note = None
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
        body["freeform_answer_supplied"] = bool(freeform_answer)
    else:
        body["ticket_mask"] = first_u256
    return body
