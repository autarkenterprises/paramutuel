# Machine / agent integration

Paramutuel is structured so **bots, indexers, and LLM-driven workflows** can interact without bespoke scraping, in line with the protocol thesis: **permissionless** markets in **standard ERC-20 collateral**, **configurable** resolution and timing per wager, and **no centralized approval** of wagers or payouts. Machines read the same indexer and MCP surfaces as humans.

Contract upgrade and redeploy procedure: [`CONTRACT-UPGRADE-RUNBOOK.md`](CONTRACT-UPGRADE-RUNBOOK.md). States and roles in depth: [`WAGER-LIFECYCLE.md`](WAGER-LIFECYCLE.md).

## ABIs

ABI-only JSON is committed under `dapp/abi/` (`ParamutuelFactoryV3.json`, `ParamutuelWagerV3.json`), each as `{"abi": [...]}`. The MCP server bundles the same files under `mcp_server/abi/`. After contract changes, run `./script/sync-abi.sh`; `dapp/tests/abi-drift.test.js` fails if the committed ABI and the contracts disagree.

## Factory: `ParamutuelFactoryV3`

### Constants and state

| Getter | Value / returns | Description |
|---|---|---|
| `BPS_DENOMINATOR()` | `10_000` | Basis-point denominator |
| `MAX_TOTAL_FEE_BPS()` | `10_000` | Cap on protocol plus extra fees combined |
| `MAX_OUTCOMES()` | `255` | Maximum outcomes per enumerated wager |
| `MAX_EXTRA_FEE_RECIPIENTS()` | `32` | Maximum proposer-chosen fee recipients |
| `treasury()` | `address` | Protocol fee recipient; fixed per factory |
| `protocolFeeBps()` | `uint16` | Protocol fee; fixed per factory |
| `minBettingWindow()` | `uint64` | Minimum seconds from creation to `bettingCloseTime` |
| `minResolutionWindow()` | `uint64` | Minimum `resolutionWindow` in seconds |
| `wagersCount()`, `wagers(i)` | `uint256`, `address` | On-chain registry of created wagers |

### Creating wagers

```solidity
function createEnumeratedWager(
    address collateralToken, string proposition, string[] outcomes,
    PayoffPolicy payoffPolicy,  // uint8 on the wire: 0 SINGLE_WINNER, 1 ANY_OF, 2 EXACT_SET, 3 AT_LEAST_K, 4 WEIGHTED_OVERLAP
    uint256 policyParam,        // k for AT_LEAST_K; must be 0 otherwise
    uint64 bettingCloseTime, uint64 resolutionWindow,
    address resolver, address bettingCloser, address resolutionCloser,
    address[] extraFeeRecipients, uint16[] extraFeeBps
    // optional: uint256[] seedTicketMasks, uint256[] seedAmounts
    // optional, after the seeds: uint256 minNewTicketStake
) returns (address wager);

function createFreeformWager(
    address collateralToken, string proposition,
    uint64 bettingCloseTime, uint64 resolutionWindow,
    address resolver, address bettingCloser, address resolutionCloser,
    address[] extraFeeRecipients, uint16[] extraFeeBps
    // optional: uint256 minNewTicketStake
) returns (address wager);
```

- `resolver = address(0)` defaults to the proposer (`msg.sender`).
- `bettingCloser = address(0)` or `resolutionCloser = address(0)` disables that role.
- `bettingCloseTime = 0` or `resolutionWindow = 0` means no time limit, and **requires** the matching closer.
- `resolutionDeadline` is `bettingCloseTime + resolutionWindow`, or `0` if either is `0`. It is for display only: an early `closeBetting()` re-anchors the real deadline earlier. Use `betting_closed_at` from the indexer, or `bettingClosedAtByAuthority()`, plus `resolutionWindow`.
- Seeds pull the proposer's tokens in the creation transaction, so approve the **factory** for the total. Each seed is a ticket mask, not an outcome index.
- `minNewTicketStake` is the minimum raw amount to open a new ticket or answer. Re-betting an existing one is never restricted. It prices griefing by dust tickets in units of the wager's own collateral; `0` means no minimum. Seeds count as opening tickets.

| Error | Condition |
|---|---|
| `BadOutcomes` | `outcomes.length < 2` |
| `TooManyOutcomes` | `outcomes.length > MAX_OUTCOMES` |
| `InvalidPolicyParam` | `policyParam` not valid for the policy |
| `WindowTooShort` | `bettingCloseTime` or `resolutionWindow` below the factory minimum |
| `InvalidLifecycleConfig` | A zero time with no matching closer |
| `BadFeeConfig` | Length mismatch, zero address or bps, more than `MAX_EXTRA_FEE_RECIPIENTS`, or total above the cap |
| `BadSeedConfig` | Seed length mismatch, zero amount, or a mask invalid for the policy or option range |

### Events

```solidity
event WagerCreatedV3Enumerated(address indexed wager, address indexed proposer, address indexed resolver,
    address collateralToken, uint8 payoffPolicy, uint256 policyParam, uint64 bettingCloseTime,
    uint64 resolutionWindow, uint64 resolutionDeadline, address bettingCloser, address resolutionCloser);
event WagerCreatedV3Freeform(address indexed wager, address indexed proposer, address indexed resolver,
    address collateralToken, uint64 bettingCloseTime, uint64 resolutionWindow, uint64 resolutionDeadline,
    address bettingCloser, address resolutionCloser);
```

## Wager: `ParamutuelWagerV3`

`MODE()` returns `0` (enumerated) or `1` (freeform). Calling an entry point for the other mode reverts with `WrongMode`. `state()` returns `0` Open, `1` Resolved, or `2` Retracted; an expired wager is `Retracted`.

### Read-only state

| Getter | Mode | Description |
|---|---|---|
| `factory()`, `proposer()`, `resolver()`, `bettingCloser()`, `resolutionCloser()`, `collateralToken()` | both | Immutable roles and token |
| `proposition()` | both | Question text |
| `bettingCloseTime()`, `resolutionWindow()`, `resolutionDeadline()` | both | See the notes above |
| `bettingClosedByAuthority()`, `bettingClosedAtByAuthority()`, `resolutionWindowClosedByAuthority()` | both | Authority closures |
| `minNewTicketStake()` | both | Minimum to open a new ticket or answer |
| `totalPot()`, `userTotalBet(addr)`, `hasClaimed(addr)` | both | Stake totals and claim status |
| `feeRecipients(i)`, `feeBps(i)`, `totalFeeBps()`, `feeBalances(addr)` | both | Fees |
| `outcomesCount()`, `numOptions()`, `outcomeText(i)` | enumerated | Outcomes |
| `payoffPolicy()`, `policyParam()` | enumerated | Settlement rule |
| `ticketPoolByMask(mask)`, `betsByMask(addr, mask)` | enumerated | Stakes |
| `usedMasksCount()`, `usedMaskAt(i)`, `userMasksCount(addr)`, `userMaskAt(addr, i)` | enumerated | Enumerate tickets |
| `winningMask()`, `payoutDenominator()` | enumerated | Resolution result and total winning units |
| `ticketPoolByAnswerId(id)`, `betsByAnswer(addr, id)` | freeform | Stakes |
| `usedAnswerIdsCount()`, `usedAnswerId(i)` | freeform | Enumerate answers |
| `winningAnswerId()`, `payoutDenominator()` | freeform | Resolution result and winning pool |

**Answer ids:** `answerId = keccak256(abi.encodePacked(bytes1(0x03), bytes(answer)))`. Matching is byte-exact: no trimming, case folding, or Unicode normalization. Do not pass answers as `cast` arguments, which strip trailing whitespace and surrounding quotes; see [`WORKFLOWS.md`](WORKFLOWS.md).

### Functions

```solidity
// Betting: state Open and betting not closed. First approve(wager, amount) on the collateral.
function placeBet(uint256 ticketMask, uint256 amount);                 // enumerated
function placeBets(uint256[] ticketMasks, uint256[] amounts);          // enumerated, one transferFrom
function placeBet(string answer, uint256 amount);                      // freeform, 1 to 1024 bytes

// Authority closes. Silent no-ops if already closed.
function closeBetting();            // bettingCloser only
function closeResolutionWindow();   // resolutionCloser only, after betting has closed

// Finalization by the resolver: betting closed and resolution window open.
function resolve(uint256 winningMask);    // enumerated
function resolve(string winningAnswer);   // freeform, byte-exact
function retract();

// Finalization by anyone: resolution window over.
function expire();

// After finalization.
function claim() returns (uint256 paid);
function withdrawFees() returns (uint256 amount);
```

A **ticket mask** is a bitmask of outcomes: bit `i` is outcome `i`, so `1 << i` backs outcome `i` alone. `SINGLE_WINNER` only admits single-bit tickets and a single-bit winning mask. Other policies take any non-empty mask within range.

`resolve` reverts with `NoWinningStake` if nothing would win. The resolver must then `retract` or let the wager expire.

**Capacity:** at most 1024 distinct tickets before new *multi-outcome* tickets revert with `TooManyDistinctTickets`. Single-outcome tickets are always accepted. This bound is what keeps `resolve` within the per-transaction gas cap; see [`PARAMUTUEL-V3-GAS.md`](PARAMUTUEL-V3-GAS.md). Freeform wagers have no limit on distinct answers, because nothing on-chain iterates them.

### Payout math

Full spec with worked examples: [`PAYOUT-CALCULATION.md`](PAYOUT-CALCULATION.md). All products use full-precision math, so none can overflow.

```text
fees   = floor(totalPot * totalFeeBps / 10000)
netPot = totalPot - fees

Resolved:  paid = sum over the bettor's winning tickets of floor(weight * netPot / payoutDenominator)
           weight = stake, or stake * |ticket ∩ winningMask| for WEIGHTED_OVERLAP
Retracted: paid = floor(userTotalBet * netPot / totalPot)
```

Each fee slice is floored and the last recipient takes the remainder. A claim that would pay 0 reverts with `NothingToClaim` and leaves `hasClaimed` false. Rounding dust stays in the wager.

### Events

```solidity
event BetPlacedV3Enumerated(address indexed bettor, uint256 ticketMask, uint256 amount);
event BetPlacedV3Freeform(address indexed bettor, bytes32 indexed answerId, uint256 amount);
event FreeformAnswerRevealedV3(bytes32 indexed answerId, string answer);  // once per distinct answer, before its first bet event
event BettingClosedByAuthorityV3(uint64 closedAt);
event ResolutionWindowClosedByAuthorityV3(uint64 closedAt);
event ResolvedV3Enumerated(uint256 winningMask);
event ResolvedV3Freeform(bytes32 indexed winningAnswerId);
event RetractedV3();
event ExpiredV3();
event ClaimedV3(address indexed bettor, uint256 amount);
event FeeAccruedV3(address indexed recipient, uint256 amount);
event FeeWithdrawnV3(address indexed recipient, uint256 amount);
```

`FreeformAnswerRevealedV3` is the only on-chain record of an answer's text. Wagers from factories deployed before ADR-0020 do not emit it; their answers are known only by hash.

### Error reference

| Error | Thrown by |
|---|---|
| `WrongMode` | Any mode-specific entry point called on the other mode |
| `InvalidTicketMask` | Bets with a zero or out-of-range mask, or multi-bit under `SINGLE_WINNER` |
| `InvalidWinningMask` | `resolve` with a zero or out-of-range mask, or multi-bit under `SINGLE_WINNER` |
| `NewTicketStakeTooLow` | A bet or seed opening a new ticket below `minNewTicketStake` |
| `TooManyDistinctTickets` | A new multi-outcome ticket when the wager already has 1024 |
| `EmptyAnswer`, `AnswerTooLong` | Freeform bets and `resolve`: answer must be 1 to 1024 bytes |
| `NotOpen` | Bets after finalization; `claim` before it |
| `BettingClosed` | Bets once betting has closed |
| `BettingNotClosed` | `resolve`, `retract`, `expire`, `closeResolutionWindow` while betting is open |
| `ResolutionWindowOver` | `resolve` and `retract` after the window; `expire` before it |
| `NotResolver`, `NotBettingCloser`, `NotResolutionCloser` | Wrong caller |
| `AlreadyFinalized` | `resolve`, `retract`, `expire` after finalization |
| `NoWinningStake` | `resolve` where nothing would win |
| `NothingToClaim` | `claim` with no stake, a zero payout, or a repeat claim; `withdrawFees` with no balance |
| `ArrayLengthMismatch` | Empty or misaligned bet arrays |
| `NotFactory` | `seedInitialBetsFromFactory` from anyone but the factory |

## HTTP indexer API

Production entrypoint: `python3 -m service.indexer.live_api` (sync loop plus API). `python3 -m service.indexer.api` serves an existing database. All responses are JSON with CORS `*`. Every path also works with an `/api` prefix.

| Path | Description |
|---|---|
| `GET /health` | `ok`, `ts`, `wager_count`, `last_indexed_block`, `chain_head`, `sync_lag_blocks`, `last_sync_error`, `skipped_log_count`, `last_skipped_log`, `factory_address` |
| `GET /wagers` | Paginated list. Params: `state` (`OPEN`, `RESOLVED`, `RETRACTED`), `q` (search all fields), `limit` (1 to 1000, default 100), `offset`, `order` (`asc` or `desc`, default `desc`) |
| `GET /wagers/{address}` | Detail bundle, below. Params: `pool_limit`, `events_limit`, `answer_id` |
| `GET /sweeper/expire-candidates` | Still-`OPEN` wagers where `expire()` is valid. Param: `now` (unix seconds) |

Detail bundle fields:

- **`wager`:** all indexed columns, including `protocol_version` (`enumerated` or `freeform`), `payoff_policy`, `policy_param`, `outcomes_json`, `betting_close_time`, `betting_closed_at`, `resolution_window`, `resolution_deadline`, `min_new_ticket_stake`, `state`.
- **`totals`:** `total_pot`, `total_fee_bps`, `winning_outcome` (a mask or answer id), `total_winning_stake` (equals on-chain `payoutDenominator`; weighted units under `WEIGHTED_OVERLAP`).
- **`outcomes`:** enumerated only. `{outcome_index, outcome_total}`, where a multi-outcome ticket counts toward each outcome it includes, so under those policies the totals overlap.
- **`ticket_pools`:** `{ticket_mask, pool_total}`. Enumerated rows are sorted by mask and never truncated. Freeform rows use the answer id as `ticket_mask`, add `answer_text` and `answer_hex`, sort by stake, and are limited by `pool_limit` (default 500, with the full count in `ticket_pools_total`). Use `answer_id` to fetch one directly. `answer_text` is `null` when the bytes are not valid UTF-8; `answer_hex` is always exact.
- **`events`:** newest `events_limit` events (default 1000) in chain order, with the full count in `events_total`.

All uint256 values are decimal strings, because JavaScript JSON parsers round numbers above 2^53.

`state` stays `OPEN` after betting closes, because V3 has no separate state for it. To tell whether a wager accepts bets, also check `betting_closed_by_authority` and `betting_close_time`.

## Configuration

`config/deployments.json` holds per-network runtime defaults: `factoryAddress`, `indexerFromBlock`, `chainId`, `explorerApiBase`. `config/collateral-allowlist.json` lists tokens surfaces present as vetted (ADR-0018). The dApp and website read both at load time.

## MCP server

`mcp_server/` exposes 21 tools:

- **Discovery:** `get_protocol_info`, `list_wagers`, `get_wager`, `get_expire_candidates`, `get_indexer_health`
- **Analysis:** `calculate_odds`, `quote_place_bet`, `quote_place_bets`
- **Transaction encoding:** `encode_create_enumerated_wager`, `encode_create_freeform_wager`, `encode_place_bet`, `encode_place_bet_freeform`, `encode_place_bets`, `encode_resolve`, `encode_resolve_freeform`, `encode_retract`, `encode_expire`, `encode_close_betting`, `encode_close_resolution_window`, `encode_claim`, `encode_withdraw_fees`

```bash
pip install mcp httpx eth-abi "eth-hash[pycryptodome]"
python -m mcp_server
```

The server reads the factory address and chain ID from `config/deployments.json`, or from `FACTORY_ADDRESS`, `CHAIN_ID`, and `INDEXER_URL`. Write tools return calldata plus approval instructions for the caller to sign. `paramutuel-mcp` is packaged for PyPI but **not yet published**; install from this repository. Agent loop guide: [`AGENT-LOOP.md`](AGENT-LOOP.md).

## Bet scout agent

A stdlib-only process at `agents/paramutuel_bettor/` for indexer-backed discovery and ranked bet ideas, meant for subagent delegation. It is packaged as `paramutuel-bettor-agent` but **not yet published**. See [`BET-AGENT.md`](BET-AGENT.md), [`BET-AGENT-DISTRIBUTION.md`](BET-AGENT-DISTRIBUTION.md), and [`agents/subagent-manifest.json`](../agents/subagent-manifest.json).

## Versioning

Existing event signatures and creation signatures are an ABI commitment: indexers and clients key on them. Add new overloads and events rather than changing existing ones, as ADR-0020 did. A contract change means a new factory address, which is one change to `config/deployments.json`. New columns are added to existing indexer databases automatically by `init_db`.
