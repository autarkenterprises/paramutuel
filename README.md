## Paramutuel (MVP)

Tagline: **“Augur for prop bets”** — starting with a minimal MVP that is intentionally structured to later support more decentralized resolution mechanisms.

**Wager research & thesis:** see [`research/market-viability.md`](research/market-viability.md) and [`research/README.md`](research/README.md).
**Chain/fee decision memo:** see [`research/chain-and-fee-review.md`](research/chain-and-fee-review.md) (Base primary, Arbitrum secondary).
**Operator workflows (CLI/API):** see [`docs/WORKFLOWS.md`](docs/WORKFLOWS.md).
**Testnet rehearsal plan:** see [`docs/TESTNET-REHEARSAL.md`](docs/TESTNET-REHEARSAL.md).
**Live testnet integration suite:** see [`docs/TESTNET-LIVE-SUITE.md`](docs/TESTNET-LIVE-SUITE.md).
**Testnet stress suite (multi-wager / multi-actor):** see [`docs/TESTNET-STRESS-SUITE.md`](docs/TESTNET-STRESS-SUITE.md).
**Live indexer hosting (Cloud Run):** see [`docs/INDEXER-HOSTING.md`](docs/INDEXER-HOSTING.md) and [`docs/CLOUD-RUN-HOSTING.md`](docs/CLOUD-RUN-HOSTING.md).
**Resolution Service (delegated resolver ops):** see [`docs/RESOLUTION-SERVICE.md`](docs/RESOLUTION-SERVICE.md).
**Backlog / task list:** see [`docs/TASKS.md`](docs/TASKS.md).
**Payout math (v1 + v2):** see [`docs/PAYOUT-CALCULATION.md`](docs/PAYOUT-CALCULATION.md).
**Service layer modules:** see [`service/README.md`](service/README.md).
**Hosted dApp & website:** see [GitHub Pages deployment](#hosted-dapp--protocol-website).

## Clone and Use on Base Sepolia (dApp + CLI)

This section is for an arbitrary user who clones the repo and wants to interact end-to-end in pre-production.

### 1) Prerequisites

- `forge` + `cast` installed (Foundry)
- `python3` and `node`
- MetaMask (or other EVM wallet)
- Base Sepolia test ETH
- Base Sepolia test USDC (for funded bet flows)

**Wallets (browser UIs):** The static dApp (`dapp/`) and the simplified **Place a bet** page (`site/bet.html`) connect through **EIP-1193**: they use `ethers.BrowserProvider` with an injected provider (`window.ethereum`). Any wallet that exposes a compliant provider works (for example MetaMask, Rabby, Coinbase Wallet, Brave Wallet, Frame). If several extensions register under `ethereum.providers[]`, the app prefers the first entry that implements `request`. **WalletConnect** and other non-injected flows are not included in the default static build; add a connector library if you need those. At the protocol level, anything that can sign transactions against the deployed contracts (Foundry `cast`, multisigs, automated services) is supported.

### 2) Clone and build

```bash
git clone https://github.com/autarkenterprises/paramutuel.git
cd paramutuel
forge build
```

`forge build` is optional for local development — the dApp ships committed ABI files in `dapp/abi/` and falls back to `out/` when available. Run `forge build` (or `./script/sync-abi.sh`) after contract changes to update the committed ABIs.

### 3) Configure wallet/network

In MetaMask, use **Base Sepolia**:

- RPC URL: `https://base-sepolia.g.alchemy.com/v2/2aW1C2BWaTdcvRNjgLwVU` (or your own provider)
- Chain ID: `84532`
- Currency: `ETH`
- Explorer: `https://sepolia.basescan.org`

### 3.1) Get test funds (Base Sepolia)

- **USDC (Base Sepolia):** [Circle faucet](https://faucet.circle.com/)  
  Select `Base Sepolia`, token `USDC`, and request to your wallet.
- **ETH gas (Base Sepolia):**
  - [Alchemy Base Sepolia faucet](https://www.alchemy.com/faucets/base-sepolia)
  - [Chainlink faucet](https://faucets.chain.link/base-sepolia)

### 4) Start the dApp locally

```bash
./script/dapp/launch_dapp.sh
```

Open:

- `http://localhost:8080/dapp/`

Alternative manual server command:

```bash
python3 -m http.server 8080
```

In the dApp UI:

- connect wallet
- factory address auto-fills from `config/deployments.json` (or can be overridden manually)
- create/load wagers and run lifecycle actions

Time semantics (important):

- In the dApp, `Bet close` can be entered as either a relative offset or an absolute local date/time. At click-time, both are converted to an absolute unix timestamp and sent as `bettingCloseTime`.
- The contract enforces closure against on-chain `block.timestamp`, not local browser time.
- Because transaction inclusion takes time, effective remaining window may be shorter than the offset entered at click-time; with tight windows, delayed inclusion can cause create-wager reverts against factory minimum window constraints.

### 5) CLI interaction (cast)

Export required env vars:

```bash
export RPC_URL_BASE_SEPOLIA="https://base-sepolia.g.alchemy.com/v2/2aW1C2BWaTdcvRNjgLwVU"
export PRIVATE_KEY="0xYOUR_PRIVATE_KEY"
source ./script/lib/deployments.sh
ensure_factory_address "base-sepolia" "./config/deployments.json"
```

#### Create wager (`createWager`)

```bash
cast send "$FACTORY_ADDRESS" \
  "createWager(address,string,string[],uint64,uint64,address,address,address,address[],uint16[])" \
  "0xCOLLATERAL_TOKEN" \
  "Will X happen?" \
  "[\"YES\",\"NO\"]" \
  0 \
  0 \
  0x0000000000000000000000000000000000000000 \
  0xBETTING_CLOSER_ADDRESS \
  0xRESOLUTION_CLOSER_ADDRESS \
  "[]" \
  "[]" \
  --rpc-url "$RPC_URL_BASE_SEPOLIA" \
  --private-key "$PRIVATE_KEY"
```

Optional seeded-liquidity overload (multi-outcome seed in one create tx):

```bash
cast send "$FACTORY_ADDRESS" \
  "createWager(address,string,string[],uint64,uint64,address,address,address,address[],uint16[],uint256[],uint256[])" \
  "0xCOLLATERAL_TOKEN" \
  "Will X happen?" \
  "[\"YES\",\"NO\",\"MAYBE\"]" \
  "$BETTING_CLOSE_TS" \
  "$RESOLUTION_WINDOW_SECS" \
  "0x0000000000000000000000000000000000000000" \
  "0xBETTING_CLOSER_ADDRESS" \
  "0xRESOLUTION_CLOSER_ADDRESS" \
  "[]" \
  "[]" \
  "[0,2]" \
  "[1000000,2500000]" \
  --rpc-url "$RPC_URL_BASE_SEPOLIA" \
  --private-key "$PRIVATE_KEY"
```

Notes:

- `bettingCloseTime = 0` and `resolutionWindow = 0` create no-max (closer-managed) windows.
- `resolver = address(0)` defaults resolver to proposer.
- `bettingCloser = address(0)` disables authority `closeBetting()`.
- `resolutionCloser = address(0)` disables authority `closeResolutionWindow()`.
- Protocol guardrail: `no-max + no closer` is rejected at wager creation.

#### Place bet

```bash
cast send "0xTOKEN" "approve(address,uint256)" "0xWAGER" 1000000000000000000 \
  --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"

cast send "0xWAGER" "placeBet(uint256,uint256)" 0 1000000000000000000 \
  --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
```

Batch bet (multiple outcomes in one tx):

```bash
cast send "0xTOKEN" "approve(address,uint256)" "0xWAGER" 3000000000000000000 \
  --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
cast send "0xWAGER" "placeBets(uint256[],uint256[])" "[0,2]" "[1000000000000000000,2000000000000000000]" \
  --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
```

#### Lifecycle actions

```bash
cast send "0xWAGER" "closeBetting()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
cast send "0xWAGER" "resolve(uint256)" 0 --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
# or retract / expire
cast send "0xWAGER" "retract()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
cast send "0xWAGER" "expire()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
```

#### Claim and fee withdrawal

```bash
cast send "0xWAGER" "claim()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
cast send "0xWAGER" "withdrawFees()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
```

### 6) Optional: full local service stack (explorer + control panel + sweeper)

Create `config/service.env` from template and run:

```bash
cp config/service.env.example config/service.env
source script/lib/load_service_env.sh
./script/testnet/launch_testnet.sh
```

`launch_testnet.sh` writes the latest deployment to `config/deployments.json` (`baseSepolia.factoryAddress`), which is used as the shared default by the dApp and testnet suites. For manual updates:

```bash
./script/testnet/set_factory_address.sh 0x...
```

Then use:

- indexer API: `http://127.0.0.1:8090`
- explorer: `http://127.0.0.1:8091`
- control panel: `http://127.0.0.1:8092`

### Recorded long-term design considerations

Smart contracts cannot observe real-world truth directly. A fully decentralized version of this protocol ultimately requires an oracle / resolution mechanism such as:

- **Dispute-driven bonded reporting (Augur-style)**: anyone can report, anyone can dispute with escalating bonds, eventual finalization, bond redistribution to honest participants, and an explicit **INVALID/AMBIGUOUS** path.
- **Optimistic oracle**: a proposed answer finalizes unless challenged; disputes are adjudicated by a decentralized mechanism.
- **Crypto-native outcomes only**: restrict wagers to on-chain observable facts (prices, contract state) to avoid external truth dependencies.

Key hard problems to plan for (later): invalid/ambiguous wagers, liveness (no one reports), spam resistance, sybil resistance, and outcome representation for numeric / non-binary answers.

### MVP scope (current milestone)

This MVP intentionally centralizes resolution **per-wager** (not per-protocol):

- The **proposer** creates a wager with a set of **text outcome strings**.
- The **proposer is also the resolver** and finalizes the wager by selecting exactly one outcome index.
- The proposer may alternatively **retract** the wager, which invalidates it and returns wagers **minus fees**.
- A protocol **treasury** receives a default fee; additional fee recipients and percentages may be specified at wager creation.

The purpose of this MVP is to clarify **actors**, their **permissions**, and the **accounting model**, while keeping the contract modular so resolution can be swapped later.

**Agents & automation:** see [`AGENTS.md`](AGENTS.md) (entry for AI agents and subagents), [`docs/MACHINE.md`](docs/MACHINE.md) for JSON HTTP API shapes, ABI locations, MCP server, and a concise on-chain state machine for bots.

**MCP server:** A 16-tool MCP server for LLM agent integration is available at `mcp_server/`. Run with `python -m mcp_server`. See [`docs/MACHINE.md`](docs/MACHINE.md) for details. A small **bet scout agent** for subagent-style workflows is on PyPI as **`paramutuel-bettor-agent`** (CLI `paramutuel-bettor`) and in-repo under `agents/paramutuel_bettor/` ([`docs/BET-AGENT.md`](docs/BET-AGENT.md), [`docs/BET-AGENT-DISTRIBUTION.md`](docs/BET-AGENT-DISTRIBUTION.md)).

### Actors and relationships (MVP)

- **Protocol (Factory)**:
  - Maintains the protocol **treasury address** and the **default protocol fee** (basis points).
  - Enforces global constraints (min windows, caps on outcomes/fees).
  - Deploys new wagers.

- **Proposer (per-wager)**:
  - The address that calls `createWager` on the factory; stored on-chain as `proposer` for transparency.

- **Resolver (per-wager)**:
  - Address authorized to **resolve** (choose winning outcome) or **retract** (invalidate).
  - Defaults to the proposer when `resolver == address(0)` is passed at creation; may be set to any other address (oracle, sponsored resolver, multisig, etc.).

- **Betting closer (per-wager)**:
  - May call **`closeBetting()`** to stop new bets.
  - `bettingCloseTime = 0` enables **no max betting window**, so only `bettingCloser` can end betting.
  - `bettingCloser == address(0)` disables authority close (time-only mode for finite windows).

- **Resolution closer (per-wager)**:
  - After betting has ended, may call **`closeResolutionWindow()`** to end the resolver window.
  - `resolutionWindow = 0` enables **no max resolution window**, so only `resolutionCloser` can end it.
  - `resolutionCloser == address(0)` disables authority close (time-only mode for finite windows).

- **Bettors (per-wager)**:
  - Deposit collateral during the betting window and allocate it to exactly one outcome per bet.
  - After resolve: winners can claim pro-rata payouts.
  - After retract/expire: bettors can claim refunds minus fees.

- **Beneficiaries (fees)**:
  - The protocol treasury is always a beneficiary (unless protocol fee is set to 0).
  - Wager creation can specify additional recipients with fee BPS.
  - Fees are taken once, at wager finalization (resolve/retract/expire).

### Lifecycle (MVP)

1. **Create wager**
   - Proposer supplies:
     - `collateralToken` (ERC20)
     - `outcomes[]` (strings)
    - `bettingCloseTime` (absolute time, or `0` for no max betting window)
    - `resolutionWindow` (duration after effective betting close, or `0` for no max resolution window)
     - `resolver` (`address(0)` → proposer)
     - `bettingCloser` (`address(0)` disables authority close)
     - `resolutionCloser` (`address(0)` disables authority close)
     - `feeRecipients[]`, `feeBps[]` (optional)
     - optional `seedOutcomeIndices[]`, `seedAmounts[]` for multi-option seeded liquidity at creation
   - Factory enforces sane constraints (min windows, caps, and rejects no-max windows without a matching closer).

2. **Betting**
   - Any address deposits collateral and chooses one or more outcome indices.
   - `placeBet` places one leg; `placeBets` places multiple legs in one transaction.
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

This MVP isolates resolution logic to per-wager functions so it can later be extended/replaced with:

- bonded reporting + dispute game
- oracle adapters
- validity/ambiguity resolution paths

### Deploying the MVP with Foundry

- **Prerequisites**:
  - `forge` installed and configured.
  - Deployer EOA with gas funds on your target network.
  - RPC URL for the target network (for MVP recommendation: **Base Sepolia** testnet first).

- **1. Configure environment**
  - Prefer the shared template **`config/service.env`** (gitignored via `*.env`); copy from `config/service.env.example` and `source script/lib/load_service_env.sh` before `forge` / scripts. A legacy repo-root **`.env`** is still supported by the loader if `config/service.env` is missing.

    ```bash
    cp config/service.env.example config/service.env
    # edit config/service.env
    source script/lib/load_service_env.sh
    ```

    Minimum variables for deploy scripts:

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
    - `protocolFeeBps_`: protocol fee in basis points (e.g. `100` = 1%; default in `DeployFactory.s.sol` / `launch_testnet.sh`).
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

- **3. Creating wagers**

  Once the factory is deployed, wagers are created via `createWager`:

  - Inputs:
    - `collateralToken`: ERC20 address used for bets (e.g. USDC).
    - `proposition`: human-readable wager proposition.
    - `outcomes[]`: text labels for possible outcomes.
    - `bettingCloseTime`: unix timestamp \(>\) `block.timestamp + minBettingWindow`.
    - `resolutionWindow`: seconds \(>= minResolutionWindow\).
    - `resolver`: `address(0)` to use the proposer; otherwise the delegated resolver address.
    - `bettingCloser`: authority address for early `closeBetting()`; use `address(0)` for time-only close on finite windows.
    - `resolutionCloser`: authority address for early `closeResolutionWindow()`; use `address(0)` for time-only close on finite windows.
    - Guardrail: if `bettingCloseTime == 0`, `bettingCloser` must be non-zero; if `resolutionWindow == 0`, `resolutionCloser` must be non-zero.
    - `extraFeeRecipients[]`, `extraFeeBps[]`: optional, additional beneficiaries.
    - optional `seedOutcomeIndices[]`, `seedAmounts[]` to seed multiple outcomes at creation.

  - You can call `createWager`:
    - From a frontend using ethers.js / viem.
    - From a Foundry script (to be added later).

- **4. Using a deployed wager**

  - **Bettors**:
    - `IERC20(collateralToken).approve(wager, amount)`
    - `ParamutuelWager(wager).placeBet(outcomeIndex, amount)`
    - or `ParamutuelWager(wager).placeBets(outcomeIndices[], amounts[])` for multi-option entry in one tx.
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
- create wagers through the deployed `ParamutuelFactory`
- seed wagers at creation and place bets via `placeBet` / `placeBets`
- resolve / retract / expire
- claim payouts and withdraw fees

Run an HTTP server from the repo root (do not use `file://`):

```bash
python3 -m http.server 8080
```

Then open:

`http://localhost:8080/dapp/`

See `dapp/README.md` for UI details and deployment assumptions.

### Hosted dApp & protocol website

The dApp and a protocol website are deployed to GitHub Pages via CI. On every push to `master` that touches `src/`, `dapp/`, `service/indexer/`, `service/explorer/static/`, `site/`, or `config/deployments.json`, a GitHub Actions workflow builds the contracts, extracts ABIs, and assembles the site.

**Live URL:** `https://autarkenterprises.github.io/paramutuel/`

The website (`site/`) is a navigation shell that embeds the dApp and explorer as iframes — no code duplication. When component files change, the website automatically stays current.

Pages:
- `/` — Landing page with protocol overview, deployment banner, and live ticker
- `/app.html` — Full dApp (embedded iframe; dApp remains a separate static bundle under `/dapp/`)
- `/bet.html` — Short place-a-bet flow
- `/explorer.html` — Wager explorer with configurable indexer URL
- `/operator.html` — Operator hub (indexer links, embedded explorer, optional service URLs)
- `/dapp/` — Standalone dApp (also accessible directly)

Details: [`docs/WEBSITE.md`](docs/WEBSITE.md). Product/engineering gap review: [`docs/PROJECT-REVIEW.md`](docs/PROJECT-REVIEW.md).

Runtime defaults for these surfaces are read from `config/deployments.json`:
- `defaultNetwork` selects which network config to use by default
- `<network>.factoryAddress` feeds dApp/website factory defaults
- `<network>.explorerApiBase` feeds website explorer API default (optional)

**Setup requirement:** In the GitHub repo settings, set Pages source to **"GitHub Actions"**.

#### Syncing ABIs after contract changes

```bash
./script/sync-abi.sh
```

This runs `forge build` and extracts ABI-only JSON into `dapp/abi/`. Commit the updated files so the hosted dApp stays in sync with contract changes.
