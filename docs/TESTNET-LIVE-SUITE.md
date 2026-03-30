# Testnet Live Suite (Base Sepolia)

This suite tests deployed contracts on Base Sepolia rather than local unit-test code paths.

It has three modes:

- `readonly` (default): `eth_call` checks only, no transactions, no gas.
- `minimal-tx`: one lightweight lifecycle flow with low-value/no-value actions to validate live state transitions.
- `funded-tx`: real collateral flow (`approve` + `placeBet` + `resolve/retract/expire` + `claim` + optional `withdrawFees`) plus optional unauthorized-role negative checks.

## Why this is low-cost

- `readonly` mode uses only RPC calls (Alchemy dashboard usage, no ETH).
- `minimal-tx` sends a small number of transactions (create market, close betting, close resolution window, expire).
- It uses `bettingCloseTime=0` and `resolutionWindow=0` so no waiting windows are needed and no bet funding is required.

## Required environment

- `RPC_URL_BASE_SEPOLIA` (or legacy `RPC_URL_SEPOLIA`)
- Factory address source:
  - default: `config/deployments.json` -> `baseSepolia.factoryAddress`
  - override: `FACTORY_ADDRESS`

Optional:

- `TESTNET_MARKET_ADDRESS` (to run additional read checks on a known market)
- `TESTNET_MODE=minimal-tx` (for transaction checks)
- `PRIVATE_KEY` (required for `minimal-tx`)
- `TESTNET_MODE=funded-tx` (for funded lifecycle checks)
- `TESTNET_COLLATERAL_TOKEN` (required for `funded-tx`, ERC20 with `decimals()/approve()/balanceOf()`)
- `TESTNET_BET_AMOUNT` (optional, default `1`; human token units)
- `TESTNET_SECONDARY_PRIVATE_KEY` (optional; if funded, places a second bet on opposite outcome)
- `TESTNET_UNAUTHORIZED_PRIVATE_KEY` (optional; enables negative access-control tx checks)

## Run

```bash
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
./script/testnet/run_live_suite.sh
```

Read-only + existing market checks:

```bash
TESTNET_MARKET_ADDRESS=0x... \
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

Funded tx mode:

```bash
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
TESTNET_MODE=funded-tx \
PRIVATE_KEY=0x... \
TESTNET_COLLATERAL_TOKEN=0x... \
TESTNET_BET_AMOUNT=1 \
./script/testnet/run_live_suite.sh
```

For multi-market and multi-actor stress testing, see [`TESTNET-STRESS-SUITE.md`](TESTNET-STRESS-SUITE.md).

## Alchemy dashboard fit

This suite works well with Alchemy:

- observe `eth_call` volume in read-only mode
- observe tx count and gas used in minimal-tx mode
- keep budgets low by running read-only in CI and minimal-tx on a scheduled cadence
