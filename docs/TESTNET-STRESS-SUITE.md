# Testnet stress suite (Base Sepolia)

This complements the [live integration suite](TESTNET-LIVE-SUITE.md) with **many markets** and **distinct EOAs per role** (proposer, resolver, betting closer, resolution closer).

## Modes

| `STRESS_MODE` | What it does | Gas |
|---------------|----------------|-----|
| `readonly` (default) | Samples up to `STRESS_SAMPLE_MARKETS` latest markets from `FACTORY_ADDRESS` and asserts on-chain invariants | None |
| `tx` | Creates `STRESS_MARKET_COUNT` new markets; each market uses **four different keys** for the four roles; runs resolve / retract / expire branches | One burst of txs |

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

## Run stress suite

Read-only:

```bash
FACTORY_ADDRESS=0x... \
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
./script/testnet/run_stress_suite.sh
```

Transaction mode (after pool + funding):

```bash
FACTORY_ADDRESS=0x... \
RPC_URL_BASE_SEPOLIA=https://base-sepolia.g.alchemy.com/v2/<key> \
STRESS_MODE=tx \
STRESS_WALLET_POOL_PATH=test/testnet/stress_wallet_pool.json \
STRESS_FUNDER_PRIVATE_KEY=0x... \
STRESS_MARKET_COUNT=5 \
./script/testnet/run_stress_suite.sh
```

`STRESS_FUNDER_PRIVATE_KEY` (or `PRIVATE_KEY`) must be funded; it is used for permissionless `expire()` in the expire-branch scenarios. Proposers and role wallets use their own keys from the pool.

## Tunables

| Variable | Default | Meaning |
|----------|---------|---------|
| `STRESS_SAMPLE_MARKETS` | `12` | Max recent markets to read in `readonly` |
| `STRESS_MARKET_COUNT` | `3` | Markets to create in `tx` mode |
| `STRESS_WALLET_POOL_PATH` | (empty) | Required for `tx`; JSON from generator |
| `STRESS_FUNDER_PRIVATE_KEY` | — | Funded key for `expire()`; falls back to `PRIVATE_KEY` |

## Alchemy / cost notes

- **Readonly** mode only issues `eth_call`; Alchemy metered usage is cheap in practice and uses **no** test ETH.
- **Tx** mode cost scales with `STRESS_MARKET_COUNT` (several txs per market). Keep counts low for routine runs; raise for occasional stress campaigns.
