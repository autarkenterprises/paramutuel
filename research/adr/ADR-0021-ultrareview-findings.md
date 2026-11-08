# ADR-0021: Correct the findings of the independent ultrareview of ADR-0020

Date: 2026-11-07
Status: **Part 1 implemented** (2026-11-07); open for the findings of parts 2 and 3
Builds on: ADR-0020, `AGENTS.md` #1 / #2 / #4 / #5 / #8 / #9

## Context

ADR-0020's remediation (`d4e2998..579b192`, 15,718 changed lines) was submitted to an independent multi-agent cloud review (Claude Code "ultrareview"). Its 8,000-changed-line cap forced a split into three stacked, review-only pull requests at real commit boundaries: #2 (`d4e2998..4e3d8c7`: contracts, indexer, services), #3 (`4e3d8c7..f8129d2`: deploy, clients, agent, MCP) and #4 (`f8129d2..579b192`: coverage, browser call fix, browser tests). They are never merged; the work is already on `master`.

The review of part 1 (#2) reported five findings, each reproduced by the reviewer. Each was re-checked against `master` before this ADR, because later parts change some of the same code.

## Findings (part 1, #2)

| ID | Severity (reviewer) | Finding | State on `master` |
|---|---|---|---|
| U1 | normal | Freeform `/wagers/{addr}` keeps only the 500 largest pools; clients that look an answer up in `ticket_pools` see 0 for any other answer and overstate its payout. | **MCP fixed** in part 2 (`quote_place_bet` sends `?answer_id=`). **Bet scout still live:** `quote_wager` takes odds from the row at `outcome_index`, but builds calldata from `freeform_answer`, so the two can describe *different answers*. The index also shifts whenever a new answer id sorts before it. |
| U2 | nit | `backfill_incomplete_metadata` has no backoff and always takes the 25 oldest incomplete rows: rows that never complete are re-read in full every pass (up to ~259 `eth_call`s each) and starve newer rows forever. | Live. |
| U3 | nit | For `WEIGHTED_OVERLAP`, `total_winning_stake` stores the contract's weighted `payoutDenominator` (pool × overlap size), which the site and explorer print as a token amount ("Winning stake 300 · Pot 100"). | Live. |
| U4 | nit | `sync_logs` makes at least two `eth_getLogs` calls per chunk (factory, then known wagers) though almost no chunk creates a wager; it doubles RPC load and cold-start replay time on the public endpoint. | Live. |
| U5 | pre-existing | The resolution service pages OPEN wagers oldest first **across every resolver** and stops silently at 50 pages × 1,000 (`/run-once`) or 1,000 rows (`/candidates`). On a permissionless factory this resolver's newest wagers fall past the cap and drift to `expire()` (refunds instead of payouts); nothing reports it. | Live. |

Findings from the reviews of parts 2 and 3 are added below as they arrive.

## Decision

Correct all five, red-to-green, on branch `adr-0021-ultrareview-findings`:

- **U1.** The bet scout looks a freeform answer up by its id, exactly as MCP does: `quote_wager` computes `answerId = keccak256(0x03 ‖ bytes(answer))` and asks the indexer for `?answer_id=`. The package stays dependency-free, so it gains a small pure-Python Keccak-256, checked against `eth-hash` in tests (as the pinned selectors already are). Odds and calldata then always describe the same answer. Without an answer there is no calldata, so `outcome_index` still picks a listed row for an informational quote (unchanged).
- **U2.** Each incomplete row records `metadata_attempts` and `metadata_retry_at`. A failed retry backs off exponentially (15 s doubling, capped at one hour, never abandoned, since an RPC outage ends). Rows are taken in `metadata_retry_at` order, so a failing row moves behind the others instead of blocking them.
- **U3.** `wager_totals` gains `payout_denominator` (the contract's value, which payouts need), and `total_winning_stake` becomes what its name and every reader say: the plain stake on winning tickets. They differ only for `WEIGHTED_OVERLAP`. Existing databases are recomputed from stored pools when the column is added.
- **U4.** One `eth_getLogs` per chunk: the factory and the known wagers (batched as before) under the union of topics. Only when that chunk creates wagers does a follow-up query fetch the new wagers' logs from the same range, because their seed bets land in the creation transaction.
- **U5.** The indexer's `/wagers` gains an exact `resolver=` filter, and the resolution service uses it, so its pages hold only its own wagers. When it still hits the page cap, `/run-once` and `/candidates` report `truncated: true` instead of hiding it. An older indexer that ignores the filter returns a superset, which the per-row resolver gate already handles.

## Success criteria

- Each finding has a test that fails on `master` and passes on the branch.
- Fast suite and local end-to-end suites pass; Python coverage stays at or above 99%.
- U4: a chunk with no creations costs exactly one `eth_getLogs` while fewer than 200 wagers are known; a wager created and bet on within one chunk is still fully indexed.
- U3: the end-to-end check that the indexer's value equals the contract's `payoutDenominator` still passes, now against `payout_denominator`.

## Failure criteria

- Any API field changes meaning for a policy other than `WEIGHTED_OVERLAP` (`total_winning_stake` must be unchanged for policies 0–3).
- A replay of an existing database produces different totals from a fresh index.

## Rejected alternatives

- **Indexer-side `answer=` text lookup (U1).** Keeps the bet scout free of a Keccak implementation, but matches only answers whose reveal event the indexer stored; an id lookup is exact for every answer.
- **Dropping a metadata row after N failures (U2).** An RPC outage of any length would then blank a wager permanently, the exact defect ADR-0020 fixed.
- **Relabelling the site's "Winning stake" for policy 4 (U3).** Every reader would have to know the policy; fixing the column fixes them all.

## After Action Report

### Part 1 (#2), 2026-11-07

**Outcome.** All five findings corrected, each with a test that failed on `master` first:

| ID | Tests (red on `master`, green on the branch) |
|---|---|
| U1 | `agents/paramutuel_bettor/tests/test_adr0021.py`: `QuoteTests` (odds for the answer being bet; the index cannot redirect them; an unstaked answer is unstaked), `KeccakTests` (known vectors, `eth-hash` parity for every length 0 to 299 plus 1,000 and 4,096), `ClientTests` |
| U2 | `service/indexer/tests/test_adr0021.py`: `BackfillBackoffTests` (doubling wait, one-hour cap, never abandoned, no starvation of a 26th row, migration) |
| U3 | `WinningStakeTests` (policy 4 keeps 147 tokens apart from 187 units; policies 0 to 3 and freeform equal; API list and detail; one-time migration for enumerated and freeform rows); the five `test_*_settles` end-to-end tests now check `payout_denominator` against the chain and `total_winning_stake` against the plain stake |
| U4 | `LogQueryTests` (one query per quiet chunk; a follow-up only for new wagers; each address once across batches; the wager list read once per sync; a malformed log and a forged creation event are harmless) |
| U5 | `ResolverFilterTests` (indexer `resolver=`), `service/resolution/tests/test_adr0021_service.py` (scoped queries; truncation reported at the page cap and past an explicit limit, not on an exact fit; both routes) |

**Success criteria.**
- Each finding has a test that fails on `master`: **met**.
- Fast suite (169 Foundry, 587 Python, 93 Node) and both local end-to-end suites (38: 18 chain, 20 browser) pass; changed Python files are at 99% to 100% coverage, the remaining lines being the documented `__main__` guards: **met**.
- U4, one `eth_getLogs` per quiet chunk with fewer than 200 wagers, and same-chunk seed bets still indexed: **met**.
- U3, the end-to-end comparison against `payoutDenominator` passes, now on `payout_denominator`: **met** for all five policies.

**Failure criteria.** Neither triggered. `total_winning_stake` is unchanged for policies 0 to 3 and freeform (asserted per policy). Migration of an existing database is asserted equal to what a fresh index writes.

**What the review got right that we had missed, and why.** Two of the five (U1, U3) were defects that ADR-0020's own tests had pinned in place, by asserting values copied from the code's output (L-017). U2 and U4 were costs that no functional test measures. U5 predates ADR-0020 and survived both audits because every test ran with one resolver.

**Found while fixing.**
- The first U4 version re-read the whole wager list twice per chunk: a cold-start replay of ~100k chunks would have paid for it. It now reads the list once per sync. A test pins this.
- `service/indexer/README.md` still said fees were recorded as 0, which ADR-0019 fixed; corrected.
- The ADR index listed ADR-0020 as "Accepted", with a malformed entry above it; corrected.

**Not done.** Nothing redeployed: the hosted indexer and resolution service pick these fixes up at the operator's next redeploy, already listed in `docs/ADR-0020-IMPLEMENTATION.md`. The bet scout is not yet published to PyPI, so no release is needed.
