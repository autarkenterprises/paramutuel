# Standard Operator Workflows (CLI / API)

This document is for operators and machine agents interacting with Paramutuel contracts directly.

Assumptions:

- Factory + wager ABIs are committed at `dapp/abi/` and also available under `out/` after `forge build`.
- You have `cast` (Foundry) installed.
- Environment has `RPC_URL` and `PRIVATE_KEY`.

## 1) Create a wager

### Finite windows (time bounded)

```bash
cast send "$FACTORY" \
  "createWager(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])" \
  "$COLLATERAL" \
  "Will X happen?" \
  "[YES,NO]" \
  "$BETTING_CLOSE_TS" \
  "$RESOLUTION_WINDOW_SECS" \
  "$RESOLVER_OR_ZERO" \
  "$BETTING_CLOSER_OR_ZERO" \
  "$RESOLUTION_CLOSER_OR_ZERO" \
  "[$EXTRA_RECIPIENTS]" \
  "[$EXTRA_BPS]" \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY"
```

### Finite windows + optional seeded liquidity

```bash
cast send "$FACTORY" \
  "createWager(address,string,string[],uint64,uint64,address,address,address,address[],uint16[],uint256[],uint256[])" \
  "$COLLATERAL" \
  "Will X happen?" \
  "[YES,NO,MAYBE]" \
  "$BETTING_CLOSE_TS" \
  "$RESOLUTION_WINDOW_SECS" \
  "$RESOLVER_OR_ZERO" \
  "$BETTING_CLOSER_OR_ZERO" \
  "$RESOLUTION_CLOSER_OR_ZERO" \
  "[$EXTRA_RECIPIENTS]" \
  "[$EXTRA_BPS]" \
  "[0,2]" \
  "[$SEED_AMOUNT_0,$SEED_AMOUNT_2]" \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY"
```

Role input semantics:

- `resolver = 0x000...0000` -> defaults resolver to proposer.
- `bettingCloser = 0x000...0000` -> disables authority `closeBetting()` (time-only close).
- `resolutionCloser = 0x000...0000` -> disables authority `closeResolutionWindow()` (time-only close).

### Closer-managed windows (no max)

Use zero sentinels:

- `bettingCloseTime = 0`
- `resolutionWindow = 0`

This means only closers can end those windows.
Protocol guardrail: these modes require non-zero closer addresses (`bettingCloser` and `resolutionCloser`) at creation.

## 2) Place bet

```bash
# approve collateral
cast send "$TOKEN" "approve(address,uint256)" "$WAGER" "$AMOUNT" \
  --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"

# place bet
cast send "$WAGER" "placeBet(uint256,uint256)" "$OUTCOME_INDEX" "$AMOUNT" \
  --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

Batch bet (multiple outcomes in one tx):

```bash
cast send "$WAGER" "placeBets(uint256[],uint256[])" "[0,2,3]" "[$A0,$A2,$A3]" \
  --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

## 3) Close betting window

Only `bettingCloser` may call:

```bash
cast send "$WAGER" "closeBetting()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

## 4) Resolve / Retract

Only `resolver` may call:

```bash
cast send "$WAGER" "resolve(uint256)" "$WINNING_INDEX" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
# or
cast send "$WAGER" "retract()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

## 5) Close resolution window

Only `resolutionCloser` may call, and only after betting is closed:

```bash
cast send "$WAGER" "closeResolutionWindow()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

## 6) Expire unresolved wager

Anyone may call `expire()` once resolution window is over (timed-out if configured, or authority-closed):

```bash
cast send "$WAGER" "expire()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

## 7) Claims / fees

```bash
cast send "$WAGER" "claim()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
cast send "$WAGER" "withdrawFees()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

## Role choreography (important)

If the same entity is both **resolver** and **resolutionCloser**, they still perform distinct actions:

1. `closeResolutionWindow()` (if they intentionally want to end resolver window).
2. `expire()` by anyone (often your sweeper), **or** `resolve()` / `retract()` by resolver before closure.

Similarly, if using no-max betting (`bettingCloseTime = 0`), someone with `bettingCloser` authority must explicitly call `closeBetting()` before resolution can proceed.

For finite windows, you may set `bettingCloser = address(0)` and/or `resolutionCloser = address(0)` to run in time-only mode (no authority pre-emption).

## 8) Service operator API workflows

### A) Control panel web (preview only)

```bash
curl -sS -X POST "http://127.0.0.1:8092/api/preview/action" \
  -H "content-type: application/json" \
  -d '{"wager":"'"$WAGER"'","action":"close-betting"}'
```

### B) Control panel web (execute, token protected)

```bash
curl -sS -X POST "http://127.0.0.1:8092/api/preview/action" \
  -H "content-type: application/json" \
  -H "authorization: Bearer $CONTROL_PANEL_TOKEN" \
  -d '{"wager":"'"$WAGER"'","action":"close-betting","execute":true}'
```

### C) Sweeper loop for unresolved candidates

```bash
python3 -m service.indexer.sweeper \
  --db-path service/indexer/indexer.db \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY" \
  --execute \
  --loop \
  --interval-seconds 60
```
