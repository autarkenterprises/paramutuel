# ADR-0008 implementation notes (v2 contracts)

**Branch:** `experiment/adr-0008-multi-winner-v2` (canonical line for all v2 work until merge to `master`)  
**Status:** Prototype — Solidity + Foundry tests; v1 `ParamutuelFactory` / `ParamutuelWager` on `master` unchanged. This branch is periodically merged **from** `master` for site/dApp/indexer shell updates while v2 contracts and tests live here.

## Rationale

ADR-0008 calls for **versioned** contracts instead of mutating deployed v1. This branch adds:

- `src/ParamutuelWagerV2.sol` — bitmask **tickets** over base options; resolver submits a **winning set** as `uint256 winningMask` (bit *i* ⇔ option *i* is true).
- `src/ParamutuelFactoryV2.sol` — creates v2 wagers with an immutable **`PayoffPolicy`** and optional **`policyParam`** (used for `AT_LEAST_K`). Validates **`policyParam`** and **seed ticket masks** before `new ParamutuelWagerV2` (`InvalidPolicyParam`, `BadSeedConfig`) so invalid creates fail cheaply and never deploy a wager that would revert on seeding.

Settlement iterates **`_usedMasks`** — the distinct ticket masks that received stake — so gas is **O(number of distinct tickets)**, bounded by `MAX_DISTINCT_TICKETS` (1024). This avoids enumerating `2^n` subsets.

## Encoding

- **Options:** `n` labels, indices `0 … n-1`, `n ≤ 256` in the wager (factory caps at **64** to match practical gas).
- **Ticket mask:** non-zero `uint256` with bits only below `n` (`mask >> n == 0`).
- **Winning mask:** same constraints; for `SINGLE_WINNER` exactly one bit set.

## Payoff policies

| Policy | Ticket wins when | Winning pool / weights |
|--------|------------------|-------------------------|
| `SINGLE_WINNER` | Ticket has exactly one bit **and** `T == W`; resolver’s `W` must be a single bit. | Same as v1: sum of stakes on winning tickets; claim ∝ stake. |
| `ANY_OF` | `(T & W) != 0` | Sum of stakes on all winning tickets; claim ∝ stake. |
| `EXACT_SET` | `T == W` | Sum of stakes on tickets equal to `W`; claim ∝ stake. |
| `AT_LEAST_K` | `popcount(T & W) >= k` with `k = policyParam` | Sum of stakes on qualifying tickets; claim ∝ stake. |
| `WEIGHTED_OVERLAP` | `(T & W) != 0` | **Partial credit:** each ticket contributes **weight** `stake * popcount(T & W)`; `totalWinningUnits` is the sum of weights; claim gets `(weight * netPot) / totalWinningUnits` per ticket. |

**Overlap semantics:** Under `ANY_OF` / `AT_LEAST_K` / `WEIGHTED_OVERLAP`, a ticket that hits multiple true outcomes is still **one** ticket — it does not “double count” outcomes except under `WEIGHTED_OVERLAP`, where **more overlap ⇒ higher weight** (intentional partial payout curve).

**Exact-set vs overlap:** Under `EXACT_SET`, only bettors who staked **exactly** the resolved set participate in the winner pool; overlapping subsets (e.g. `{A}` when `W={A,B}`) **lose** — expected for “you must call the full combination” markets. Product phrase **“all of these outcomes”** means **exactly this set** (`T == W`), not “all my picks are true” (`T ⊆ W`); the latter is **out of scope** for v2 unless added as a new policy in a follow-up ADR.

## Resolver constraints

- `resolve(winningMask)` **reverts** with `NoWinningStake` if no ticket qualifies under the policy. This avoids a resolved state with zero claimable winners (resolver must pick a `W` that matches at least one ticket).

## Indexer / API / dApp (not done on this branch)

Planned fields (for a follow-up PR):

- `payoff_policy`, `policy_param`, `winning_mask` (or `winning_set_bits`), `ticket_mask` on bet rows instead of scalar `outcome_index`.
- Replay of `BetPlaced(bettor, ticketMask, amount)` and `Resolved(winningMask)`.

## Security / limits

- **Distinct tickets:** cap 1024 per wager to limit resolve/claim loops.
- **Options:** factory max 64 outcomes.
- **Audits:** not performed; **do not use in production** without review.

## Tests

`forge test --match-contract ParamutuelV2Test` covers single-winner parity, `ANY_OF` split, `EXACT_SET` exclusion, `AT_LEAST_K`, `WEIGHTED_OVERLAP` rounding, retract refunds, and a small fuzz on pot conservation.

## Related

- [`PAYOUT-CALCULATION.md`](PAYOUT-CALCULATION.md) — human-readable fee + claim formulas (v1 and v2)
- [`research/adr/ADR-0008-multi-winner-and-settlement-generalization.md`](../research/adr/ADR-0008-multi-winner-and-settlement-generalization.md)
- [`ADR-0008-GAS.md`](ADR-0008-GAS.md) — gas profile and how to regenerate
- [`ADR-0008-TEMPLATES.md`](ADR-0008-TEMPLATES.md) — product templates + `WagerV2Masks` helpers
- `src/libraries/WagerV2Masks.sol` — bitmask utilities for tickets
- `test/ParamutuelV2Extensive.t.sol` — lifecycle / policy matrix tests
- `test/ParamutuelV2Gas.t.sol` — `gasleft()` logs + scaling check
- `script/profile_v2_gas.sh` — `forge test ... --gas-report` wrapper
