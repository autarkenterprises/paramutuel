#!/usr/bin/env python3
"""Paramutuel Protocol MCP Server.

Exposes on-chain parimutuel wager operations to LLM agents via the
Model Context Protocol.  Read operations hit the indexer HTTP API;
write helpers return ABI-encoded calldata (no private keys needed).

Usage:
    # stdio transport (default for MCP clients)
    python -m mcp_server

    # or with explicit config
    INDEXER_URL=https://paramutuel-git-406244230167.europe-west1.run.app \
    FACTORY_ADDRESS=0x655f6c5a3dc4cb3bf68173952bca9dac1bb5bf39 \
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
)

FACTORY_V2_ADDRESS = os.environ.get(
    "FACTORY_V2_ADDRESS",
    _network_cfg.get("factoryV2Address", ""),
).strip()

FACTORY_FREEFORM_ADDRESS = os.environ.get(
    "FACTORY_FREEFORM_ADDRESS",
    _network_cfg.get("factoryFreeformAddress", ""),
).strip()

CHAIN_ID = int(os.environ.get("CHAIN_ID", _network_cfg.get("chainId", 84532)))

# ── ABI loading ────────────────────────────────────────────────────

_PACKAGE_ABI_DIR = Path(__file__).resolve().parent / "abi"
_REPO_ABI_DIR = _ROOT / "dapp" / "abi"


def _load_abi(name: str) -> list[dict]:
    # 1) Bundled with pip package
    path = _PACKAGE_ABI_DIR / f"{name}.json"
    if not path.exists():
        # 2) Repo-relative committed ABIs
        path = _REPO_ABI_DIR / f"{name}.json"
    if not path.exists():
        # 3) Foundry build output
        path = _ROOT / "out" / f"{name}.sol" / f"{name}.json"
    data = json.loads(path.read_text())
    return data["abi"]


def _load_abi_optional(name: str) -> list[dict]:
    try:
        return _load_abi(name)
    except (OSError, json.JSONDecodeError, KeyError):
        return []


FACTORY_ABI = _load_abi("ParamutuelFactory")
WAGER_ABI = _load_abi("ParamutuelWager")
FACTORY_V2_ABI = _load_abi_optional("ParamutuelFactoryV2")
WAGER_V2_ABI = _load_abi_optional("ParamutuelWagerV2")
FACTORY_FREEFORM_ABI = _load_abi_optional("ParamutuelFactoryFreeform")
WAGER_FREEFORM_ABI = _load_abi_optional("ParamutuelWagerFreeform")

# ── ABI encoding helpers ───────────────────────────────────────────

from eth_abi import encode as abi_encode  # noqa: E402
from eth_hash.auto import keccak as _keccak256  # noqa: E402

_ZERO_ADDRESS = "0x" + "00" * 20


def _selector(sig: str) -> bytes:
    """Compute 4-byte Keccak-256 function selector from a canonical signature."""
    return _keccak256(sig.encode())[:4]


def _encode_call(sig: str, types: list[str], values: list) -> str:
    """Return 0x-prefixed hex calldata for a function call."""
    sel = _selector(sig)
    if types:
        encoded = abi_encode(types, values)
    else:
        encoded = b""
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
    """Compute pre- and post-bet implied odds and expected payout."""
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
    """Compute odds for a multi-outcome batch bet.

    In a single tx, the net pot after fees depends on the *sum* of all bet
    amounts. This differs from per-leg single-bet math.
    """
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


def _is_betting_open(wager_row: dict[str, Any], now_ts: int) -> bool:
    """Best-effort client-side betting-open check (avoid obvious reverts)."""
    return _betting_open_status(wager_row, now_ts=now_ts)[0]


def _betting_open_status(wager_row: dict[str, Any], now_ts: int) -> tuple[bool, str]:
    """Return (is_open, revert_hint) using indexer fields.

    This is a best-effort client-side check: between quote-time and tx
    submission, state can change. The caller should still handle reverts.
    """
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
    """GET request to the indexer API."""
    url = INDEXER_URL + path
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


# ── MCP Server ────────────────────────────────────────────────────

mcp_server = FastMCP(
    "paramutuel",
    instructions=(
        "Paramutuel Protocol: on-chain parimutuel betting wagers on Base. "
        "Use these tools to discover wagers, analyze odds, and prepare "
        "transactions for wager creation, betting, resolution, and claims. "
        "Write tools return ABI-encoded calldata — the caller must sign and "
        "submit the transaction."
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
    """Get full details for a specific wager including totals, outcomes, and event history.

    Args:
        wager_address: The wager contract address (0x...).
    """
    data = await _indexer_get(f"/wagers/{wager_address}")
    return json.dumps(data, indent=2)


@mcp_server.tool()
async def get_expire_candidates() -> str:
    """Find wagers that are past their resolution deadline and can be expired by anyone.

    Returns wagers where expire() can be called to unlock refunds.
    """
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
    factory_functions = [
        e["name"]
        for e in FACTORY_ABI
        if e.get("type") == "function"
    ]
    wager_functions = [
        e["name"]
        for e in WAGER_ABI
        if e.get("type") == "function"
    ]
    factory_v2_functions = (
        sorted(
            {
                e["name"]
                for e in FACTORY_V2_ABI
                if e.get("type") == "function"
            }
        )
        if FACTORY_V2_ABI
        else []
    )
    wager_v2_functions = (
        sorted(
            {
                e["name"]
                for e in WAGER_V2_ABI
                if e.get("type") == "function"
            }
        )
        if WAGER_V2_ABI
        else []
    )
    factory_freeform_functions = (
        sorted({e["name"] for e in FACTORY_FREEFORM_ABI if e.get("type") == "function"})
        if FACTORY_FREEFORM_ABI
        else []
    )
    wager_freeform_functions = (
        sorted({e["name"] for e in WAGER_FREEFORM_ABI if e.get("type") == "function"})
        if WAGER_FREEFORM_ABI
        else []
    )
    return json.dumps(
        {
            "factory_address": FACTORY_ADDRESS,
            "factory_v2_address": FACTORY_V2_ADDRESS or None,
            "factory_freeform_address": FACTORY_FREEFORM_ADDRESS or None,
            "chain_id": CHAIN_ID,
            "indexer_url": INDEXER_URL,
            "factory_functions": sorted(set(factory_functions)),
            "wager_functions": sorted(set(wager_functions)),
            "factory_v2_functions": factory_v2_functions,
            "wager_v2_functions": wager_v2_functions,
            "factory_freeform_functions": factory_freeform_functions,
            "wager_freeform_functions": wager_freeform_functions,
            "constants": {
                "BPS_DENOMINATOR": 10_000,
                "MAX_TOTAL_FEE_BPS": 10_000,
                "MAX_OUTCOMES": 255,
                "FREEFORM_MAX_ANSWER_BYTES": 1024,
                "FREEFORM_MAX_DISTINCT_ANSWERS_CAP": 1024,
            },
            "notes": {
                "v2_wagers": (
                    "Indexer marks protocol_version=v2. placeBet first uint256 is ticketMask "
                    "(single-outcome legs use 1<<outcomeIndex). resolve(uint256) passes winningMask."
                ),
                "freeform_wagers": (
                    "ADR-0009: no enumerated outcomes. placeBet(string,uint256) and resolve(string) "
                    "use identical UTF-8 bytes for ticket id keccak256(bytes(answer)). "
                    "Indexer protocol_version=freeform."
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

    All amounts are in raw token units (e.g. for USDC with 6 decimals,
    1 USDC = 1000000). Read total_pot, outcome_total (outcomeTotals[i]),
    and total_fee_bps from the wager contract or indexer.

    Args:
        total_pot: Current total pot in raw token units.
        outcome_total: Current total wagered on the target outcome.
        total_fee_bps: Wager's total fee in basis points.
        bet_amount: Hypothetical bet amount in raw token units.
    """
    result = _compute_odds(total_pot, outcome_total, total_fee_bps, bet_amount)
    return json.dumps(result, indent=2)


@mcp_server.tool()
async def quote_place_bet(
    wager_address: str,
    outcome_index: int,
    amount: int,
    require_open: bool = False,
) -> str:
    """Quote odds + return placeBet calldata + approval instructions.

    All amounts are in raw token units.
    """
    import time

    if amount <= 0:
        raise ValueError("amount must be > 0")

    data = await _indexer_get(f"/wagers/{wager_address}")
    wager = data.get("wager") or {}
    totals = data.get("totals") or {}
    outcomes = data.get("outcomes") or []

    if not wager:
        raise ValueError("Indexer returned no wager payload")

    now_ts = int(time.time())
    betting_open, revert_hint = _betting_open_status(wager, now_ts=now_ts)
    if require_open and not betting_open:
        raise ValueError(revert_hint or "wager betting is not open")

    collateral_token = str(wager.get("collateral_token") or "").strip()
    total_pot = int(totals.get("total_pot", 0) or 0)
    total_fee_bps = int(totals.get("total_fee_bps", 0) or 0)

    protocol_version = str(wager.get("protocol_version") or "v1").strip().lower()
    ticket_mask: int | None = None
    first_arg: int
    outcome_total: int | None = None

    if protocol_version == "v2":
        ticket_mask = int(1) << int(outcome_index)
        first_arg = ticket_mask
        ticket_pools = data.get("ticket_pools") or []
        key = str(ticket_mask)
        for tp in ticket_pools:
            if str(tp.get("ticket_mask")) == key:
                outcome_total = int(tp.get("pool_total", 0) or 0)
                break
        if outcome_total is None:
            outcome_total = 0
    else:
        first_arg = int(outcome_index)
        for o in outcomes:
            if int(o.get("outcome_index")) == int(outcome_index):
                outcome_total = int(o.get("outcome_total", 0) or 0)
                break
        if outcome_total is None:
            raise ValueError(f"Outcome index {outcome_index} not found in this wager.")

    odds = _compute_odds(
        total_pot=total_pot,
        outcome_total=outcome_total,
        total_fee_bps=total_fee_bps,
        bet_amount=amount,
    )

    calldata = _encode_call(
        "placeBet(uint256,uint256)",
        ["uint256", "uint256"],
        [first_arg, amount],
    )

    body: dict[str, Any] = {
        "wager_address": wager_address,
        "collateral_token": collateral_token,
        "protocol_version": protocol_version,
        "outcome_index": outcome_index,
        "amount": amount,
        "betting_open": betting_open,
        "execution_allowed": betting_open,
        "revert_hint": revert_hint,
        "odds": odds,
        "placeBet": {
            "to": wager_address,
            "calldata": calldata,
            "approval_required": {
                "token": collateral_token,
                "spender": wager_address,
                "amount": amount,
                "approve_calldata": _encode_erc20_approve(wager_address, amount),
            },
        },
    }
    if ticket_mask is not None:
        body["ticket_mask"] = ticket_mask
    return json.dumps(body, indent=2)


@mcp_server.tool()
async def quote_place_bets(
    wager_address: str,
    outcome_indices: list[int],
    amounts: list[int],
    require_open: bool = False,
) -> str:
    """Quote odds + return placeBets calldata + approval instructions.

    outcome_indices/amounts are aligned arrays. All amounts are in raw token units.
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
    outcomes = data.get("outcomes") or []

    if not wager:
        raise ValueError("Indexer returned no wager payload")

    now_ts = int(time.time())
    betting_open, revert_hint = _betting_open_status(wager, now_ts=now_ts)
    if require_open and not betting_open:
        raise ValueError(revert_hint or "wager betting is not open")

    collateral_token = str(wager.get("collateral_token") or "").strip()

    total_pot = int(totals.get("total_pot", 0) or 0)
    total_fee_bps = int(totals.get("total_fee_bps", 0) or 0)

    protocol_version = str(wager.get("protocol_version") or "v1").strip().lower()

    if protocol_version == "v2":
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

    totals_by_outcome: dict[int, int] = {}
    for o in outcomes:
        idx = int(o.get("outcome_index"))
        totals_by_outcome[idx] = int(o.get("outcome_total", 0) or 0)

    outcome_totals: list[int] = []
    for idx in outcome_indices:
        if idx not in totals_by_outcome:
            raise ValueError(f"Outcome index {idx} not found in this wager.")
        outcome_totals.append(totals_by_outcome[idx])

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
        [outcome_indices, amounts],
    )

    return json.dumps(
        {
            "wager_address": wager_address,
            "collateral_token": collateral_token,
            "protocol_version": protocol_version,
            "outcome_indices": outcome_indices,
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
async def encode_create_wager(
    collateral_token: str,
    proposition: str,
    outcomes: list[str],
    betting_close_time: int = 0,
    resolution_window: int = 0,
    resolver: str = _ZERO_ADDRESS,
    betting_closer: str = _ZERO_ADDRESS,
    resolution_closer: str = _ZERO_ADDRESS,
    extra_fee_recipients: list[str] | None = None,
    extra_fee_bps: list[int] | None = None,
    seed_outcome_indices: list[int] | None = None,
    seed_amounts: list[int] | None = None,
) -> str:
    """Encode calldata for creating a new parimutuel wager.

    Returns the ABI-encoded calldata to send to the factory contract.
    If seed arrays are provided, uses the seeded overload. The caller
    must approve the factory for the total seed amount first.

    Args:
        collateral_token: ERC-20 token address for bets.
        proposition: Human-readable wager proposition.
        outcomes: List of outcome labels (minimum 2, max 255).
        betting_close_time: Absolute unix timestamp for betting close (0 = no time cap, requires betting_closer).
        resolution_window: Seconds after betting close for resolver to act (0 = no time cap, requires resolution_closer).
        resolver: Resolver address (0x0 = proposer resolves).
        betting_closer: Address that can close betting early (0x0 = disabled).
        resolution_closer: Address that can close resolution window early (0x0 = disabled).
        extra_fee_recipients: Additional fee recipient addresses.
        extra_fee_bps: Fee basis points for each extra recipient.
        seed_outcome_indices: Outcome indices for initial seed bets.
        seed_amounts: Raw token amounts for each seed bet.
    """
    fee_recipients = extra_fee_recipients or []
    fee_bps = extra_fee_bps or []
    seeds_idx = seed_outcome_indices or []
    seeds_amt = seed_amounts or []

    if seeds_idx or seeds_amt:
        sig = "createWager(address,string,string[],uint64,uint64,address,address,address,address[],uint16[],uint256[],uint256[])"
        types = [
            "address", "string", "string[]", "uint64", "uint64",
            "address", "address", "address",
            "address[]", "uint16[]", "uint256[]", "uint256[]",
        ]
        values = [
            collateral_token, proposition, outcomes,
            betting_close_time, resolution_window,
            resolver, betting_closer, resolution_closer,
            fee_recipients, fee_bps, seeds_idx, seeds_amt,
        ]
    else:
        sig = "createWager(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])"
        types = [
            "address", "string", "string[]", "uint64", "uint64",
            "address", "address", "address",
            "address[]", "uint16[]",
        ]
        values = [
            collateral_token, proposition, outcomes,
            betting_close_time, resolution_window,
            resolver, betting_closer, resolution_closer,
            fee_recipients, fee_bps,
        ]

    calldata = _encode_call(sig, types, values)
    total_seed = sum(seeds_amt)

    result: dict[str, Any] = {
        "to": FACTORY_ADDRESS,
        "calldata": calldata,
        "description": f"Create wager: '{proposition}' with {len(outcomes)} outcomes",
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
async def encode_create_wager_v2(
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
    """Encode calldata for ParamutuelFactoryV2.createWager (ADR-0008 v2).

    `payoff_policy` is the uint8 enum value from `ParamutuelWagerV2.PayoffPolicy`
    (0=SINGLE_WINNER, 1=ANY_OF, 2=EXACT_SET, 3=AT_LEAST_K, 4=WEIGHTED_OVERLAP).
    For AT_LEAST_K, set `policy_param` to k. Seeds use ticket bitmasks (not outcome indices).
    """
    if not FACTORY_V2_ADDRESS:
        raise ValueError(
            "FACTORY_V2_ADDRESS is not configured (env or config/deployments.json factoryV2Address)"
        )

    fee_recipients = extra_fee_recipients or []
    fee_bps = extra_fee_bps or []
    masks = seed_ticket_masks or []
    samt = seed_amounts or []

    if masks or samt:
        sig = (
            "createWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,"
            "address,address[],uint16[],uint256[],uint256[])"
        )
        types = [
            "address",
            "string",
            "string[]",
            "uint8",
            "uint256",
            "uint64",
            "uint64",
            "address",
            "address",
            "address",
            "address[]",
            "uint16[]",
            "uint256[]",
            "uint256[]",
        ]
        values = [
            collateral_token,
            proposition,
            outcomes,
            payoff_policy,
            policy_param,
            betting_close_time,
            resolution_window,
            resolver,
            betting_closer,
            resolution_closer,
            fee_recipients,
            fee_bps,
            masks,
            samt,
        ]
    else:
        sig = (
            "createWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,"
            "address,address[],uint16[])"
        )
        types = [
            "address",
            "string",
            "string[]",
            "uint8",
            "uint256",
            "uint64",
            "uint64",
            "address",
            "address",
            "address",
            "address[]",
            "uint16[]",
        ]
        values = [
            collateral_token,
            proposition,
            outcomes,
            payoff_policy,
            policy_param,
            betting_close_time,
            resolution_window,
            resolver,
            betting_closer,
            resolution_closer,
            fee_recipients,
            fee_bps,
        ]

    calldata = _encode_call(sig, types, values)
    total_seed = sum(samt)
    result: dict[str, Any] = {
        "to": FACTORY_V2_ADDRESS,
        "calldata": calldata,
        "description": f"Create v2 wager: '{proposition}' ({len(outcomes)} outcomes, policy={payoff_policy})",
    }
    if total_seed > 0:
        result["approval_required"] = {
            "token": collateral_token,
            "spender": FACTORY_V2_ADDRESS,
            "amount": total_seed,
            "approve_calldata": _encode_erc20_approve(FACTORY_V2_ADDRESS, total_seed),
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
    """Encode `ParamutuelFactoryFreeform.createFreeformWager` (ADR-0009).

    No outcome list: bettors supply text answers per `placeBet(string,uint256)` on the deployed wager.
    """
    if not FACTORY_FREEFORM_ADDRESS:
        raise ValueError(
            "FACTORY_FREEFORM_ADDRESS is not configured (env or config/deployments.json factoryFreeformAddress)"
        )
    fee_recipients = extra_fee_recipients or []
    fee_bps = extra_fee_bps or []
    sig = "createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[])"
    types = [
        "address",
        "string",
        "uint64",
        "uint64",
        "address",
        "address",
        "address",
        "address[]",
        "uint16[]",
    ]
    values = [
        collateral_token,
        proposition,
        betting_close_time,
        resolution_window,
        resolver,
        betting_closer,
        resolution_closer,
        fee_recipients,
        fee_bps,
    ]
    calldata = _encode_call(sig, types, values)
    return json.dumps(
        {
            "to": FACTORY_FREEFORM_ADDRESS,
            "calldata": calldata,
            "description": f"Create freeform wager: '{proposition}'",
        },
        indent=2,
    )


@mcp_server.tool()
async def encode_place_bet(
    wager_address: str,
    collateral_token: str,
    outcome_index: int,
    amount: int,
    ticket_mask: int | None = None,
) -> str:
    """Encode calldata for placing a single bet on a wager outcome.

    The caller must first approve the wager to spend the collateral token.

    Args:
        wager_address: The wager contract address.
        collateral_token: The ERC-20 collateral token address.
        outcome_index: v1: first `placeBet` uint256 (outcome index). Ignored when `ticket_mask` set.
        amount: Bet amount in raw token units.
        ticket_mask: v2: explicit ticket bitmask for first `placeBet` uint256. When omitted, uses `outcome_index`.
    """
    first_u256 = int(ticket_mask) if ticket_mask is not None else int(outcome_index)
    calldata = _encode_call(
        "placeBet(uint256,uint256)",
        ["uint256", "uint256"],
        [first_u256, amount],
    )
    return json.dumps(
        {
            "to": wager_address,
            "calldata": calldata,
            "description": f"Bet {amount} (first uint256={first_u256})",
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
    """Encode `ParamutuelWagerFreeform.placeBet(string,uint256)`.

    `answer` must match resolver `resolve(string)` bytes exactly to win (keccak256(bytes(answer)) ticket id).
    """
    calldata = _encode_call("placeBet(string,uint256)", ["string", "uint256"], [answer, amount])
    return json.dumps(
        {
            "to": wager_address,
            "calldata": calldata,
            "description": f"Freeform bet amount={amount} (answer bytes hashed on-chain)",
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
    outcome_indices: list[int],
    amounts: list[int],
    ticket_masks: list[int] | None = None,
) -> str:
    """Encode calldata for placing multiple bets across outcomes in one transaction.

    Args:
        wager_address: The wager contract address.
        collateral_token: The ERC-20 collateral token address.
        outcome_indices: v1: outcome indices used as first array. Ignored when `ticket_masks` is set.
        amounts: List of bet amounts in raw token units (aligned with the first uint256[]).
        ticket_masks: v2: explicit ticket bitmasks array (same length as `amounts`).
    """
    if ticket_masks is not None:
        if len(ticket_masks) != len(amounts):
            raise ValueError("ticket_masks and amounts length mismatch")
        first_arr = ticket_masks
    else:
        if len(outcome_indices) != len(amounts):
            raise ValueError("outcome_indices and amounts length mismatch")
        first_arr = outcome_indices
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
            "description": f"Batch bet on {len(first_arr)} legs, total {total}",
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
async def encode_resolve(wager_address: str, winning_outcome_index: int) -> str:
    """Encode calldata for resolving a wager to a winning outcome.

    Only the wager's resolver can submit this transaction.

    Args:
        wager_address: The wager contract address.
        winning_outcome_index: v1: winning outcome index. v2: winningMask (bitmask);
            for a single winner use 1 << outcomeIndex.
    """
    calldata = _encode_call(
        "resolve(uint256)", ["uint256"], [winning_outcome_index]
    )
    return json.dumps(
        {
            "to": wager_address,
            "calldata": calldata,
            "description": f"Resolve wager to outcome {winning_outcome_index}",
        },
        indent=2,
    )


@mcp_server.tool()
async def encode_resolve_freeform(wager_address: str, winning_answer: str) -> str:
    """Encode `ParamutuelWagerFreeform.resolve(string)`.

    Reverts on-chain if no stake on `keccak256(bytes(winning_answer))`.
    """
    calldata = _encode_call("resolve(string)", ["string"], [winning_answer])
    return json.dumps(
        {
            "to": wager_address,
            "calldata": calldata,
            "description": "Resolve freeform wager to exact winning answer string",
        },
        indent=2,
    )


@mcp_server.tool()
async def encode_retract(wager_address: str) -> str:
    """Encode calldata for retracting (invalidating) a wager.

    Only the wager's resolver can submit this. Bettors get refunds minus fees.

    Args:
        wager_address: The wager contract address.
    """
    calldata = _encode_call("retract()", [], [])
    return json.dumps(
        {"to": wager_address, "calldata": calldata, "description": "Retract wager"},
        indent=2,
    )


@mcp_server.tool()
async def encode_expire(wager_address: str) -> str:
    """Encode calldata for expiring a wager past its resolution deadline.

    Anyone can submit this transaction. Moves wager to Retracted state.

    Args:
        wager_address: The wager contract address.
    """
    calldata = _encode_call("expire()", [], [])
    return json.dumps(
        {"to": wager_address, "calldata": calldata, "description": "Expire wager"},
        indent=2,
    )


@mcp_server.tool()
async def encode_close_betting(wager_address: str) -> str:
    """Encode calldata for closing the betting window early.

    Only the wager's bettingCloser can submit this.

    Args:
        wager_address: The wager contract address.
    """
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
    """Encode calldata for closing the resolution window early.

    Only the wager's resolutionCloser can submit this, and only after
    betting is closed.

    Args:
        wager_address: The wager contract address.
    """
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
    """Encode calldata for claiming payout or refund after wager finalization.

    For resolved wagers: winners get pro-rata payout from net pot.
    For retracted/expired wagers: all bettors get pro-rata refund minus fees.

    Args:
        wager_address: The wager contract address.
    """
    calldata = _encode_call("claim()", [], [])
    return json.dumps(
        {"to": wager_address, "calldata": calldata, "description": "Claim payout"},
        indent=2,
    )


@mcp_server.tool()
async def encode_withdraw_fees(wager_address: str) -> str:
    """Encode calldata for withdrawing accrued fee balance.

    Only addresses listed as fee recipients can withdraw.

    Args:
        wager_address: The wager contract address.
    """
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
