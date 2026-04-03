// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Bitmask helpers for `ParamutuelWagerV2` tickets (`uint256` mask, bit i = option i selected).
/// @dev `numOptions` must match the wager's outcome count; bits at or above `numOptions` are invalid on-chain.
library WagerV2Masks {
    /// @return mask `1 << optionIndex` (single-outcome ticket).
    function singleOutcome(uint256 optionIndex) internal pure returns (uint256 mask) {
        mask = 1 << optionIndex;
    }

    /// @return bitwise OR of two tickets (combined selection).
    function union(uint256 maskA, uint256 maskB) internal pure returns (uint256) {
        return maskA | maskB;
    }

    /// @return mask with bits `0 .. numOptions-1` all set (ticket backing every base option).
    /// @dev Reverts if `numOptions` is 0 or > 255 (`1 << numOptions` would overflow uint256).
    function fullSet(uint256 numOptions) internal pure returns (uint256) {
        require(numOptions > 0 && numOptions < 256, "MASKS_RANGE");
        unchecked {
            return (1 << numOptions) - 1;
        }
    }

    /// @return whether `mask` only uses bits below `numOptions`.
    function isValidMask(uint256 mask, uint256 numOptions) internal pure returns (bool) {
        if (mask == 0) return false;
        return (mask >> numOptions) == 0;
    }
}
