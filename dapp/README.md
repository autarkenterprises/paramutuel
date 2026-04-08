## Minimal dApp (MVP)

This is a minimal, no-build frontend that uses `ethers` from a CDN (UMD bundle) and loads contract ABIs from committed files in `dapp/abi/`, with a fallback to Foundry build artifacts in `out/`.

It supports:
- **Protocol choice:** **v1** (`ParamutuelFactory` / `ParamutuelWager`, single winning outcome) or **v2** (`ParamutuelFactoryV2` / `ParamutuelWagerV2`, ADR-0008 bitmask tickets and payoff policies).
- Creating wagers via the selected factory (v2 adds payoff policy, `policyParam` for `AT_LEAST_K`, and parses `WagerCreatedV2`).
- Optional seeded liquidity at create-time (multi-outcome in one tx)
- Configuring delegated lifecycle roles (`resolver`, `bettingCloser`, `resolutionCloser`)
- Finite windows or closer-managed no-max windows (`bettingCloseTime = 0`, `resolutionWindow = 0`)
- Placing bets (`placeBet`)
- Placing batch bets across outcomes (`placeBets`)
- Odds/payout preview for the selected outcome and bet size
- Closing betting / resolution windows + resolving / retracting / expiring wagers
- Claiming payouts
- Withdrawing fees (`withdrawFees`)

### Prerequisites

- A node wallet with gas funds on your target network
- Deployed contract addresses:
  - `ParamutuelFactory` (v1) and/or `ParamutuelFactoryV2` (v2)
  - Optional: set `factoryV2Address` in `config/deployments.json` for auto-fill when **Protocol → v2** is selected (v1 continues to use `factoryAddress`).
  - Wagers are created dynamically; the dApp reads the wager address from `WagerCreated` or `WagerCreatedV2`.
- Serve the directory with an HTTP server (do not open via `file://...`).

### Run locally

From repo root:

```bash
./script/dapp/launch_dapp.sh
```

Then open:

`http://localhost:8080/dapp/`

Manual alternative:

```bash
python3 -m http.server 8080
```

### How to configure

In the dApp UI, paste:
- **Protocol** (v1 vs v2) — loading an existing wager **auto-detects** v2 via `payoffPolicy()`.
- `Factory address` (auto-filled from `config/deployments.json`: `factoryAddress` / `factoryV2Address` by protocol)
- `Collateral token preset` (network-aware dropdown; includes Base mainnet and Base Sepolia presets)
- `Collateral token (ERC20) address`
- Outcomes (comma-separated strings)
- Proposition
- Optional **Resolver address** (empty = your connected wallet resolves; or set an oracle / sponsored resolver)
- Optional **Betting closer** and **Resolution closer** addresses (`empty` disables authority close for that window; set either field to your connected wallet address to delegate that closer role to the proposer)
- `Bet close input mode` (`relative` seconds-from-now or `absolute` local date/time)
- `Resolution window input mode` (`relative` seconds-after-close or `absolute` local date/time)
- `Resolution window` (seconds after close, when relative mode is selected)
- Optional no-max checkboxes for both windows (closer-managed mode)
- Wager template selection (sports, election, long-horizon, closer-managed)
- Optional extra fee recipients + bps (comma-separated)
- Optional seed outcome indices + seed amounts (comma-separated aligned lists). **v2:** each seed index is a **single-outcome** ticket mask (`1 << index`).
- **v2 only:** payoff policy dropdown + policy param (`k` for `AT_LEAST_K`, otherwise `0`). Up to **64** outcomes on the v2 factory.
- **Betting / resolution (v2):** enter **comma-separated outcome indices** to build the ticket or winning set bitmask (e.g. `0,2`). **v1** remains a **single integer** per field (no commas).

### Notes

- The wallet section shows detected network (`chainId`) after connect. If token preset and wallet network mismatch, the UI warns and blocks wager-creation submission.
- **Bet amounts** are converted using the collateral token’s on-chain `decimals()` (read via your connected wallet’s RPC). You only need **Manual decimals override** if the token is non-standard or the call fails.
- Time fields in the create form support both relative and absolute UX. On submit, the dApp sends an absolute unix `bettingCloseTime` either from `now + offset` (relative mode) or from your selected local date/time (absolute mode).
- Resolution timing supports both relative and absolute UX. In absolute mode, the dApp converts your selected resolution-close timestamp into `resolutionWindow` seconds after the effective betting close.
- The dApp enforces that the computed resolution window (including absolute-mode conversion) is at least the factory `minResolutionWindow`.
- Leaving closer fields empty creates time-only finite windows (no authority pre-emption) when finite windows are configured.
- If you enable a no-max window, the dApp requires the matching closer address to prevent creating an uncloseable wager.
- Seeded create flow automatically performs token `approve(factory, totalSeedAmount)` before submitting `createWager`.
- The contract compares against on-chain `block.timestamp`. If transaction inclusion is delayed, the effective remaining window can be shorter than expected; very tight windows can fail factory minimum-window checks at execution time.
- The dApp attempts to read factory `minBettingWindow()` and `minResolutionWindow()` and warns if your inputs violate them.
- Seeding and batch bets support multi-outcome entries with one approval + one transaction path.
- Factory address defaults are loaded from the repo-level single source of truth (`config/deployments.json`) when served over HTTP.
- Shared logic used by the UI is in `dapp/logic.js` with independent tests in `dapp/tests/logic.test.js`.

