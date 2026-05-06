# ADR-0013 implementation notes (test stratification and coverage baseline)

**Status:** Implemented on branch `adr-0013-test-stratification`.
**ADR:** [`research/adr/ADR-0013-test-stratification-and-coverage-baseline.md`](../research/adr/ADR-0013-test-stratification-and-coverage-baseline.md)

## Files added

| Path | Role |
|------|------|
| `script/test-fast.sh` | Top-level fast-suite runner (forge + Python unit tests + dApp Node tests). |
| `script/test-extended.sh` | Top-level extended-suite runner (wraps `script/testnet/run_live_suite.sh` + `run_stress_suite.sh`). |
| `docs/COVERAGE-BASELINE.md` | Per-file coverage rationale (Python baseline captured 2026-05-06; Solidity status). |
| `research/adr/ADR-0013-test-stratification-and-coverage-baseline.md` | The ADR itself. |
| `docs/ADR-0013-IMPLEMENTATION.md` | This file. |

`research/adr/README.md` gains a one-line entry for ADR-0013. `LOG.md` gains a 2026-05-06 entry. No existing source or test files are modified.

## Fast suite layers

`script/test-fast.sh` runs, in order, aborting on first failure:

1. **Foundry contract suite** — `forge test`. 65 tests across 5 suites under `test/*.t.sol` as of baseline.
2. **MCP server unit tests** — `python3 -m unittest discover -s mcp_server/tests -p "test_*.py"`. 39 tests, 1 expected failure.
3. **Bet scout agent unit tests** — `PYTHONPATH=. python3 -m unittest discover -s agents/paramutuel_bettor/tests -p "test_*.py"`. 20 tests.
4. **Service unit tests** — one discover invocation per service:
   - `service/indexer/tests` (29 tests, 1 expected failure)
   - `service/proposition/tests` (9 tests)
   - `service/explorer/tests` (5 tests)
   - `service/resolution/tests` (9 tests)
   - `service/control_panel/tests` (16 tests, 1 expected failure)
5. **dApp pure-helper tests** — `node --test tests/logic.test.js` invoked from `dapp/`. 29 tests.

Total fast suite: ≈ 221 assertions (sum of forge tests + Python tests + Node tests).

End-to-end timing on the development machine at baseline: ≈ 12 seconds (forge ≈ 0.7s; Python tests ≈ 9.4s dominated by the indexer suite's HTTP fixtures; Node tests ≈ 0.5s).

## Extended suite layers

`script/test-extended.sh` runs, in order:

1. `script/testnet/run_live_suite.sh` — read-only / minimal-tx / funded-tx modes against Base Sepolia. Mode forwarded via `TESTNET_MODE`.
2. `script/testnet/run_stress_suite.sh` — multi-wager stress matrix with wallet-pool funding.

Both wrappers self-validate required env (`RPC_URL_BASE_SEPOLIA`, `FACTORY_ADDRESS`, `PRIVATE_KEY` when applicable). The extended runner forwards env unchanged.

## Coverage baseline

See `docs/COVERAGE-BASELINE.md` for the full per-file table and refresh recipe.

**Python baseline (2026-05-06):** TOTAL 3463 statements, 1355 missed, **61% covered**. Every 0%-covered and sub-50%-covered module has rationale recorded.

**Solidity baseline:** `forge coverage` blocked by stack-too-deep on `src/ParamutuelWagerV3.sol`. Functional 65/65 pass under production compile. Path forward (constructor refactor, library extraction, or alternative tool) tracked as a follow-up in ADR-0013 § "Follow-ups".

## Operational notes

- The fast runner is fail-fast by design (first failing layer aborts). Combined with `set -euo pipefail`, an unset variable in any layer's command also fails immediately. This is intentional; per `AGENTS.md` #7 the contributor's job after a failure is to fix that failure.
- The Python layers are discovered per-leaf-directory rather than from the repo root because the project tree is not a single Python package — discovering from the root would try to import non-package files (e.g. `out/`, `cache/`, `_site/`).
- `PYTHONPATH=.` is set explicitly for the `agents/paramutuel_bettor` layer so `import agents.paramutuel_bettor` resolves; other layers self-locate via their `__init__.py`.
- The dApp layer runs in a `( cd dapp && ... )` subshell so the parent shell's working directory is restored even on failure.

## Out of scope

- **CI integration.** No `.github/workflows/` exists at the time of writing. When CI lands, the natural shape is: `script/test-fast.sh` on every PR; `script/test-extended.sh` on a nightly schedule with secrets; coverage baseline refresh as a manual workflow_dispatch.
- **Migrating tests to `pytest`.** Existing tests are `unittest`-based; switching is not a coverage-quality issue.
- **Lifting Python coverage above 61%.** That is per-module work tracked in `docs/COVERAGE-BASELINE.md`; ADR-0013 only establishes the baseline.
- **Landing the missing `documentation_workedExample` regression tests** referenced from `docs/PAYOUT-CALCULATION.md`. Tracked as a separate L-003 commit; should ship before ADR-0014 starts.
