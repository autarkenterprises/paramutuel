#!/usr/bin/env python3
"""Paramutuel Protocol MCP Server (V3 unified, ADR-0010).

Exposes on-chain parimutuel wager operations to LLM agents via the
Model Context Protocol.  Read operations hit the indexer HTTP API;
write helpers return ABI-encoded calldata (no private keys needed).

All tools target the unified V3 factory (`ParamutuelFactoryV3`) with
two wager modes:

  * `enumerated` — bitmask tickets + payoff policies.
  * `freeform`   — UTF-8 answer strings; answerId = keccak256(0x03 || bytes(answer)).

Usage:
    # stdio transport (default for MCP clients)
    python -m mcp_server

    # or with explicit config
    INDEXER_URL=https://paramutuel-git-406244230167.europe-west1.run.app \
    FACTORY_ADDRESS=0x11F036ab9C2621a21892E37E9d372d1b2Fe1dCD6 \
        python -m mcp_server
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# ── Configuration ──────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parent.parent

_DEPLOYMENTS_PATH = _ROOT / "config" / "deployments.json"


def _load_deployments() -> dict:
    if _DEPLOYMENTS_PATH.exists():
        return json.loads(_DEPLOYMENTS_PATH.read_text())
    return {}


_deployments = _load_deployments()
_default_network = _deployments.get("defaultNetwork", "baseSepolia")
_network_cfg = _deployments.get(_default_network, {})

INDEXER_URL = os.environ.get(
    "INDEXER_URL",
    _network_cfg.get("explorerApiBase", "http://127.0.0.1:8090"),
).rstrip("/")

FACTORY_ADDRESS = os.environ.get(
    "FACTORY_ADDRESS",
    _network_cfg.get("factoryAddress", ""),
).strip()

CHAIN_ID = int(os.environ.get("CHAIN_ID", _network_cfg.get("chainId", 84532)))

# ── ABI loading ────────────────────────────────────────────────────

_PACKAGE_ABI_DIR = Path(__file__).resolve().parent / "abi"
_REPO_ABI_DIR = _ROOT / "dapp" / "abi"


def _load_abi(name: str) -> list[dict]:
    path = _PACKAGE_ABI_DIR / f"{name}.json"
    if not path.exists():
        path = _REPO_ABI_DIR / f"{name}.json"
    if not path.exists():
        path = _ROOT / "out" / f"{name}.sol" / f"{name}.json"
    data = json.loads(path.read_text())
    return data["abi"]


FACTORY_ABI = _load_abi("ParamutuelFactoryV3")
WAGER_ABI = _load_abi("ParamutuelWagerV3")

# ── ABI encoding helpers ───────────────────────────────────────────

from eth_abi import encode as abi_encode  # noqa: E402
from eth_hash.auto import keccak as _keccak256  # noqa: E402

_ZERO_ADDRESS = "0x" + "00" * 20

_FREEFORM_V3_DOMAIN = bytes([0x03])


def _freeform_answer_id_hex(answer: str) -> str:
    """Match `ParamutuelWagerV3._answerId`: keccak256(abi.encodePacked(domain byte, bytes(answer)))."""
    digest = _keccak256(_FREEFORM_V3_DOMAIN + answer.encode("utf-8"))
    return "0x" + digest.hex()


def _selector(sig: str) -> bytes:
    return _keccak256(sig.encode())[:4]


def _encode_call(sig: str, types: list[str], values: list) -> str:
    sel = _selector(sig)
    encoded = abi_encode(types, values) if types else b""
    return "0x" + (sel + encoded).hex()


def _encode_erc20_approve(spender: str, amount: int) -> str:
    return _encode_call(
        "approve(address,uint256)", ["address", "uint256"], [spender, amount]
    )


# ── Odds calculator ───────────────────────────────────────────────


def _compute_odds(
    total_pot: int,
    outcome_total: int,
    total_fee_bps: int,
    bet_amount: int,
) -> dict:
    bps_denom = 10_000

    net_before = total_pot - (total_pot * total_fee_bps // bps_denom)
    current_multiple = (
        round(net_before / outcome_total, 4) if outcome_total > 0 else None
    )

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


def _compute_batch_odds(
    total_pot: int,
    outcome_totals: list[int],
    total_fee_bps: int,
    bet_amounts: list[int],
) -> dict:
    if len(outcome_totals) != len(bet_amounts):
        raise ValueError("outcome_totals and bet_amounts length mismatch")

    bps_denom = 10_000
    net_before = total_pot - (total_pot * total_fee_bps // bps_denom)

    total_bet = sum(bet_amounts)
    pot_after = total_pot + total_bet
    net_after = pot_after - (pot_after * total_fee_bps // bps_denom)

    legs: list[dict[str, Any]] = []
    for outcome_total, bet_amount in zip(outcome_totals, bet_amounts):
        current_multiple = (
            round(net_before / outcome_total, 4) if outcome_total > 0 else None
        )
        outcome_after = outcome_total + bet_amount
        post_multiple = round(net_after / outcome_after, 4) if outcome_after > 0 else None
        expected_payout = (bet_amount * net_after) // outcome_after if outcome_after > 0 else 0
        expected_profit = expected_payout - bet_amount
        legs.append(
            {
                "current_payout_multiple": current_multiple,
                "post_bet_payout_multiple": post_multiple,
                "expected_payout_raw": expected_payout,
                "expected_profit_raw": expected_profit,
            }
        )

    return {
        "net_pot_after": net_after,
        "total_pot_after": pot_after,
        "legs": legs,
    }


def _betting_open_status(wager_row: dict[str, Any], now_ts: int) -> tuple[bool, str]:
    state = str(wager_row.get("state", "")).upper()
    if state != "OPEN":
        return False, "wager.state != OPEN"

    betting_closed_by_authority = int(
        wager_row.get("betting_closed_by_authority", 0) or 0
    )
    if betting_closed_by_authority == 1:
        return False, "betting was closed by authority"

    betting_close_time = int(wager_row.get("betting_close_time", 0) or 0)
    if betting_close_time == 0:
        return True, ""

    if now_ts >= betting_close_time:
        return False, "betting_close_time has passed"

    return True, ""


# ── HTTP helpers ──────────────────────────────────────────────────


async def _indexer_get(path: str) -> dict:
    url = INDEXER_URL + path
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


# ── MCP Server ────────────────────────────────────────────────────

mcp_server = FastMCP(
    "paramutuel",
    instructions=(
        "Paramutuel Protocol (V3 unified): on-chain parimutuel betting wagers on Base. "
        "Use these tools to discover wagers, analyze odds, and prepare transactions for "
        "wager creation (enumerated or freeform), betting, resolution, and claims. "
        "Write tools return ABI-encoded calldata — the caller must sign and submit."
    ),
)


# ── Discovery tools ──────────────────────────────────────────────


@mcp_server.tool()
async def list_wagers(
    state: str | None = None,
    limit: int = 100,
) -> str:
    """List parimutuel wagers from the indexer.

    Args:
        state: Filter by wager state (OPEN, RESOLVED, RETRACTED). Omit for all.
        limit: Max number of wagers to return (1-1000, default 100).
    """
    params = f"?limit={limit}"
    if state:
        params += f"&state={state.upper()}"
    data = await _indexer_get(f"/wagers{params}")
    return json.dumps(data, indent=2)


@mcp_server.tool()
async def get_wager(wager_address: str) -> str:
    """Get full details for a specific wager (totals, outcomes / ticket pools, events).

    `wager.protocol_version` is `enumerated` or `freeform` (wager mode in V3).
    """
    data = await _indexer_get(f"/wagers/{wager_address}")
    return json.dumps(data, indent=2)


@mcp_server.tool()
async def get_expire_candidates() -> str:
    """Find wagers past their resolution deadline that can be `expire()`d by anyone."""
    import time

    data = await _indexer_get(f"/sweeper/expire-candidates?now={int(time.time())}")
    return json.dumps(data, indent=2)


@mcp_server.tool()
async def get_indexer_health() -> str:
    """Return indexer /health information (sync indicators, wager counts, errors)."""
    data = await _indexer_get("/health")
    return json.dumps(data, indent=2)


@mcp_server.tool()
async def get_protocol_info() -> str:
    """Get protocol configuration: factory address, chain, indexer URL, and ABI summaries."""
    factory_functions = sorted({e["name"] for e in FACTORY_ABI if e.get("type") == "function"})
    wager_functions = sorted({e["name"] for e in WAGER_ABI if e.get("type") == "function"})
    return json.dumps(
        {
            "factory_address": FACTORY_ADDRESS or None,
            "chain_id": CHAIN_ID,
            "indexer_url": INDEXER_URL,
            "factory_functions": factory_functions,
            "wager_functions": wager_functions,
            "constants": {
                "BPS_DENOMINATOR": 10_000,
                "MAX_TOTAL_FEE_BPS": 10_000,
                "MAX_OUTCOMES": 255,
                "FREEFORM_MAX_ANSWER_BYTES": 1024,
                "FREEFORM_MAX_DISTINCT_ANSWERS_CAP": 1024,
                "FREEFORM_ANSWER_DOMAIN_BYTE": 3,
            },
            "wager_modes": {
                "enumerated": (
                    "Bitmask tickets + payoff policies (SINGLE_WINNER, ANY_OF, EXACT_SET, "
                    "AT_LEAST_K, WEIGHTED_OVERLAP). placeBet(uint256 ticketMask, uint256 amount); "
                    "resolve(uint256 winningMask)."
                ),
                "freeform": (
                    "UTF-8 answer strings. placeBet(string answer, uint256 amount); "
                    "resolve(string winningAnswer). Answer id = "
                    "keccak256(abi.encodePacked(bytes1(0x03), bytes(answer)))."
                ),
            },
        },
        indent=2,
    )


# ── Analysis tools ────────────────────────────────────────────────


@mcp_server.tool()
async def calculate_odds(
    total_pot: int,
    outcome_total: int,
    total_fee_bps: int,
    bet_amount: int,
) -> str:
    """Calculate implied odds and expected payout for a hypothetical bet.

    All amounts are in raw token units (e.g. USDC 6 decimals: 1 USDC = 1_000_000).
    """
    result = _compute_odds(total_pot, outcome_total, total_fee_bps, bet_amount)
    return json.dumps(result, indent=2)


@mcp_server.tool()
async def quote_place_bet(
    wager_address: str,
    outcome_index: int = 0,
    amount: int = 0,
    require_open: bool = False,
    answer: str = "",
) -> str:
    """Quote odds + return placeBet calldata + approval instructions.

    For `enumerated` wagers, the single-outcome bet builds `ticketMask = 1 << outcome_index`.
    For `freeform` wagers, pass the exact UTF-8 `answer` string (ticket pool is keyed by
    domain-separated answerId).
    """
    import time

    if amount <= 0:
        raise ValueError("amount must be > 0")

    data = await _indexer_get(f"/wagers/{wager_address}")
    wager = data.get("wager") or {}
    totals = data.get("totals") or {}

    if not wager:
        raise ValueError("Indexer returned no wager payload")

    now_ts = int(time.time())
    betting_open, revert_hint = _betting_open_status(wager, now_ts=now_ts)
    if require_open and not betting_open:
        raise ValueError(revert_hint or "wager betting is not open")

    collateral_token = str(wager.get("collateral_token") or "").strip()
    total_pot = int(totals.get("total_pot", 0) or 0)
    total_fee_bps = int(totals.get("total_fee_bps", 0) or 0)

    protocol_version = str(wager.get("protocol_version") or "enumerated").strip().lower()
    body: dict[str, Any] = {
        "wager_address": wager_address,
        "collateral_token": collateral_token,
        "protocol_version": protocol_version,
        "amount": amount,
        "betting_open": betting_open,
        "execution_allowed": betting_open,
        "revert_hint": revert_hint,
    }

    if protocol_version == "enumerated":
        ticket_mask = int(1) << int(outcome_index)
        ticket_pools = data.get("ticket_pools") or []
        outcome_total = 0
        key = str(ticket_mask)
        for tp in ticket_pools:
            if str(tp.get("ticket_mask")) == key:
                outcome_total = int(tp.get("pool_total", 0) or 0)
                break
        calldata = _encode_call(
            "placeBet(uint256,uint256)",
            ["uint256", "uint256"],
            [ticket_mask, amount],
        )
        body["outcome_index"] = outcome_index
        body["ticket_mask"] = ticket_mask
    elif protocol_version == "freeform":
        ans = answer.strip()
        if not ans:
            raise ValueError(
                "freeform wagers require non-empty `answer` (same UTF-8 bytes as on-chain placeBet/resolve)."
            )
        aid = _freeform_answer_id_hex(ans)
        ticket_pools = data.get("ticket_pools") or []
        outcome_total = 0
        key = aid.lower()
        for tp in ticket_pools:
            if str(tp.get("ticket_mask")).lower() == key:
                outcome_total = int(tp.get("pool_total", 0) or 0)
                break
        calldata = _encode_call("placeBet(string,uint256)", ["string", "uint256"], [ans, amount])
        body["answer"] = ans
        body["answer_id"] = aid
    else:
        raise ValueError(
            f"Unsupported protocol_version {protocol_version!r}; expected 'enumerated' or 'freeform'."
        )

    odds = _compute_odds(
        total_pot=total_pot,
        outcome_total=outcome_total,
        total_fee_bps=total_fee_bps,
        bet_amount=amount,
    )
    body["odds"] = odds
    body["placeBet"] = {
        "to": wager_address,
        "calldata": calldata,
        "approval_required": {
            "token": collateral_token,
            "spender": wager_address,
            "amount": amount,
            "approve_calldata": _encode_erc20_approve(wager_address, amount),
        },
    }
    return json.dumps(body, indent=2)


@mcp_server.tool()
async def quote_place_bets(
    wager_address: str,
    outcome_indices: list[int],
    amounts: list[int],
    require_open: bool = False,
) -> str:
    """Quote odds + return placeBets calldata + approval instructions (enumerated only).

    outcome_indices/amounts are aligned arrays. All amounts are in raw token units.
    Freeform wagers have no batch helper — use quote_place_bet once per answer string.
    """
    import time

    if len(outcome_indices) != len(amounts):
        raise ValueError("outcome_indices and amounts length mismatch")
    if not amounts:
        raise ValueError("amounts must be non-empty")
    if any(a <= 0 for a in amounts):
        raise ValueError("all amounts must be > 0")

    data = await _indexer_get(f"/wagers/{wager_address}")
    wager = data.get("wager") or {}
    totals = data.get("totals") or {}

    if not wager:
        raise ValueError("Indexer returned no wager payload")

    now_ts = int(time.time())
    betting_open, revert_hint = _betting_open_status(wager, now_ts=now_ts)
    if require_open and not betting_open:
        raise ValueError(revert_hint or "wager betting is not open")

    protocol_version = str(wager.get("protocol_version") or "enumerated").strip().lower()
    if protocol_version != "enumerated":
        raise ValueError(
            "placeBets batch is only available on enumerated wagers; freeform has no batch helper."
        )

    collateral_token = str(wager.get("collateral_token") or "").strip()
    total_pot = int(totals.get("total_pot", 0) or 0)
    total_fee_bps = int(totals.get("total_fee_bps", 0) or 0)

    ticket_pools = data.get("ticket_pools") or []

    def _pool_for_mask(m: int) -> int:
        key = str(m)
        for tp in ticket_pools:
            if str(tp.get("ticket_mask")) == key:
                return int(tp.get("pool_total", 0) or 0)
        return 0

    ticket_masks = [int(1) << int(i) for i in outcome_indices]
    outcome_totals = [_pool_for_mask(m) for m in ticket_masks]
    odds = _compute_batch_odds(
        total_pot=total_pot,
        outcome_totals=outcome_totals,
        total_fee_bps=total_fee_bps,
        bet_amounts=amounts,
    )
    total_bet = sum(amounts)
    calldata = _encode_call(
        "placeBets(uint256[],uint256[])",
        ["uint256[]", "uint256[]"],
        [ticket_masks, amounts],
    )
    return json.dumps(
        {
            "wager_address": wager_address,
            "collateral_token": collateral_token,
            "protocol_version": protocol_version,
            "outcome_indices": outcome_indices,
            "ticket_masks": ticket_masks,
            "amounts": amounts,
            "betting_open": betting_open,
            "execution_allowed": betting_open,
            "revert_hint": revert_hint,
            "odds": odds,
            "placeBets": {
                "to": wager_address,
                "calldata": calldata,
                "approval_required": {
                    "token": collateral_token,
                    "spender": wager_address,
                    "amount": total_bet,
                    "approve_calldata": _encode_erc20_approve(wager_address, total_bet),
                },
            },
        },
        indent=2,
    )


# ── Transaction encoding tools ────────────────────────────────────


@mcp_server.tool()
async def encode_create_enumerated_wager(
    collateral_token: str,
    proposition: str,
    outcomes: list[str],
    payoff_policy: int,
    policy_param: int,
    betting_close_time: int = 0,
    resolution_window: int = 0,
    resolver: str = _ZERO_ADDRESS,
    betting_closer: str = _ZERO_ADDRESS,
    resolution_closer: str = _ZERO_ADDRESS,
    extra_fee_recipients: list[str] | None = None,
    extra_fee_bps: list[int] | None = None,
    seed_ticket_masks: list[int] | None = None,
    seed_amounts: list[int] | None = None,
) -> str:
    """Encode `ParamutuelFactoryV3.createEnumeratedWager` (bitmask tickets + payoff policies).

    `payoff_policy` is the uint8 enum value from `ParamutuelWagerV3.PayoffPolicy`
    (0=SINGLE_WINNER, 1=ANY_OF, 2=EXACT_SET, 3=AT_LEAST_K, 4=WEIGHTED_OVERLAP).
    For AT_LEAST_K set `policy_param=k`. Seeds use ticket bitmasks (not outcome indices).
    """
    if not FACTORY_ADDRESS:
        raise ValueError(
            "FACTORY_ADDRESS is not configured (env or config/deployments.json factoryAddress)"
        )

    fee_recipients = extra_fee_recipients or []
    fee_bps = extra_fee_bps or []
    masks = seed_ticket_masks or []
    samt = seed_amounts or []

    if masks or samt:
        sig = (
            "createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,"
            "address,address[],uint16[],uint256[],uint256[])"
        )
        types = [
            "address", "string", "string[]", "uint8", "uint256", "uint64", "uint64",
            "address", "address", "address", "address[]", "uint16[]", "uint256[]", "uint256[]",
        ]
        values = [
            collateral_token, proposition, outcomes, payoff_policy, policy_param,
            betting_close_time, resolution_window,
            resolver, betting_closer, resolution_closer,
            fee_recipients, fee_bps, masks, samt,
        ]
    else:
        sig = (
            "createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,"
            "address,address[],uint16[])"
        )
        types = [
            "address", "string", "string[]", "uint8", "uint256", "uint64", "uint64",
            "address", "address", "address", "address[]", "uint16[]",
        ]
        values = [
            collateral_token, proposition, outcomes, payoff_policy, policy_param,
            betting_close_time, resolution_window,
            resolver, betting_closer, resolution_closer,
            fee_recipients, fee_bps,
        ]

    calldata = _encode_call(sig, types, values)
    total_seed = sum(samt)
    result: dict[str, Any] = {
        "to": FACTORY_ADDRESS,
        "calldata": calldata,
        "description": f"Create enumerated wager: '{proposition}' ({len(outcomes)} outcomes, policy={payoff_policy})",
    }
    if total_seed > 0:
        result["approval_required"] = {
            "token": collateral_token,
            "spender": FACTORY_ADDRESS,
            "amount": total_seed,
            "approve_calldata": _encode_erc20_approve(FACTORY_ADDRESS, total_seed),
        }
    return json.dumps(result, indent=2)


@mcp_server.tool()
async def encode_create_freeform_wager(
    collateral_token: str,
    proposition: str,
    betting_close_time: int = 0,
    resolution_window: int = 0,
    resolver: str = _ZERO_ADDRESS,
    betting_closer: str = _ZERO_ADDRESS,
    resolution_closer: str = _ZERO_ADDRESS,
    extra_fee_recipients: list[str] | None = None,
    extra_fee_bps: list[int] | None = None,
) -> str:
    """Encode `ParamutuelFactoryV3.createFreeformWager` (domain-separated answer ids)."""
    if not FACTORY_ADDRESS:
        raise ValueError(
            "FACTORY_ADDRESS is not configured (env or config/deployments.json factoryAddress)"
        )
    fee_recipients = extra_fee_recipients or []
    fee_bps = extra_fee_bps or []
    sig = "createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[])"
    types = [
        "address", "string", "uint64", "uint64",
        "address", "address", "address", "address[]", "uint16[]",
    ]
    values = [
        collateral_token, proposition,
        betting_close_time, resolution_window,
        resolver, betting_closer, resolution_closer,
        fee_recipients, fee_bps,
    ]
    calldata = _encode_call(sig, types, values)
    return json.dumps(
        {
            "to": FACTORY_ADDRESS,
            "calldata": calldata,
            "description": f"Create freeform wager: '{proposition}'",
        },
        indent=2,
    )


@mcp_server.tool()
async def encode_place_bet(
    wager_address: str,
    collateral_token: str,
    outcome_index: int = 0,
    amount: int = 0,
    ticket_mask: int | None = None,
) -> str:
    """Encode `placeBet(uint256,uint256)` on an enumerated V3 wager.

    Pass `ticket_mask` directly for multi-outcome tickets; otherwise the helper
    builds `1 << outcome_index` (single-outcome ticket). The caller must first
    approve the wager to spend `amount` of the collateral token.
    """
    if amount <= 0:
        raise ValueError("amount must be > 0")
    mask = int(ticket_mask) if ticket_mask is not None else int(1) << int(outcome_index)
    calldata = _encode_call(
        "placeBet(uint256,uint256)",
        ["uint256", "uint256"],
        [mask, amount],
    )
    return json.dumps(
        {
            "to": wager_address,
            "calldata": calldata,
            "description": f"Place enumerated bet amount={amount} ticketMask={mask}",
            "approval_required": {
                "token": collateral_token,
                "spender": wager_address,
                "amount": amount,
                "approve_calldata": _encode_erc20_approve(wager_address, amount),
            },
        },
        indent=2,
    )


@mcp_server.tool()
async def encode_place_bet_freeform(
    wager_address: str,
    collateral_token: str,
    answer: str,
    amount: int,
) -> str:
    """Encode `placeBet(string,uint256)` on a freeform V3 wager.

    `answer` must match the resolver's `resolve(string)` bytes exactly to win
    (ticket id = keccak256(abi.encodePacked(bytes1(0x03), bytes(answer)))).
    """
    if amount <= 0:
        raise ValueError("amount must be > 0")
    calldata = _encode_call("placeBet(string,uint256)", ["string", "uint256"], [answer, amount])
    return json.dumps(
        {
            "to": wager_address,
            "calldata": calldata,
            "description": f"Place freeform bet amount={amount} (answer hashed on-chain with 0x03 domain byte)",
            "answer_id": _freeform_answer_id_hex(answer),
            "approval_required": {
                "token": collateral_token,
                "spender": wager_address,
                "amount": amount,
                "approve_calldata": _encode_erc20_approve(wager_address, amount),
            },
        },
        indent=2,
    )


@mcp_server.tool()
async def encode_place_bets(
    wager_address: str,
    collateral_token: str,
    amounts: list[int],
    outcome_indices: list[int] | None = None,
    ticket_masks: list[int] | None = None,
) -> str:
    """Encode batch `placeBets(uint256[],uint256[])` on an enumerated V3 wager.

    Pass either `ticket_masks` (exact) or `outcome_indices` (helper builds masks).
    Arrays must align with `amounts`.
    """
    if ticket_masks is not None:
        if len(ticket_masks) != len(amounts):
            raise ValueError("ticket_masks and amounts length mismatch")
        first_arr = ticket_masks
    else:
        if outcome_indices is None or len(outcome_indices) != len(amounts):
            raise ValueError("outcome_indices and amounts length mismatch")
        first_arr = [int(1) << int(i) for i in outcome_indices]
    total = sum(amounts)
    calldata = _encode_call(
        "placeBets(uint256[],uint256[])",
        ["uint256[]", "uint256[]"],
        [first_arr, amounts],
    )
    return json.dumps(
        {
            "to": wager_address,
            "calldata": calldata,
            "description": f"Batch enumerated bet on {len(first_arr)} legs, total {total}",
            "ticket_masks": first_arr,
            "approval_required": {
                "token": collateral_token,
                "spender": wager_address,
                "amount": total,
                "approve_calldata": _encode_erc20_approve(wager_address, total),
            },
        },
        indent=2,
    )


@mcp_server.tool()
async def encode_resolve(wager_address: str, winning_mask: int) -> str:
    """Encode `resolve(uint256)` on an enumerated V3 wager.

    `winning_mask` is the bitmask of winning outcomes; for a single winner use
    `1 << outcomeIndex`. Only the wager's resolver can submit this.
    """
    calldata = _encode_call("resolve(uint256)", ["uint256"], [winning_mask])
    return json.dumps(
        {
            "to": wager_address,
            "calldata": calldata,
            "description": f"Resolve enumerated wager (winningMask={winning_mask})",
        },
        indent=2,
    )


@mcp_server.tool()
async def encode_resolve_freeform(wager_address: str, winning_answer: str) -> str:
    """Encode `resolve(string)` on a freeform V3 wager.

    Ticket id = keccak256(abi.encodePacked(bytes1(0x03), bytes(winning_answer))).
    """
    calldata = _encode_call("resolve(string)", ["string"], [winning_answer])
    return json.dumps(
        {
            "to": wager_address,
            "calldata": calldata,
            "description": "Resolve freeform wager to exact winning answer string",
            "answer_id": _freeform_answer_id_hex(winning_answer),
        },
        indent=2,
    )


@mcp_server.tool()
async def encode_retract(wager_address: str) -> str:
    """Encode `retract()` on a V3 wager (resolver only; bettors refunded minus fees)."""
    calldata = _encode_call("retract()", [], [])
    return json.dumps(
        {"to": wager_address, "calldata": calldata, "description": "Retract wager"},
        indent=2,
    )


@mcp_server.tool()
async def encode_expire(wager_address: str) -> str:
    """Encode `expire()` on a V3 wager past its resolution deadline (anyone can call)."""
    calldata = _encode_call("expire()", [], [])
    return json.dumps(
        {"to": wager_address, "calldata": calldata, "description": "Expire wager"},
        indent=2,
    )


@mcp_server.tool()
async def encode_close_betting(wager_address: str) -> str:
    """Encode `closeBetting()` (bettingCloser only)."""
    calldata = _encode_call("closeBetting()", [], [])
    return json.dumps(
        {
            "to": wager_address,
            "calldata": calldata,
            "description": "Close betting (authority)",
        },
        indent=2,
    )


@mcp_server.tool()
async def encode_close_resolution_window(wager_address: str) -> str:
    """Encode `closeResolutionWindow()` (resolutionCloser only, after betting closed)."""
    calldata = _encode_call("closeResolutionWindow()", [], [])
    return json.dumps(
        {
            "to": wager_address,
            "calldata": calldata,
            "description": "Close resolution window (authority)",
        },
        indent=2,
    )


@mcp_server.tool()
async def encode_claim(wager_address: str) -> str:
    """Encode `claim()` (winners on resolved, bettors on retracted/expired)."""
    calldata = _encode_call("claim()", [], [])
    return json.dumps(
        {"to": wager_address, "calldata": calldata, "description": "Claim payout"},
        indent=2,
    )


@mcp_server.tool()
async def encode_withdraw_fees(wager_address: str) -> str:
    """Encode `withdrawFees()` (fee recipients only)."""
    calldata = _encode_call("withdrawFees()", [], [])
    return json.dumps(
        {
            "to": wager_address,
            "calldata": calldata,
            "description": "Withdraw accrued fees",
        },
        indent=2,
    )


# ── Entrypoint ────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp_server.run()
