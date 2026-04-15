# Faucet runbook — funding the ARG treasury on Base Sepolia

Target: **0.15 ETH + 600 USDC** on the ARG treasury address
(`.roles.treasury.address` in `config/microwonk-wallets.json`).
Verify at any point with `./script/microwonk/check_balances.sh`; the treasury
row shows `LOW-ETH` / `LOW-USDC` until both thresholds clear.

This runbook is resumable. If we leave in the middle of a top-up, any new
session can read `config/faucet-playbook.json` + `config/faucet-state.json`
and pick up from the next eligible drip via:

```bash
python3 script/microwonk/next_faucet_run.py resume
```

## Architecture

```
                                                                  ┌─────────────┐
  CDP faucet ─┐                                                   │  microwonks │
  Alchemy   ─┐│                                           fund    │     ×8      │
  QuickNode ─┼┼─> dock_01 ─┐                          ┌──────────>│  proposer   │
  LearnWeb3 ─┘│            │   load_treasury.sh       │           │  resolver   │
              │            ├──────────────────────────>  TREASURY │             │
  Circle     ─┼─> dock_02 ─┤   (batch dock -> treasury)│           └─────────────┘
  Circle     ─┼─> dock_03 ─┘                          │
  (parallel)  │
```

Rationale: faucet rate limits are *per-address*, so 3 loading docks ≈ 3× the
per-hour Circle throughput. Docks also keep the treasury off faucet logs.

## 1. One-time setup

```bash
# Generate 3 loading-dock EOAs.
./script/microwonk/loading_dock_init.sh 3

# Load the new keys into your shell.
source config/microwonk-keys.env

# Verify addresses.
python3 script/microwonk/next_faucet_run.py next
```

The advisor prints one row per (faucet × dock) pair with a `READY` or `wait`
status. On first run every pair is `READY`.

## 2. Account prep (human-only, one-time per faucet)

| Faucet | What you do |
|--------|-------------|
| Coinbase CDP | Create a CDP project at `portal.cdp.coinbase.com`; no per-wallet linking required. |
| Alchemy | Create an Alchemy account; connect a wallet on *Ethereum mainnet* that holds ≥ 0.001 ETH (one-time gate). |
| QuickNode | Create a QuickNode account; sign in. |
| LearnWeb3 | Sign in via GitHub OAuth. |
| Circle | Create a Circle Developer account; confirm email. |

Skip any you can't set up — the advisor just reports fewer eligible rows.

## 3. The drip loop

Repeat until the treasury is full. Each cycle:

```bash
# 1. Check what's eligible now.
python3 script/microwonk/next_faucet_run.py next

# 2. Claude + you visit each READY faucet (Chrome):
#    - You handle sign-in and CAPTCHA.
#    - Claude pastes the dock address, clicks Request, reads the tx hash.

# 3. After each successful drip, record it so rate limits are respected.
python3 script/microwonk/next_faucet_run.py record \
    coinbase_cdp_base_sepolia dock_01 0x<tx_hash>

# 4. When any dock has nontrivial balance, batch it to the treasury.
./script/microwonk/load_treasury.sh

# 5. Progress check.
python3 script/microwonk/next_faucet_run.py progress
```

Concrete schedule for a full top-up from zero:

| Cycle | Action | Throughput per cycle |
|-------|--------|----------------------|
| T+0h | Hit CDP + Alchemy + QuickNode + LearnWeb3 on dock_01 | 0.27 ETH |
| T+0h | Hit Circle on dock_01, dock_02, dock_03 | 30 USDC |
| T+1h | Circle on all 3 docks | 30 USDC (total 60) |
| T+2h … T+20h | Continue Circle (hourly) | +30 USDC per hour |
| T+24h | CDP / Alchemy / QuickNode / LearnWeb3 reset (dock_01 or a fresh dock) | +0.27 ETH |

Realistic timeline: **~20 hours** to hit 600 USDC with 3 parallel Circle
streams. ETH clears in a single round if three ETH faucets are healthy.

If Circle caps at 10/hr/address feels too slow:
- Rotate loading docks weekly with `FORCE=1 ./script/microwonk/loading_dock_init.sh 5` to get 5 streams.
- Keep a buffer in the treasury so future campaign top-ups are smaller, not from zero.

## 4. Claude's role vs. yours

**You (human):**
- Account creation and sign-in (CDP, Alchemy, QuickNode, LearnWeb3, Circle).
- CAPTCHAs and "I am not a robot" checks.
- Wallet-connect confirmations in MetaMask / Coinbase Wallet extensions.
- Approve any unexpected dialog.

**Claude (browser + shell):**
- Open faucet tabs on request.
- Paste the current dock address into the right field.
- Click Request / Send / Get Tokens.
- Read the success toast or tx hash from the DOM.
- Call `next_faucet_run.py record …` after each drip.
- Call `load_treasury.sh` periodically to forward dock balances.
- Call `check_balances.sh` and `progress` to decide when to stop.

## 5. Stop condition

`check_balances.sh` returns exit 0 (no `LOW-*` flags) and `progress` prints
`OK` for both ETH and USDC. At that point run:

```bash
./script/microwonk/fund_wallets.sh
./script/microwonk/check_balances.sh
```

The treasury should now sit near-empty-but-above-floor; every microwonk +
proposer + resolver should show the default per-wallet allocation.

## 6. Recovery

- **Dock private key lost** — any USDC/ETH on it is stuck. Delete the entry
  from `microwonk-loading-docks.json`, generate a replacement with
  `FORCE=1 loading_dock_init.sh`, re-register with faucets.
- **Treasury compromised** — sweep microwonks (`sweep_wallets.sh`), drain old
  treasury manually, rotate with `FORCE=1 treasury_init.sh`, re-fund via this
  runbook.
- **Faucet depleted / down** — advisor keeps reporting `READY`, but the
  faucet returns an error. Mark the visit anyway with `record … --amount-raw 0`
  to park the cooldown, then move on; retry the faucet next cycle.
- **`load_treasury.sh` stalls** — check `RPC_URL_BASE_SEPOLIA`, gas price, and
  dock ETH balance (needs > `DOCK_MIN_ETH_WEI` = 0.0002 ETH to cover gas).

## 7. Machine-readable resume

```bash
python3 script/microwonk/next_faucet_run.py resume > /tmp/faucet_plan.json
```

Produces a JSON blob with `ready[]`, `waiting[]`, and `progress`. A Chrome-
driving loop (Claude or otherwise) can consume it directly:

```json
{
  "ready": [
    {
      "faucet_id": "coinbase_cdp_base_sepolia",
      "asset": "ETH",
      "url": "https://portal.cdp.coinbase.com/products/faucet",
      "dock_key": "dock_01",
      "dock_address": "0x…",
      "claude_step": "paste address into the address field, click Request, read success banner tx hash"
    }
  ],
  "waiting": [ … ],
  "progress": {
    "treasury": "0x…",
    "eth_raw": "123456789",
    "usdc_raw": "987654",
    "target_eth_wei": 150000000000000000,
    "target_usdc_raw": 600000000
  }
}
```

Feed that blob to a new Claude session with
`Let's resume the microwonk faucet top-up` and it will read the JSON, pick the
next `ready` entry, drive Chrome, and record outcomes.
