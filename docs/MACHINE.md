# Machine / agent integration

Paramutuel is structured so **bots, indexers, and LLM-driven workflows** can interact without bespoke scraping—aligned with the protocol thesis: **permissionless** markets in **real on-chain collateral (ERC-20)**, **configurable** resolution and timing per wager, and **no centralized approval** of wagers or payouts. Machines read the same indexer and MCP surfaces as humans.

Contract upgrade/redeploy procedure: [`CONTRACT-UPGRADE-RUNBOOK.md`](CONTRACT-UPGRADE-RUNBOOK.md).

## ABIs

Pre-extracted ABI-only JSON is committed under `dapp/abi/` for the unified V3 protocol (`ParamutuelFactoryV3.json`, `ParamutuelWagerV3.json`). Each file is `{"abi": [...]}`. Full Foundry artifacts are available under `out/` after `forge build`.

The MCP server bundles the same ABIs under `mcp_server/abi/` (see `paramutuel-mcp` wheel `force-include`).

To re-sync after contract changes: `./script/sync-abi.sh`.

### Indexer payload notes (V3)

Hosted indexer `GET /wagers/{address}` includes `ticket_pools` (enumerated: per ticket-bitmask stake totals; freeform: per `answerId` hex keyed as `ticket_mask`) and wager fields `protocol_version` (`"enumerated"` or `"freeform"`), `payoff_policy`, `policy_param`. MCP `quote_place_bet` / `quote_place_bets` interpret `protocol_version === "enumerated"` and map a chosen **outcome index** to ticket mask `1 << index` for single-outcome legs. For **`protocol_version === "freeform"`**, use MCP **`encode_place_bet_freeform`** / **`encode_resolve_freeform`** (exact UTF-8 strings); `quote_place_bet` does not apply. Tooling: `encode_create_wager` and `encode_create_freeform_wager` both target the single unified `FACTORY_ADDRESS` / `factoryAddress` (V3).

## Factory (`ParamutuelFactory`)

### Constants

| Name | Value | Description |
|------|-------|-------------|
| `BPS_DENOMINATOR` | `10_000` | Basis-point denominator |
| `MAX_TOTAL_FEE_BPS` | `10_000` | 100% fee cap (protocol + extra combined) |
| `MAX_OUTCOMES` | `255` | Maximum outcome count per wager |

### Read-only state

| Getter | Returns | Description |
|--------|---------|-------------|
| `treasury()` | `address` | Protocol fee recipient |
| `protocolFeeBps()` | `uint16` | Default protocol fee in basis points |
| `minBettingWindow()` | `uint64` | Minimum seconds from creation to `bettingCloseTime` |
| `minResolutionWindow()` | `uint64` | Minimum `resolutionWindow` duration in seconds |
| `wagersCount()` | `uint256` | Number of wagers created |
| `wagers(i)` | `address` | Wager address by index |

### `createWager` (two overloads)

```solidity
// Without seeds
function createWager(
    address collateralToken,
    string memory proposition,
    string[] memory outcomes,
    uint64  bettingCloseTime,
    uint64  resolutionWindow,
    address resolver,
    address bettingCloser,
    address resolutionCloser,
    address[] memory extraFeeRecipients,
    uint16[]  memory extraFeeBps
) external returns (address wager);

// With seeds
function createWager(
    address collateralToken,
    string memory proposition,
    string[] memory outcomes,
    uint64  bettingCloseTime,
    uint64  resolutionWindow,
    address resolver,
    address bettingCloser,
    address resolutionCloser,
    address[] memory extraFeeRecipients,
    uint16[]  memory extraFeeBps,
    uint256[] memory seedOutcomeIndices,
    uint256[] memory seedAmounts
) external returns (address wager);
```

**Parameter semantics:**

- `resolver = address(0)` → defaults to proposer (`msg.sender`).
- `bettingCloser = address(0)` → disables authority `closeBetting()`.
- `resolutionCloser = address(0)` → disables authority `closeResolutionWindow()`.
- `bettingCloseTime = 0` → no time cap on betting (closer-managed). **Requires** non-zero `bettingCloser`.
- `resolutionWindow = 0` → no time cap on resolution (closer-managed). **Requires** non-zero `resolutionCloser`.
- `resolutionDeadline` is computed as `bettingCloseTime + resolutionWindow` (or `0` if either is `0`).
- Seeded overload: proposer's tokens are `transferFrom`'d to the wager and recorded as bets at create-time. Seed arrays must be same length and contain positive amounts. Caller must have approved the factory for the total seed amount.

**Validation / reverts:**

| Error | Condition |
|-------|-----------|
| `BadOutcomes` | `outcomes.length < 2` |
| `TooManyOutcomes` | `outcomes.length > MAX_OUTCOMES` |
| `WindowTooShort` | `bettingCloseTime != 0 && bettingCloseTime < block.timestamp + minBettingWindow` |
| `WindowTooShort` | `resolutionWindow != 0 && resolutionWindow < minResolutionWindow` |
| `InvalidLifecycleConfig` | `bettingCloseTime == 0 && bettingCloser == address(0)` |
| `InvalidLifecycleConfig` | `resolutionWindow == 0 && resolutionCloser == address(0)` |
| `BadFeeConfig` | Fee recipients/bps length mismatch, zero address, or zero bps |
| `BadFeeConfig` | Total fee BPS > `MAX_TOTAL_FEE_BPS` |
| `BadSeedConfig` | Seed indices/amounts length mismatch or zero amount |

### Events

```solidity
event WagerCreated(
    address indexed wager,
    address indexed proposer,
    address indexed resolver,
    address collateralToken,
    uint64  bettingCloseTime,
    uint64  resolutionWindow,
    uint64  resolutionDeadline,
    address bettingCloser,
    address resolutionCloser
);
```

## Wager (`ParamutuelWager`)

### State enum

```solidity
enum State { Open, Resolved, Retracted }
```

- **Open** — betting may be active; wager is not finalized.
- **Resolved** — winning outcome selected; winners can claim.
- **Retracted** — invalidated (by resolver retract or expiry); all bettors can claim refund minus fees.

For roles, timers vs authority closers, and a full transition matrix, see [`docs/WAGER-LIFECYCLE.md`](WAGER-LIFECYCLE.md).

### Read-only state

| Getter | Returns | Description |
|--------|---------|-------------|
| `factory()` | `address` | Factory that created this wager |
| `proposer()` | `address` | Address that called `createWager` |
| `resolver()` | `address` | Address authorized to resolve/retract |
| `bettingCloser()` | `address` | Authority for `closeBetting()` (`address(0)` = disabled) |
| `resolutionCloser()` | `address` | Authority for `closeResolutionWindow()` (`address(0)` = disabled) |
| `collateralToken()` | `address` | ERC-20 token address used for bets |
| `proposition()` | `string` | Wager proposition text |
| `state()` | `State` | Current lifecycle state |
| `bettingCloseTime()` | `uint64` | Scheduled betting close (0 = no time cap) |
| `resolutionWindow()` | `uint64` | Duration after betting close for resolver to act (0 = no time cap) |
| `resolutionDeadline()` | `uint64` | `bettingCloseTime + resolutionWindow` (0 if either is 0) |
| `outcomesCount()` | `uint256` | Number of outcomes |
| `outcomeText(i)` | `string` | Label for outcome at index `i` |
| `outcomeTotals(i)` | `uint256` | Total wagered on outcome `i` (raw token units) |
| `totalPot()` | `uint256` | Sum of all bets (raw token units) |
| `bets(addr, i)` | `uint256` | Amount `addr` bet on outcome `i` |
| `userTotalBet(addr)` | `uint256` | Total amount `addr` bet across all outcomes |
| `winningOutcome()` | `uint256` | Winning outcome index (valid only if `state == Resolved`) |
| `totalWinningStake()` | `uint256` | Total wagered on winning outcome |
| `hasClaimed(addr)` | `bool` | Whether `addr` has claimed |
| `feeRecipients(i)` | `address` | Fee recipient at index `i` |
| `feeBps(i)` | `uint16` | Fee basis points for recipient `i` |
| `totalFeeBps()` | `uint256` | Sum of all fee bps |
| `feeBalances(addr)` | `uint256` | Accrued unclaimed fees for `addr` |
| `feesCharged()` | `bool` | Whether fees have been deducted from the pot |
| `bettingClosedByAuthority()` | `bool` | Whether betting was closed by `bettingCloser` |
| `bettingClosedAtByAuthority()` | `uint64` | Timestamp when authority closed betting |
| `resolutionWindowClosedByAuthority()` | `bool` | Whether resolution window was closed by `resolutionCloser` |

### Lifecycle functions

**Betting** (state must be `Open`, betting window must be open):

```solidity
// Caller must first: collateralToken.approve(wager, amount)
function placeBet(uint256 outcomeIndex, uint256 amount) external returns ();
function placeBets(uint256[] calldata outcomeIndices, uint256[] calldata amounts) external returns ();
```

- `placeBets` transfers the sum of all amounts in one `transferFrom`, then records each leg.
- Reverts: `NotOpen`, `BettingClosed`, `InvalidOutcome`, `ArrayLengthMismatch` (for `placeBets`).

**Authority close** (callable at any time by the designated closer):

```solidity
function closeBetting() external;          // only bettingCloser; idempotent
function closeResolutionWindow() external; // only resolutionCloser; only after betting is closed; idempotent
```

- Reverts: `NotBettingCloser` / `NotResolutionCloser`, `BettingNotClosed` (for `closeResolutionWindow`).

**Finalization** (after betting is closed, while resolution window is open):

```solidity
function resolve(uint256 outcomeIndex) external; // only resolver
function retract() external;                      // only resolver
```

- Both charge fees once at finalization.
- Reverts: `NotResolver`, `AlreadyFinalized`, `BettingNotClosed`, `ResolutionWindowOver`, `InvalidOutcome` (for `resolve`).

**Expiry** (after resolution window is over, by anyone):

```solidity
function expire() external;
```

- Moves state to `Retracted`. Charges fees. Enables refund claims.
- Reverts: `AlreadyFinalized`, `BettingNotClosed`, `ResolutionWindowOver` (if window is still open).

**Claims** (after finalization):

```solidity
function claim() external returns (uint256 paid);
function withdrawFees() external returns (uint256 amount);
```

- Reverts: `NotOpen` (if still Open), `NothingToClaim`.

### Payout math

Full prose spec (v1 + v2): [`PAYOUT-CALCULATION.md`](PAYOUT-CALCULATION.md).

Fees are charged once at finalization:

```
totalFees = (totalPot * totalFeeBps) / BPS_DENOMINATOR
netPot    = totalPot - totalFees
```

Fee distribution: each recipient gets `(totalFees * feeBps[i]) / totalFeeBps`; the last recipient absorbs rounding dust.

**Resolved** — winners split the net pot pro-rata by their winning-outcome stake:

```
payout = (userWinStake * netPot) / totalWinningStake
```

**Retracted / Expired** — all bettors get a pro-rata refund from the net pot:

```
refund = (userTotalBet * netPot) / totalPot
```

### Events

```solidity
event BetPlaced(address indexed bettor, uint256 indexed outcomeIndex, uint256 amount);
event BettingClosedByAuthority(uint64 closedAt);
event ResolutionWindowClosedByAuthority(uint64 closedAt);
event Resolved(uint256 indexed outcomeIndex);
event Retracted();
event Expired();
event Claimed(address indexed bettor, uint256 amount);
event FeeAccrued(address indexed recipient, uint256 amount);
event FeeWithdrawn(address indexed recipient, uint256 amount);
```

### ParamutuelWagerV3 (ADR-0010)

In `src/` on **`master`**: the unified `ParamutuelWagerV3` selects its shape at construction via an immutable `WagerMode` (Enumerated / Freeform). Enumerated mode carries bitmask **tickets**, `resolve(uint256 winningMask)`, and **`PayoffPolicy`** (`SINGLE_WINNER`, `ANY_OF`, `EXACT_SET`, `AT_LEAST_K`, `WEIGHTED_OVERLAP`) — the same semantics the deleted `ParamutuelWagerV2` used to provide. Freeform mode carries `placeBet(string,uint256)` / `resolve(string)` (exact UTF-8 bytes; `answerId = keccak256(abi.encodePacked(0x03, bytes(answer)))` — domain-separated per ADR-0010). Colloquial **“any of” / “all of”** ↔ policy mapping: [`PAYOUT-CALCULATION.md`](PAYOUT-CALCULATION.md) Part B glossary. Spec: [`ADR-0010-IMPLEMENTATION.md`](ADR-0010-IMPLEMENTATION.md). Gas: [`PARAMUTUEL-V3-GAS.md`](PARAMUTUEL-V3-GAS.md). Templates: [`ADR-0008-TEMPLATES.md`](ADR-0008-TEMPLATES.md).

### Error reference

| Error | Thrown by |
|-------|----------|
| `InvalidOutcome` | `placeBet`, `placeBets`, `resolve` — outcome index out of range |
| `NotOpen` | `placeBet`, `placeBets`, `claim` — wrong state |
| `BettingClosed` | `placeBet`, `placeBets` — betting window has ended |
| `BettingNotClosed` | `resolve`, `retract`, `expire`, `closeResolutionWindow` — betting still open |
| `ResolutionWindowOver` | `resolve`, `retract` — window expired; `expire` — window still open |
| `NotResolver` | `resolve`, `retract` — caller is not the resolver |
| `NotBettingCloser` | `closeBetting` — caller is not the betting closer |
| `NotResolutionCloser` | `closeResolutionWindow` — caller is not the resolution closer |
| `AlreadyFinalized` | `resolve`, `retract`, `expire` — wager already resolved/retracted |
| `NothingToClaim` | `claim` — no stake, no winning stake, or already claimed; `withdrawFees` — zero balance |
| `ArrayLengthMismatch` | `placeBets`, `seedInitialBetsFromFactory` — indices/amounts length mismatch |
| `NotFactory` | `seedInitialBetsFromFactory` — caller is not the factory |
| `FeeConfigMismatch` | constructor — `feeRecipients` and `feeBps` length mismatch |
| `FeeTooHigh` | constructor — total fee BPS exceeds `BPS_DENOMINATOR` |

**Note:** `seedInitialBetsFromFactory(address bettor, uint256[] outcomeIndices, uint256[] amounts)` is callable only by the factory during wager creation. External callers cannot invoke it. `FeeConfigMismatch` and `FeeTooHigh` are constructor-level checks (the factory validates first, so these are defensive guards).

## HTTP indexer API (JSON)

Run `python -m service.indexer.api` (see module for flags). All responses are `application/json`. CORS is enabled (`Access-Control-Allow-Origin: *`).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | `{ "ok": true, "ts": <unix> }` |
| GET | `/wagers?state=OPEN&limit=100` | List wagers (optional `state`, `limit` 1–1000). |
| GET | `/wagers/:address` | Single wager, totals, outcome rows, event history (`payload_json` parsed). |
| GET | `/sweeper/expire-candidates?now=<unix>` | Wagers still `OPEN` where `expire()` is valid: timed-out resolution window (from effective betting close + `resolution_window`) or `resolution_window_closed` set by indexer from `ResolutionWindowClosedByAuthority`. |

### Environment / ops

- **`RPC_URL`**: use your node when running the indexer CLI (`service.indexer.indexer`).
- **`--db-path`**: SQLite file for the indexer (schema in `service/indexer/schema.sql`).
- **`--factory-address`**: factory contract to filter `WagerCreated` logs.

## Configuration

`config/deployments.json` stores runtime defaults (factory address, network selection, optional indexer URL). The dApp and website read this at load time.

## dApp

Static `dapp/` UI loads ABIs from `dapp/abi/` (committed), with a fallback to `../out/` (Foundry build output) for local development. The hosted site is deployed to GitHub Pages via CI.

## Service operations

- Explorer server: `python3 -m service.explorer.server --indexer-base-url http://127.0.0.1:8090`
- Control panel CLI: `python3 -m service.control_panel.cli ...`
- Control panel web: `python3 -m service.control_panel.web --rpc-url ... --private-key ...`

Operator transaction workflows are documented in `docs/WORKFLOWS.md`.

## MCP server

A ready-to-use MCP (Model Context Protocol) server is available at `mcp_server/`. It exposes 17 tools across three categories:

- **Discovery:** `get_protocol_info`, `list_wagers`, `get_wager`, `get_expire_candidates`, `get_indexer_health`
- **Analysis:** `calculate_odds`, `quote_place_bet`, `quote_place_bets`
- **Transaction encoding:** `encode_create_wager`, `encode_create_wager_v2`, `encode_place_bet`, `encode_place_bets`, `encode_resolve`, `encode_retract`, `encode_expire`, `encode_close_betting`, `encode_close_resolution_window`, `encode_claim`, `encode_withdraw_fees`

Run with:

```bash
pip install mcp httpx eth-abi "eth-hash[pycryptodome]"
python -m mcp_server
```

Or via the entry point after `pip install -e mcp_server/`:

```bash
paramutuel-mcp
```

The server reads the unified V3 factory address and chain ID from `config/deployments.json` (overridable via `FACTORY_ADDRESS` and `CHAIN_ID` env vars). Discovery tools query the indexer API; transaction-encoding tools return raw calldata and approval instructions for the caller's signer.

Tests: `python -m pytest mcp_server/tests/test_server.py` (or `python -m unittest mcp_server/tests/test_server.py`).

Agent loop integration guide: [`docs/AGENT-LOOP.md`](AGENT-LOOP.md).

## Bet scout agent (adoption)

A minimal **stdlib** process for indexer-backed discovery and ranked bet ideas is published as **`paramutuel-bettor-agent`** on PyPI (CLI `paramutuel-bettor`) and lives in-repo under `agents/paramutuel_bettor/`. It is meant for **frontier-model subagents** and scripted delegation; pair it with the MCP server for authoritative `quote_place_bet` calldata before signing. See [`AGENTS.md`](../AGENTS.md), [`docs/BET-AGENT.md`](BET-AGENT.md), [`docs/BET-AGENT-DISTRIBUTION.md`](BET-AGENT-DISTRIBUTION.md), [`agents/subagent-manifest.json`](../agents/subagent-manifest.json), and the Cursor skill `.cursor/skills/paramutuel-bettor/SKILL.md`.

## Versioning

Changing `createWager` or event layouts is an **ABI break**. Bump deployed factory version or document migration when upgrading.

Upgrading the indexer from a pre–window-delegation build: **recreate the SQLite DB** (or migrate with `ALTER TABLE`) so `wagers` includes `betting_closer`, `resolution_closer`, `resolution_window`, `betting_closed_by_authority`, `betting_closed_at`, `resolution_window_closed`, and `resolution_window_closed_at`; `WagerCreated` and closure-event topics changed.
