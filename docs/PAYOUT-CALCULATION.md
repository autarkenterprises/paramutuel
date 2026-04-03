# Payout calculation (human-readable specification)

This document describes how **collateral token amounts** are computed when a wager finalizes, for:

1. **Protocol v1** — `ParamutuelWager` (single winning **outcome index**).
2. **Protocol v2** — `ParamutuelWagerV2` (bitmask **tickets** and **payoff policies**; ADR-0008).

**Source layout:** v1 is on `master`. The v2 contract may live on branch `experiment/adr-0008-multi-winner-v2` until merged; the Part B formulas match that implementation.

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

- Contracts: `src/ParamutuelWager.sol`; `src/ParamutuelWagerV2.sol` (v2 branch; see note at top)
- Machine / API context: [`MACHINE.md`](MACHINE.md)
- v2 prototype docs (on branch `experiment/adr-0008-multi-winner-v2`): `docs/ADR-0008-IMPLEMENTATION.md`, ADR-0008 in `research/adr/`
