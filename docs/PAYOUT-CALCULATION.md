# Payout calculation (human-readable specification)

This document describes how **collateral token amounts** are computed when a wager finalizes, for:

1. **Legacy v1** (historical) — single winning **outcome index**, single-winner pool split. Retained below for the simplest case; superseded by the V3 enumerated `SINGLE_WINNER` policy.
2. **Enumerated mode** (ADR-0008 economics, now implemented by `ParamutuelWagerV3` with `MODE()==0`) — bitmask **tickets** and **payoff policies**.

**Source layout:** the canonical contracts are `src/ParamutuelWagerV3.sol` + `src/ParamutuelFactoryV3.sol` (ADR-0010). Part B below matches the enumerated-mode logic in `ParamutuelWagerV3` ([`docs/ADR-0010-IMPLEMENTATION.md`](ADR-0010-IMPLEMENTATION.md), [`docs/ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md) for policy semantics). Freeform-mode payouts (`MODE()==1`) follow the single-winner split over `answerId` pools — see [`ADR-0009-IMPLEMENTATION.md`](ADR-0009-IMPLEMENTATION.md).

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

## Part B — Enumerated mode (`ParamutuelWagerV3`, ADR-0010)

*(Contract: `src/ParamutuelWagerV3.sol`, `MODE()==0`. Semantics are identical to the deleted `ParamutuelWagerV2` of ADR-0008.)*

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

### Worked examples

All five examples use **fees = 0** and **raw integer** stakes (same convention as the top-of-document **ERC-20 raw units** paragraph). Each example is pinned by a Foundry regression test named `test<Policy>_documentationWorkedExample_*` in **`test/ParamutuelV3Enumerated.t.sol`** — if you change any stake or payout figure below, the test must be updated to match.

#### Worked example (`SINGLE_WINNER`) — 3 outcomes, split-stake bettor

- Three base options **A, B, C** (indices `0 … 2`; masks **`{A}=1`**, **`{B}=2`**, **`{C}=4`**).
- **`payoffPolicy = SINGLE_WINNER`**, **`policyParam = 0`**.
- Resolver sets **`W = {B}`**, i.e. **`winningMask = 2`**. Because `SINGLE_WINNER` requires `popcount(W) == 1`, a single-bit `W` is mandatory and all tickets must also be single-bit.

| Bettor | Ticket (set) | Mask | Stake (raw) | vs `W = {B}` |
|--------|----------------|------|-------------|----------------|
| Alice | `{A}` | **1** | **100** | **Lose** (`1 ≠ 2`) |
| Alice | `{B}` | **2** | **50** | **Win** (`2 == 2`) |
| Bob | `{B}` | **2** | **200** | **Win** (`2 == 2`) |
| Carol | `{C}` | **4** | **150** | **Lose** (`4 ≠ 2`) |

Note Alice holds **two tickets** — one losing, one winning. Both stakes contribute to **`totalPot`** and to fees (if any), but **only** the winning stake contributes to **`totalWinningUnits`** and to Alice's claim.

**`totalPot`** = 100 + 50 + 200 + 150 = **500**; **`netPot`** = **500**.

Only one distinct **winning** mask appears: **`2`**. Its pool is **`ticketPoolTotal[2]`** = 50 + 200 = **250**, so **`totalWinningUnits` = 250**.

**Claims** (\(\lfloor \texttt{amt} \times \texttt{netPot} / \texttt{denom} \rfloor\)):

- **Alice** (only her winning `{B}` stake counts): ⌊50 × 500 / 250⌋ = **100**.
- **Bob:** ⌊200 × 500 / 250⌋ = **400**.

**100 + 400 = 500 = `netPot`** — the floors close exactly, no dust. Alice recovers her winning stake plus half of Carol's forfeited stake; her losing **`{A}`** stake is gone. **Carol** and **Alice-on-losing-ticket** paths never trigger a separate revert because `claim` aggregates **all** of a bettor's tickets in one call — Alice's single `claim()` pays **100** total; Carol's single `claim()` reverts with `NothingToClaim` because none of her tickets won.

**Contrast with `ANY_OF`:** Under `SINGLE_WINNER`, **multi-bit** tickets (e.g. `{A, B}`) are **rejected at `placeBet`** with `InvalidTicketMask`. Under `ANY_OF`, the same multi-bit tickets are legal and would win so long as overlap with `W` is non-empty.

Regression: **`testSingleWinner_documentationWorkedExample_threeOutcomes`** in **`test/ParamutuelV3Enumerated.t.sol`**.

#### Worked example (`ANY_OF`) — 5 outcomes, multi-bit tickets

The numbers **100**, **50**, … are **only** illustrative **raw integers** (they could mean **100 wei** in a test, or **100** of any token's smallest unit). They are **not** "100 ETH" or "100 USDC" unless you scale the whole worked example consistently.

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

**On-chain identity:** The figures **142**, **71**, **213**, **285**, and **2** match `claim` when the stakes (**100**, **50**, **200**, **150**) are the **actual** raw amounts passed to `placeBet` (as in the Foundry regression). If you use **human-scale** stakes (e.g. **`500e6`** raw for **500 USDC**), **`netPot`** is also in **raw** form; Alice's lines are still \(\lfloor \texttt{amt} \times \texttt{netPot} / \texttt{denom} \rfloor\) — the **remainder** left on the contract stays **dust on the smallest-unit scale**, not "a few dollars" or "a few ETH." You **cannot** derive payouts by multiplying the toy integers **213** × **`10^6`** unless you repeat the same floor math on full-precision integers. Regression: **`testAnyOf_documentationWorkedExample_fiveOutcomes`** in **`test/ParamutuelV3Enumerated.t.sol`**.

#### Worked example (`EXACT_SET`) — 3 outcomes, strict match

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

Regression: **`testExactSet_documentationWorkedExample_threeOutcomes`** in **`test/ParamutuelV3Enumerated.t.sol`**.

#### Worked example (`AT_LEAST_K`) — 4 outcomes, `k = 2`

This example is the decisive one for understanding `AT_LEAST_K`: it shows that the test is **not** "at least `k` of the ticket's picks are in `W`" (i.e. subset-like logic), it is **not** "the ticket must lie inside `W`", and ticket size itself is irrelevant — only **`popcount(T & W)`** is compared against `k`.

- Four base options **A, B, C, D** (masks **`{A}=1`**, **`{B}=2`**, **`{C}=4`**, **`{D}=8`**).
- **`payoffPolicy = AT_LEAST_K`**, **`policyParam = 2`**.
- Resolver sets **`W = {A, B, C}`**, i.e. **`winningMask = 7`**.

| Bettor | Ticket (set) | Mask | Stake (raw) | `popcount(T & W)` | Outcome |
|--------|----------------|------|-------------|--------------------|---------|
| Alice | `{A, B}` | **3** | **100** | **2** (`{A,B}`) | **Win** (≥ 2) |
| Bob | `{A, D}` | **9** | **60** | **1** (`{A}`) | **Lose** (< 2) — 2-bit ticket, but only one bit in **`W`** |
| Carol | `{A, B, C}` | **7** | **80** | **3** (`{A,B,C}`) | **Win** |
| Dave | `{B, C, D}` | **14** | **50** | **2** (`{B,C}`) | **Win** — extra bit **`D ∉ W`** does **not** disqualify |

**`totalPot`** = 100 + 60 + 80 + 50 = **290**; **`netPot`** = **290**.

Three **distinct winning masks** appear: **`3`** (pool 100), **`7`** (pool 80), **`14`** (pool 50). So **`totalWinningUnits`** = 100 + 80 + 50 = **230**. Bob's losing pool is excluded.

**Claims** (\(\lfloor \texttt{amt} \times \texttt{netPot} / \texttt{denom} \rfloor\)):

- **Alice:** ⌊100 × 290 / 230⌋ = ⌊29000 / 230⌋ = **126**.
- **Carol:** ⌊80 × 290 / 230⌋ = ⌊23200 / 230⌋ = **100**.
- **Dave:** ⌊50 × 290 / 230⌋ = ⌊14500 / 230⌋ = **63**.

**Sum = 126 + 100 + 63 = 289**; **dust = 1** left on the contract.

**Reading the matrix:**

- **Bob loses** despite holding a 2-bit ticket — **`T & W = {A}`** has only **one** bit. `AT_LEAST_K` asks about **overlap**, not ticket size or number of picks.
- **Dave wins** despite picking **`D ∉ W`** — his overlap is 2 (`{B,C}`). Extra "wrong" bits do **not** hurt; they only grow the ticket pool and therefore shrink Dave's own relative share (vs. a 2-bit ticket of equal stake landing exactly on `{B,C}`, which would still have overlap 2 and same weight).
- **Alice and Carol** both win but on **different** masks, so they **share** `netPot` with Dave in proportion to their **pool** on each mask.

**Subset-of-truth uniform case:** If every ticket had **exactly `k = 2`** bits (a product rule enforced off-chain), `popcount(T & W) ≥ 2` ⇔ `T ⊆ W`. In this example Alice's `{A,B}` is a subset of **`W`** and Bob's `{A,D}` is not, which is exactly the subset-of-truth distinction. With mixed ticket sizes (Carol's 3-bit, Dave's 3-bit including a D), the subset interpretation breaks down — Dave is **not** a subset of **`W`** yet still wins. This is why **`PAYOUT-CALCULATION.md`** Part B glossary marks subset-of-truth as **"no dedicated enum value"** and only recommends `AT_LEAST_K` for the uniform-ticket case.

Regression: **`testAtLeastK_documentationWorkedExample_fourOutcomes_k2`** in **`test/ParamutuelV3Enumerated.t.sol`**.

#### Worked example (`WEIGHTED_OVERLAP`) — 4 outcomes, partial credit

This example isolates the one effect that makes `WEIGHTED_OVERLAP` different from `ANY_OF`: every winning ticket's contribution to the denominator **and** to its bettor's payout is **multiplied by its overlap size**. Same stake, larger overlap ⇒ larger share.

- Four base options **A, B, C, D** (masks **`{A}=1`**, **`{B}=2`**, **`{C}=4`**, **`{D}=8`**).
- **`payoffPolicy = WEIGHTED_OVERLAP`**, **`policyParam = 0`**.
- Resolver sets **`W = {A, B, C}`**, i.e. **`winningMask = 7`**.
- **Every** bettor stakes **100** so overlap is the **only** variable.

| Bettor | Ticket (set) | Mask | Stake | `popcount(T & W)` | Weight (`stake × overlap`) |
|--------|----------------|------|-------|--------------------|-----------------------------|
| Alice | `{A}` | **1** | **100** | **1** | **100** |
| Bob | `{A, B}` | **3** | **100** | **2** | **200** |
| Carol | `{A, B, C}` | **7** | **100** | **3** | **300** |
| Dave | `{D}` | **8** | **100** | **0** | **0** — overlap is zero, ticket is out of the money |

**`totalPot`** = 100 × 4 = **400**; **`netPot`** = **400**.

**`totalWinningUnits`** = 100 + 200 + 300 + 0 = **600**. Dave contributes **nothing** to the denominator (overlap == 0 short-circuits both the "ticket wins" check and the weight accumulation) but his stake still joins the pot from which winners are paid.

**Claims** under `WEIGHTED_OVERLAP` use **`weight`** (not raw stake) as the numerator:

- **Alice:** ⌊100 × 400 / 600⌋ = ⌊40000 / 600⌋ = **66**.
- **Bob:** ⌊200 × 400 / 600⌋ = ⌊80000 / 600⌋ = **133**.
- **Carol:** ⌊300 × 400 / 600⌋ = ⌊120000 / 600⌋ = **200**.

**Sum = 66 + 133 + 200 = 399**; **dust = 1**. The ratio **66 : 133 : 200** is approximately **1 : 2 : 3** — exactly the overlap ratio — because all three bettors staked the same amount. If Alice had staked **300** instead of 100 (overlap still 1), her weight would be **300** and she would earn the same payout as Carol despite covering only one winning option. That is the whole point of `WEIGHTED_OVERLAP`: stake × specificity.

**Contrast with `ANY_OF`:** Same scenario under `ANY_OF` (all overlap ≥ 1 ⇒ win) would use `totalWinningUnits = 100 + 100 + 100 = 300` and pay each winner ⌊100 × 400 / 300⌋ = **133** — Alice and Carol are indistinguishable despite Carol covering the **entire** winning set. `WEIGHTED_OVERLAP` gives Carol **~3×** Alice's payout; `ANY_OF` gives them the same.

Regression: **`testWeightedOverlap_documentationWorkedExample_fourOutcomes`** in **`test/ParamutuelV3Enumerated.t.sol`**.

### Retracted or expired (refund)

Identical formula to **v1**:

\[
\texttt{paid} = \left\lfloor \frac{\texttt{userTotalBet} \times \texttt{netPot}}{\texttt{totalPot}} \right\rfloor
\]

---

## Part C — Freeform mode (`ParamutuelWagerV3`, `MODE()==1`)

*(ADR-0009 economics, now implemented by `ParamutuelWagerV3` in freeform mode — see [`ADR-0009-IMPLEMENTATION.md`](ADR-0009-IMPLEMENTATION.md) and [`ADR-0010-IMPLEMENTATION.md`](ADR-0010-IMPLEMENTATION.md).)*

### Ticket identity

Freeform wagers have **no** outcomes array. A bet is placed with a UTF-8 string `answer` and is pooled under a `bytes32` **`answerId`**:

\[
\texttt{answerId} = \texttt{keccak256}\bigl(\texttt{0x03} \,\Vert\, \texttt{bytes(answer)}\bigr)
\]

The **`0x03`** prefix is `FREEFORM_ANSWER_DOMAIN` — a domain-separation byte chosen in ADR-0010 so freeform ids cannot collide with unrelated `bytes32` uses in the same contract.

**Exact-byte match:** two bets with even one byte of difference (case, whitespace, Unicode normalization, trailing newline) produce **different** `answerId`s and therefore **different** pools. The contract does **no** canonicalization; off-chain UX is responsible for any normalization policy.

### When is a ticket a "winner"?

The resolver calls **`resolve(winningAnswer)`** with **one** UTF-8 string. Its `answerId` is computed with the same domain byte and compared. A bet wins iff its `answerId` equals the winning id. No policy engine, no partial credit, no `popcount`. If no bet was placed on the winning string, `resolve` reverts with `NoWinningStake`.

### Payout

Identical to **v1** single-winner parimutuel, with `answerId` pools replacing outcome-index pools:

- `totalWinningStake` = sum of all stakes whose `answerId` matches the resolver's.
- For each winning bettor with stake `userWinStake` on the winning id:

  \[
  \texttt{paid} = \left\lfloor \frac{\texttt{userWinStake} \times \texttt{netPot}}{\texttt{totalWinningStake}} \right\rfloor
  \]

Losers (any bettor whose answer does not match) forfeit their stake to the winning pool (minus fees). Retract / expire refunds use the same formula as enumerated mode.

#### Worked example (freeform mode) — case-sensitive answers

The point of this example is to show that **exact UTF-8 bytes** govern the split — "rosebud" and "Rosebud" are two separate pools.

- Proposition: "What was Rosebud?" (freeform wager, `MODE()==1`).
- Fees = 0. Raw integer stakes, same convention as Part B.

| Bettor | Answer (exact bytes) | Stake (raw) | `answerId` vs winner |
|--------|------------------------|-------------|-----------------------|
| Alice | `"rosebud"` | **200** | matches winning id |
| Bob | `"rosebud"` | **100** | matches winning id |
| Carol | `"Rosebud"` | **150** | **different** id (capital `R`) — **loses** |
| Dave | `"a sled"` | **50** | different id — **loses** |

Resolver calls **`resolve("rosebud")`**.

**`totalPot`** = 200 + 100 + 150 + 50 = **500**; **`netPot`** = **500**.

Only one winning `answerId` — the keccak of `0x03 || "rosebud"`. Its pool is **`ticketPoolTotal[that id]`** = 200 + 100 = **300**. So **`totalWinningStake`** = **300**.

**Claims:**

- **Alice:** ⌊200 × 500 / 300⌋ = ⌊100000 / 300⌋ = **333**.
- **Bob:** ⌊100 × 500 / 300⌋ = ⌊50000 / 300⌋ = **166**.

**Sum = 333 + 166 = 499**; **dust = 1** left on the contract. Carol's and Dave's single `claim()` calls each revert with `NothingToClaim`.

**Reading the matrix:**

- **Alice and Bob share** one pool because they sent the same UTF-8 bytes. The contract does not "see" their text — it only sees the two identical `answerId`s.
- **Carol loses** despite being semantically correct (Rosebud *is* the canonical spelling in the film). One byte difference ⇒ one id difference ⇒ separate pool. Any off-chain canonicalization must happen **before** `placeBet`.
- **Dave loses** on a completely different answer; his stake funds the winners like any other parimutuel loser.

Regression: **`testFreeform_documentationWorkedExample_rosebud`** in **`test/ParamutuelV3Freeform.t.sol`**.

### Retracted or expired (refund)

Identical formula to enumerated mode:

\[
\texttt{paid} = \left\lfloor \frac{\texttt{userTotalBet} \times \texttt{netPot}}{\texttt{totalPot}} \right\rfloor
\]

where `userTotalBet` is the sum of **all** of a bettor's stakes across **all** of their distinct `answerId`s.

---

## Summary table

| Final state | Enumerated (`ParamutuelWagerV3`, `MODE()==0`) | Freeform (`ParamutuelWagerV3`, `MODE()==1`) |
|-------------|-----------------------------------------------|----------------------------------------------|
| **Resolved** | Share **`netPot`** by **policy-specific** winning tickets and (for weighted) overlap scores. `SINGLE_WINNER` recovers the legacy v1 single-index split. | Share **`netPot`** among stakers of the winning `answerId` (single winning string, exact UTF-8 bytes). |
| **Retracted / Expired** | Pro-rata **`netPot`** by **`userTotalBet / totalPot`**. | Same. |
| **Fees** | Once at finalize; split by **bps**; last recipient gets remainder. | Same. |

---

## References

- Contract: `src/ParamutuelWagerV3.sol` (unified, mode-dispatched)
- Machine / API context: [`MACHINE.md`](MACHINE.md)
- Unified protocol spec: [`ADR-0010-IMPLEMENTATION.md`](ADR-0010-IMPLEMENTATION.md)
- Enumerated policies, gas, templates: [`ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md)
- Freeform semantics: [`ADR-0009-IMPLEMENTATION.md`](ADR-0009-IMPLEMENTATION.md)
- ADRs: `research/adr/ADR-0008-multi-winner-and-settlement-generalization.md`, `research/adr/ADR-0010-unified-wager-enumerated-and-freeform.md`
