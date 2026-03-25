# Standard Operator Workflows (CLI / API)

This document is for operators and machine agents interacting with Paramutuel contracts directly.

Assumptions:

- Factory + market ABIs are available under `out/`.
- You have `cast` (Foundry) installed.
- Environment has `RPC_URL` and `PRIVATE_KEY`.

## 1) Create a market

### Finite windows (time bounded)

```bash
cast send "$FACTORY" \
  "createMarket(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])" \
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

### Closer-managed windows (no max)

Use zero sentinels:

- `bettingCloseTime = 0`
- `resolutionWindow = 0`

This means only closers can end those windows.

## 2) Place bet

```bash
# approve collateral
cast send "$TOKEN" "approve(address,uint256)" "$MARKET" "$AMOUNT" \
  --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"

# place bet
cast send "$MARKET" "placeBet(uint256,uint256)" "$OUTCOME_INDEX" "$AMOUNT" \
  --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

## 3) Close betting window

Only `bettingCloser` may call:

```bash
cast send "$MARKET" "closeBetting()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

## 4) Resolve / Retract

Only `resolver` may call:

```bash
cast send "$MARKET" "resolve(uint256)" "$WINNING_INDEX" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
# or
cast send "$MARKET" "retract()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

## 5) Close resolution window

Only `resolutionCloser` may call, and only after betting is closed:

```bash
cast send "$MARKET" "closeResolutionWindow()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

## 6) Expire unresolved market

Anyone may call `expire()` once resolution window is over (timed-out if configured, or authority-closed):

```bash
cast send "$MARKET" "expire()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

## 7) Claims / fees

```bash
cast send "$MARKET" "claim()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
cast send "$MARKET" "withdrawFees()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

## Role choreography (important)

If the same entity is both **resolver** and **resolutionCloser**, they still perform distinct actions:

1. `closeResolutionWindow()` (if they intentionally want to end resolver window).
2. `expire()` by anyone (often your sweeper), **or** `resolve()` / `retract()` by resolver before closure.

Similarly, if using no-max betting (`bettingCloseTime = 0`), someone with `bettingCloser` authority must explicitly call `closeBetting()` before resolution can proceed.

## 8) Service operator API workflows

### A) Control panel web (preview only)

```bash
curl -sS -X POST "http://127.0.0.1:8092/api/preview/action" \
  -H "content-type: application/json" \
  -d '{"market":"'"$MARKET"'","action":"close-betting"}'
```

### B) Control panel web (execute, token protected)

```bash
curl -sS -X POST "http://127.0.0.1:8092/api/preview/action" \
  -H "content-type: application/json" \
  -H "authorization: Bearer $CONTROL_PANEL_TOKEN" \
  -d '{"market":"'"$MARKET"'","action":"close-betting","execute":true}'
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
