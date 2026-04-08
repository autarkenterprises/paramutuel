"""Shared helpers for Base Sepolia live/stress integration tests (v1 + v2 factories)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
# Non-zero sentinel used in stress/minimal tests (not a real ERC-20; no funded transfers).
DUMMY_COLLATERAL = "0x0000000000000000000000000000000000000001"

# keccak256("WagerCreated(address,address,address,address,uint64,uint64,uint64,address,address)")
WAGER_CREATED_TOPIC_V1 = "0x1b9545daed972e7de65f9c8b3445fdfd1af0c41cdc5774595c37bc7e35f28def"

# keccak256("WagerCreatedV2(address,address,address,address,uint8,uint256,uint64,uint64,uint64,address,address)")
WAGER_CREATED_TOPIC_V2 = "0x7245d6cca974fb4447fd236c460f3aa281da5ffa682c9b5392e99c37bb3ca89a"

# ParamutuelWagerV2.PayoffPolicy enum order (must match Solidity)
PAYOFF_SINGLE_WINNER = 0
PAYOFF_ANY_OF = 1
PAYOFF_EXACT_SET = 2
PAYOFF_AT_LEAST_K = 3
PAYOFF_WEIGHTED_OVERLAP = 4

V2_CREATE_WAGER_SIG = (
    "createWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,address,address[],uint16[])"
)


def default_factory_v2_address() -> str:
    env = os.environ.get("FACTORY_V2_ADDRESS", "").strip()
    if env:
        return env
    config_path = Path(__file__).resolve().parents[2] / "config" / "deployments.json"
    if not config_path.exists():
        return ""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return str((data.get("baseSepolia") or {}).get("factoryV2Address") or "").strip()


def topic_to_address(topic_word: str) -> str:
    cleaned = topic_word.lower().replace("0x", "")
    return "0x" + cleaned[-40:]


def extract_wager_address_from_receipt(
    receipt_payload: dict,
    factory_address: str,
    created_topic0: str,
) -> str:
    """Return new wager address from factory log matching topic0 (v1 or v2 WagerCreated)."""
    fac = factory_address.lower()
    t0 = created_topic0.lower()
    for log in receipt_payload.get("logs", []):
        if str(log.get("address", "")).lower() != fac:
            continue
        topics = log.get("topics") or []
        if len(topics) < 2:
            continue
        if str(topics[0]).lower() != t0:
            continue
        return topic_to_address(str(topics[1]))
    raise AssertionError(
        f"Factory create event (topic {created_topic0[:12]}…) not found in receipt logs"
    )


@dataclass(frozen=True)
class V2FundedResolveCase:
    """One funded v2 scenario: create → bet on ticket_masks → resolve(winning_mask) → claim."""

    case_id: str
    payoff_policy: int
    policy_param: int
    outcomes_json: str
    ticket_masks: tuple[int, ...]
    winning_mask: int
    use_place_bets: bool = False


# Full matrix of payoff policies with concrete tickets / winning sets (ADR-0008 semantics).
V2_FUNDED_RESOLVE_CASES: tuple[V2FundedResolveCase, ...] = (
    V2FundedResolveCase(
        case_id="single_winner",
        payoff_policy=PAYOFF_SINGLE_WINNER,
        policy_param=0,
        outcomes_json='["Y","N"]',
        ticket_masks=(1,),  # outcome 0 only
        winning_mask=1,
    ),
    V2FundedResolveCase(
        case_id="any_of",
        payoff_policy=PAYOFF_ANY_OF,
        policy_param=0,
        outcomes_json='["Y","N"]',
        ticket_masks=(1, 2),  # stake on each single-outcome ticket
        winning_mask=3,  # both outcomes in winning set → both tickets overlap
        use_place_bets=True,
    ),
    V2FundedResolveCase(
        case_id="exact_set",
        payoff_policy=PAYOFF_EXACT_SET,
        policy_param=0,
        outcomes_json='["Y","N"]',
        ticket_masks=(3,),  # ticket must match full set {0,1}
        winning_mask=3,
    ),
    V2FundedResolveCase(
        case_id="at_least_k",
        payoff_policy=PAYOFF_AT_LEAST_K,
        policy_param=2,
        outcomes_json='["A","B","C"]',
        ticket_masks=(3,),  # mask 0b011 — two bits set
        winning_mask=3,  # overlap has popcount 2 >= k=2
    ),
    V2FundedResolveCase(
        case_id="weighted_overlap",
        payoff_policy=PAYOFF_WEIGHTED_OVERLAP,
        policy_param=0,
        outcomes_json='["Y","N"]',
        ticket_masks=(1, 2),
        winning_mask=3,
        use_place_bets=True,
    ),
)

# Minimal-tx (no ERC-20) v2: authority-close then expire — one row per policy (dummy collateral).
V2_MINIMAL_EXPIRE_POLICIES: tuple[tuple[int, int, str], ...] = (
    (PAYOFF_SINGLE_WINNER, 0, '["A","B"]'),
    (PAYOFF_ANY_OF, 0, '["A","B"]'),
    (PAYOFF_EXACT_SET, 0, '["A","B"]'),
    (PAYOFF_AT_LEAST_K, 2, '["A","B","C"]'),
    (PAYOFF_WEIGHTED_OVERLAP, 0, '["A","B"]'),
)
