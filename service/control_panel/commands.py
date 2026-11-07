"""Control panel — calldata builders and transaction runner for V3 wager actions.

Pure functions over operator inputs that produce ``cast send`` argument lists. Centralising the
encoders here means the proposition service, the resolution service, the sweeper and the control-panel
CLI / web shell agree byte-for-byte on calldata; encoding drift between them would silently mint
differently-encoded wagers.

Every argument travels as ABI-encoded calldata rather than as ``cast`` positional arguments, because
``cast`` alters strings and can mistake them for flags; :mod:`service.control_panel.abi` has the
details. ``CastCommand`` therefore also carries the function and readable arguments, for previews.

V3 protocol surface:

- ``createEnumeratedWager`` and ``createFreeformWager``. The overloads that take
  ``minNewTicketStake`` are used only when it is non-zero, so a zero minimum works against every
  deployed factory.
- Lifecycle actions scoped to a wager address: ``closeBetting``, ``closeResolutionWindow``,
  ``resolve``, ``retract``, ``expire``, ``claim``, ``withdrawFees``.

For ``resolver`` the zero address means "default to proposer"; for the betting and resolution closers
it means "role disabled" (time-based close only) — see ADR-0005's 2026-09-26 AAR revision.
"""
from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable

from .abi import encode, encode_call

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
REDACTED = "<redacted>"
# Long enough for inclusion on a congested chain, short enough that a stuck RPC cannot hang a service.
CAST_TIMEOUT_SECONDS = 180


def redact_argv(argv: list[str]) -> list[str]:
    """Copy of a ``cast`` argv with the ``--private-key`` value masked, safe to log or return."""
    out = list(argv)
    for i, token in enumerate(out[:-1]):
        if token == "--private-key":
            out[i + 1] = REDACTED
    return out


@dataclass
class CastCommand:
    """A ready-to-run ``cast send``, plus what it does in readable form.

    ``command`` holds the private key and must never be logged or returned; use :meth:`shell` or
    :meth:`preview`, which redact it.
    """

    command: list[str]
    signature: str = ""
    args: list[Any] = field(default_factory=list)

    def shell(self) -> str:
        """Copy-pasteable shell line with the key masked."""
        return " ".join(shlex.quote(x) for x in redact_argv(self.command))

    def preview(self) -> dict[str, Any]:
        """JSON-safe description for operator review. Integers become strings so a uint256 mask or
        stake survives a JavaScript client."""
        return {
            "command": redact_argv(self.command),
            "function": self.signature,
            "args": _jsonable(self.args),
        }


def _jsonable(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else value


@dataclass
class CastResult:
    """Outcome of one ``cast send``. ``ok`` means mined with status 1, and nothing weaker."""

    ok: bool
    stdout: str = ""
    stderr: str = ""
    tx_hash: str | None = None
    returncode: int | None = None


def _first_json_object(text: str) -> dict | None:
    """The JSON object in ``cast`` output, or None. Not simply ``json.loads``: seen on a real node,
    cast's RPC poller can log to stdout around the receipt, which must not read as a failed transaction."""
    start = text.find("{")
    if start < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _scrub_key(text: str, argv: list[str]) -> str:
    """Remove the private key from text that came back from ``cast``, in case an error echoed it."""
    for i, token in enumerate(argv[:-1]):
        if token == "--private-key" and argv[i + 1]:
            key = argv[i + 1]
            text = text.replace(key, REDACTED).replace(key.removeprefix("0x"), REDACTED)
    return text


def run_cast_send(
    argv: list[str],
    *,
    runner: Callable[..., Any] | None = None,
    timeout: int = CAST_TIMEOUT_SECONDS,
) -> CastResult:
    """Run a ``cast send --json`` and report what actually happened on-chain.

    The exit code is not enough: ``cast send`` exits 0 for a transaction that was mined and reverted,
    which is reachable whenever chain state changes between gas estimation and inclusion. Before this
    existed, services recorded such a transaction as a success. Success therefore requires a JSON
    receipt with status 1, so any other output (help text, an empty result) is a failure too.
    """
    run = runner or subprocess.run
    try:
        proc = run(argv, check=False, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return CastResult(False, stderr="`cast` not found on PATH. Install Foundry, or use an image that includes it.")
    except subprocess.TimeoutExpired:
        return CastResult(False, stderr=f"`cast send` timed out after {timeout}s; the transaction may still be mined. Check the chain before retrying.")

    stdout = _scrub_key(getattr(proc, "stdout", "") or "", argv)
    stderr = _scrub_key(getattr(proc, "stderr", "") or "", argv)
    if proc.returncode != 0:
        return CastResult(False, stdout, stderr or f"cast exited {proc.returncode}", returncode=proc.returncode)
    receipt = _first_json_object(stdout)
    if receipt is None or "status" not in receipt:
        return CastResult(False, stdout, f"unexpected cast output, not a transaction receipt: {stdout[:200]}", returncode=0)
    tx_hash = receipt.get("transactionHash")
    if str(receipt["status"]).lower() not in ("0x1", "1"):
        return CastResult(False, stdout, f"transaction {tx_hash} was mined but reverted on-chain (status {receipt['status']})", tx_hash, 0)
    return CastResult(True, stdout, stderr, tx_hash, 0)


def cast_send_argv(*, to: str, calldata: str, rpc_url: str, private_key: str) -> list[str]:
    """Argv for sending prepared calldata. ``--json`` is what lets :func:`run_cast_send` read the receipt."""
    return ["cast", "send", "--json", "--rpc-url", rpc_url, "--private-key", private_key, to, calldata]


def _command(*, to: str, signature: str, types: list[str], values: list, rpc_url: str, private_key: str) -> CastCommand:
    # `to` is not part of the calldata, so validate it explicitly with the encoder's address rule.
    encode(["address"], [to])
    calldata = encode_call(signature, types, values)
    return CastCommand(cast_send_argv(to=to, calldata=calldata, rpc_url=rpc_url, private_key=private_key), signature, list(values))


# `createEnumeratedWager` long form. The control panel always emits a form that takes seed arrays; empty
# arrays mean "no seeds" without altering semantics.
ENUMERATED_CREATE_SIG_WITH_SEEDS = (
    "createEnumeratedWager("
    "address,string,string[],uint8,uint256,uint64,uint64,"
    "address,address,address,address[],uint16[],uint256[],uint256[]"
    ")"
)
ENUMERATED_CREATE_SIG_WITH_MIN_STAKE = ENUMERATED_CREATE_SIG_WITH_SEEDS[:-1] + ",uint256)"
_ENUMERATED_CREATE_TYPES = [
    "address", "string", "string[]", "uint8", "uint256", "uint64", "uint64",
    "address", "address", "address", "address[]", "uint16[]", "uint256[]", "uint256[]",
]


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
    min_new_ticket_stake: int = 0,
    rpc_url: str,
    private_key: str,
) -> CastCommand:
    """Build a ``cast send`` command for ``ParamutuelFactoryV3.createEnumeratedWager``.

    ``seed_outcome_indices`` is an ergonomic shorthand: each index ``i`` is
    promoted to the single-outcome ticket bitmask ``1 << i`` before it is
    passed to the factory's ``uint256[] seedTicketMasks`` argument. Multi-bit
    seeds (for ``ANY_OF`` / ``EXACT_SET`` policies) are NOT expressible here —
    a mask passed as an "index" would itself be shifted — so call the
    factory directly with explicit masks for those.

    ``payoff_policy`` is the ``ParamutuelWagerV3.PayoffPolicy`` enum:
    ``0=SINGLE_WINNER, 1=ANY_OF, 2=EXACT_SET, 3=AT_LEAST_K, 4=WEIGHTED_OVERLAP``.
    ``policy_param`` is ``k`` for ``AT_LEAST_K`` and ``0`` otherwise.
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

    seed_ticket_masks = [1 << int(i) for i in seed_outcome_indices]
    for mask in seed_ticket_masks:
        if mask == 0 or mask.bit_length() > len(outcomes):
            raise ValueError("seed_outcome_indices entries must be in [0, len(outcomes)-1]")

    values: list[Any] = [
        collateral, proposition, list(outcomes), int(payoff_policy), int(policy_param),
        betting_close_time, resolution_window, resolver, betting_closer, resolution_closer,
        list(extra_recipients), list(extra_bps), seed_ticket_masks, list(seed_amounts),
    ]
    if min_new_ticket_stake:
        return _command(
            to=factory,
            signature=ENUMERATED_CREATE_SIG_WITH_MIN_STAKE,
            types=_ENUMERATED_CREATE_TYPES + ["uint256"],
            values=values + [min_new_ticket_stake],
            rpc_url=rpc_url,
            private_key=private_key,
        )
    return _command(
        to=factory,
        signature=ENUMERATED_CREATE_SIG_WITH_SEEDS,
        types=_ENUMERATED_CREATE_TYPES,
        values=values,
        rpc_url=rpc_url,
        private_key=private_key,
    )


FREEFORM_CREATE_SIG = (
    "createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[])"
)
FREEFORM_CREATE_SIG_WITH_MIN_STAKE = FREEFORM_CREATE_SIG[:-1] + ",uint256)"
_FREEFORM_CREATE_TYPES = ["address", "string", "uint64", "uint64", "address", "address", "address", "address[]", "uint16[]"]


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
    min_new_ticket_stake: int = 0,
    rpc_url: str,
    private_key: str,
) -> CastCommand:
    """Build a ``cast send`` command for ``ParamutuelFactoryV3.createFreeformWager``."""
    if len(extra_recipients) != len(extra_bps):
        raise ValueError("extra_recipients and extra_bps length mismatch")
    if betting_close_time == 0 and betting_closer.lower() == ZERO_ADDRESS:
        raise ValueError("betting_close_time=0 requires a non-zero betting_closer")
    if resolution_window == 0 and resolution_closer.lower() == ZERO_ADDRESS:
        raise ValueError("resolution_window=0 requires a non-zero resolution_closer")

    values: list[Any] = [
        collateral, proposition, betting_close_time, resolution_window, resolver, betting_closer,
        resolution_closer, list(extra_recipients), list(extra_bps),
    ]
    if min_new_ticket_stake:
        return _command(
            to=factory,
            signature=FREEFORM_CREATE_SIG_WITH_MIN_STAKE,
            types=_FREEFORM_CREATE_TYPES + ["uint256"],
            values=values + [min_new_ticket_stake],
            rpc_url=rpc_url,
            private_key=private_key,
        )
    return _command(
        to=factory,
        signature=FREEFORM_CREATE_SIG,
        types=_FREEFORM_CREATE_TYPES,
        values=values,
        rpc_url=rpc_url,
        private_key=private_key,
    )


def _parse_winning_mask(raw: Any) -> int:
    """Accept an integer or a decimal/hex string; a mask can be far wider than a JavaScript number."""
    if isinstance(raw, bool) or isinstance(raw, float):
        raise ValueError(f"winning_mask must be a positive integer, got {raw!r}")
    try:
        mask = int(raw, 0) if isinstance(raw, str) else int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"winning_mask must be a positive integer, got {raw!r}") from None
    if mask <= 0:
        raise ValueError(f"winning_mask must be a positive integer, got {raw!r}")
    return mask


def build_wager_action_command(
    *,
    wager: str,
    action: str,
    rpc_url: str,
    private_key: str,
    winning_mask: Any = None,
    protocol_version: str | None = None,
    winning_answer: str | None = None,
) -> CastCommand:
    """Build a ``cast send`` for one lifecycle action.

    ``winning_mask`` is the raw bitmask for ``resolve(uint256)``, so outcome 0 alone is mask 1. It was
    previously named ``outcome_index``, which invited exactly the confusion that made the resolution
    service pay the wrong outcome before ADR-0019. ``winning_answer`` is sent byte-exact: V3 hashes
    those bytes to find the winning pool, so nothing here may trim or normalise it (ADR-0009 §5).
    """
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
            if not winning_answer:
                raise ValueError("winning_answer required for freeform resolve(string)")
            signature, types, values = "resolve(string)", ["string"], [winning_answer]
        else:
            if winning_mask is None:
                raise ValueError("winning_mask required for resolve(uint256)")
            signature, types, values = "resolve(uint256)", ["uint256"], [_parse_winning_mask(winning_mask)]
    else:
        if action not in action_to_sig:
            raise ValueError(f"unsupported action: {action}")
        signature, types, values = action_to_sig[action], [], []
    return _command(to=wager, signature=signature, types=types, values=values, rpc_url=rpc_url, private_key=private_key)


def lifecycle_workflow(*, no_max_betting: bool, no_max_resolution: bool) -> list[str]:
    steps = ["createEnumeratedWager / createFreeformWager", "placeBet / placeBet(string)"]
    if no_max_betting:
        steps.append("closeBetting")
    if no_max_resolution:
        steps.append("closeResolutionWindow (optional before expire)")
    steps.extend(["resolve/retract OR expire", "claim/withdrawFees"])
    return steps
