"""Minimal stdlib ABI encoder for the V3 calls the operator services send.

Why this exists: `cast` cannot be trusted with arbitrary strings. Verified against cast 1.5.1 on a
local chain (ADR-0020):

- it silently strips trailing whitespace: "Paris " is encoded as "Paris";
- it silently strips surrounding quotes: '"Paris"' is encoded as "Paris";
- it parses a positional argument such as `--gas-limit=1` as a flag;
- its array syntax stores JSON escapes verbatim, so `caf\\u00e9` reaches the chain literally, and has
  no way at all to express some strings.

For freeform wagers that is a correctness problem and not a cosmetic one: answers are chosen by bettors
and matched byte-exactly, so the first two cases can resolve a *different pool* than the operator
intended. Everything user-supplied is therefore encoded here and handed to `cast send` as raw calldata,
leaving `cast` to do only what it does reliably: sign and broadcast.

Standard library only, matching the service images. Checked against eth_abi and eth_hash by
`tests/test_abi.py`. Python has no keccak256 in its standard library, hence the pinned selector table;
that test recomputes each one.
"""
from __future__ import annotations

import re

# keccak256(signature)[:4] for every function the operator services call.
SELECTORS: dict[str, str] = {
    "resolve(uint256)": "0x4f896d4f",
    "resolve(string)": "0x461a4478",
    "retract()": "0x47f57b32",
    "expire()": "0x79599f96",
    "claim()": "0x4e71d92d",
    "withdrawFees()": "0x476343ee",
    "closeBetting()": "0x15ac534d",
    "closeResolutionWindow()": "0x22ad3cf6",
    "createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,address,address[],uint16[],uint256[],uint256[])": "0xade4c7fd",
    "createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,address,address[],uint16[],uint256[],uint256[],uint256)": "0xe691d6f1",
    "createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[])": "0xcecc699e",
    "createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[],uint256)": "0x30903e90",
}

_UINT_RE = re.compile(r"^uint(\d+)$")
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _word(value: int) -> bytes:
    return value.to_bytes(32, "big")


def _encode_uint(value: object, bits: int, type_name: str) -> bytes:
    # `bool` is an `int` subclass; JSON `true` must not pass as 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{type_name} value must be an integer, got {value!r}")
    if not 0 <= value < 2**bits:
        raise ValueError(f"{type_name} value out of range: {value}")
    return _word(value)


def _encode_address(value: object) -> bytes:
    if not isinstance(value, str) or not _ADDRESS_RE.match(value):
        raise ValueError(f"invalid address: {value!r}")
    return bytes(12) + bytes.fromhex(value[2:])


def _encode_string(value: object) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"string value expected, got {value!r}")
    raw = value.encode("utf-8")
    padding = (32 - len(raw) % 32) % 32
    return _word(len(raw)) + raw + bytes(padding)


def _is_dynamic(type_name: str) -> bool:
    return type_name == "string" or type_name.endswith("[]")


def _encode_value(type_name: str, value: object) -> bytes:
    if type_name == "address":
        return _encode_address(value)
    if type_name == "string":
        return _encode_string(value)
    if type_name.endswith("[]"):
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"{type_name} value must be a list, got {value!r}")
        element = type_name[:-2]
        return _word(len(value)) + encode([element] * len(value), list(value))
    match = _UINT_RE.match(type_name)
    if match:
        return _encode_uint(value, int(match.group(1)), type_name)
    raise ValueError(f"unsupported ABI type: {type_name}")


def encode(types: list[str], values: list) -> bytes:
    """ABI-encode a tuple of values: static values and offsets in the head, dynamic data in the tail."""
    if len(types) != len(values):
        raise ValueError("types and values length mismatch")
    head_size = 32 * len(types)
    head = b""
    tail = b""
    for type_name, value in zip(types, values):
        encoded = _encode_value(type_name, value)
        if _is_dynamic(type_name):
            head += _word(head_size + len(tail))
            tail += encoded
        else:
            head += encoded
    return head + tail


def encode_call(signature: str, types: list[str], values: list) -> str:
    """Return `0x`-prefixed calldata. Raises KeyError for a function not in `SELECTORS`."""
    return SELECTORS[signature] + encode(types, values).hex()
