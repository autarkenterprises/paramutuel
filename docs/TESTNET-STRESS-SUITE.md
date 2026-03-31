# Testnet stress suite (Base Sepolia)

This complements the [live integration suite](TESTNET-LIVE-SUITE.md) with **many wagers** and **distinct EOAs per role** (proposer, resolver, betting closer, resolution closer).

## Modes

| `STRESS_MODE` | What it does | Gas |
|---------------|----------------|-----|
| `readonly` (default) | Samples up to `STRESS_SAMPLE_WAGERS` latest wagers from configured factory address and asserts on-chain invariants | None |
| `tx` | Creates `STRESS_WAGER_COUNT` new wagers; each wager uses **four different keys** for the four roles; runs resolve / retract / expire branches | One burst of txs |
| `funded-tx` | Creates `STRESS_WAGER_COUNT` new wagers; each wager uses **six different keys** (4 roles + 2 bettors), does real `approve` + `placeBet`, then resolve/retract/expire and claims | Higher tx burst |

## Automatically creating wallets

EOAs are just **secp256k1 private keys**. You can generate them locally without MetaMask:

1. **Foundry (recommended in this repo)**

   ```bash
   python3 script/testnet/gen_stress_wallet_pool.py 40 test/testnet/stress_wallet_pool.json
   ```

   This repeatedly runs `cast wallet new --json` and merges the results into one JSON file.

2. **One-off key**

   ```bash
   cast wallet new --json
   ```

3. **Mnemonic-derived keys** (not wired into scripts here)

   ```bash
   cast wallet new-mnemonic
   cast wallet private-key --mnemonic "<phrase>" --mnemonic-index 0
   ```

**Security:** treat generated keys like secrets. The pool file is listed in `.gitignore`; never commit it.

## Funding actors

Each address that sends a transaction needs Base Sepolia ETH for gas. After generating the pool, fund every address (faucet or transfer from a funded test wallet):

```bash
export RPC_URL_BASE_SEPOLIA="https://base-sepolia.g.alchemy.com/v2/<key>"
export PRIVATE_KEY="0xFUNDER"
export STRESS_POOL_PATH="test/testnet/stress_wallet_pool.json"
# optional: STRESS_FUND_WEI=5000000000000000
./script/testnet/fund_stress_wallets.sh
```

For funded collateral scenarios, you can also fan out Base Sepolia USDC from a funded key:

```bash
export RPC_URL_BASE_SEPOLIA="https://base-sepolia.g.alchemy.com/v2/<key>"
export PRIVATE_KEY="0xFUNDER"
export STRESS_POOL_PATH="test/testnet/stress_wallet_pool.json"
# optional: STRESS_USDC_TOKEN=0x036CbD53842c5426634e7929541eC2318f3dCf7e
# optional: STRESS_USDC_AMOUNT_RAW=100000   # 0.1 USDC (6 decimals)
./script/testnet/fund_stress_wallets_usdc.sh
```

## Run stress suite

Factory address source:
- default: `config/deployments.json` -> `baseSepolia.factoryAddress`
- override: `FACTORY_ADDRESS`

Recommended cadence:

1. `readonly` on each change set
2. `tx` for lifecycle/state-transition stress
3. `funded-tx` for full ERC-20 settlement paths

Quick sanity check for the resolved factory address:

```bash
source ./script/lib/deployments.sh
ensure_factory_address "base-sepolia" "./config/deployments.json"
echo "$FACTORY_ADDRESS"
```

Read-only:

```bash
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
./script/testnet/run_stress_suite.sh
```

Transaction mode (after pool + funding):

```bash
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
STRESS_MODE=tx \
STRESS_WALLET_POOL_PATH=test/testnet/stress_wallet_pool.json \
STRESS_FUNDER_PRIVATE_KEY=0x... \
STRESS_WAGER_COUNT=5 \
./script/testnet/run_stress_suite.sh
```

Funded transaction mode (after pool + ETH + collateral funding):

```bash
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
STRESS_MODE=funded-tx \
STRESS_WALLET_POOL_PATH=test/testnet/stress_wallet_pool.json \
STRESS_COLLATERAL_TOKEN=0x... \
STRESS_BET_AMOUNT=1 \
./script/testnet/run_stress_suite.sh
```

`STRESS_FUNDER_PRIVATE_KEY` (or `PRIVATE_KEY`) must be funded; it is used for permissionless `expire()` in the expire-branch scenarios. Proposers and role wallets use their own keys from the pool.

## Tunables

| Variable | Default | Meaning |
|----------|---------|---------|
| `STRESS_SAMPLE_WAGERS` | `12` | Max recent wagers to read in `readonly` |
| `STRESS_WAGER_COUNT` | `3` | Wagers to create in `tx` mode |
| `STRESS_WALLET_POOL_PATH` | (empty) | Required for `tx`; JSON from generator |
| `STRESS_FUNDER_PRIVATE_KEY` | — | Funded key for `expire()`; falls back to `PRIVATE_KEY` |
| `STRESS_COLLATERAL_TOKEN` | (empty) | Required for `funded-tx`; ERC20 with `decimals()/approve()/balanceOf()` |
| `STRESS_BET_AMOUNT` | `1` | Human token units per bettor per wager in `funded-tx` |
| `STRESS_UNAUTHORIZED_PRIVATE_KEY` | (empty) | Optional; enables negative access-control checks in `funded-tx` |
| `STRESS_INDEXER_BASE_URL` | from `config/deployments.json` | Optional override for hosted indexer visibility checks |

## Alchemy / cost notes

- **Readonly** mode only issues `eth_call`; Alchemy metered usage is cheap in practice and uses **no** test ETH.
- **Tx** mode cost scales with `STRESS_WAGER_COUNT` (several txs per wager). Keep counts low for routine runs; raise for occasional stress campaigns.
- **Funded-tx** mode adds ERC20 transfers + claims, so both ETH gas and funded collateral balances are required for bettor wallets.
