# Machine / agent integration

Paramutuel is structured so **bots, indexers, and LLM-driven workflows** can interact without bespoke scraping.

## On-chain interface

- **ABIs**: build with Foundry (`forge build`) and read JSON under `out/ParamutuelFactory.sol/` and `out/ParamutuelMarket.sol/`.
- **Factory** `createMarket(collateralToken, question, outcomes, bettingCloseTime, resolutionWindow, resolver, bettingCloser, resolutionCloser, extraFeeRecipients, extraFeeBps)`  
  - `resolver`, `bettingCloser`, or `resolutionCloser` may be `address(0)` to default all three roles to the **proposer** (`msg.sender`).
  - `bettingCloseTime = 0` means no max betting window (closer-managed).
  - `resolutionWindow = 0` means no max resolution window (closer-managed).
- **Market lifecycle** (high level):
  - `placeBet` while open and not yet closed by time or `closeBetting()`.
  - `closeBetting()` — only `bettingCloser`; required to end betting when `bettingCloseTime = 0`.
  - After betting is closed: `resolve` / `retract` by `resolver` while the resolution window is open.
  - `closeResolutionWindow()` — only `resolutionCloser`, only after betting has ended; required to end resolution when `resolutionWindow = 0`.
  - `expire()` — anyone once the resolution window is over (by time or authority).
  - `claim`, `withdrawFees` after finalization.

## HTTP indexer API (JSON)

Run `python -m service.indexer.api` (see module for flags). All responses are `application/json`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | `{ "ok": true, "ts": <unix> }` |
| GET | `/markets?state=OPEN&limit=100` | List markets (optional `state`, `limit` 1–1000). |
| GET | `/markets/:address` | Single market, totals, outcome rows, event history (`payload_json` parsed). |
| GET | `/sweeper/expire-candidates?now=<unix>` | Markets still `OPEN` where `expire()` is valid: timed-out resolution window (from effective betting close + `resolution_window`) or `resolution_window_closed` set by indexer from `ResolutionWindowClosedByAuthority`. |

### Environment / ops

- **`RPC_URL`**: use your node when running the indexer CLI (`service.indexer.indexer`).
- **`--db-path`**: SQLite file for the indexer (schema in `service/indexer/schema.sql`).
- **`--factory-address`**: factory contract to filter `MarketCreated` logs.

## dApp

Static `dapp/` UI loads ABIs from `../out/` — run `forge build` before serving so agents and humans share the same artifact versions.

## Service operations

- Explorer server: `python3 -m service.explorer.server --indexer-base-url http://127.0.0.1:8090`
- Control panel CLI: `python3 -m service.control_panel.cli ...`
- Control panel web: `python3 -m service.control_panel.web --rpc-url ... --private-key ...`

Operator transaction workflows are documented in `docs/WORKFLOWS.md`.

## Versioning

Changing `createMarket` or event layouts is an **ABI break**. Bump deployed factory version or document migration when upgrading.

Upgrading the indexer from a pre–window-delegation build: **recreate the SQLite DB** (or migrate with `ALTER TABLE`) so `markets` includes `betting_closer`, `resolution_closer`, `resolution_window`, `betting_closed_by_authority`, `betting_closed_at`, `resolution_window_closed`, and `resolution_window_closed_at`; `MarketCreated` and closure-event topics changed.
