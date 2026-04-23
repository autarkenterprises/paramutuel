# ADR-0009 implementation notes (freeform text wagers)

> **Superseded (contract layer) by [`ADR-0010-IMPLEMENTATION.md`](ADR-0010-IMPLEMENTATION.md).** The standalone `ParamutuelWagerFreeform` / `ParamutuelFactoryFreeform` contracts have been **deleted from the tree**; the ADR-0009 freeform semantics below are now implemented by `ParamutuelWagerV3` when constructed with `MODE = Freeform` via `ParamutuelFactoryV3.createFreeformWager(...)`. The event is `WagerCreatedV3Freeform`; indexer/MCP/dApp surfaces use a single `factoryAddress` (no separate `factoryFreeformAddress`). Read this document for the economic rules; read ADR-0010 for current calldata shapes and config.

**Status:** **Implemented** on `master` as V3 freeform mode — contracts, Foundry tests, indexer, MCP, dApp, and bet scout surfaces below (references to the deleted `ParamutuelWagerFreeform` describe historical structure).
**ADR:** [`research/adr/ADR-0009-freeform-text-wagers.md`](../research/adr/ADR-0009-freeform-text-wagers.md)

## Rationale

Freeform markets cannot reuse the **enumerated bitmask** model without pretending every possible answer was known at `createWager`. This document records **implementation-facing** choices and where they live in the repo.

## Contract surface (shipped — V3 freeform mode)

### Factory (`src/ParamutuelFactoryV3.sol`)

- `createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[])` — same economic/role shape as the enumerated path (collateral, proposition, windows, resolver/closers, extra fees). **No** `outcomes` array. Immutable per-wager cap is `MAX_DISTINCT_TICKETS = 1024`.
- Event: `WagerCreatedV3Freeform` (topic0 `0xf59da875…4c53`).

### Wager (`src/ParamutuelWagerV3.sol`, `MODE()==1`)

- `placeBet(string calldata answer, uint256 amount)` and `resolve(string calldata winningAnswer)` — **UTF-8 bytes** must match exactly between bet and resolve (`keccak256(bytes(answer))` ticket id).
- Lifecycle peers shared with enumerated mode: `closeBetting`, `closeResolutionWindow`, `expire`, `retract`, `claim`, `withdrawFees`.
- `outcomesCount()` returns **0** for indexer/dApp probing (freeform has no enumerated outcomes).

### Ticket identity & limits

- `answerId = keccak256(bytes(answer))`; on-chain mapping `ticketPoolTotal(bytes32)` and `usedAnswerIds` pattern (see Solidity).
- `MAX_ANSWER_BYTES = 1024`; `maxDistinctAnswers` immutable (constructor; factory uses 1024).
- **No winning stake:** `resolve` **reverts** with `NoWinningStake` if no pool on the winning id.

### Events

- `BetPlacedFreeform(bettor, answerId indexed, amount)` — indexer uses **answer id** topic for `wager_ticket_pools.ticket_mask` (hex string).
- `ResolvedFreeform(winningAnswerId indexed)`.

## Indexer / API / MCP / dApp / agents

- **Indexer:** `protocol_version = 'freeform'` is emitted on rows that originate from `WagerCreatedV3Freeform`; `apply_log` handles `WagerCreatedV3Freeform`, `BetPlacedFreeform`, `ResolvedFreeform`. CLI/env: `--factory-address` / `FACTORY_ADDRESS`; `config/deployments.json` key `factoryAddress` (single unified V3 factory — no separate freeform key).
- **MCP (`paramutuel-mcp`):** `encode_create_freeform_wager`, `encode_place_bet_freeform`, `encode_resolve_freeform`; `get_protocol_info` exposes `factory_address` and freeform constants (`MAX_ANSWER_BYTES`, `MAX_DISTINCT_TICKETS`).
- **dApp (`dapp/`):** Protocol option **freeform**; loads `ParamutuelFactoryV3` / `ParamutuelWagerV3` ABIs from `dapp/abi/` and dispatches via `MODE()==1`.
- **Bet scout:** `protocol_version === "freeform"` uses `ticket_pools` rows (sorted by `ticket_mask`); `quote` accepts optional `freeform_answer` for `placeBet` calldata (otherwise informational odds only — indexer does not store plaintext answers).
- **Deploy:** `script/DeployFactoryV3.s.sol`.

## Security checklist

- **Griefing:** many 1-wei distinct answers → blows `_usedAnswerIds` length and resolve/claim cost; **hard cap** + monitoring.
- **Calldata DoS:** max answer length.
- **Content:** strings may carry abuse/PII; off-chain policy for display and indexing.
- **Resolver:** same trust model as v2 `winningMask`; additional **format** ambiguity if users disagree on canonical spelling.

## Tests (when implemented)

- Exact match: two bets same string → same pool; claim splits correctly.
- Near-miss: different bytes → different `answerId`, only winner pool paid.
- Empty answer / length revert.
- Distinct-answer cap hit.
- No stake on winning string — chosen revert or refund behavior.
- Lifecycle parity with existing retract/expire expectations.

## Related

- [`ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md) — v2 bitmask implementation (distinct from freeform).
- [`ADR-0008-GAS.md`](ADR-0008-GAS.md) — how v2 gas scales (distinct tickets, not `numOptions`).
- [`PARAMUTUEL-V3-GAS.md`](PARAMUTUEL-V3-GAS.md) — **V3** combined factory: freeform `placeBet` / `resolve` / `claim` gas (domain-separated `answerId`).

---

## Appendix: enumerated-mode outcome cap — how high can `MAX_OUTCOMES` go?

> The historical analysis below was written against `ParamutuelFactoryV2` / `ParamutuelWagerV2` / the `WagerV2Masks` library. Those contracts and the library have been **deleted from the tree**; the same cap (`MAX_OUTCOMES = 255`) and the same bitmask math now live in `ParamutuelFactoryV3` / `ParamutuelWagerV3` when constructed with `MODE = Enumerated`. The reasoning stands as-is.

**Current protocol:** `ParamutuelFactoryV3` sets **`MAX_OUTCOMES = 255`** (maximum index 254; the enumerated-mode full-set helper requires `numOptions < 256`).

This section records *why* that bound exists and how cost scales as `N` grows (for example versus the previous factory cap of 64).

### What actually scales with `numOptions` today

In enumerated-mode `ParamutuelWagerV3`, **resolve and claim** iterate **`_usedMasks.length`** (distinct ticket masks), **not** `numOptions`. See [`PARAMUTUEL-V3-GAS.md`](PARAMUTUEL-V3-GAS.md): resolve cost grows ~linearly with **distinct masks** (~4–5k gas per extra mask in sampled scenarios).

Per-operation costs tied to `numOptions`:

| Mechanism | Depends on `N = numOptions`? |
|-----------|------------------------------|
| `mask >> N != 0` validation | **O(1)** EVM shift; 64 vs 255 is not a meaningful difference. |
| `_popcount(x)` | **O(number of set bits in `x`)**, not `N`. Worst-case iterations increase only if policies allow tickets with **more** bits set; cap is at most the number of bits that can be 1 in a **valid** mask, which is **≤ `N`**. So pathological `ANY_OF` / `WEIGHTED_OVERLAP` tickets could do more work when `N` is larger; `SINGLE_WINNER` (one bit) is **unchanged**. |
| `createWager` + constructor | **Stores `string[] _outcomes`** — cost scales **~linearly with `N`** and with **label length** (major cost driver when raising the cap). |
| Calldata size at create | **Linear in `N`** (every outcome string). |

So **raising `N` does not multiply resolve gas by itself**; it mainly increases **creation cost** (outcome string storage) and **worst-case popcount work** for policies that allow wide masks.

### Single `uint256` bitmask: hard ceiling at 256 bits

Tickets and `winningMask` are `uint256`. At most **256** bit positions exist per word.

The enumerated-mode full-set helper computes `(1 << numOptions) - 1`, which **overflows** if `numOptions == 256` (`1 << 256` reverts in Solidity 0.8). It therefore requires `numOptions < 256`, i.e. **at most 255** options for that helper as written. (Historically implemented as `WagerV2Masks.fullSet`; the library was deleted when V2 was folded into V3 and the same math is now inlined in `ParamutuelWagerV3`.)

The wager uses `if (mask >> numOptions != 0)` to reject bits outside the option range. In Solidity, **`uint256 >> 256` is 0**, so for `numOptions == 256` that check **never** rejects high bits — the entire word would need **different validation** (e.g. treat `N == 256` as “all bits are legal” and only require `mask != 0` where appropriate, and use `type(uint256).max` for the full set).

**Practical summary:**

- **255 options** is the adopted factory maximum under the current **shift + library** pattern (profile `createWager` for large `N`).
- **Exactly 256 options** is still **one word**, but needs **explicit special-casing** in mask validation and `fullSet`-style helpers — not a new data structure, but **not** a one-constant tweak.

### Is settling a 255-outcome market “much more expensive” than a 64-outcome one?

- **Settlement (resolve/claim):** **No**, not inherently — same as today, dominated by **distinct tickets**, not `N`.
- **Market creation:** **Roughly proportional to `N`** (storage for outcome labels + calldata). Large-N markets pay more at deploy than small-N markets.
- **Worst-case bit operations:** **Only** for policies where tickets can set **many** of the `N` bits; for typical single-outcome or small-set tickets, the difference is **small**.

### Follow-up: exactly 256 options in one word

The factory stops at **255** so `mask >> numOptions` and `(1 << numOptions) - 1` patterns remain well-defined. Supporting **256** atomic options in one `uint256` would require **special-cased validation** and a full-set constant of `type(uint256).max` — deferred unless product demands it.
