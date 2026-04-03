# Paramutuel v2 wager templates (product patterns)

These are **recommended combinations** of `PayoffPolicy`, `policyParam`, and ticket construction for common markets. Encode tickets with `WagerV2Masks` (`src/libraries/WagerV2Masks.sol`) or equivalent off-chain logic.

| Template | Policy | `policyParam` | Ticket shape | Resolver submits |
|----------|--------|---------------|--------------|------------------|
| **Classic binary** | `SINGLE_WINNER` | `0` | Single bit per leg (`1 << i`) | One winning bit |
| **Sector / any hit** | `ANY_OF` | `0` | Any non-empty subset of a “sector” | Bitmask of all true base options |
| **Exact parlay set** | `EXACT_SET` | `0` | Usually multi-bit subset | `W` equal to the winning combination ticket |
| **K-of-N overlap** | `AT_LEAST_K` | `k` | Any subset; win if `|T ∩ W| ≥ k` | Bitmask of true options |
| **Scored / graded exposure** | `WEIGHTED_OVERLAP` | `0` | Any subset | Bitmask of true options; payout ∝ `stake × \|T ∩ W\|` |

## Narrative examples

1. **“Which tickers close green?”** (AAPL, MSFT, GOOG, …)  
   - Use **`ANY_OF`**: bettors pick subsets they believe will land in the green set; anyone overlapping the resolved set shares the pool pro-rata by stake.

2. **“Call the exact winning basket”**  
   - Use **`EXACT_SET`**: only tickets equal to the final resolved set collect the pot; overlapping but inexact tickets lose (high risk / high specificity).

3. **“At least 3 of my 5 picks must hit”**  
   - Use **`AT_LEAST_K`** with `k = 3`: ticket is a 5-bit mask; resolver posts which of the five hit; payout if intersection size ≥ 3.

4. **“Traditional YES/NO single winner”**  
   - Use **`SINGLE_WINNER`**: same economics as v1 for a two-outcome line; tickets must be exactly one bit.

5. **“Partial credit for partial truth”**  
   - Use **`WEIGHTED_OVERLAP`**: larger overlap between ticket and truth yields more weight; useful when you want smoother payoffs than binary any-of.

## Lifecycle presets (time windows)

Mirror v1 dApp-style **windows** from `ParamutuelFactory` / `ParamutuelWager` (absolute `bettingCloseTime`, `resolutionWindow`). v2 factory uses the same min-window rules:

| Name | Suggested betting close | Resolution window |
|------|-------------------------|-------------------|
| Flash | `now + 15 minutes` | `2 hours` |
| Intraday | `now + 4 hours` | `24 hours` |
| Weekly event | `now + 7 days` | `48 hours` |

(Adjust to your chain’s `minBettingWindow` / `minResolutionWindow` on the deployed factory.)

## Solidity snippet

```solidity
import {WagerV2Masks} from "src/libraries/WagerV2Masks.sol";

// 4-outcome "any ticker up" style ticket: user backs options 0 and 2
uint256 ticket = WagerV2Masks.union(
    WagerV2Masks.singleOutcome(0),
    WagerV2Masks.singleOutcome(2)
);
// Resolver later: winningMask = WagerV2Masks.fullSet(4) if all four were true, etc.
```

## Related

- [`ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md) — policy math and limits  
- [`ADR-0008-GAS.md`](ADR-0008-GAS.md) — measured gas (regenerate with Foundry)
