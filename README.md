## Paramutuel (MVP)

Tagline: **“Augur for prop bets”** — starting with a minimal MVP that is intentionally structured to later support more decentralized resolution mechanisms.

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

### Actors and relationships (MVP)

- **Protocol (Factory)**:
  - Maintains the protocol **treasury address** and the **default protocol fee** (basis points).
  - Enforces global constraints (min windows, caps on outcomes/fees).
  - Deploys new markets.

- **Proposer / Resolver (per-market)**:
  - Creates the market by providing outcome strings, time windows, and optional fee recipients.
  - Only address that can **resolve** (choose winning outcome) or **retract** (invalidate).

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
     - `bettingCloseTime`
     - `resolutionWindow` (deadline = close + window)
     - `feeRecipients[]`, `feeBps[]` (optional)
   - Factory enforces sane constraints (min betting window, min resolution window, caps).

2. **Betting**
   - Any address deposits collateral and chooses an outcome index.
   - Bets close at `bettingCloseTime`.

3. **Finalization**
   - After close and before deadline:
     - Proposer may **resolve(outcomeIndex)**.
     - Proposer may **retract()**.
   - After deadline (if not resolved/retracted):
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

