# Testnet Live Suite (Base Sepolia)

This suite tests deployed contracts on Base Sepolia rather than local unit-test code paths.

It has two modes:

- `readonly` (default): `eth_call` checks only, no transactions, no gas.
- `minimal-tx`: one lightweight lifecycle flow with low-value/no-value actions to validate live state transitions.

## Why this is low-cost

- `readonly` mode uses only RPC calls (Alchemy dashboard usage, no ETH).
- `minimal-tx` sends a small number of transactions (create market, close betting, close resolution window, expire).
- It uses `bettingCloseTime=0` and `resolutionWindow=0` so no waiting windows are needed and no bet funding is required.

## Required environment

- `RPC_URL_BASE_SEPOLIA` (or legacy `RPC_URL_SEPOLIA`)
- `FACTORY_ADDRESS`

Optional:

- `TESTNET_MARKET_ADDRESS` (to run additional read checks on a known market)
- `TESTNET_MODE=minimal-tx` (for transaction checks)
- `PRIVATE_KEY` (required for `minimal-tx`)

## Run

```bash
FACTORY_ADDRESS=0x... \
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
./script/testnet/run_live_suite.sh
```

Read-only + existing market checks:

```bash
FACTORY_ADDRESS=0x... \
TESTNET_MARKET_ADDRESS=0x... \
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
./script/testnet/run_live_suite.sh
```

Minimal tx mode:

```bash
FACTORY_ADDRESS=0x... \
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
TESTNET_MODE=minimal-tx \
PRIVATE_KEY=0x... \
./script/testnet/run_live_suite.sh
```

For multi-market and multi-actor stress testing, see [`TESTNET-STRESS-SUITE.md`](TESTNET-STRESS-SUITE.md).

## Alchemy dashboard fit

This suite works well with Alchemy:

- observe `eth_call` volume in read-only mode
- observe tx count and gas used in minimal-tx mode
- keep budgets low by running read-only in CI and minimal-tx on a scheduled cadence
