## Minimal dApp (MVP)

This is a minimal, no-build frontend that uses `ethers` from a CDN (UMD bundle) and loads contract ABIs from Foundry build artifacts in `out/`.

It supports:
- Creating markets via `ParamutuelFactory`
- Placing bets (`placeBet`)
- Resolving / retracting / expiring markets
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
python3 -m http.server 8080
```

Then open:

`http://localhost:8080/dapp/`

### How to configure

In the dApp UI, paste:
- `Factory address`
- `Collateral token (ERC20) address`
- Outcomes (comma-separated strings)
- Question text
- `Bet close` (seconds from now)
- `Resolution window` (seconds after close)
- Optional extra fee recipients + bps (comma-separated)

### Notes

- Amounts are parsed using the `decimals` input (defaults to `18`).
- The dApp attempts to read factory `minBettingWindow()` and `minResolutionWindow()` and warns if your inputs violate them.
- This MVP resolver is centralized-per-market (the market `resolver` is whoever calls `createMarket`).

