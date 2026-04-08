# Payout calculation (human-readable specification)

This document describes how **collateral token amounts** are computed when a wager finalizes, for:

1. **Protocol v1** — `ParamutuelWager` (single winning **outcome index**).
2. **Protocol v2** — `ParamutuelWagerV2` (bitmask **tickets** and **payoff policies**; ADR-0008).

**Source layout:** v1 ships from `master`. v2 (`ParamutuelWagerV2`, `ParamutuelFactoryV2`) is developed on **`experiment/adr-0008-multi-winner-v2`** until merged after certification ([`docs/ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md)). Part B matches `src/ParamutuelWagerV2.sol` on that branch.

All amounts are in the wager’s **ERC-20 raw units** (wei of that token). Arithmetic uses **integer division**; rounding favors staying **at or below** the true rational value, so a few wei of collateral can remain in the contract after all claims.

---

## Shared concepts (v1 and v2)

### Pot and fees

- **`totalPot`** — Sum of every stake ever recorded on the wager while it was **Open** (including seeded bets from the factory, if any).
- **`totalFeeBps`** — Sum of all fee basis points configured at creation (treasury + extra recipients). **`BPS_DENOMINATOR` = 10_000** (100% = 10_000 bps).
- **When** the wager leaves **Open** via **`resolve`**, **`retract`**, or **`expire`**, fees are charged **once** (idempotent if called again internally):

  \[
  \texttt{totalFees} = \left\lfloor \frac{\texttt{totalPot} \times \texttt{totalFeeBps}}{10\_000} \right\rfloor
  \]

- **Net pot** (what bettors compete for after fees):

  \[
  \texttt{netPot} = \texttt{totalPot} - \texttt{totalFees}
  \]

### Fee split (recipients)

`totalFees` is split among `feeRecipients` in proportion to `feeBps[i]`:

- For each recipient except the **last**,  
  \(\texttt{slice}_i = \left\lfloor \dfrac{\texttt{totalFees} \times \texttt{feeBps}[i]}{\texttt{totalFeeBps}} \right\rfloor\).
- The **last** recipient receives **`totalFees` minus** the sum of the earlier slices (so rounding dust accrues to the last recipient).

Those slices are credited to **`feeBalances[recipient]`** and withdrawn with **`withdrawFees()`** (separate from bettor **`claim()`**).

### Claims (bettors)

- Each address may call **`claim()` at most once** (`hasClaimed`).
- The contract transfers **`paid`** collateral to `msg.sender` as computed below.

---

## Part A — v1 (`ParamutuelWager`)

### Bets

- Each bet is on a single **outcome index** \(i\) in `0 … outcomesCount-1`.
- **`bets[bettor][i]`** — that bettor’s total stake on outcome \(i\).
- **`userTotalBet[bettor]`** — sum of `bets[bettor][*]` across all outcomes.

### Resolved (single winner)

The resolver calls **`resolve(outcomeIndex)`** with one winning index **`w`**.

- **`totalWinningStake`** \(=\) **`outcomeTotals[w]`** — total stake on the winning outcome (fixed at resolve time).

**Bettor payout** (state **Resolved**):

- Let **`userWinStake = bets[bettor][w]`**.
- If **`userWinStake == 0`**, `claim` reverts (nothing to claim as a winner).

\[
\texttt{paid} = \left\lfloor \frac{\texttt{userWinStake} \times \texttt{netPot}}{\texttt{totalWinningStake}} \right\rfloor
\]

**Interpretation:** all winning stakes share **`netPot`** in proportion to how much each bettor placed on the winning outcome. Losers forfeit their stake to that pool (minus fees).

**Edge case:** If **`totalWinningStake == 0`** (nobody staked on `w`), `claim` for a “winner” path reverts; the economic situation is degenerate and should be avoided operationally.

### Retracted or expired (refund)

After **`retract()`** or **`expire()`**, state is **Retracted**. Every bettor with **`userTotalBet > 0`** may claim a **pro-rata refund** of **`netPot`** (not of `totalPot`):

\[
\texttt{paid} = \left\lfloor \frac{\texttt{userTotalBet} \times \texttt{netPot}}{\texttt{totalPot}} \right\rfloor
\]

**Interpretation:** fees are taken from the pot first; the remaining **`netPot`** is split in proportion to each bettor’s **original** stake relative to **`totalPot`**. This matches “refund minus fee share” on the gross stakes.

---

## Part B — v2 (`ParamutuelWagerV2`)

*(Contract: `src/ParamutuelWagerV2.sol` — on `experiment/adr-0008-multi-winner-v2` until merged to `master`.)*

### Tickets and winning set

- There are **`numOptions`** base options, indexed `0 … numOptions-1`.
- A **ticket** is a non-zero bitmask **`T`**: bit \(i\) is set iff the ticket includes option \(i\). Only bits below **`numOptions`** are valid.
- The resolver calls **`resolve(winningMask)`** with bitmask **`W`**: bit \(i\) set means option \(i\) is in the **true / winning set**.

Stake is pooled **per ticket mask**: **`ticketPoolTotal[T]`** is the sum of all stakes on ticket **`T`**. **`bets[bettor][T]`** is that bettor’s stake on **`T`**.

### When is a ticket a “winner”?

Let **`overlap = T & W`** (bits in both ticket and truth). Define **`popcount(x)`** = number of set bits in **`x`**.

| Policy | Ticket **`T`** wins if … |
|--------|-------------------------|
| **SINGLE_WINNER** | **`W`** has exactly one bit, **`T`** has exactly one bit, and **`T == W`**. |
| **ANY_OF** | **`overlap ≠ 0`** (any shared true option). |
| **EXACT_SET** | **`T == W`** (ticket equals the full resolved set). |
| **AT_LEAST_K** | **`popcount(overlap) ≥ policyParam`** (integer **`k`** set at creation). |
| **WEIGHTED_OVERLAP** | **`overlap ≠ 0`** (same overlap test as “in the money”; payout uses weights below). |

**Product wording:** When copy says **“all of these outcomes,”** it maps to **EXACT_SET** above — the ticket must match the resolver’s set **exactly** (`T == W`). A different rule — **win if every selected option is among the true outcomes** (`T ⊆ W`, i.e. “my picks are all winners” without requiring `T == W`) — is **not** in v2; treat it as future scope and document explicitly if product needs it.

If **`resolve`** would yield **no** winning ticket with positive pool, the call **reverts** (`NoWinningStake`).

### Denominator: `totalWinningUnits`

At **`resolve`**, the contract sums over every **distinct** ticket mask that ever received stake (`usedMasks`):

- For policies **other than** **WEIGHTED_OVERLAP**, for each winning ticket **`T`** with pool **`P = ticketPoolTotal[T]`**:

  \[
  \texttt{totalWinningUnits} \mathrel{+}= P
  \]

- For **WEIGHTED_OVERLAP**, for each winning **`T`** with pool **`P`** and overlap **`O = T & W`**:

  \[
  \texttt{totalWinningUnits} \mathrel{+}= P \times \texttt{popcount}(O)
  \]

So for **ANY_OF** / **EXACT_SET** / **AT_LEAST_K** / **SINGLE_WINNER**, the denominator is the **sum of winning pools** (each distinct winning mask counts once with its total stake). For **WEIGHTED_OVERLAP**, stakes are weighted by **how many** winning options the ticket hits.

### Bettor payout (Resolved)

Let **`denom = totalWinningUnits`** (stored on-chain). For each ticket mask **`T`** the bettor used, with stake **`amt = bets[bettor][T]`**, if **`T`** wins against **`W`**:

- **Non–WEIGHTED_OVERLAP policies:**

  \[
  \texttt{paid} \mathrel{+}= \left\lfloor \frac{\texttt{amt} \times \texttt{netPot}}{\texttt{denom}} \right\rfloor
  \]

- **WEIGHTED_OVERLAP**, with **`O = T & W`**:

  \[
  \texttt{weight} = \texttt{amt} \times \texttt{popcount}(O)
  \]
  \[
  \texttt{paid} \mathrel{+}= \left\lfloor \frac{\texttt{weight} \times \texttt{netPot}}{\texttt{denom}} \right\rfloor
  \]

Summed over all of the bettor’s tickets. If the sum is **0** (e.g. only losing tickets), **`claim`** reverts.

**Interpretation:**

- **ANY_OF** / **EXACT_SET** / **AT_LEAST_K** / **SINGLE_WINNER**: same idea as v1 — **`netPot`** is split among **winning stakes** in proportion to each **winning ticket’s pool share**; each bettor’s share is proportional to their stake on each winning mask.
- **WEIGHTED_OVERLAP**: larger **overlap** between **`T`** and **`W`** multiplies that ticket’s contribution to the denominator and to the bettor’s claim (partial credit).

#### Worked example (`ANY_OF`)

Assume **fees are 0**. All stakes below are **integer raw token units** as on-chain (see [Pot and fees](#pot-and-fees) above).

- Five base options **A–E** (indices `0 … 4`).
- Resolver sets **`W = {A, C, E}`**.
- **Alice** stakes **100** on ticket **`{A, C}`** and **50** on **`{E, D}`**. Under **ANY_OF**, both tickets **win**: the first overlaps **A** and **C**; the second overlaps **E** (even though **D** is not in **`W`**).
- **Bob** stakes **200** on ticket **`{A}`** only (wins).
- **Carol** stakes **150** on **`{B}`** (loses; no overlap with **`W`**).

Then **`totalPot`** = 100 + 50 + 200 + 150 = **500**, and with no fees **`netPot`** = **500**.

**`totalWinningUnits`** counts only **winning** ticket pools: 100 + 50 + 200 = **350** (Carol’s losing pool is excluded).

Per-ticket claims (integer division, then summed per bettor):

- **Alice:** ⌊100 × 500 / 350⌋ + ⌊50 × 500 / 350⌋ = **142** + **71** = **213**.
- **Bob:** ⌊200 × 500 / 350⌋ = **285**.

**Alice + Bob** receive **498** of **`netPot`**; **2** raw units remain in the contract as **rounding dust** from flooring each term. **Carol** has no winning ticket, so **`claim()`** reverts (`NothingToClaim`) in the resolved-winner path.

**On-chain identity:** The figures **142**, **71**, **213**, **285**, and **2** match `claim` when the stakes (**100**, **50**, **200**, **150**) are the **actual** raw token amounts passed to `placeBet` (e.g. **100 wei** of a token). If you multiply every stake and thus **`totalPot`** by **`10^18`**, each term is still \(\lfloor \texttt{amt} \times \texttt{netPot} / \texttt{denom} \rfloor\) in **wei**; you **cannot** obtain Alice’s payout by simply multiplying **213** by **`10^18`** — the floored division is applied at full precision. Regression: **`testAnyOf_documentationWorkedExample_fiveOutcomes`** in **`test/ParamutuelV2Extensive.t.sol`**.

### Retracted or expired (refund)

Identical formula to **v1**:

\[
\texttt{paid} = \left\lfloor \frac{\texttt{userTotalBet} \times \texttt{netPot}}{\texttt{totalPot}} \right\rfloor
\]

---

## Summary table

| Final state | v1 (`ParamutuelWager`) | v2 (`ParamutuelWagerV2`) |
|-------------|------------------------|---------------------------|
| **Resolved** | Share **`netPot`** by stake on **one** winning outcome index. | Share **`netPot`** by **policy-specific** winning tickets and (for weighted) overlap scores. |
| **Retracted / Expired** | Pro-rata **`netPot`** by **`userTotalBet / totalPot`**. | Same. |
| **Fees** | Once at finalize; split by **bps**; last recipient gets remainder. | Same. |

---

## References

- Contracts: `src/ParamutuelWager.sol`, `src/ParamutuelWagerV2.sol`
- Machine / API context: [`MACHINE.md`](MACHINE.md)
- v2 policies, gas, templates: [`ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md)
- ADR: `research/adr/ADR-0008-multi-winner-and-settlement-generalization.md`
