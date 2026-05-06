# ADR-0013: Test stratification and coverage baseline

Date: 2026-05-06
Status: **Proposed** — Implemented on branch `adr-0013-test-stratification`.
Builds on: [`AGENTS.md`](../../AGENTS.md) project-generic practice **#1, #2** (TDD, total-or-documented coverage), project-specific practice **#13, #14** (extended suite separation and cadence), ADR-0012 (template).

## Context

`AGENTS.md` practice #13 mandates that slower regressions live in an explicit extended suite, and #14 requires the extended suite be run in parallel during feature work and **blocked on** before any commit that changes functionality measured by it. Practice #2 requires total coverage **or** rationale for partial coverage.

Today the repository already has the right physical structure:

- Foundry fast suite at `test/*.t.sol` (5 suites, 65 tests as of 2026-05-06).
- Python unit tests under `mcp_server/tests/`, `agents/paramutuel_bettor/tests/`, and `service/<svc>/tests/` (≈ 167 tests in 6 directories, including 3 expected-failure markers).
- dApp pure-helper tests at `dapp/tests/logic.test.js` (29 tests).
- Extended testnet suite at `test/testnet/` with shell wrappers `script/testnet/run_live_suite.sh` and `script/testnet/run_stress_suite.sh`.

What's missing is **codification**: there is no top-level "fast" or "extended" runner, no documented coverage baseline, and no place that records the rationale for partial coverage. A new contributor can locate the tests but not the cadence.

## Decision

1. **Adopt a top-level fast / extended split as policy and as runners:**

   - `script/test-fast.sh` runs every check that does **not** require live RPC, secrets, or external indexer access. The default test path. Layers: `forge test`, the four Python unit test groups (mcp_server, agents/paramutuel_bettor, each `service/<svc>/tests`), `dapp` Node tests. Aborts on first failure.
   - `script/test-extended.sh` wraps the existing `script/testnet/run_live_suite.sh` and `script/testnet/run_stress_suite.sh`. Forwards `TESTNET_MODE`. Aborts on first failure. Skip flags `EXTENDED_SKIP_LIVE` / `EXTENDED_SKIP_STRESS`; refuses to run with both set.

2. **Adopt the existing physical layout as canonical:**

   - Solidity fast tests under `test/*.t.sol`, extended tests under `test/testnet/*.py`. No reorganization in this ADR.
   - Python unit tests live with their module under `<module>/tests/`. No move into a top-level `tests/` tree.
   - dApp tests stay under `dapp/tests/`.

3. **Record the coverage baseline at `docs/COVERAGE-BASELINE.md`:**

   - Python `coverage` baseline captured 2026-05-06: **TOTAL 3463 statements, 1355 missed, 61% covered**.
   - Per-module rationale for every 0%-covered file (entrypoints / servers / CLIs exercised by extended suite or manual ops) and every sub-50% file (live-RPC adapters, ingest scheduling, LLM synthesis).
   - Solidity `forge coverage` is currently **blocked** by stack-too-deep when via-IR is disabled (a known Foundry limitation against complex contracts). The functional Foundry suite passes 65/65 under the production compile; documented path forward in `docs/COVERAGE-BASELINE.md` § Solidity coverage.

4. **TDD posture (per practice #1):**

   - The runners themselves are thin shell wrappers. Their "test" is end-to-end execution: the runner exits 0 when the entire suite passes. `script/test-fast.sh` was run end-to-end on this branch and exited 0.
   - Going forward, ADR-numbered branches that touch code must run `script/test-fast.sh` clean before commit. Branches that change extended-suite-measured functionality must also run `script/test-extended.sh` clean before merge to `master`.

5. **Coverage-uplift posture (per practice #2):**

   - 61% Python coverage with the documented rationale **is** the current "documented partial coverage" stance — it is recorded in `docs/COVERAGE-BASELINE.md` per file.
   - Ratchet: the baseline does not regress except by ADR-recorded decision. Any future commit that drops a previously-covered module's coverage requires either an updated rationale entry in `docs/COVERAGE-BASELINE.md` or a new test.
   - Solidity coverage is a known follow-up; the unblocking work is captured in `docs/COVERAGE-BASELINE.md` (constructor refactor, library extraction, or alternative coverage tool).

## Decision points

- **One top-level runner per cadence (fast / extended) rather than per language** (`forge`, `pytest`, `node`). Rationale: the AGENTS.md cadence distinction is fast-vs-extended; that's the contract a contributor needs at the prompt. Per-language entrypoints are a layer below and remain available directly.
- **Fail-fast vs run-all-and-aggregate:** fail-fast. Practice #7 ("passing, regression-free test suite evaluation" before commit) means the contributor's job after a failure is to fix that failure, not enumerate the rest. Cascading failures usually come from the same root cause anyway.
- **Coverage baseline as a checked-in markdown file** (`docs/COVERAGE-BASELINE.md`) rather than CI-only output. Rationale: rationale for *why* a file is uncovered is durable knowledge; the percentage is the easy part.
- **No CI integration in this ADR.** The repo has no `.github/workflows/` directory at the time of writing (already verified). When CI is introduced, it should call `script/test-fast.sh` for PR checks and `script/test-extended.sh` (with secrets) for nightly runs.

## Success criteria

- `script/test-fast.sh` exists, is executable, and exits 0 on `master` HEAD.
- `script/test-extended.sh` exists, is executable, and successfully delegates to the testnet wrappers (verified by the wrappers' env validation, even without secrets present locally — the script's own logic is testable with skip flags).
- `docs/COVERAGE-BASELINE.md` exists with a per-file rationale for every 0%-covered module and every sub-50% module.
- A contributor reading `AGENTS.md` #13/#14 can locate both runners by name in less than one minute.

## Failure criteria

- The runners exist but bit-rot (a layer is added or moved without updating the runner). Mitigation: any commit that adds a Python `tests/` directory under `service/`, `agents/`, or `mcp_server/` must update `script/test-fast.sh`. This is enforced by the runner's fail-fast nature — a missed directory is a missed test, not a silent gap.
- The coverage baseline becomes deadwood (file exists but the recipe stops producing it). Mitigation: the recipe is in the file; refresh cadence is documented; rationale entries are forced to age.
- Contributors run only `forge test` or only Python tests and miss cross-layer regressions. Mitigation: `script/test-fast.sh` is the documented commit-gate; per practice #7 it must pass before any commit.

## Rejected alternatives

- **Move all Python tests into a top-level `tests/` tree.** Rejected — adds a structural move that violates practice #8 (no unrelated changes) for no measurable benefit; per-module `tests/` keeps tests close to the code they exercise.
- **Use `pytest` instead of `unittest discover`.** Rejected for now — the existing tests are written against `unittest` (`unittest.TestCase`, `expectedFailure`); a discovery-only switch is fine, but adding a pytest dependency to run already-passing tests adds ceremony without leverage. Future ADR may revisit if richer fixtures or parametrization become valuable.
- **Track Solidity coverage by gating CI on a numeric floor.** Rejected — `forge coverage` is currently blocked by stack-too-deep; gating on a number that cannot be measured is theatre. Address the compile obstacle first, then revisit.
- **Run extended suite on every commit.** Rejected — this is exactly what AGENTS.md #14 forbids. Extended runs in parallel and blocks before functionality-changing merges, not on every commit.

## After Action Report

**AAR date:** Pending
**AAR status:** Pending

**Outcome vs success criteria:** to be populated after one ADR cycle (e.g. ADR-0014 or the next code-touching ADR) confirms the runners are exercised in practice and the coverage baseline is refreshed when modules change.

**Outcome vs failure criteria:** to be populated.

**Lessons:** to be populated.

**Follow-ups:**

- Unblock `forge coverage` (constructor refactor / library extraction / alternative tool).
- Add deterministic unit tests for the indexer's live-RPC error-recovery paths to lift `service/indexer/live_api.py` above the current 23%.
- Land the regression test stubs named in `docs/PAYOUT-CALCULATION.md` (e.g. `testSingleWinner_documentationWorkedExample_threeOutcomes`, `testAtLeastK_documentationWorkedExample_fourOutcomes_k2`, `testWeightedOverlap_documentationWorkedExample_fourOutcomes`, `testFreeform_documentationWorkedExample_rosebud`) so the worked examples round-trip through the fast suite. **This is L-003 work and should ship as its own commit before ADR-0014.**

**Revision schedule:** at next code-touching ADR (likely ADR-0014).
