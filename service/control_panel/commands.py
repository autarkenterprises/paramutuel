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
    seed_outcome_indices: list[int] | None = None,
    seed_amounts: list[int] | None = None,
    rpc_url: str,
    private_key: str,
) -> CastCommand:
    if seed_outcome_indices is None:
        seed_outcome_indices = []
    if seed_amounts is None:
        seed_amounts = []
    if len(outcomes) < 2:
        raise ValueError("outcomes must have at least 2 items")
    if len(extra_recipients) != len(extra_bps):
        raise ValueError("extra_recipients and extra_bps length mismatch")
    if len(seed_outcome_indices) != len(seed_amounts):
        raise ValueError("seed_outcome_indices and seed_amounts length mismatch")
    for amount in seed_amounts:
        if amount <= 0:
            raise ValueError("seed_amounts must be positive integers")
    if betting_close_time == 0 and betting_closer.lower() == ZERO_ADDRESS:
        raise ValueError("betting_close_time=0 requires a non-zero betting_closer")
    if resolution_window == 0 and resolution_closer.lower() == ZERO_ADDRESS:
        raise ValueError("resolution_window=0 requires a non-zero resolution_closer")

    cmd = [
        "cast",
        "send",
        factory,
        "createWager(address,string,string[],uint64,uint64,address,address,address,address[],uint16[],uint256[],uint256[])",
        collateral,
        proposition,
        _json_arg(outcomes),
        str(betting_close_time),
        str(resolution_window),
        resolver,
        betting_closer,
        resolution_closer,
        _json_arg(extra_recipients),
        _json_arg(extra_bps),
        _json_arg(seed_outcome_indices),
        _json_arg(seed_amounts),
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
) -> CastCommand:
    action_to_sig = {
        "close-betting": "closeBetting()",
        "close-resolution-window": "closeResolutionWindow()",
        "retract": "retract()",
        "expire": "expire()",
        "claim": "claim()",
        "withdraw-fees": "withdrawFees()",
    }
    if action == "resolve":
        if outcome_index is None:
            raise ValueError("outcome_index required for resolve")
        sig = "resolve(uint256)"
        args = [str(outcome_index)]
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
    steps = ["createWager", "placeBet"]
    if no_max_betting:
        steps.append("closeBetting")
    if no_max_resolution:
        steps.append("closeResolutionWindow (optional before expire)")
    steps.extend(["resolve/retract OR expire", "claim/withdrawFees"])
    return steps
