"""Shared helpers for Base Sepolia live/stress integration tests (ADR-0010 V3 factory)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# Circle USDC on Base Sepolia — default `TESTNET_COLLATERAL_TOKEN` for live funded tests when unset.
DEFAULT_COLLATERAL_TOKEN_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
# Non-zero sentinel used in stress/minimal tests (not a real ERC-20; no funded transfers).
DUMMY_COLLATERAL = "0x0000000000000000000000000000000000000001"

# keccak256 of ParamutuelFactoryV3 event signatures (see src/ParamutuelFactoryV3.sol).
WAGER_CREATED_TOPIC_V3_ENUMERATED = (
    "0xff766b6fc8dd2e2b1c7be675a874f160c4cada5bf32dac8b1b2e0d6ae7bdb0da"
)
WAGER_CREATED_TOPIC_V3_FREEFORM = (
    "0xf59da875d5b5de3b09728f042bebc2a20357ee08ca31bbaf584efd9cb0ec4c53"
)

# ParamutuelWagerV3.PayoffPolicy enum order (must match Solidity)
PAYOFF_SINGLE_WINNER = 0
PAYOFF_ANY_OF = 1
PAYOFF_EXACT_SET = 2
PAYOFF_AT_LEAST_K = 3
PAYOFF_WEIGHTED_OVERLAP = 4

# ADR-0010 V3 factory: unified `createEnumeratedWager` with appended seed arrays
# (uint256[] seedTicketMasks, uint256[] seedAmounts). Callers always send the
# long form; pass `[]` `[]` for no seeds.
V3_ENUMERATED_CREATE_WAGER_SIG = (
    "createEnumeratedWager("
    "address,string,string[],uint8,uint256,uint64,uint64,"
    "address,address,address,address[],uint16[],uint256[],uint256[]"
    ")"
)

V3_FREEFORM_CREATE_WAGER_SIG = (
    "createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[])"
)


def default_factory_address() -> str:
    """Return the V3 factory address from env `FACTORY_ADDRESS` or config/deployments.json baseSepolia.factoryAddress."""
    env = os.environ.get("FACTORY_ADDRESS", "").strip()
    if env:
        return env
    config_path = Path(__file__).resolve().parents[2] / "config" / "deployments.json"
    if not config_path.exists():
        return ""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return str((data.get("baseSepolia") or {}).get("factoryAddress") or "").strip()


def topic_to_address(topic_word: str) -> str:
    cleaned = topic_word.lower().replace("0x", "")
    return "0x" + cleaned[-40:]


def extract_wager_address_from_receipt(
    receipt_payload: dict,
    factory_address: str,
    created_topic0: str,
) -> str:
    """Return new wager address from factory log matching topic0 (V3 enumerated or freeform WagerCreated)."""
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
class V3FundedResolveCase:
    """One funded V3 enumerated scenario: create → bet on ticket_masks → resolve(winning_mask) → claim."""

    case_id: str
    payoff_policy: int
    policy_param: int
    outcomes_json: str
    ticket_masks: tuple[int, ...]
    winning_mask: int
    use_place_bets: bool = False


# Full matrix of payoff policies with concrete tickets / winning sets (ADR-0008 semantics, V3 shapes).
V3_FUNDED_RESOLVE_CASES: tuple[V3FundedResolveCase, ...] = (
    V3FundedResolveCase(
        case_id="single_winner",
        payoff_policy=PAYOFF_SINGLE_WINNER,
        policy_param=0,
        outcomes_json='["Y","N"]',
        ticket_masks=(1,),  # outcome 0 only
        winning_mask=1,
    ),
    V3FundedResolveCase(
        case_id="any_of",
        payoff_policy=PAYOFF_ANY_OF,
        policy_param=0,
        outcomes_json='["Y","N"]',
        ticket_masks=(1, 2),  # stake on each single-outcome ticket
        winning_mask=3,  # both outcomes in winning set → both tickets overlap
        use_place_bets=True,
    ),
    V3FundedResolveCase(
        case_id="exact_set",
        payoff_policy=PAYOFF_EXACT_SET,
        policy_param=0,
        outcomes_json='["Y","N"]',
        ticket_masks=(3,),  # ticket must match full set {0,1}
        winning_mask=3,
    ),
    V3FundedResolveCase(
        case_id="at_least_k",
        payoff_policy=PAYOFF_AT_LEAST_K,
        policy_param=2,
        outcomes_json='["A","B","C"]',
        ticket_masks=(3,),  # mask 0b011 — two bits set
        winning_mask=3,  # overlap has popcount 2 >= k=2
    ),
    V3FundedResolveCase(
        case_id="weighted_overlap",
        payoff_policy=PAYOFF_WEIGHTED_OVERLAP,
        policy_param=0,
        outcomes_json='["Y","N"]',
        ticket_masks=(1, 2),
        winning_mask=3,
        use_place_bets=True,
    ),
)

# Minimal-tx (no ERC-20) V3: authority-close then expire — one row per policy (dummy collateral).
V3_MINIMAL_EXPIRE_POLICIES: tuple[tuple[int, int, str], ...] = (
    (PAYOFF_SINGLE_WINNER, 0, '["A","B"]'),
    (PAYOFF_ANY_OF, 0, '["A","B"]'),
    (PAYOFF_EXACT_SET, 0, '["A","B"]'),
    (PAYOFF_AT_LEAST_K, 2, '["A","B","C"]'),
    (PAYOFF_WEIGHTED_OVERLAP, 0, '["A","B"]'),
)
