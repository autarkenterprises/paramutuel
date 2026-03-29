## Paramutuel (MVP)

Tagline: **“Augur for prop bets”** — starting with a minimal MVP that is intentionally structured to later support more decentralized resolution mechanisms.

**Market research & thesis:** see [`research/market-viability.md`](research/market-viability.md) and [`research/README.md`](research/README.md).
**Chain/fee decision memo:** see [`research/chain-and-fee-review.md`](research/chain-and-fee-review.md) (Base primary, Arbitrum secondary).
**Operator workflows (CLI/API):** see [`docs/WORKFLOWS.md`](docs/WORKFLOWS.md).
**Testnet rehearsal plan:** see [`docs/TESTNET-REHEARSAL.md`](docs/TESTNET-REHEARSAL.md).
**Service layer modules:** see [`service/README.md`](service/README.md).

## Clone and Use on Base Sepolia (dApp + CLI)

This section is for an arbitrary user who clones the repo and wants to interact end-to-end in pre-production.

### 1) Prerequisites

- `forge` + `cast` installed (Foundry)
- `python3` and `node`
- MetaMask (or other EVM wallet)
- Base Sepolia test ETH

### 2) Clone and build

```bash
git clone https://github.com/autarkenterprises/paramutuel.git
cd paramutuel
forge build
```

`forge build` is required because the dApp reads ABIs from `out/`, which is not committed.

### 3) Configure wallet/network

In MetaMask, use **Base Sepolia**:

- RPC URL: `https://base-sepolia.g.alchemy.com/v2/2aW1C2BWaTdcvRNjgLwVU` (or your own provider)
- Chain ID: `84532`
- Currency: `ETH`
- Explorer: `https://sepolia.basescan.org`

### 4) Start the dApp locally

```bash
python3 -m http.server 8080
```

Open:

- `http://localhost:8080/dapp/`

In the dApp UI:

- connect wallet
- set factory address:
  - `0xb288575730Eff094d21d13f1705eB671e8799E70`
- create/load markets and run lifecycle actions

### 5) CLI interaction (cast)

Export required env vars:

```bash
export RPC_URL_BASE_SEPOLIA="https://base-sepolia.g.alchemy.com/v2/2aW1C2BWaTdcvRNjgLwVU"
export PRIVATE_KEY="0xYOUR_PRIVATE_KEY"
```

#### Create market

```bash
cast send "0xb288575730Eff094d21d13f1705eB671e8799E70" \
  "createMarket(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])" \
  "0xCOLLATERAL_TOKEN" \
  "Will X happen?" \
  "[\"YES\",\"NO\"]" \
  0 \
  0 \
  0x0000000000000000000000000000000000000000 \
  0x0000000000000000000000000000000000000000 \
  0x0000000000000000000000000000000000000000 \
  "[]" \
  "[]" \
  --rpc-url "$RPC_URL_BASE_SEPOLIA" \
  --private-key "$PRIVATE_KEY"
```

Notes:

- `bettingCloseTime = 0` and `resolutionWindow = 0` create no-max (closer-managed) windows.
- zero addresses for resolver/closers default those roles to proposer.

#### Place bet

```bash
cast send "0xTOKEN" "approve(address,uint256)" "0xMARKET" 1000000000000000000 \
  --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"

cast send "0xMARKET" "placeBet(uint256,uint256)" 0 1000000000000000000 \
  --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
```

#### Lifecycle actions

```bash
cast send "0xMARKET" "closeBetting()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
cast send "0xMARKET" "resolve(uint256)" 0 --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
# or retract / expire
cast send "0xMARKET" "retract()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
cast send "0xMARKET" "expire()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
```

#### Claim and fee withdrawal

```bash
cast send "0xMARKET" "claim()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
cast send "0xMARKET" "withdrawFees()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
```

### 6) Optional: full local service stack (explorer + control panel + sweeper)

Create `.env` from template and run:

```bash
cp .env.example .env
set -a && source .env && set +a
./script/testnet/launch_testnet.sh
```

Then use:

- indexer API: `http://127.0.0.1:8090`
- explorer: `http://127.0.0.1:8091`
- control panel: `http://127.0.0.1:8092`

### Recorded long-term design considerations

Smart contracts cannot observe real-world truth directly. A fully decentralized version of this protocol ultimately requires an oracle / resolution mechanism such as:

- **Dispute-driven bonded reporting (Augur-style)**: anyone can report, anyone can dispute with escalating bonds, eventual finalization, bond redistribution to honest participants, and an explicit **INVALID/AMBIGUOUS** path.
- **Optimistic oracle**: a proposed answer finalizes unless challenged; disputes are adjudicated by a decentralized mechanism.
- **Crypto-native outcomes only**: restrict markets to on-chain observable facts (prices, contract state) to avoid external truth dependencies.

Key hard problems to plan for (later): invalid/ambiguous markets, liveness (no one reports), spam resistance, sybil resistance, and outcome representation for numeric / non-binary answers.

### MVP scope (current milestone)

This MVP intentionally centralizes resolution **per-market** (not per-protocol):

- The **proposer** creates a market with a set of **text outcome strings**.
- The **proposer is also the resolver** and finalizes the market by selecting exactly one outcome index.
- The proposer may alternatively **retract** the market, which invalidates it and returns wagers **minus fees**.
- A protocol **treasury** receives a default fee; additional fee recipients and percentages may be specified at market creation.

The purpose of this MVP is to clarify **actors**, their **permissions**, and the **accounting model**, while keeping the contract modular so resolution can be swapped later.

**Agents & automation:** see [`docs/MACHINE.md`](docs/MACHINE.md) for JSON HTTP API shapes, ABI locations, and a concise on-chain state machine for bots.

### Actors and relationships (MVP)

- **Protocol (Factory)**:
  - Maintains the protocol **treasury address** and the **default protocol fee** (basis points).
  - Enforces global constraints (min windows, caps on outcomes/fees).
  - Deploys new markets.

- **Proposer (per-market)**:
  - The address that calls `createMarket` on the factory; stored on-chain as `proposer` for transparency.

- **Resolver (per-market)**:
  - Address authorized to **resolve** (choose winning outcome) or **retract** (invalidate).
  - Defaults to the proposer when `resolver == address(0)` is passed at creation; may be set to any other address (oracle, sponsored resolver, multisig, etc.).

- **Betting closer (per-market)**:
  - May call **`closeBetting()`** to stop new bets.
  - `bettingCloseTime = 0` enables **no max betting window**, so only `bettingCloser` can end betting.
  - Defaults to the proposer when `bettingCloser == address(0)` at creation.

- **Resolution closer (per-market)**:
  - After betting has ended, may call **`closeResolutionWindow()`** to end the resolver window.
  - `resolutionWindow = 0` enables **no max resolution window**, so only `resolutionCloser` can end it.
  - Defaults to the proposer when `resolutionCloser == address(0)` at creation.

- **Bettors (per-market)**:
  - Deposit collateral during the betting window and allocate it to exactly one outcome per bet.
  - After resolve: winners can claim pro-rata payouts.
  - After retract/expire: bettors can claim refunds minus fees.

- **Beneficiaries (fees)**:
  - The protocol treasury is always a beneficiary (unless protocol fee is set to 0).
  - Market creation can specify additional recipients with fee BPS.
  - Fees are taken once, at market finalization (resolve/retract/expire).

### Lifecycle (MVP)

1. **Create market**
   - Proposer supplies:
     - `collateralToken` (ERC20)
     - `outcomes[]` (strings)
    - `bettingCloseTime` (absolute time, or `0` for no max betting window)
    - `resolutionWindow` (duration after effective betting close, or `0` for no max resolution window)
     - `resolver` (`address(0)` → proposer)
     - `bettingCloser` (`address(0)` → proposer)
     - `resolutionCloser` (`address(0)` → proposer)
     - `feeRecipients[]`, `feeBps[]` (optional)
   - Factory enforces sane constraints (min betting window, min resolution window, caps).

2. **Betting**
   - Any address deposits collateral and chooses an outcome index.
  - Bets stop when **`bettingCloseTime`** is reached **or** **`closeBetting()`** is called by `bettingCloser`.
  - If `bettingCloseTime = 0`, betting remains open until `closeBetting()`.

3. **Finalization**
  - After betting has closed and while the resolution window is open (not timed out and **`closeResolutionWindow()`** not yet called):
     - Resolver may **resolve(outcomeIndex)**.
     - Resolver may **retract()**.
  - After the resolution window ends by **timestamp** (if configured) or **authority** (if not resolved/retracted):
     - Anyone may **expire()**, which invalidates and enables refunds (minus fees) to avoid stuck funds.

4. **Claims**
   - If resolved: winners claim pro-rata from the net pot.
   - If retracted/expired: bettors claim refund minus fees.
   - Fee recipients withdraw their accrued fee balances.

### Notes on “distributed” roadmap (later)

This MVP isolates resolution logic to per-market functions so it can later be extended/replaced with:

- bonded reporting + dispute game
- oracle adapters
- validity/ambiguity resolution paths

### Deploying the MVP with Foundry

- **Prerequisites**:
  - `forge` installed and configured.
  - Deployer EOA with gas funds on your target network.
  - RPC URL for the target network (for MVP recommendation: **Base Sepolia** testnet first).

- **1. Configure environment**
  - Create a `.env` in the repo root (already ignored by `.gitignore`):

    ```bash
    RPC_URL_BASE_SEPOLIA="https://sepolia.base.org"
    PRIVATE_KEY="0x..."              # deployer private key
    ETHERSCAN_API_KEY="..."          # optional, for verification
    ```

  - Optionally, add RPC endpoints to `foundry.toml`:

    ```toml
    [rpc_endpoints]
    base_sepolia = "${RPC_URL_BASE_SEPOLIA}"
    ```

- **2. Deploy `ParamutuelFactory`**

  - Constructor parameters:
    - `treasury_`: address to receive protocol fees (e.g. DAO multisig).
    - `protocolFeeBps_`: protocol fee in basis points (e.g. `200` = 2%).
    - `minBettingWindow_`: minimum seconds between creation and `bettingCloseTime`.
    - `minResolutionWindow_`: minimum resolution window length in seconds.

  - Using the provided script:

    ```bash
    forge script script/DeployFactory.s.sol \
      --rpc-url $RPC_URL_BASE_SEPOLIA \
      --private-key $PRIVATE_KEY \
      --broadcast
    ```

  - The script logs the deployed `ParamutuelFactory` address; record this as the protocol entrypoint.

- **3. Creating markets**

  Once the factory is deployed, markets are created via `createMarket`:

  - Inputs:
    - `collateralToken`: ERC20 address used for bets (e.g. USDC).
    - `question`: human-readable prop question.
    - `outcomes[]`: text labels for possible outcomes.
    - `bettingCloseTime`: unix timestamp \(>\) `block.timestamp + minBettingWindow`.
    - `resolutionWindow`: seconds \(>= minResolutionWindow\).
    - `resolver`: `address(0)` to use the proposer; otherwise the delegated resolver address.
    - `extraFeeRecipients[]`, `extraFeeBps[]`: optional, additional beneficiaries.

  - You can call `createMarket`:
    - From a frontend using ethers.js / viem.
    - From a Foundry script (to be added later).

- **4. Using a deployed market**

  - **Bettors**:
    - `IERC20(collateralToken).approve(market, amount)`
    - `ParamutuelMarket(market).placeBet(outcomeIndex, amount)`
  - **Resolver** (often the proposer):
    - After `bettingCloseTime` and before `resolutionDeadline`:
      - `resolve(winningOutcomeIndex)` or `retract()`.
  - **Anyone**:
    - After `resolutionDeadline` if still open: `expire()` to unlock refunds.
  - **Claims**:
    - Bettors call `claim()` after finalization.
    - Fee recipients call `withdrawFees()` to pull accrued fees.

### Minimal dApp

A minimal no-build dApp is available in `dapp/`. It can:
- create markets through the deployed `ParamutuelFactory`
- place bets (`placeBet`)
- resolve / retract / expire
- claim payouts and withdraw fees

Run an HTTP server from the repo root (do not use `file://`):

```bash
python3 -m http.server 8080
```

Then open:

`http://localhost:8080/dapp/`

See `dapp/README.md` for UI details and deployment assumptions.


