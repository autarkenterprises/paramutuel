"""Control panel — calldata builders for V3 wager-lifecycle actions.

Pure functions over operator inputs that produce ``cast send`` argument
lists. Centralising the encoders here means the proposition service
(which dispatches its own create commands) and the control-panel CLI /
web shell agree byte-for-byte on calldata; encoding drift between the
two would silently mint differently-encoded wagers.

V3 protocol surface assumptions baked in:

- Two factory entry points: ``createEnumeratedWager`` (12-arg or 14-arg
  with seed bets) and ``createFreeformWager``.
- Lifecycle actions are scoped to a wager address: ``closeBetting``,
  ``resolve``, ``retract``, ``expire``, ``withdrawFees``. The encoders
  produce the function selector + ABI-packed args; the CLI handles the
  ``--rpc-url`` / ``--private-key`` / ``--allow-execute`` plumbing.

Address handling uses the EIP-55 checksum form except where the protocol
explicitly accepts ``0x0`` to mean "default to proposer" (resolver,
betting closer, resolution closer).
"""
from __future__ import annotations

import json
import shlex
from dataclasses import dataclass

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


@dataclass
class CastCommand:
    command: list[str]

    def shell(self) -> str:
        return " ".join(shlex.quote(x) for x in self.command)


def _json_arg(items: list[str] | list[int]) -> str:
    return json.dumps(items, separators=(",", ":"))


# ADR-0010 unified V3 factory signatures.
#
# `createEnumeratedWager` has two overloads: the shorter one with no seed
# arrays, and a longer one that appends `(uint256[] seedTicketMasks,
# uint256[] seedAmounts)`. The control panel always emits the long form —
# when the caller provides no seeds it simply passes empty arrays, which
# the factory treats as "no seeds" without altering semantics.
ENUMERATED_CREATE_SIG_WITH_SEEDS = (
    "createEnumeratedWager("
    "address,string,string[],uint8,uint256,uint64,uint64,"
    "address,address,address,address[],uint16[],uint256[],uint256[]"
    ")"
)


def build_create_wager_command(
    *,
    factory: str,
    collateral: str,
    proposition: str,
    outcomes: list[str],
    betting_close_time: int,
    resolution_window: int,
    resolver: str,
    betting_closer: str,
    resolution_closer: str,
    extra_recipients: list[str],
    extra_bps: list[int],
    payoff_policy: int = 0,
    policy_param: int = 0,
    seed_outcome_indices: list[int] | None = None,
    seed_amounts: list[int] | None = None,
    rpc_url: str,
    private_key: str,
) -> CastCommand:
    """Build a `cast send` command for `ParamutuelFactoryV3.createEnumeratedWager`.

    `seed_outcome_indices` is an ergonomic shorthand: each index `i` is
    promoted to the single-outcome ticket bitmask `1 << i` before it is
    passed to the factory's `uint256[] seedTicketMasks` argument. Multi-bit
    seeds (for `ANY_OF` / `EXACT_SET` policies) still go through this path
    by passing the precomputed mask as the index value.

    `payoff_policy` is the `ParamutuelWagerV3.PayoffPolicy` enum:
    `0=SINGLE_WINNER, 1=ANY_OF, 2=EXACT_SET, 3=AT_LEAST_K, 4=WEIGHTED_OVERLAP`.
    `policy_param` is `k` for `AT_LEAST_K` and `0` otherwise.
    """
    if seed_outcome_indices is None:
        seed_outcome_indices = []
    if seed_amounts is None:
        seed_amounts = []
    if len(outcomes) < 2:
        raise ValueError("outcomes must have at least 2 items")
    if len(outcomes) > 255:
        raise ValueError("outcomes must have at most 255 items (factory MAX_OUTCOMES)")
    if len(extra_recipients) != len(extra_bps):
        raise ValueError("extra_recipients and extra_bps length mismatch")
    if len(seed_outcome_indices) != len(seed_amounts):
        raise ValueError("seed_outcome_indices and seed_amounts length mismatch")
    for amount in seed_amounts:
        if amount <= 0:
            raise ValueError("seed_amounts must be positive integers")
    if payoff_policy not in (0, 1, 2, 3, 4):
        raise ValueError("payoff_policy must be a PayoffPolicy enum value in 0..4")
    if betting_close_time == 0 and betting_closer.lower() == ZERO_ADDRESS:
        raise ValueError("betting_close_time=0 requires a non-zero betting_closer")
    if resolution_window == 0 and resolution_closer.lower() == ZERO_ADDRESS:
        raise ValueError("resolution_window=0 requires a non-zero resolution_closer")

    # Each `seed_outcome_indices[i]` becomes the single-outcome ticket
    # bitmask `1 << i`. Callers that need multi-bit seed tickets (e.g.
    # `ANY_OF` covering outcomes {0,2}) should call the factory directly
    # with the explicit mask.
    seed_ticket_masks = [1 << int(i) for i in seed_outcome_indices]
    for mask in seed_ticket_masks:
        if mask == 0 or mask.bit_length() > len(outcomes):
            raise ValueError(
                "seed_outcome_indices entries must be in [0, len(outcomes)-1]"
            )

    cmd = [
        "cast",
        "send",
        factory,
        ENUMERATED_CREATE_SIG_WITH_SEEDS,
        collateral,
        proposition,
        _json_arg(outcomes),
        str(int(payoff_policy)),
        str(int(policy_param)),
        str(betting_close_time),
        str(resolution_window),
        resolver,
        betting_closer,
        resolution_closer,
        _json_arg(extra_recipients),
        _json_arg(extra_bps),
        _json_arg(seed_ticket_masks),
        _json_arg(seed_amounts),
        "--rpc-url",
        rpc_url,
        "--private-key",
        private_key,
    ]
    return CastCommand(cmd)


FREEFORM_CREATE_SIG = (
    "createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[])"
)


def build_create_freeform_wager_command(
    *,
    factory: str,
    collateral: str,
    proposition: str,
    betting_close_time: int,
    resolution_window: int,
    resolver: str,
    betting_closer: str,
    resolution_closer: str,
    extra_recipients: list[str],
    extra_bps: list[int],
    rpc_url: str,
    private_key: str,
) -> CastCommand:
    if len(extra_recipients) != len(extra_bps):
        raise ValueError("extra_recipients and extra_bps length mismatch")
    if betting_close_time == 0 and betting_closer.lower() == ZERO_ADDRESS:
        raise ValueError("betting_close_time=0 requires a non-zero betting_closer")
    if resolution_window == 0 and resolution_closer.lower() == ZERO_ADDRESS:
        raise ValueError("resolution_window=0 requires a non-zero resolution_closer")

    cmd = [
        "cast",
        "send",
        factory,
        FREEFORM_CREATE_SIG,
        collateral,
        proposition,
        str(betting_close_time),
        str(resolution_window),
        resolver,
        betting_closer,
        resolution_closer,
        _json_arg(extra_recipients),
        _json_arg(extra_bps),
        "--rpc-url",
        rpc_url,
        "--private-key",
        private_key,
    ]
    return CastCommand(cmd)


def build_wager_action_command(
    *,
    wager: str,
    action: str,
    rpc_url: str,
    private_key: str,
    outcome_index: int | None = None,
    protocol_version: str | None = None,
    winning_answer: str | None = None,
) -> CastCommand:
    action_to_sig = {
        "close-betting": "closeBetting()",
        "close-resolution-window": "closeResolutionWindow()",
        "retract": "retract()",
        "expire": "expire()",
        "claim": "claim()",
        "withdraw-fees": "withdrawFees()",
    }
    pv = (protocol_version or "enumerated").strip().lower()
    if action == "resolve":
        if pv == "freeform":
            ans = (winning_answer or "").strip()
            if not ans:
                raise ValueError("winning_answer required for freeform resolve(string)")
            sig = "resolve(string)"
            args = [ans]
        else:
            if outcome_index is None:
                raise ValueError("outcome_index (winning index or bitmask) required for resolve(uint256)")
            sig = "resolve(uint256)"
            args = [str(int(outcome_index))]
    else:
        if action not in action_to_sig:
            raise ValueError(f"unsupported action: {action}")
        sig = action_to_sig[action]
        args = []

    cmd = [
        "cast",
        "send",
        wager,
        sig,
        *args,
        "--rpc-url",
        rpc_url,
        "--private-key",
        private_key,
    ]
    return CastCommand(cmd)


def lifecycle_workflow(*, no_max_betting: bool, no_max_resolution: bool) -> list[str]:
    steps = ["createEnumeratedWager / createFreeformWager", "placeBet / placeBet(string)"]
    if no_max_betting:
        steps.append("closeBetting")
    if no_max_resolution:
        steps.append("closeResolutionWindow (optional before expire)")
    steps.extend(["resolve/retract OR expire", "claim/withdrawFees"])
    return steps
