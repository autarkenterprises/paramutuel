# ADR-0019 implementation notes — V3 verification audit

Companion to [`research/adr/ADR-0019-v3-verification-audit.md`](../research/adr/ADR-0019-v3-verification-audit.md).
Branch: `adr-0019-v3-verification-audit`.

## Method

1. **Contracts (`src/`)** — full line-by-line review by the lead agent against ADR-0001 / 0002 /
   0005 / 0008 / 0009 / 0010, `docs/PAYOUT-CALCULATION.md`, `docs/WAGER-LIFECYCLE.md`; git-history
   trace of the test suite; PoC for suspected issues.
2. **Peripheral layers** — two read-only Cursor sub-agents (`agent -p --mode ask`, `composer-2.5`;
   Opus / GPT quota was exhausted) scoped to `service/` and to `dapp/` + `mcp_server/` +
   `agents/` + `site/`, with the contract semantics given as ground truth. **Every reported lead
   was re-verified by the lead agent against the code before acting**; unverified leads were
   dropped.
3. **Cross-language invariants checked directly** — indexer event `topic0` hashes vs the compiled
   ABI (13/13 match), `answerId` domain byte, fee math, window anchoring in indexer / sweeper /
   resolution logic.
4. Fixes: strict red → green per unit — each new test was run and observed failing against the
   unfixed code before the fix was written (the contract lifecycle suite, whose target code
   pre-exists, is instead proven by mutation below); one commit per logical unit.

## Findings and disposition

| # | Area | Finding | Severity | Disposition |
|---|------|---------|----------|-------------|
| 1 | contracts | Economics, fee charging, refunds, reentrancy posture | — | **Verified correct** |
| 2 | tests | V1 lifecycle suite deleted in `b2a2f28`, never ported; 15 custom errors + 8 `require` strings untested | High (process) | **Fixed** — `test/ParamutuelV3Lifecycle.t.sol` (40 tests) + `script/check-revert-coverage.py` in the fast suite |
| 3 | contracts | Freeform answer-space exhaustion: 1024 × 1-wei bets (~101.5M gas) lock out new answers; same for multi-bit enumerated (≥ 11 options) | Medium (security) | **Pinned** by `test_freeform_answerSpaceExhaustion_griefingBoundary`; contract mitigation **Proposed** (new bytecode) |
| 4 | ADR-0005 | "Closers default to proposer" text + AAR "Met" claim are false since `bc8e4a8` | Medium (intent record) | **Fixed** — AAR revision appended; L-008 |
| 5 | contracts | Zero-time windows depend on closer-key liveness; `resolutionDeadline` is informational after an early close | Low (documented) | **Pinned** by lifecycle tests; recorded in ADR-0005 revision |
| 6 | resolution service | `outcomeIndex` sent raw to `resolve(uint256)` — `outcomeIndex: 1` resolved **outcome 0** (wrong winner) | **High** | **Fixed** (`3294f55`) |
| 7 | resolution service | `POST /run-once` unauthenticated, CORS `*`, dry-run echoed `--private-key` | **High** (security) | **Fixed** (`3294f55`) — token-gated, fail closed, redacted |
| 8 | resolution service, control panel | Freeform winning answer `.strip()`-ed; V3 is byte-exact | Medium | **Fixed** (`3294f55`, `2ecfe09`) |
| 9 | indexer | `wager_totals.total_fee_bps` hard-coded `'0'` → every fee-aware preview / EV assumed no fees | Medium | **Fixed** (`c8e7469`); verified end-to-end on anvil (`total_fee_bps = 350` for 100 + 250 bps) |
| 9b | indexer | `total_pot` summed in SQLite 64-bit ints: > ~9.22 tokens (18 decimals) became `'1.0e+19'`; a single bet ≥ 2^63 raised mid-`apply_log`, committing a torn state (event + pool written, pot not) | Medium | **Fixed** — Python big-int sum + per-log `SAVEPOINT` |
| 10 | dApp | Enumerated odds preview called non-existent `ticketPoolTotal` → always failed | Medium | **Fixed** (`2456498`) + static ABI-drift test |
| 11 | site | Staking enabled after betting closed (indexer `OPEN` ≠ bettable); per-outcome multiples shown for multi-winner policies | Medium | **Fixed** (`5a82ce1`) via unit-tested `site/bet-logic.js` |
| 12 | bet scout | `recommend` ranked closed wagers and mis-scored multi-winner policies | Medium | **Fixed** (`f914110`) — skipped with reasons; `odds_model_exact` |
| 13 | MCP | Quotes presented single-pool multiples for multi-winner policies | Low | **Fixed** (`61f2eeb`) — `odds_model_exact` + `odds_note` |
| 15 | indexer / clients (intent) | ADR-0009 expects freeform odds "keyed by observed answers"; no layer recovers answer **text** (only `answerId` hashes), so bettors cannot see or join existing answers without guessing exact bytes | Medium (intent gap) | **Follow-up** — needs its own ADR (decode `placeBet(string,…)` calldata per tx; contract-wallet callers need traces) |
| 14 | control panel | Docstrings repeated the stale closer default and a wrong multi-bit-seed claim | Low | **Fixed** (`2ecfe09`) |

Leads examined and **rejected** after verification: proposition `dispatch_proposal(dry_run=True)`
returns the key-bearing command, but no HTTP route calls it with `dry_run=True`; bet-side answer
trimming in dApp / site / MCP is a consistent off-chain convention permitted by ADR-0009 §5 (now
documented in `docs/RESOLUTION-SERVICE.md`), not a defect.

## Mutation evidence for the lifecycle suite (AGENTS.md #1)

The contracts pre-exist, so red-before-green is demonstrated by mutation: each guard below was
weakened in an isolated copy of the repo (`src/` in the working tree was never modified), the
lifecycle suite was run, and the mutation reverted. Harness: a 28-mutation Python script
(one exact-string replacement per mutation; `KILLED` = at least one test failed).

| # | Mutation (guard weakened) | Result |
|---|---|---|
| 1 | closeBetting auth | Killed |
| 2 | closeBetting idempotence | Killed |
| 3 | closeResWin auth | Killed |
| 4 | closeResWin needs betting closed | Killed |
| 5 | resWinOpen ignores authority | Killed |
| 6 | resWinOpen off-by-one | Killed |
| 7 | resWinOver off-by-one | Killed |
| 8 | anchor ignores authority close | Killed |
| 9 | bettingClosed off-by-one | Killed |
| 10 | retract auth | Killed |
| 11 | retract finality | Killed |
| 12 | expire finality | Killed |
| 13 | expire needs betting closed | Killed |
| 14 | seeder auth | Killed |
| 15 | claim nonReentrant | Killed |
| 16 | claim transfer check | Killed |
| 17 | withdrawFees zeroes balance | Killed |
| 18 | fee remainder to last | Survived in first run → test strengthened in `d25577a`; re-run **killed** (`203 != 205`) |
| 19 | placeBet transferFrom check | Killed |
| 20 | distinct ticket cap | Killed |
| 21 | placeBet after final | Killed |
| 22 | factory window min | Killed |
| 23 | factory fee cap | Killed |
| 24 | factory zero recipient | Killed |
| 25 | factory treasury slot | Killed |
| 26 | factory zero treasury | Killed |
| 27 | wager ctor fee cap | Killed |
| 28 | wager ctor distinct cap | Killed |

**Result: 28 / 28 killed** (27 on the first run; the fee-remainder survivor exposed a test whose amounts divided evenly, fixed and re-verified).

## Verification

- `script/test-fast.sh` — **pass** (109 Foundry tests, revert-path coverage, all Python unit
  suites, 39 node tests).
- `script/check-revert-coverage.py` against master's `test/` — **fails** listing the 23
  unasserted revert reasons; against this branch — passes (30 errors, 8 strings).
- Indexer fee enrichment — local anvil deployment of the real factory, `createEnumeratedWager`
  with protocol 100 bps + extra 250 bps, `fetch_wager_metadata` returned `total_fee_bps = 350`.
- Extended suite — **not run**: it exercises the *hosted* indexer image and funded Base Sepolia
  transactions, neither of which contains these changes until redeploy; no contract changed.
  Run it after the redeploys below.

## Operator follow-ups (not done by the agent — outward-facing)

1. **Resolution service redeploy with `RESOLUTION_SERVICE_TOKEN` set.** Without it the new build
   rejects every `POST /run-once` (fail closed). Rotate the resolver key if the old service was
   ever reachable from outside the operator host: its dry-run response disclosed the key.
2. **Audit existing decision files** for `outcomeIndex` entries executed by the old build (no
   `winningMask`): it sent `resolve(i)` with `i` as the *mask*. `i = 0` reverted; `i = 1` paid
   outcome 0 (intended 1); `i = 2` paid outcome 1 (intended 2); `i = 4` paid outcome 2 (intended
   4); any non-power-of-two `i` reverted on a SINGLE_WINNER wager. Only `i = 0`-intended
   decisions were impossible — every executed `outcomeIndex > 0` resolution paid the wrong side.
3. **Indexer redeploy** so `total_fee_bps` is populated and 18-decimal pots are exact (cold start replays from
   `indexerFromBlock`). At audit time the hosted indexer returned HTTP 500 / 503 on `/health`.
4. `config/deployments.json` `baseSepolia.factoryAddress` reports `wagersCount() == 0`; confirm it
   is the intended ARG factory.
5. **Contract mitigation ADR** for finding 3 (minimum stake to open a new answer / mask, or a
   proposer-chosen `maxDistinctAnswers`) before the next factory deployment (ADR-0015 cutover is
   a natural vehicle).
6. Naming hazard: the control panel's `outcomeIndex` field / `--outcome-index` flag carries a
   **bitmask** (labels say so), while the resolution service's `outcomeIndex` is an **index**.
   Consider renaming the control-panel field to `winningMask` in a follow-up.
7. Freeform answer-text recovery (finding 15) — new ADR; tracked in `docs/TASKS.md`.
