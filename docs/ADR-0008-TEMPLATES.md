# Paramutuel enumerated-mode wager templates (product patterns)

> **Scope:** these templates apply to the unified **`ParamutuelWagerV3`** when constructed with `MODE = Enumerated` (see [`ADR-0010-IMPLEMENTATION.md`](ADR-0010-IMPLEMENTATION.md)). They describe the same `PayoffPolicy` semantics ADR-0008 defined for the now-deleted `ParamutuelWagerV2`.

These are **recommended combinations** of `PayoffPolicy`, `policyParam`, and ticket construction for common markets. Ticket bitmasks are plain `uint256` values (bit `i` ⇔ outcome index `i`); construct them off-chain (`1 << i`, bitwise OR for unions, `(1 << n) - 1` for full set with `n < 256`). For **“any of” / “all of”** product wording vs **`EXACT_SET`** vs subset-of-truth **`T ⊆ W`**, see the glossary in [`PAYOUT-CALCULATION.md`](PAYOUT-CALCULATION.md) Part B.

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

The V3 factory exposes the same absolute `bettingCloseTime` / `resolutionWindow` inputs with `minBettingWindow` / `minResolutionWindow` enforcement:

| Name | Suggested betting close | Resolution window |
|------|-------------------------|-------------------|
| Flash | `now + 15 minutes` | `2 hours` |
| Intraday | `now + 4 hours` | `24 hours` |
| Weekly event | `now + 7 days` | `48 hours` |

(Adjust to your chain’s `minBettingWindow` / `minResolutionWindow` on the deployed factory.)

## Off-chain mask construction (Python / JS)

```python
# 4-outcome "any ticker up" style ticket: user backs options 0 and 2
ticket = (1 << 0) | (1 << 2)  # 0b0101 = 5

# Resolver later: winning bitmask if all four were true
full_set = (1 << 4) - 1       # 0b1111 = 15 (requires n < 256)
```

The same shapes apply to `placeBet(uint256 ticketMask, uint256 amount)` and `resolve(uint256 winningMask)` calldata.

## Related

- [`ADR-0010-IMPLEMENTATION.md`](ADR-0010-IMPLEMENTATION.md) — unified V3 protocol (enumerated + freeform modes)
- [`ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md) — enumerated policy math and limits
- [`PARAMUTUEL-V3-GAS.md`](PARAMUTUEL-V3-GAS.md) — measured gas on the current contracts
