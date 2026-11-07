# Coverage baseline

Per `AGENTS.md` practice #2: coverage must be total, **or** documented with rationale for partial coverage. This file records the as-of baseline and the rationale for every uncovered path. Refresh after any non-trivial test or module change; ADR-0013 captures the *recipe*, this file captures the *result*.

## Refresh recipe

```bash
# Python (run from repo root)
coverage erase
for d in mcp_server/tests \
         service/indexer/tests \
         service/proposition/tests \
         service/explorer/tests \
         service/resolution/tests \
         service/control_panel/tests; do
  PYTHONPATH=. coverage run --append --source=mcp_server,service,agents \
    -m unittest discover -s "$d" -p "test_*.py"
done
PYTHONPATH=. coverage run --append --source=mcp_server,service,agents \
  -m unittest discover -s agents/paramutuel_bettor/tests -p "test_*.py"
coverage report

# Solidity / Foundry — see "Solidity coverage" below.
```

## Python — 2026-05-06 baseline

**TOTAL — 3463 statements, 1355 missed, 61% covered.**

Full per-file numbers in `git show` of this commit; the salient pattern is that **non-test, sub-50%-covered files are entirely entrypoint / server / CLI modules**, intentionally exercised by the extended (testnet) suite or manual ops runbooks rather than unit tests.

### 0%-covered modules (intentional — entrypoint / server / CLI)

| File | Stmts | Why uncovered | Where it IS exercised |
|------|-------|---------------|------------------------|
| `agents/paramutuel_bettor/__main__.py` | 101 | CLI entrypoint; argparse + subcommand dispatch. | `paramutuel-bettor health` / `json` invoked end-to-end in manual smoke and `script/bettor-agent/`; pure-helper logic underneath is unit-tested via `tests/test_*.py`. |
| `agents/paramutuel_bettor/config.py` | 21 | Reads env / `config/deployments.json` to build runtime config. | Indirectly via the CLI integration runs; pure-data helpers live in tested modules. |
| `mcp_server/__main__.py` | 2 | One-line `if __name__ == "__main__"` server bootstrap. | The server itself is tested by `mcp_server/tests/test_server.py` (in-process). |
| `service/control_panel/cli.py` | 75 | Operator CLI. | Runbook-driven; `commands.py` (the logic) is 80% covered. |
| `service/control_panel/web.py` | 90 | Token-gated web shell. | Operated under `--allow-execute` flag in deployment; logic in `commands.py` is unit-covered. |
| `service/explorer/server.py` | 72 | Flask-style HTTP wrapper. | Live testnet integration suite hits the deployed Cloud Run instance; pure logic in `logic.py` is 89% covered. |
| `service/proposition/server.py` | 271 | HTTP server + ingest dispatch. | Manual operator panel + scheduled ingest jobs; ingest / dispatch / db logic underneath is partially unit-covered. |

### Sub-50%-covered modules with documented rationale

| File | % | Rationale |
|------|---|-----------|
| `service/indexer/live_api.py` | 23% | Live RPC + WebSocket adapter — the *uncovered* paths are the RPC error handlers (HTTP 400 bisect, deep-reorg recovery, chunk-size adjustment). They are exercised by the **extended suite** (`script/test-extended.sh` → live Base Sepolia run) but not by unit tests, by design — mocking out the failure modes well enough to be useful is harder than running the real failure on testnet. **Follow-up:** add deterministic unit tests for the bisect heuristic. |
| `service/resolution/service.py` | 27% | Cloud Run service entrypoint + decision dispatch. Pure decision logic is in `logic.py` (76% covered). The uncovered paths are the HTTP server lifecycle and `--allow-execute` gating; **both run live in production** during the Resonance Exchange ARG (`docs/MICROWONK-ARG.md`) — the prior "exercised by manual operator runs" rationale was understated. **Revised follow-up:** lift coverage of the lifecycle / dispatch paths with deterministic unit tests against a fake `subprocess` shim, since the live ARG path now depends on them. |
| `service/proposition/ingest.py` | 40% | Periodic-ingest scheduling logic; partial coverage today. The Co-ordinator's wager dispatch cadence (`docs/MICROWONK-ARG.md`) runs through this module live during the ARG. **Follow-up:** targeted unit tests for the timing / async glue, tracked in `docs/TASKS.md`. |
| `service/proposition/synthesize.py` | 50% | Rule-based draft synthesis paths; some branches reserved for an LLM-backed expansion under feature flag (see module docstring). |

### 50–80%-covered modules (acceptable; unit tests cover happy paths)

`service/indexer/indexer.py` 55%, `service/proposition/json_sources.py` 56%, `service/indexer/sweeper.py` 62%, `agents/paramutuel_bettor/planner.py` 58%, `service/proposition/dispatch.py` 59%, `service/control_panel/commands.py` 80%, `service/proposition/rss.py` 81%, `agents/paramutuel_bettor/policy.py` 89%, `service/explorer/logic.py` 89%.

The 50-80% band covers the production-critical pure-logic modules. Each has working tests for happy paths and the most likely error branches; the missed lines are typically optional-feature branches (e.g. `synthesize.py` LLM prompts) or rare-error paths.

## Solidity coverage

**Unblocked by ADR-0020.** The 17-argument wager constructor caused the stack-too-deep error that blocked `forge coverage` from ADR-0013 on. It now takes a struct.

```bash
forge coverage --ir-minimum --report summary \
  --no-match-test 'C1_coldResolve|test_C2_freeform|test_C6_' --no-match-path 'test/ParamutuelV3Invariant.t.sol'
```

The excluded tests pin gas bounds, or take very long instrumented. They add no line coverage.

| File | Lines | Statements | Functions |
|---|---|---|---|
| `src/ParamutuelFactoryV3.sol` | 98.90% (90/91) | 99.22% (128/129) | 100% |
| `src/ParamutuelWagerV3.sol` | 98.52% (266/270) | 98.55% (341/346) | 100% |
| `src/utils/BitMath.sol` | 100% (7/7) | 100% (10/10) | 100% |
| `src/utils/FullMath.sol` | 64% (16/25) | 68.97% (20/29) | 100% |
| `src/utils/ReentrancyGuard.sol` | 100% (4/4) | 100% (3/3) | 100% |

**Every remaining gap is an instrumentation artifact, not untested code:**

- `--ir-minimum` loses source mappings. It reports `_chargeFees();` as never run at all four call sites, although `fees-skip-charge-on-retract` and `fee-remainder-to-last` in `script/mutation-check.py` are killed by failing tests.
- Inline assembly has no line mapping, which accounts for all of `FullMath`'s gaps. `test_mulDiv_fullPrecision_fuzz` and the `C4-*` mutations exercise that path.
- The branch column (78% on both contracts) counts the failure side of every `require` as never taken. `script/check-revert-coverage.py` shows each is asserted by a `vm.expectRevert`, and `test/ParamutuelV3Hardening.t.sol` adds per-site guards.

The stronger evidence is mutation testing: `python3 script/mutation-check.py` kills 66 of 66 mutations, with the suite passing on the unmodified code first. It takes about 45 minutes, so it runs on the extended path.

## Python — current (ADR-0020, 2026-11-07)

Unit suites only. **99%** of 2,967 statements, up from 78% when ADR-0020 first measured it, and the end-to-end suites run on top of this.

```bash
for d in mcp_server/tests service/indexer/tests service/proposition/tests service/explorer/tests \
         service/resolution/tests service/control_panel/tests agents/paramutuel_bettor/tests; do
  PYTHONPATH=. python3 -m coverage run --append --source=mcp_server,service,agents \
    -m unittest discover -s "$d" -p "test_*.py"
done
python3 -m coverage report -m --omit='*/tests/*,*/__init__.py'
```

**The 16 statements not covered, and why that is accepted (AGENTS.md #2):**

| Statements | Where | Rationale |
|---|---|---|
| 10 | `if __name__ == "__main__": main()` in each service | One-line entry guards. Each `main` is tested directly, and `test_browser_e2e.py` runs `live_api` as a real process. |
| 5 | Script-mode error block in `agents/paramutuel_bettor/__main__.py` | Exercised by `test_script_mode_reports_errors_as_json_with_a_failing_exit_code`, through a subprocess that coverage does not follow. |
| 1 | The `unknown command` branch in the same file | `argparse` with `required=True` rejects these first. Kept so that adding a subcommand without a handler fails loudly. |

## JavaScript

`node --test --experimental-test-coverage` (from `dapp/`) puts `logic.js` at 99.5% of lines and `bet-logic.js` at 98.9%. Those files hold the pure decisions, and their only gaps are the browser branch of the UMD wrapper, which the browser test runs. The wiring in `dapp/app.js`, `site/bet-page.js`, `site/propose-wager.js` and `service/explorer/static/app.js` needs a page around it, so it is not measured by line. `test/integration/test_browser_e2e.py` covers it by behaviour instead: each person-facing flow runs in real Chrome, and the result is checked on chain. That test found the most serious defect of ADR-0020, which no unit test could have.

**Accepted gaps:** the network toggle's mainnet path and the operator hub's outbound links are only load-tested, because `baseMainnet` has no factory yet. Rarely used dApp form modes (absolute dates, no-max windows) are covered by unit tests of `computeWindowArgs` and not by a browser run.

## Refresh cadence

- After every commit that adds or removes a non-test Python module.
- After any commit on `master` that changes a sub-50% file (so the rationale stays accurate).
- Before mainnet readiness gate (re-baseline + coverage delta vs prior baseline as a release artifact).
