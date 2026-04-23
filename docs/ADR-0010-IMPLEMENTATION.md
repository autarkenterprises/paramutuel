# ADR-0010 implementation notes (unified V3 wager — enumerated + freeform)

**Status:** **Implemented** on `master`. `ParamutuelFactoryV3` + `ParamutuelWagerV3` are the canonical contracts; the legacy standalone `ParamutuelFactory` / `ParamutuelFactoryV2` / `ParamutuelFactoryFreeform` and their wagers (plus the `WagerV2Masks` library) have been **deleted from the tree**. Indexer, MCP, dApp, site, agents, and testnet suites are V3-only.
**ADR:** [`research/adr/ADR-0010-unified-wager-enumerated-and-freeform.md`](../research/adr/ADR-0010-unified-wager-enumerated-and-freeform.md)
**Supersedes (contract layer):** [`ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md), [`ADR-0009-IMPLEMENTATION.md`](ADR-0009-IMPLEMENTATION.md) — their economic / lifecycle math is unchanged and still authoritative; only the *contract surface* moved to V3.

## Wager mode enum

```solidity
enum WagerMode { Enumerated, Freeform }  // immutable per wager
enum PayoffPolicy { SINGLE_WINNER, ANY_OF, EXACT_SET, AT_LEAST_K, WEIGHTED_OVERLAP }
```

`ParamutuelWagerV3.MODE()` returns `0` (Enumerated) or `1` (Freeform). It is set once in the constructor by the factory and never mutated. Wrong-mode calls revert with `WrongMode()`.

## Factory (`src/ParamutuelFactoryV3.sol`)

One factory, two create paths; same unified `ParamutuelWagerV3` bytecode is deployed either way.

### `createEnumeratedWager(...)` — two overloads

```solidity
createEnumeratedWager(
  address  collateralToken,
  string   proposition,
  string[] outcomes,
  PayoffPolicy payoffPolicy,
  uint256  policyParam,
  uint64   bettingCloseTime,
  uint64   resolutionWindow,
  address  resolver,
  address  bettingCloser,
  address  resolutionCloser,
  address[] extraFeeRecipients,
  uint16[]  extraFeeBps
)                                       // 12 args — no seeding

createEnumeratedWager(
  ...same 12 args...,
  uint256[] seedTicketMasks,
  uint256[] seedAmounts
)                                       // 14 args — with create-time seed bets
```

- `outcomes.length` ∈ `[2, MAX_OUTCOMES]` with `MAX_OUTCOMES = 255`.
- `policyParam != 0` **only** for `AT_LEAST_K` (where `1 ≤ k ≤ numOutcomes`); other policies revert with `InvalidPolicyParam` on nonzero param.
- Seed ticket masks are validated *before* wager deploy (`mask != 0`, `mask >> numOutcomes == 0`, single-bit for `SINGLE_WINNER`); `seedAmounts[i] != 0`; mismatched lengths revert with `BadSeedConfig`.
- If `seedAmounts.length > 0`, factory pulls `sum(seedAmounts)` from `msg.sender` via `transferFrom` and invokes `seedInitialBetsFromFactory` on the new wager.
- Fee config: factory-level `protocolFeeBps` + `(extraFeeRecipients, extraFeeBps)`; sum ≤ `MAX_TOTAL_FEE_BPS = 10_000`.
- Emits **`WagerCreatedV3Enumerated`**.

### `createFreeformWager(...)`

```solidity
createFreeformWager(
  address  collateralToken,
  string   proposition,
  uint64   bettingCloseTime,
  uint64   resolutionWindow,
  address  resolver,
  address  bettingCloser,
  address  resolutionCloser,
  address[] extraFeeRecipients,
  uint16[]  extraFeeBps
)                                       // 9 args
```

- **No** `outcomes` array. Constructor forwards `WAGER_MAX_DISTINCT_ANSWERS = 1024` as the immutable distinct-answer cap.
- Emits **`WagerCreatedV3Freeform`**.

### Factory constants

| Constant | Value | Role |
|----------|------:|------|
| `BPS_DENOMINATOR` | `10_000` | Fee math |
| `MAX_TOTAL_FEE_BPS` | `10_000` | Hard cap on sum of fee bps |
| `MAX_OUTCOMES` | `255` | Enumerated outcome count |
| `WAGER_MAX_DISTINCT_ANSWERS` | `1024` | Freeform distinct-answer cap |

## Wager (`src/ParamutuelWagerV3.sol`)

Shared state: collateral, proposition, windows, roles (`resolver`, `bettingCloser`, `resolutionCloser`), reentrancy guard, fee accounting, lifecycle state (`Open` → `Resolved` | `Retracted`).

### Mode-specific external surface

| Entrypoint | Enumerated | Freeform |
|------------|-----------|----------|
| `placeBet(uint256 ticketMask, uint256 amount)` | ✅ `onlyEnumerated` | reverts `WrongMode` |
| `placeBets(uint256[] masks, uint256[] amounts)` | ✅ `onlyEnumerated` | reverts `WrongMode` |
| `placeBet(string answer, uint256 amount)` | reverts `WrongMode` | ✅ `onlyFreeform` |
| `resolve(uint256 winningMask)` | ✅ `onlyEnumerated` | reverts `WrongMode` |
| `resolve(string winningAnswer)` | reverts `WrongMode` | ✅ `onlyFreeform` |
| `outcomesCount()` | returns `numOptions` | returns **0** |

Lifecycle peers shared across modes: `closeBetting`, `closeResolutionWindow`, `expire`, `retract`, `claim`, `withdrawFees`.

### Enumerated semantics (unchanged from ADR-0008)

- Ticket identity: `uint256 ticketMask` (non-zero; `mask >> numOptions == 0`); for `SINGLE_WINNER`, `popcount(mask) == 1`.
- Distinct ticket cap: `MAX_DISTINCT_TICKETS = 1024` per wager (bounds resolve/claim loops).
- Resolve: `resolve(uint256 winningMask)` reverts `NoWinningStake` if no qualifying ticket.
- Payoff math by policy: see [`ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md) and [`PAYOUT-CALCULATION.md`](PAYOUT-CALCULATION.md) Part B.

### Freeform semantics (unchanged from ADR-0009)

- Ticket identity: **domain-separated** `answerId = keccak256(abi.encodePacked(FREEFORM_ANSWER_DOMAIN, bytes(answer)))` where `FREEFORM_ANSWER_DOMAIN = 0x03`. This isolates freeform ids from any other `bytes32` uses in the same contract (open question #2 in ADR-0010, resolved with a fixed single-byte tag).
- `MAX_ANSWER_BYTES = 1024`; empty answer reverts `EmptyAnswer`.
- Resolve: `resolve(string)` hashes with the same domain byte, reverts `NoWinningStake` if no pool.

## Events (topic0 hashes)

All V3 events are distinct from the deleted legacy events to prevent indexer collisions.

### Factory

| Event | Topic0 |
|-------|--------|
| `WagerCreatedV3Enumerated(address indexed wager, address indexed proposer, address indexed resolver, address collateralToken, uint8 payoffPolicy, uint256 policyParam, uint64 bettingCloseTime, uint64 resolutionWindow, uint64 resolutionDeadline, address bettingCloser, address resolutionCloser)` | `0xff766b6fc8dd2e2b1c7be675a874f160c4cada5bf32dac8b1b2e0d6ae7bdb0da` |
| `WagerCreatedV3Freeform(address indexed wager, address indexed proposer, address indexed resolver, address collateralToken, uint64 bettingCloseTime, uint64 resolutionWindow, uint64 resolutionDeadline, address bettingCloser, address resolutionCloser)` | `0xf59da875d5b5de3b09728f042bebc2a20357ee08ca31bbaf584efd9cb0ec4c53` |

### Wager

| Event | Topic0 |
|-------|--------|
| `BetPlacedV3Enumerated(address indexed bettor, uint256 ticketMask, uint256 amount)` | `0xd49e0d995d5bc2e9cc268a6a482b0d8ec9ed18ddeae89fc67001c2efa6fee5b0` |
| `BetPlacedV3Freeform(address indexed bettor, bytes32 indexed answerId, uint256 amount)` | `0xecda6e726cfee6e62f696fb6fc02e680aa5742138f2635d615d7b8bca3db15c4` |
| `ResolvedV3Enumerated(uint256 winningMask)` | `0x0a2e969cad318ad34168d32c8cbce850c7903442301e6e8d824116385833f290` |
| `ResolvedV3Freeform(bytes32 indexed winningAnswerId)` | `0xfeae22eca71fbae658ba63b5add1f9f5371e7fd5bf7597f8b97cdaf24a29a922` |
| `BettingClosedByAuthorityV3(uint64 closedAt)` | `0x309f6e1169f98c711fa766027cd3ca7a3faa5d73827678a743758b5e0a19593f` |
| `ResolutionWindowClosedByAuthorityV3(uint64 closedAt)` | `0xee6e1578965b067c63388674310a835bfa8973df58b6fe92892eee8ddf9c03fa` |
| `RetractedV3()` | `0xebabcf541ed74aefa8ba4e51e11c11b14add951948fb15973a044658cf583ba3` |
| `ExpiredV3()` | `0x2cd032a0386e334d4ec0a27e3922b8673bbc85a3938f1d9e39aaf827ee803cbc` |
| `ClaimedV3(address indexed bettor, uint256 amount)` | `0x18f56b95da8109fe45e8ff222168c73ba869a66cdb44a1d68d00576efc4377f6` |
| `FeeAccruedV3(address indexed recipient, uint256 amount)` | `0x61e2d065e1dccf6ff8fc518812577d7c01bb33d905b7975c1776a9c2b386cf16` |
| `FeeWithdrawnV3(address indexed recipient, uint256 amount)` | `0xa1f7a7f54e12a1df5b55a8b583db7040559f7fa32576e9ecdacf7dbd49c99e75` |

Canonical map: `service/indexer/indexer.py` (`TOPICS`).

## Indexer / API

- **One factory address:** `config/deployments.json` → `baseSepolia.factoryAddress` / `baseMainnet.factoryAddress`. Env override: `FACTORY_ADDRESS`. No separate `factoryV2Address` / `factoryFreeformAddress`.
- **`protocol_version`:** `wagers` rows carry either `"enumerated"` (from `WagerCreatedV3Enumerated`) or `"freeform"` (from `WagerCreatedV3Freeform"`); legacy `v1` / `v2` / `freeform_standalone` code paths are gone.
- **`apply_log`** in `service/indexer/indexer.py` decodes exactly the V3 topics above.
- **Ticket pools:** the `wager_ticket_pools` table stores `ticket_mask` as:
  - Enumerated → hex string of the `uint256` bitmask.
  - Freeform → hex string of `answerId` (domain-separated `keccak256`).
- **API / health:** `/health` echoes the single `factoryAddress`; search endpoints expose `protocol_version` to let clients branch on mode.

## MCP (`mcp_server/`)

- Tools: `encode_create_enumerated_wager`, `encode_create_freeform_wager`, `encode_place_bet_enumerated`, `encode_place_bet_freeform`, `encode_resolve_enumerated`, `encode_resolve_freeform`, plus lifecycle (`encode_close_betting`, `encode_close_resolution_window`, `encode_expire`, `encode_retract`, `encode_claim`, `encode_withdraw_fees`).
- `get_protocol_info` exposes `factory_address`, `chain_id`, and V3 constants (`MAX_OUTCOMES`, `MAX_DISTINCT_TICKETS`, `MAX_ANSWER_BYTES`, `BPS_DENOMINATOR`, `FREEFORM_ANSWER_DOMAIN`).
- Env: `FACTORY_ADDRESS`, `CHAIN_ID`.

## dApp (`dapp/`)

- ABIs: `dapp/abi/ParamutuelFactoryV3.json`, `dapp/abi/ParamutuelWagerV3.json` (emitted by `script/sync-abi.sh`).
- Protocol selector toggles **enumerated** vs **freeform**; both dispatch into the same unified factory / wager ABI via the mode parameter.
- Loads mode from chain by reading `wager.MODE()` on any detected wager address.

## Bet scout (`agents/paramutuel_bettor/`)

- `protocol_version === "enumerated"` consumes enumerated policy metadata (`payoff_policy`, `policy_param`, outcome labels) and emits bitmask `ticketMask` calldata.
- `protocol_version === "freeform"` consumes `ticket_pools` rows (sorted by `ticket_mask` = `answerId` hex); `quote` accepts optional `freeform_answer` to produce `placeBet(string, uint256)` calldata (otherwise odds-only — indexer does not store plaintext answers).

## Deploy

- **Script:** `script/DeployFactoryV3.s.sol` (single unified factory deploy).
- **Env / config after deploy:** write the wager factory address to `config/deployments.json` → `baseSepolia.factoryAddress` (or `baseMainnet.factoryAddress`). No secondary factory keys.

## Testnet

- Live: `test/testnet/test_live_base_sepolia.py` — classes `TestBaseSepoliaLiveV3PolicyMatrix` (enumerated policy matrix, funded + minimal tx) and `TestBaseSepoliaLiveFreeform` (freeform matrix).
- Stress: `test/testnet/test_stress_base_sepolia.py` — class `TestBaseSepoliaStressV3PolicyMatrix`.
- Env vars: `FACTORY_ADDRESS`, `TESTNET_SKIP_V3_MATRIX`, `TESTNET_V3_CASES`, `TESTNET_SKIP_FREEFORM`, `STRESS_V3_CASES`, `STRESS_SKIP_V3_MATRIX`.
- See [`TESTNET-LIVE-SUITE.md`](TESTNET-LIVE-SUITE.md) and [`TESTNET-STRESS-SUITE.md`](TESTNET-STRESS-SUITE.md).

## Migration notes (legacy ABIs → V3)

There is **no migration path** in code — the legacy contracts were deleted, not wrapped. Any integrator that needs to interact with already-deployed legacy factories must pin to a pre-V3 tag of this repo; all on-tree tooling assumes V3.

Conceptual mapping from old to new:

| Legacy call | V3 equivalent |
|-------------|---------------|
| `ParamutuelFactory.createWager(...)` (v1) | `createEnumeratedWager(..., SINGLE_WINNER, 0, ...)` with single-bit tickets |
| `ParamutuelFactoryV2.createWager(..., payoffPolicy, policyParam, ...)` | `createEnumeratedWager(...)` (12- or 14-arg overload) |
| `ParamutuelFactoryFreeform.createFreeformWager(...)` | `createFreeformWager(...)` |
| `ParamutuelWagerV2.placeBet(uint256 mask, uint256 amt)` | `ParamutuelWagerV3.placeBet(uint256, uint256)` (enumerated mode) |
| `ParamutuelWagerFreeform.placeBet(string, uint256)` | `ParamutuelWagerV3.placeBet(string, uint256)` (freeform mode) |
| `ParamutuelWagerV2.resolve(uint256 winningMask)` | `ParamutuelWagerV3.resolve(uint256)` (enumerated) |
| `ParamutuelWagerFreeform.resolve(string)` | `ParamutuelWagerV3.resolve(string)` (freeform) |

**Breaking vs v2/freeform:** all V3 events are renamed (e.g. `BetPlaced` → `BetPlacedV3Enumerated` / `BetPlacedV3Freeform`; `Resolved` → `ResolvedV3Enumerated` / `ResolvedV3Freeform`). Indexer schemas that previously distinguished by event *name* now distinguish by the V3-prefixed name + `MODE()` read on the wager.

**Breaking for freeform `answerId`:** the V3 freeform `answerId` uses the domain-separated hash (`keccak256(abi.encodePacked(0x03, bytes(answer)))`), not the raw `keccak256(bytes(answer))` used by the deleted `ParamutuelWagerFreeform`. Any off-chain tool that precomputed answer ids for the old contract must re-hash under the new domain byte.

## Tests

- **Foundry:** `test/ParamutuelV3*.t.sol` covers both modes — enumerated policy matrix (`SINGLE_WINNER`, `ANY_OF`, `EXACT_SET`, `AT_LEAST_K`, `WEIGHTED_OVERLAP`), freeform exact-match + no-winning-stake revert, lifecycle (retract / expire / claim / withdraw fees), fee accounting, seeding invariants, `WrongMode` guard on every wrong-mode external.
- **Gas:** [`PARAMUTUEL-V3-GAS.md`](PARAMUTUEL-V3-GAS.md) — measured enumerated + freeform gas on the current contracts (generated via `script/profile_v3_gas.sh`).
- **Python:** indexer / MCP / control_panel / resolution / bet scout suites all target V3 topics + ABIs; see respective `tests/` directories.

## Security

Same trust model and bounds as ADR-0008 / ADR-0009:

- **Distinct ticket cap** (`MAX_DISTINCT_TICKETS = 1024`) bounds resolve/claim loops for both modes.
- **Option cap** (`MAX_OUTCOMES = 255`) keeps enumerated bitmask math well-defined in `uint256`.
- **Answer length cap** (`MAX_ANSWER_BYTES = 1024`) caps freeform calldata.
- **Resolver trust** is identical to v1/v2/freeform: resolver submits `winningMask` / `winningAnswer`; no on-chain arbitration. Off-chain resolution service + proposition service govern real-world dispute policy.
- **No upgrades / no admin mutation** of any wager once deployed (same immutability posture as ADR-0001).

## Related

- [`ADR-0008-IMPLEMENTATION.md`](ADR-0008-IMPLEMENTATION.md) — enumerated payoff-policy math (historical contract layer, current economics).
- [`ADR-0008-TEMPLATES.md`](ADR-0008-TEMPLATES.md) — product templates for enumerated mode.
- [`ADR-0009-IMPLEMENTATION.md`](ADR-0009-IMPLEMENTATION.md) — freeform economics + outcome-cap discussion.
- [`PAYOUT-CALCULATION.md`](PAYOUT-CALCULATION.md) — human-readable fee / claim formulas (enumerated + freeform).
- [`PARAMUTUEL-V3-GAS.md`](PARAMUTUEL-V3-GAS.md) — measured V3 gas profile.
- [`CONTRACT-UPGRADE-RUNBOOK.md`](CONTRACT-UPGRADE-RUNBOOK.md) — deploy / re-point runbook.
