# Testnet Live Suite (Base Sepolia)

This suite tests deployed contracts on Base Sepolia rather than local unit-test code paths.

It has three modes:

- `readonly` (default): `eth_call` checks only, no transactions, no gas.
- `minimal-tx`: one lightweight lifecycle flow with low-value/no-value actions to validate live state transitions.
- `funded-tx`: real collateral flow (`approve` + `placeBet` + `resolve/retract/expire` + `claim` + optional `withdrawFees`) plus optional unauthorized-role negative checks.

## Why this is low-cost

- `readonly` mode uses only RPC calls (Alchemy dashboard usage, no ETH).
- `minimal-tx` sends a small number of transactions (create wager, close betting, close resolution window, expire).
- It uses `bettingCloseTime=0` and `resolutionWindow=0` so no waiting windows are needed and no bet funding is required.

## Required environment

- `RPC_URL_BASE_SEPOLIA` (or legacy `RPC_URL_SEPOLIA`)
- Factory address source:
  - default: `config/deployments.json` -> `baseSepolia.factoryAddress`
  - override: `FACTORY_ADDRESS`

Optional:

- `TESTNET_WAGER_ADDRESS` (to run additional read checks on a known V3 wager — `factory()` must match the configured V3 factory)
- `TESTNET_MODE=minimal-tx` (for transaction checks)
- `PRIVATE_KEY` (required for `minimal-tx`)
- `TESTNET_MODE=funded-tx` (for funded lifecycle checks)
- `TESTNET_COLLATERAL_TOKEN` (optional for `funded-tx`; if unset, the suite defaults to **Base Sepolia USDC** `0x036CbD53842c5426634e7929541eC2318f3dCF7e`. Override when you want another ERC-20 with `decimals()/approve()/balanceOf()`.)
- `TESTNET_BET_AMOUNT` (optional, default `1`; human token units)
- `TESTNET_SECONDARY_PRIVATE_KEY` (optional; if funded, places a second bet on opposite outcome)
- `TESTNET_UNAUTHORIZED_PRIVATE_KEY` (optional; enables negative access-control tx checks)
- `TESTNET_INDEXER_BASE_URL` (optional; defaults to `config/deployments.json` -> `baseSepolia.explorerApiBase` for hosted indexer visibility checks)

**V3 enumerated-mode policy matrix** (class `TestBaseSepoliaLiveV3PolicyMatrix` in `test/testnet/test_live_base_sepolia.py`):

- Factory address: `FACTORY_ADDRESS` or `config/deployments.json` → `baseSepolia.factoryAddress` (the single unified V3 factory).
- `TESTNET_SKIP_V3_MATRIX=1` — force-skip the enumerated policy matrix.
- `TESTNET_MODE=minimal-tx` — runs a **matrix over all `PayoffPolicy` values** (dummy collateral): create → authority closes → `expire()` (no ERC-20).
- `TESTNET_MODE=funded-tx` — runs a **funded resolve matrix**: for each policy, creates a V3 enumerated wager (`MODE()==0`) with real collateral, places **`placeBet` or `placeBets`** (per scenario), `resolve(winningMask)`, `claim()`. Cases cover `SINGLE_WINNER`, `ANY_OF` (+ batch `placeBets`), `EXACT_SET`, `AT_LEAST_K` (3 outcomes, `policyParam=2`), and `WEIGHTED_OVERLAP`.
- `TESTNET_V3_CASES` — comma-separated subset of case ids: `single_winner`, `any_of`, `exact_set`, `at_least_k`, `weighted_overlap` (default: all).

**V3 freeform mode** (`TestBaseSepoliaLiveFreeform` in `test/testnet/test_live_base_sepolia.py`):

- Factory: `FACTORY_ADDRESS` or `config/deployments.json` → `baseSepolia.factoryAddress` (same unified V3 factory; freeform wagers are dispatched by `MODE()==1`).
- `TESTNET_SKIP_FREEFORM=1` — skip all freeform live tests.
- `TESTNET_MODE=minimal-tx` — create (dummy collateral) → authority close → `expire()`.
- `TESTNET_MODE=funded-tx` — resolve / retract / expire matrix with real collateral (default USDC if `TESTNET_COLLATERAL_TOKEN` unset) and `placeBet(string,uint256)` / `resolve(string)`.

## Hosted indexer visibility (`test_funded_tx_resolution_window_guards_and_indexer_visibility`)

One funded test polls the **remote** HTTP API configured as `TESTNET_INDEXER_BASE_URL` or `config/deployments.json` → `baseSepolia.explorerApiBase`. It creates a fresh on-chain wager, then searches `/wagers?q=<wager_address>` until a row appears.

That step is **best-effort**, not a hard guarantee of your local run:

- **Lag:** The indexer follows chain logs on its own schedule (poll interval, RPC batching, catch-up). A wager can exist on-chain for minutes before the API returns it.
- **Deployment drift:** The hosted URL in the repo may index a fixed set of factory addresses and `fromBlock` values. Wagers created from factories or blocks that instance does **not** watch will never appear, so the poll times out even though the chain state is valid.
- **Outcome:** On timeout the test **skips** with a clear message instead of failing the whole suite—on-chain guards in the same test still ran; only the “indexer caught up” assertion is skipped.

To tighten this check, point `TESTNET_INDEXER_BASE_URL` at an indexer you control that watches the same factories you use in the test, or run a local `live_api` against your `deployments.json`.

## Run

Recommended order:

1. run `readonly` first (zero gas)
2. run `minimal-tx` second (lifecycle smoke)
3. run `funded-tx` last (full collateral flow)

Before any mode, confirm the effective factory address (from config unless overridden):

```bash
source ./script/lib/deployments.sh
ensure_factory_address "base-sepolia" "./config/deployments.json"
echo "$FACTORY_ADDRESS"
```

```bash
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
./script/testnet/run_live_suite.sh
```

Read-only + existing wager checks:

```bash
TESTNET_WAGER_ADDRESS=0x... \
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
./script/testnet/run_live_suite.sh
```

Minimal tx mode:

```bash
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
TESTNET_MODE=minimal-tx \
PRIVATE_KEY=0x... \
./script/testnet/run_live_suite.sh
```

Funded tx mode (collateral defaults to Base Sepolia USDC if `TESTNET_COLLATERAL_TOKEN` is unset):

```bash
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
TESTNET_MODE=funded-tx \
PRIVATE_KEY=0x... \
TESTNET_BET_AMOUNT=1 \
./script/testnet/run_live_suite.sh
```

For multi-wager and multi-actor stress testing, see [`TESTNET-STRESS-SUITE.md`](TESTNET-STRESS-SUITE.md).

## Alchemy dashboard fit

This suite works well with Alchemy:

- observe `eth_call` volume in read-only mode
- observe tx count and gas used in minimal-tx mode
- keep budgets low by running read-only in CI and minimal-tx on a scheduled cadence
