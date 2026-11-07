// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Full-precision `a * b / denominator`
/// @notice Wager arithmetic must never overflow, because the failure mode is permanent loss: with
///         checked 256-bit math, a stake or pot on a high-supply token made `claim` revert forever,
///         and `totalPot * totalFeeBps` could make `resolve`, `retract` and `expire` all revert
///         (ADR-0020 finding C4). Every payout has the shape `amount * netPot / total` with
///         `amount <= total`, so the true result always fits in 256 bits even when the intermediate
///         product does not.
/// @dev Remco Bloemen's 512-bit `mulDiv` (MIT, https://xn--2-umb.com/21/muldiv), the same algorithm
///      used by OpenZeppelin `Math.mulDiv` and Uniswap `FullMath`. Vendored rather than imported to
///      keep `src/` free of compile-time dependencies. Rounds down, matching the protocol's
///      "dust stays in the wager" solvency rule.
library FullMath {
    /// @notice The true quotient does not fit in 256 bits, or `denominator` is zero.
    error MulDivOverflow();

    /// @notice Returns `floor(a * b / denominator)` computed without intermediate overflow.
    function mulDiv(uint256 a, uint256 b, uint256 denominator) internal pure returns (uint256 result) {
        unchecked {
            // 512-bit product as [prod1 prod0]: the difference between the product mod 2^256-1 and
            // the product mod 2^256 recovers the high word.
            uint256 prod0;
            uint256 prod1;
            assembly {
                let mm := mulmod(a, b, not(0))
                prod0 := mul(a, b)
                prod1 := sub(sub(mm, prod0), lt(mm, prod0))
            }

            // Also rejects denominator == 0, since prod1 >= 0.
            if (denominator <= prod1) revert MulDivOverflow();

            // Common case: the product fits in 256 bits.
            if (prod1 == 0) return prod0 / denominator;

            // Make the division exact by subtracting the remainder from [prod1 prod0].
            uint256 remainder;
            assembly {
                remainder := mulmod(a, b, denominator)
                prod1 := sub(prod1, gt(remainder, prod0))
                prod0 := sub(prod0, remainder)
            }

            // Factor powers of two out of the denominator, shifting the product to match. `twos` is
            // the largest power of two dividing `denominator`, so this cannot lose bits.
            uint256 twos = denominator & (0 - denominator);
            assembly {
                denominator := div(denominator, twos)
                prod0 := div(prod0, twos)
                twos := add(div(sub(0, twos), twos), 1)
            }
            prod0 |= prod1 * twos;

            // `denominator` is now odd, so it has an inverse mod 2^256. Start from a seed correct to
            // 4 bits and apply Newton-Raphson; precision doubles each round, reaching 256 bits.
            uint256 inverse = (3 * denominator) ^ 2;
            inverse *= 2 - denominator * inverse; // 8 bits
            inverse *= 2 - denominator * inverse; // 16 bits
            inverse *= 2 - denominator * inverse; // 32 bits
            inverse *= 2 - denominator * inverse; // 64 bits
            inverse *= 2 - denominator * inverse; // 128 bits
            inverse *= 2 - denominator * inverse; // 256 bits

            // The division is exact and `result` fits (checked above), so multiplying by the
            // modular inverse yields the true quotient.
            result = prod0 * inverse;
        }
    }
}
