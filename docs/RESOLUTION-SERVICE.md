# Resolution Service

This service implements the ADR intent for delegated resolver operations:

- watch/open-query wagers from the indexer
- filter to wagers where `resolver == RESOLUTION_SERVICE_ADDRESS`
- apply an operator decision file (`resolve` or `retract`)
- send resolver transactions (`cast send`) when eligible

It is intentionally simple and deterministic for MVP operations.

## Endpoints

- `GET /health` - liveness + indexer connectivity + resolver address.
- `GET /candidates` - open wagers with actionability diagnostics and decision match.
- `POST /run-once` - run one cycle over actionable decisions.
  - body: `{"execute": false}` for dry run (default)
  - body: `{"execute": true}` to broadcast transactions

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

For **v1** wagers, use `outcomeIndex` (passed to `resolve(uint256)` as the winning outcome index). For **ADR-0008 v2** wagers (`protocol_version: "v2"` in the indexer), set **`winningMask`** to the bitmask the contract expects (for a single winning outcome at index `i`, use `1 << i`). If both are present, **`winningMask` wins**. For **freeform** wagers (`protocol_version: "freeform"`), set **`winningAnswer`** to the exact string passed to `resolve(string)` (same bytes bettors used in `placeBet(string,uint256)` for that side).

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

Use `Dockerfile.resolution`.

Required env for execution:

- `PRIVATE_KEY` (resolver key)
- optional `RESOLUTION_SERVICE_ADDRESS` (derived from `PRIVATE_KEY` if omitted)
- optional overrides: `INDEXER_BASE_URL`, `RPC_URL_BASE_SEPOLIA`, `RESOLUTION_DECISIONS_PATH`

Deploy helper:

```bash
export GCP_PROJECT_ID="your-project-id"
./script/deploy/redeploy_cloud_run_resolution.sh
```

Then verify:

- `GET /health`
- `GET /candidates`
- `POST /run-once` with `{"execute": false}`

Before enabling execute mode in production, confirm the decisions file contains only intended wagers/outcomes.
