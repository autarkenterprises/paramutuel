# Microwonk wallet infrastructure

Scripts that create, fund, audit, rotate, and tear down the Ethereum wallets
used by the microwonk ARG (see
[`docs/MICROWONK-ARG.md`](../../docs/MICROWONK-ARG.md)).

## Roster

Eleven wallets defined in
[`config/microwonk-roster.json`](../../config/microwonk-roster.json):

| Role | Key | Handle | Purpose |
|------|-----|--------|---------|
| treasury | `arg_treasury` | — | Campaign float. Funds every other wallet. On mainnet this becomes a Safe with a small hot replenisher. |
| proposer | `resonance_xchg` | `@resonance_xchg` | Proposes wagers via Proposition Service; posts the in-universe broadcast feed. |
| resolver | `resolution_service` | — | Signs `resolve` / `retract` / `expire` on behalf of the Resolution Service. |
| wonk | `srce_01_echo` | `@SRCE_01_echo` | Cetacean politics, ACI dynamics. |
| wonk | `crtx_7_prime` | `@CRTX_7_prime` | Embodied-soul / clone dynamics. |
| wonk | `trbn_44_null` | `@TRBN_44_null` | God-machine jurisprudence. |
| wonk | `frog_sat_ix` | `@FROG_sat_ix` | SIMFAT / amphibian conservation. |
| wonk | `dsmr_00_flux` | `@DSMR_00_flux` | Desidereification dynamics. |
| wonk | `wkdl_k8_arb` | `@WKDL_k8_arb` | WonkDollar arbitrage. |
| wonk | `mmth_03_edge` | `@MMTH_03_edge` | 8/mmm incursion monitoring. |
| wonk | `arch_v2_root` | `@ARCH_v2_root` | Cross-corpus archivist. |

## Files this directory produces

| Path | Contents | Committed? |
|------|----------|-----------|
| `config/microwonk-wallets.json` | Public addresses keyed by persona; generation & rotation timestamps. | **Yes** |
| `config/microwonk-keys.env` | `export MICROWONK_KEY_<KEY>=0x…` plus `MICROWONK_TREASURY_PRIVATE_KEY` alias. | **No** (gitignored, chmod 600) |
| `config/microwonk-disbursements.log` | Append-only TSV ledger of every treasury→wallet and wallet→sink transfer. | **Yes** (no secrets) |

## Env vars used by the scripts

| Variable | Consumed by | Notes |
|----------|-------------|-------|
| `MICROWONK_TREASURY_PRIVATE_KEY` | fund, sweep | Preferred funder key. Set by `generate_wallets.sh` / `treasury_init.sh`. |
| `PRIVATE_KEY` | fund (fallback) | Legacy fallback — shares the Proposition Service key; a warning is printed. |
| `MICROWONK_KEY_<KEY>` | sweep | Per-wallet keys used to sweep each microwonk back to the treasury. |
| `RPC_URL_BASE_SEPOLIA` | all | Testnet RPC. |
| `RPC_URL_BASE_MAINNET` | all (when `NETWORK=base-mainnet`) | Mainnet RPC. |
| `MICROWONK_FUND_WEI` | fund | Per-recipient ETH (default 0.01). |
| `MICROWONK_USDC_RAW` | fund | Per-recipient USDC raw (default 50 USDC). |
| `MICROWONK_ROLE_MULT` | fund | Multiplier for proposer + resolver (default 5). |
| `TREASURY_MIN_WEI` | check | Floor for LOW-ETH flag (default 0.05 ETH). |
| `TREASURY_MIN_USDC_RAW` | check | Floor for LOW-USDC flag (default 200 USDC). |
| `SWEEP_TO` | sweep | Destination address; defaults to treasury row from wallets.json. |

## Typical lifecycle

### First launch

```bash
# 1. Mint 11 EOAs (treasury + proposer + resolver + 8 wonks).
./script/microwonk/generate_wallets.sh

# 2. Load keys into the current shell.
source config/microwonk-keys.env

# 3. Fund the treasury EOA from a faucet.
#    Treasury address: `jq '.roles.treasury.address' config/microwonk-wallets.json`
#    Needs ~0.15 ETH and ~600 USDC on Base Sepolia.

# 4. Distribute from treasury to every other wallet.
./script/microwonk/fund_wallets.sh

# 5. Verify.
./script/microwonk/check_balances.sh
```

### Rotating the treasury (no effect on microwonks)

```bash
# Optional: sweep any residuals on microwonks back to the current treasury.
./script/microwonk/sweep_wallets.sh

# Optional: drain the old treasury to a cold wallet.
SWEEP_TO=0xCOLD ./script/microwonk/sweep_wallets.sh   # see note below

# Mint a fresh treasury EOA and rewrite keys.env/wallets.json in place.
FORCE=1 ./script/microwonk/treasury_init.sh
source config/microwonk-keys.env

# Fund the new treasury (faucet / Safe transfer) and re-run fund_wallets.sh.
./script/microwonk/fund_wallets.sh
```

Note: `sweep_wallets.sh SWEEP_TO=0x…` sweeps **microwonk** wallets to the given
address. The old treasury must be drained manually (simple `cast send` from the
treasury key to the cold wallet) before you re-run `treasury_init.sh`.

### Campaign teardown

```bash
SWEEP_TO=0xCOLD ./script/microwonk/sweep_wallets.sh
# then manually drain treasury EOA with its key.
```

## Why these defaults

| Knob | Default | Reasoning |
|------|---------|-----------|
| 0.01 ETH / wonk | enough for thousands of `placeBet` txs at Base Sepolia gas |
| 50 USDC / wonk | dozens of small wagers at the ARG notional (~1-5 USDC each) |
| 5× for proposer / resolver | proposer posts `proposeBond` on every new wager; resolver batches many `resolve`s |
| Treasury floor 0.05 ETH / 200 USDC | ~ one full refund round in reserve, so nothing stalls if a top-up is late |

Initial treasury requirements (testnet): **~0.15 ETH** and **~600 USDC**. With
the defaults above, each refund round costs the same.

## Treasury management posture

- **Testnet (now through the campaign):** single dedicated EOA. Key lives in
  `config/microwonk-keys.env`, chmod 600, gitignored. Funded from the Base
  Sepolia + Circle faucets. Balance alarms at 0.05 ETH / 200 USDC.
- **Mainnet (future):** Gnosis Safe 2-of-3 owns the float. The EOA whose key
  ends up in `microwonk-keys.env` is a small *replenisher* that holds <$100 at
  any moment; the Safe tops it up on a schedule or via a module. All other
  behaviour stays identical; only the funding source changes.
- **Role separation:** the treasury key is never the proposer key and never the
  resolver key. Compromise of any one is recoverable; compromise of a combined
  key is not.
- **Rotation:** one treasury per campaign. Rotating mid-campaign is supported
  by `treasury_init.sh FORCE=1` but should be paired with a sweep first.
- **Accounting:** every transfer through `fund_wallets.sh` / `sweep_wallets.sh`
  appends one row per (wallet, asset) to `config/microwonk-disbursements.log`.
  Commit the log after each run for an auditable ledger.

## Operational hygiene

- `microwonk-keys.env` must never be pushed. `.gitignore` covers it, but audit
  before every push.
- `FORCE=1 generate_wallets.sh` destroys the old `microwonk-keys.env` — sweep
  first.
- Each persona's wallet is used by exactly one bettor sub-agent. Splitting a
  persona across accounts requires updating the roster, sweeping, and
  regenerating.
- Mainnet rotations should produce a new versioned roster file
  (`microwonk-roster.v2.json`) so historical on-chain activity stays
  attributable.
