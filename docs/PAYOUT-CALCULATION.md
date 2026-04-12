# Payout calculation (human-readable specification)

This document describes how **collateral token amounts** are computed when a wager finalizes, for:

1. **Protocol v1** — `ParamutuelWager` (single winning **outcome index**).
2. **Protocol v2** — `ParamutuelWagerV2` (bitmask **tickets** and **payoff policies**; ADR-0008).

**Source layout:** v1 and v2 both live on `master`: `ParamutuelWager` / `ParamutuelFactory` and `ParamutuelWagerV2` / `ParamutuelFactoryV2` under `src/`. Integration history for v2 tracked on branch **`experiment/adr-0008-multi-winner-v2`**. Part B matches `src/ParamutuelWagerV2.sol` in-tree ([`docs/ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md)).

All amounts are in the wager’s **ERC-20 raw units**: the token’s **smallest indivisible unit** (for **ETH** / **WETH**, “wei”; for **USDC**, \(10^{-6}\) of a dollar — i.e. **`1e6` raw units = 1 USDC**). Arithmetic uses **integer division**; each payout line is floored, so **unclaimed collateral** after every winner has claimed is **rounding dust** only.

**Production expectation:** That dust is **tiny in human terms** — on the order of **a few smallest units per floored division** (many lines across many bettors can add up, but still **far below one cent** for USDC or **far below one finney** for 18‑decimal ETH), **not** a percentage of **`netPot`**. Losing **multiple whole tokens** (e.g. 3 **USDC** or **ETH**) out of a **500**‑unit pot would **not** come from this rounding; it would imply misconfiguration, fees, or a bug, and should be investigated separately.

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

*(Contract: `src/ParamutuelWagerV2.sol`.)*

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

### Glossary: “any of” / “all of” (product copy → policy)

| Colloquial intent | Formal idea | Policy to use | On-chain win test |
|-------------------|-------------|---------------|-------------------|
| **“Any of these”** / at least one pick is true | Overlap with **`W`** | **ANY_OF** | **`(T & W) ≠ 0`** |
| **“Exactly this combination”** / full slate | Ticket equals the resolver’s full set | **EXACT_SET** | **`T == W`** |
| **“All my picks are winners”** (each picked option is in **`W`**) | **Subset-of-truth** **`T ⊆ W`** (equivalently **`T & W == T`**) | **No dedicated enum value** — see below | — |
| **Legacy single outcome** | One true option, one-bit tickets | **SINGLE_WINNER** | **`T == W`**, single-bit **`W`** |

**Disambiguating “all of”:** Marketing phrase **“all of these outcomes”** usually means **EXACT_SET** — the bettor’s ticket must match **`W` exactly** (`T == W`). That is **stricter** than **“every option I picked is among the true ones”** (**`T ⊆ W`**): e.g. **`T = {A}`** and **`W = {A,B}`** satisfies **`T ⊆ W`** but **fails** **EXACT_SET**.

**Subset-of-truth (`T ⊆ W`) without a new policy:** The baseline v2 enum does **not** include **`ALL_PICKS_TRUE`**-style semantics. Practical options:

1. **Uniform ticket size:** If **every** stake uses a mask with **exactly `k`** bits (enforce in UI / market rules), then **`AT_LEAST_K`** with **`policyParam = k`** matches **`T ⊆ W`** for those tickets: **`popcount(T & W) ≥ k`** with **`popcount(T) = k`** iff every bit of **`T`** appears in **`W`**.
2. **Variable ticket sizes:** A **single** global **`k`** cannot express per-ticket subset semantics for all masks. Split markets by ticket shape, or specify a **new `PayoffPolicy`** in a follow-up ADR.

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

Assume **fees are 0**. The numbers **100**, **50**, … are **only** illustrative **raw integers** (they could mean **100 wei** in a test, or **100** of any token’s smallest unit). They are **not** “100 ETH” or “100 USDC” unless you scale the whole worked example consistently.

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

**Alice + Bob** receive **498** of **`netPot`**; **2** of the **same smallest units** remain in the contract as **rounding dust** (in the toy table, that is literally **2 wei** if stakes were **100 wei**, **50 wei**, … — **not** 2 whole USDC or 2 ETH). **Carol** has no winning ticket, so **`claim()`** reverts (`NothingToClaim`) in the resolved-winner path.

**On-chain identity:** The figures **142**, **71**, **213**, **285**, and **2** match `claim` when the stakes (**100**, **50**, **200**, **150**) are the **actual** raw amounts passed to `placeBet` (as in the Foundry regression). If you use **human-scale** stakes (e.g. **`500e6`** raw for **500 USDC**), **`netPot`** is also in **raw** form; Alice’s lines are still \(\lfloor \texttt{amt} \times \texttt{netPot} / \texttt{denom} \rfloor\) — the **remainder** left on the contract stays **dust on the smallest-unit scale**, not “a few dollars” or “a few ETH.” You **cannot** derive payouts by multiplying the toy integers **213** × **`10^6`** unless you repeat the same floor math on full-precision integers. Regression: **`testAnyOf_documentationWorkedExample_fiveOutcomes`** in **`test/ParamutuelV2Extensive.t.sol`**.

#### Worked example (`EXACT_SET`)

Same **raw integer** convention as the **ANY_OF** example above (toy amounts in **smallest token units**; see the **ERC-20 raw units** and **rounding dust** paragraphs at the top of this document).

- Three base options **A, B, C** (indices `0 … 2`). Ticket masks: **`{A}=1`**, **`{B}=2`**, **`{C}=4`**, **`{A,C}=5`**, **`{A,B,C}=7`**.
- **`payoffPolicy = EXACT_SET`**, **`policyParam = 0`**.
- Resolver sets **`W = {A, C}`**, i.e. **`winningMask = 5`**.

Under **EXACT_SET**, a ticket **`T`** wins **only if** **`T == W`**. Overlap is **not** enough: a ticket on **`{A}`** or on the full **`{A,B,C}`** **loses** because those masks are **not** exactly **`5`**.

| Bettor | Ticket (set) | Mask | Stake (raw) | vs `W = {A,C}` |
|--------|----------------|------|-------------|----------------|
| Alice | `{A, C}` | **5** | **60** | **Win** (`5 == 5`) |
| Bob | `{A}` | **1** | **100** | **Lose** (`1 ≠ 5`) |
| Carol | `{A, B, C}` | **7** | **140** | **Lose** (`7 ≠ 5`) |
| Dave | `{A, C}` | **5** | **40** | **Win** (`5 == 5`) |

**`totalPot`** = 60 + 100 + 140 + 40 = **340**; with **no fees**, **`netPot` = 340**.

Only one **distinct winning mask** appears: **`5`**. Its pool is **`ticketPoolTotal[5]`** = 60 + 40 = **100**, so **`totalWinningUnits` = 100**. Losers’ stakes remain in **`netPot`** but do **not** enter the denominator — they are effectively forfeit to the winning side of the pool (same parimutuel idea as v1 losers funding winners).

**Claims** (each winning line: \(\lfloor \texttt{amt} \times \texttt{netPot} / \texttt{denom} \rfloor\)):

- **Alice:** ⌊60 × 340 / 100⌋ = **204**.
- **Dave:** ⌊40 × 340 / 100⌋ = **136**.

**204 + 136 = 340 = `netPot`**: in this table the floors **close exactly** (no dust). **Bob** and **Carol** have **no** winning ticket, so **`claim()`** reverts (`NothingToClaim`).

**Contrast with `ANY_OF`:** If this were **`ANY_OF`** and the same **`W`**, tickets **`{A}`** and **`{A,B,C}`** would **win** (non-zero overlap); under **`EXACT_SET`** they **lose** because they did not name **exactly** **`{A,C}`**.

Regression: **`testExactSet_documentationWorkedExample_threeOutcomes`** in **`test/ParamutuelV2Extensive.t.sol`**.

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
