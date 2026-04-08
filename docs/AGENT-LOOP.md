# Agent Betting Loop (MCP)

**See also:** [`docs/BET-AGENT.md`](BET-AGENT.md) for the small **bet scout agent** (`agents.paramutuel_bettor`) that can run as a subprocess / subagent and complements these MCP tools.

This doc is a practical integration guide for any MCP-capable agent or bot that wants to place bets programmatically.

The goal is to make this loop:
1. Discover actionable wagers
2. Quote odds + prepare calldata (including `approve`)
3. Let an executor sign + submit transactions
4. Optionally re-quote if `betting_open` is false (using `revert_hint`)

---

## Inputs / conventions

- All bet sizes in the tools are **raw token units** (the same units the contracts use; e.g. USDC 6 decimals means `1 USDC = 1_000_000`).
- `quote_place_bet` / `quote_place_bets` will always include:
  - `betting_open` (boolean)
  - `execution_allowed` (boolean, equals `betting_open`)
  - `revert_hint` (string hint when betting is not open)
- The tools return **ABI-encoded calldata** plus an **ERC-20 approve instruction** (`approve_calldata`).

---

## Loop A: single-outcome bet

1. Discover open wagers:

```text
list_wagers(state="OPEN", limit=20)
```

2. Pick a `wager_address` from the returned list.

3. Quote a bet (do not require open; handle fallback yourself):

```text
quote_place_bet(
  wager_address="0x…",
  outcome_index=0,
  amount=1000000,
  require_open=false
)
```

4. If `betting_open=false`, your agent should:
   - Read `revert_hint`
   - Re-quote later or pick a different wager

5. Otherwise, pass the returned instructions to your executor:
   - execute `approve(token=..., spender=wager_address, amount=...)`
   - execute `placeBet(to=wager_address, calldata=...)`

---

## Loop B: batch bet (recommended for efficiency)

1. Discover open wagers:

```text
list_wagers(state="OPEN", limit=20)
```

2. Pick a `wager_address`.

3. Quote a batch bet:

```text
quote_place_bets(
  wager_address="0x…",
  outcome_indices=[0, 2],
  amounts=[1000000, 500000],
  require_open=false
)
```

4. If `betting_open=false`, use `revert_hint` and decide to:
   - retry later, or
   - select a different wager

5. Otherwise, your executor should:
   - approve the total batch amount (sum of `amounts`)
   - submit `placeBets` with the returned calldata

---

## Loop C: freeform text answer (ADR-0009)

Indexer marks these with `protocol_version === "freeform"`. There is **no** enumerated outcome index on-chain (`outcomesCount() === 0`).

1. Discover wagers as usual (`list_wagers`). Inspect `protocol_version` on detail payloads.
2. **Do not** use `quote_place_bet` (it targets `placeBet(uint256,uint256)`). Use:
   - `encode_place_bet_freeform(wager_address, collateral_token, answer, amount)` for the bet, and
   - `encode_resolve_freeform(wager_address, winning_answer)` for resolution (resolver only).
3. The **`answer` and `winning_answer` strings must match exactly** in UTF-8 bytes; otherwise the ticket id (`keccak256(bytes(answer))`) will not match.
4. Optional: `encode_create_freeform_wager(...)` against `FACTORY_FREEFORM_ADDRESS` / deployments `factoryFreeformAddress`.

---

## Reliability pattern (important)

Even with indexer-based quoting, betting can change between quote-time and tx submission.

Recommended safe pattern:
1. `quote_place_bet(s)` with `require_open=false`
2. If `betting_open=true`, submit tx(s)
3. If tx reverts anyway, capture the revert reason and:
   - re-quote
   - adjust bet sizing / timing / target wager

---

## Minimal example (pseudo-code)

```text
wagers = list_wagers(state="OPEN", limit=50)
for w in wagers:
  q = quote_place_bets(w.wager_address, outcome_indices=[0], amounts=[amount_raw], require_open=false)
  if not q.betting_open:
    continue
  executor.approve(q.placeBets.approval_required)
  executor.send(to=q.placeBets.to, calldata=q.placeBets.calldata)
  break
```

