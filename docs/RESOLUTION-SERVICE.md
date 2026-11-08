# Resolution Service

This service implements the ADR intent for delegated resolver operations:

- watch/open-query wagers from the indexer
- filter to wagers where `resolver == RESOLUTION_SERVICE_ADDRESS`
- apply an operator decision file (`resolve` or `retract`)
- send resolver transactions (`cast send`) when eligible

It is intentionally simple and deterministic for MVP operations.

## Endpoints

- `GET /health` - liveness, indexer connectivity, resolver address, and whether the decision file is readable (`decisions_ok`, `decisions_error`). A corrupt file also makes `/candidates` and `/run-once` return a JSON 500, and nothing is sent until it is fixed.
- `GET /candidates` - this resolver's open wagers, oldest first, with actionability diagnostics. `truncated: true` means more exist than one page (`limit`, at most 1000) shows. Decision **contents** appear only with the token: a decision written before betting closes tells a reader the winner while they can still bet (ADR-0020). Without it, `decision_present` shows only that one exists.
- `POST /run-once` - run one cycle over actionable decisions. **Requires** `Authorization: Bearer $RESOLUTION_SERVICE_TOKEN` (or `X-Token: $RESOLUTION_SERVICE_TOKEN`); returns `401` otherwise, and rejects every request when the token is unset (fail closed, ADR-0019). It reads up to 50,000 of this resolver's open wagers; `truncated: true` in the response means more exist, so run it again once these are acted on (ADR-0021).
  - body: `{"execute": false}` for dry run (default) — echoed `cast` commands have `--private-key` redacted
  - body: `{"execute": true}` to broadcast transactions. A result's `ok` means mined with status 1; a reverted transaction is reported as failed, with its `tx_hash`.

## Decision file

Default path: `config/resolution-decisions.base-sepolia.json`

Shape:

```json
{
  "0xWAGER...": { "action": "resolve", "outcomeIndex": 1 },
  "0xWAGER...": { "action": "resolve", "winningMask": 4 },
  "0xWAGER...": { "action": "resolve", "winningAnswer": "Exact UTF-8 text" },
  "0xWAGER...": { "action": "retract" }
}
```

For **enumerated** wagers (`protocol_version: "enumerated"` in the indexer — V3 `MODE()==0`), either set **`outcomeIndex`** `i` (0-based; the service sends the single-bit mask `1 << i`) or set **`winningMask`** to the raw bitmask passed to `resolve(uint256)` (use this for multi-winner policies). `winningMask` takes precedence when both are present. Before ADR-0019 `outcomeIndex` was sent unpromoted, so `outcomeIndex: 1` resolved outcome 0 — re-check any decision files written against the old behaviour. For **freeform** wagers (`protocol_version: "freeform"` — V3 `MODE()==1`), set **`winningAnswer`** to the exact UTF-8 string passed to `resolve(string)` (same bytes bettors used in `placeBet(string,uint256)` for that side). The service sends those bytes exactly, as raw calldata: it does not trim or normalise them, and it does not pass them through `cast`'s argument parser, which would strip trailing whitespace and surrounding quotes. Note the convention on the bet side: the dApp and staking site trim surrounding whitespace before `placeBet(string,…)` as a typing aid, while machine surfaces (the MCP server, the scout, direct calls) send exactly what they are given. A staked answer can therefore carry whitespace, so copy the winning answer from the indexer's `ticket_pools[].answer_text` rather than retyping it. A mismatch normally reverts with `NoWinningStake`, but it resolves a different pool if someone staked on exactly the bytes you sent.

Only wagers that are:

1. `OPEN`
2. assigned to the service resolver address
3. betting-closed
4. still within resolution window

are actionable for `resolve/retract`.

## Local run

```bash
PYTHONPATH=. python3 -m service.resolution.service \
  --indexer-base-url "http://127.0.0.1:8090" \
  --rpc-url "$RPC_URL_BASE_SEPOLIA" \
  --private-key "$PRIVATE_KEY" \
  --resolver-address "0xYourResolverAddress" \
  --decisions-path "config/resolution-decisions.base-sepolia.json" \
  --port 8093
```

## Cloud Run

Use `Dockerfile.resolution`, which includes a pinned `cast` for signing and broadcasting. `cast` accepts a raw key only as a process argument, so run this service alone in its container, or on a host with no other local users.

Required env for execution:

- `PRIVATE_KEY` (resolver key)
- `RESOLUTION_SERVICE_TOKEN` (bearer token for `POST /run-once`; without it the endpoint is disabled)
- optional `RESOLUTION_SERVICE_ADDRESS` (derived from `PRIVATE_KEY` with `cast` if omitted)
- optional overrides: `INDEXER_BASE_URL`, `RPC_URL_BASE_SEPOLIA`, `RESOLUTION_DECISIONS_PATH`

Deploy helper:

```bash
export GCP_PROJECT_ID="your-project-id"
./script/deploy/redeploy_cloud_run_resolution.sh
```

Then verify:

- `GET /health`
- `GET /candidates` with `Authorization: Bearer $RESOLUTION_SERVICE_TOKEN`
- `POST /run-once` with `{"execute": false}` and `Authorization: Bearer $RESOLUTION_SERVICE_TOKEN`

Before enabling execute mode in production, confirm the decisions file contains only intended wagers/outcomes.
