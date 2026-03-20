# Checkpoint 5 Implementation: Odds Calculator Spec (dApp + Service)

Status: In progress  
Owner: dApp + Service + Data tracks  
Linked roadmap: `research/execution-roadmap.md` (Checkpoint 5)

## Objective

Provide users with transparent, actionable payout previews:

- current odds proxy per outcome
- expected payout for entered bet size
- preview of odds impact after hypothetical bet

---

## 1) Definitions

Let:

- `P` = current `totalPot`
- `f` = `totalFeeBps`
- `B` = `BPS_DENOMINATOR = 10_000`
- `T_i` = current total stake on outcome `i`
- `x` = user hypothetical bet size on outcome `i`

Net pot function:

- `net(P) = P - floor(P * f / B)`

---

## 2) Current Implied Payout Multiple (if outcome i wins now)

If `T_i > 0`:

- `multiple_i = net(P) / T_i`

Display format:

- as decimal multiple (e.g., `1.84x`)
- and implied profit multiple (`multiple_i - 1`)

If `T_i == 0`, display `N/A` (no current stake on outcome).

---

## 3) Expected Payout for Hypothetical Bet x on Outcome i

Post-bet pot and outcome total:

- `P' = P + x`
- `T_i' = T_i + x`

Expected payout if outcome `i` wins:

- `payout_preview = floor(x * net(P') / T_i')`

Expected net profit:

- `profit_preview = payout_preview - x`

---

## 4) Odds Impact Preview

Show before/after:

- `multiple_before = net(P) / T_i` (if `T_i > 0`)
- `multiple_after  = net(P') / T_i'`
- `delta = multiple_after - multiple_before`

Interpretation:

- Large positive `x` on a thin outcome tends to reduce that outcome’s future multiple.

---

## 5) Rounding and Precision Policy

- Match Solidity integer math behavior (`floor` semantics).
- UI should disclose:
  - “Preview uses integer rounding and may differ by small amount after concurrent bets.”
- Recompute on every state refresh and before tx confirmation.

---

## 6) Edge Cases

- Market not open: disable betting preview.
- `x <= 0`: invalid input.
- `T_i == 0`:
  - no current multiple
  - post-bet preview still computable from `T_i' = x`.
- High fee + tiny pools: warn about low net return.

---

## 7) Shared Implementation Strategy

- Implement calculator as a shared pure library used by:
  - dApp frontend
  - service backend
- Keep a common test vector file to ensure parity.

---

## 8) Test Vectors (minimum)

### Vector A (binary pool)

- `P = 400`, `f = 500`, `T_yes = 100`, `T_no = 300`, `x = 40` on YES
- `net(P) = 380`
- `multiple_yes_before = 3.8`
- `P' = 440`, `net(P') = 418`
- `T_yes' = 140`
- `payout_preview = floor(40 * 418 / 140) = 119`

### Vector B (multi-outcome)

- `P = 350`, `f = 500`, `T_2 = 200`, `x = 25` on outcome 2
- `net(P) = 332`
- `multiple_before = 332 / 200 = 1.66`
- `P' = 375`, `net(P') = 357`
- `T_2' = 225`
- `payout_preview = floor(25 * 357 / 225) = 39`

### Vector C (zero-liquidity outcome)

- `P = 100`, `f = 200`, `T_i = 0`, `x = 10`
- `current multiple = N/A`
- `P' = 110`, `net(P') = 108`
- `T_i' = 10`
- `payout_preview = floor(10 * 108 / 10) = 108`

---

## Exit Criteria

- Shared calculator implemented in dApp + service.
- All test vectors pass in both implementations.
- UI clearly communicates preview assumptions and rounding caveat.

