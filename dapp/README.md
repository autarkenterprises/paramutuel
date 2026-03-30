## Minimal dApp (MVP)

This is a minimal, no-build frontend that uses `ethers` from a CDN (UMD bundle) and loads contract ABIs from Foundry build artifacts in `out/`.

It supports:
- Creating markets via `ParamutuelFactory`
- Configuring delegated lifecycle roles (`resolver`, `bettingCloser`, `resolutionCloser`)
- Finite windows or closer-managed no-max windows (`bettingCloseTime = 0`, `resolutionWindow = 0`)
- Placing bets (`placeBet`)
- Odds/payout preview for the selected outcome and bet size
- Closing betting / resolution windows + resolving / retracting / expiring markets
- Claiming payouts
- Withdrawing fees (`withdrawFees`)

### Prerequisites

- A node wallet with gas funds on your target network
- Deployed contract addresses:
  - `ParamutuelFactory` address
  - (markets are created dynamically; the dApp reads the market address from the `MarketCreated` event)
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
- `Factory address`
- `Collateral token preset` (network-aware dropdown; includes Base mainnet and Base Sepolia presets)
- `Collateral token (ERC20) address`
- Outcomes (comma-separated strings)
- Question text
- Optional **Resolver address** (empty = your connected wallet resolves; or set an oracle / sponsored resolver)
- Optional **Betting closer** and **Resolution closer** addresses (`empty` disables authority close for that window)
- `Bet close input mode` (`relative` seconds-from-now or `absolute` local date/time)
- `Resolution window` (seconds after close)
- Optional no-max checkboxes for both windows (closer-managed mode)
- Market template selection (sports, election, long-horizon, closer-managed)
- Optional extra fee recipients + bps (comma-separated)

### Notes

- The wallet section shows detected network (`chainId`) after connect. If token preset and wallet network mismatch, the UI warns and blocks create-market submission.
- **Bet amounts** are converted using the collateral token’s on-chain `decimals()` (read via your connected wallet’s RPC). You only need **Manual decimals override** if the token is non-standard or the call fails.
- Time fields in the create form support both relative and absolute UX. On submit, the dApp sends an absolute unix `bettingCloseTime` either from `now + offset` (relative mode) or from your selected local date/time (absolute mode).
- Leaving closer fields empty creates time-only finite windows (no authority pre-emption) when finite windows are configured.
- If you enable a no-max window, the dApp requires the matching closer address to prevent creating an uncloseable market.
- The contract compares against on-chain `block.timestamp`. If transaction inclusion is delayed, the effective remaining window can be shorter than expected; very tight windows can fail factory minimum-window checks at execution time.
- The dApp attempts to read factory `minBettingWindow()` and `minResolutionWindow()` and warns if your inputs violate them.
- Shared logic used by the UI is in `dapp/logic.js` with independent tests in `dapp/tests/logic.test.js`.

