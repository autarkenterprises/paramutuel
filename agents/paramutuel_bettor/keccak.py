"""Ethereum's Keccak-256, in pure Python.

The bet scout ships with no runtime dependencies (see ``indexer_client.py``), and Python's standard
library has no Keccak: ``hashlib.sha3_256`` is the final SHA-3 standard, which pads differently and
gives different digests. The scout needs Keccak for exactly one thing: a freeform answer's id,
``keccak256(0x03 || bytes(answer))``, which it uses to ask the indexer for that answer's pool
(ADR-0021 U1). Speed is irrelevant at one short hash per quote.

This is the Keccak-f[1600] permutation with rate 1088 bits (136 bytes), capacity 512, and the
original Keccak padding ``0x01 .. 0x80``. ``tests/test_adr0021.py`` checks it against ``eth-hash``
on known vectors and random inputs of every length across the padding boundaries.
"""
from __future__ import annotations

_MASK = (1 << 64) - 1
_RATE = 136  # bytes absorbed per permutation for a 256-bit output

# Round constants for iota, one per round of Keccak-f[1600].
_ROUND_CONSTANTS = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)

# Rotation offsets for rho, indexed by lane x + 5 * y.
_ROTATIONS = (
    0, 1, 62, 28, 27,
    36, 44, 6, 55, 20,
    3, 10, 43, 25, 39,
    41, 45, 15, 21, 8,
    18, 2, 61, 56, 14,
)


def _rotl(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (64 - shift))) & _MASK


def _permute(lanes: list[int]) -> None:
    """Keccak-f[1600] in place on 25 64-bit lanes, lane (x, y) at index x + 5 * y."""
    for constant in _ROUND_CONSTANTS:
        # theta: mix each column's parity into its neighbours.
        parity = [lanes[x] ^ lanes[x + 5] ^ lanes[x + 10] ^ lanes[x + 15] ^ lanes[x + 20] for x in range(5)]
        for x in range(5):
            mix = parity[(x - 1) % 5] ^ _rotl(parity[(x + 1) % 5], 1)
            for y in range(0, 25, 5):
                lanes[x + y] ^= mix
        # rho and pi: rotate every lane, then move lane (x, y) to (y, 2x + 3y).
        moved = [0] * 25
        for x in range(5):
            for y in range(5):
                moved[y + 5 * ((2 * x + 3 * y) % 5)] = _rotl(lanes[x + 5 * y], _ROTATIONS[x + 5 * y])
        # chi: the only non-linear step, row by row.
        for y in range(0, 25, 5):
            row = moved[y : y + 5]
            for x in range(5):
                lanes[x + y] = row[x] ^ (~row[(x + 1) % 5] & row[(x + 2) % 5])
        # iota: break the symmetry between rounds.
        lanes[0] ^= constant


def keccak256(data: bytes) -> bytes:
    """Return the 32-byte Keccak-256 digest of ``data``, as Solidity's ``keccak256`` computes it."""
    padded = bytearray(data)
    padded.append(0x01)
    padded.extend(b"\x00" * (-len(padded) % _RATE))
    padded[-1] |= 0x80
    lanes = [0] * 25
    for start in range(0, len(padded), _RATE):
        block = padded[start : start + _RATE]
        for i in range(_RATE // 8):
            lanes[i] ^= int.from_bytes(block[8 * i : 8 * i + 8], "little")
        _permute(lanes)
    return b"".join(lane.to_bytes(8, "little") for lane in lanes[:4])
