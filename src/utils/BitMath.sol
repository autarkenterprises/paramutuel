// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Ticket-mask bit helpers shared by the V3 wager and factory
/// @notice Constant-time on purpose. The previous Kernighan loop cost ~58 gas per set bit, which let
///         a griefer fill `_usedMasks` with near-full masks and push `resolve` past the 2^24
///         per-transaction gas cap on wagers with roughly 197 or more outcomes (ADR-0020 finding
///         C1). With this version the per-mask cost no longer depends on bit count.
library BitMath {
    /// @notice Number of set bits in `x`. Correct for every mask a wager can hold, which is at most
    ///         255 bits wide (`MAX_OUTCOMES` in the factory, `OUTCOMES_MAX` in the wager).
    /// @dev Classic SWAR population count: sum adjacent bits, then pairs, then nibbles, leaving a
    ///      count per byte; the multiply gathers those counts into the top byte. That final step
    ///      counts modulo 256, so `type(uint256).max` would read as 0. That value is unreachable
    ///      because mask width is capped at 255 bits, which is why the wager's ceiling is 255 rather
    ///      than 256. Pinned by `test_popcount_matchesNaive_fuzz`.
    function popcount(uint256 x) internal pure returns (uint256) {
        unchecked {
            x -= (x >> 1) & 0x5555555555555555555555555555555555555555555555555555555555555555;
            x = (x & 0x3333333333333333333333333333333333333333333333333333333333333333)
                + ((x >> 2) & 0x3333333333333333333333333333333333333333333333333333333333333333);
            x = (x + (x >> 4)) & 0x0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f;
            return (x * 0x0101010101010101010101010101010101010101010101010101010101010101) >> 248;
        }
    }

    /// @notice True iff exactly one bit of `x` is set (a single-outcome ticket).
    function isSingleBit(uint256 x) internal pure returns (bool) {
        unchecked {
            return x != 0 && x & (x - 1) == 0;
        }
    }
}
