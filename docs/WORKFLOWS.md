# Standard Operator Workflows (CLI / API)

This document is for operators and machine agents interacting with Paramutuel contracts directly.

Assumptions:

- Factory + wager ABIs are committed at `dapp/abi/` and also available under `out/` after `forge build`.
- You have `cast` (Foundry) installed.
- Environment has `RPC_URL` and `PRIVATE_KEY`.

## 1) Create a wager

### Finite windows (time bounded)

Payoff policy is `0` `SINGLE_WINNER`, `1` `ANY_OF`, `2` `EXACT_SET`, `3` `AT_LEAST_K`, or `4` `WEIGHTED_OVERLAP`. The next argument is `k` for `AT_LEAST_K` and `0` otherwise.

```bash
cast send "$FACTORY" \
  "createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,address,address[],uint16[])" \
  "$COLLATERAL" \
  "Will X happen?" \
  '["YES","NO"]' \
  0 0 \
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

`cast` mangles some strings (see the warning in section 4), so for propositions or outcome labels containing quotes, backslashes or non-ASCII text, use the control panel CLI, which encodes them exactly:

```bash
python3 -m service.control_panel.cli create-wager \
  --factory "$FACTORY" --collateral "$COLLATERAL" \
  --proposition "Will the café reopen?" --outcomes "Yes,No" \
  --betting-close-time "$BETTING_CLOSE_TS" --resolution-window "$RESOLUTION_WINDOW_SECS"
# Prints the command for review. Add --execute (before the subcommand) to send it.
```

### Finite windows + seeded liquidity

Approve the **factory** for the total first. Seeds are ticket masks: mask `1` is outcome 0, mask `4` is outcome 2.

```bash
cast send "$COLLATERAL" "approve(address,uint256)" "$FACTORY" "$SEED_TOTAL" \
  --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"

cast send "$FACTORY" \
  "createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,address,address[],uint16[],uint256[],uint256[])" \
  "$COLLATERAL" \
  "Will X happen?" \
  '["YES","NO","MAYBE"]' \
  0 0 \
  "$BETTING_CLOSE_TS" \
  "$RESOLUTION_WINDOW_SECS" \
  "$RESOLVER_OR_ZERO" \
  "$BETTING_CLOSER_OR_ZERO" \
  "$RESOLUTION_CLOSER_OR_ZERO" \
  "[$EXTRA_RECIPIENTS]" \
  "[$EXTRA_BPS]" \
  "[1,4]" \
  "[$SEED_AMOUNT_0,$SEED_AMOUNT_2]" \
  --rpc-url "$RPC_URL" \
  --private-key "$PRIVATE_KEY"
```

Add a final `uint256` to the signature and arguments to set `minNewTicketStake`, the minimum raw amount needed to open a new ticket. It makes griefing with dust tickets cost real collateral.

### Freeform

```bash
python3 -m service.control_panel.cli create-freeform-wager \
  --factory "$FACTORY" --collateral "$COLLATERAL" \
  --proposition "Who wins?" \
  --betting-close-time "$BETTING_CLOSE_TS" --resolution-window "$RESOLUTION_WINDOW_SECS" \
  --min-new-ticket-stake 1000000
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

A ticket is a **bitmask**: `1 << i` backs outcome `i` alone, so mask `1` is outcome 0, mask `2` is outcome 1, and mask `3` is both (multi-outcome policies only).

```bash
# approve collateral
cast send "$TOKEN" "approve(address,uint256)" "$WAGER" "$AMOUNT" \
  --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"

# place bet
cast send "$WAGER" "placeBet(uint256,uint256)" "$TICKET_MASK" "$AMOUNT" \
  --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

Batch bet (several tickets in one tx):

```bash
cast send "$WAGER" "placeBets(uint256[],uint256[])" "[1,4,8]" "[$A0,$A2,$A3]" \
  --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

For freeform wagers use the dApp, the site, or the MCP server's `encode_place_bet_freeform`, for the reason in section 4.

## 3) Close betting window

Only `bettingCloser` may call:

```bash
cast send "$WAGER" "closeBetting()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

## 4) Resolve / Retract

Only `resolver` may call:

**Enumerated wagers.** The argument is the winning **bitmask**: outcome 0 alone is `1`, outcome 1 alone is `2`.

```bash
cast send "$WAGER" "resolve(uint256)" "$WINNING_MASK" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

**Freeform wagers** match the answer byte for byte. **Do not pass an answer as a `cast` argument:** `cast` strips trailing whitespace and surrounding quotes and treats a leading `--` as a flag, so it can send a different answer than the one you typed, and resolve the wrong pool. Use the control panel CLI, which sends exactly what you pass. Review the printed command, then repeat with `--execute`:

```bash
python3 -m service.control_panel.cli wager-action --wager "$WAGER" --action resolve \
  --protocol-version freeform --winning-answer "$WINNING_ANSWER"
```

**Retract** (both modes):

```bash
cast send "$WAGER" "retract()" --rpc-url "$RPC_URL" --private-key "$PRIVATE_KEY"
```

`cast send` exits 0 even when a transaction is mined and reverts. In scripts, check the receipt: `--json` and `.status == "0x1"`. The services in this repository all do.

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

The response shows the function and decoded arguments alongside the command. The command carries raw calldata, with the key redacted.

```bash
curl -sS -X POST "http://127.0.0.1:8092/api/preview/action" \
  -H "content-type: application/json" \
  -d '{"wager":"'"$WAGER"'","action":"resolve","winningMask":"1"}'
```

### B) Control panel web (execute, token protected)

Requires `--allow-execute` on the server. Check `ok` in the response: it means mined with status 1.

```bash
curl -sS -X POST "http://127.0.0.1:8092/api/preview/action" \
  -H "content-type: application/json" \
  -H "authorization: Bearer $CONTROL_PANEL_TOKEN" \
  -d '{"wager":"'"$WAGER"'","action":"close-betting","execute":true}'
```

### C) Sweeper loop for unresolved candidates

Reads `PRIVATE_KEY` from the environment. Dry-run unless `--execute` is given.

```bash
python3 -m service.indexer.sweeper \
  --db-path service/indexer/indexer.db \
  --rpc-url "$RPC_URL" \
  --execute \
  --loop \
  --interval-seconds 60
```
