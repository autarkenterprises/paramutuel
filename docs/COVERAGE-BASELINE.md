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

# Solidity / Foundry — see "Solidity coverage" below for current obstacle.
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
| `service/resolution/service.py` | 27% | Cloud Run service entrypoint + decision dispatch. Pure decision logic is in `logic.py` (76% covered). The uncovered paths are the HTTP server lifecycle and `--allow-execute` gating; both are exercised by manual operator runs. |
| `service/proposition/ingest.py` | 40% | Periodic-ingest scheduling logic; partial coverage today. **Follow-up:** the bulk of the uncovered code is timing / async glue that warrants targeted unit tests; tracked in `docs/TASKS.md`. |
| `service/proposition/synthesize.py` | 50% | LLM-prompt synthesis paths; some branches require live model calls and are tested manually. |

### 50–80%-covered modules (acceptable; unit tests cover happy paths)

`service/indexer/indexer.py` 55%, `service/proposition/json_sources.py` 56%, `service/indexer/sweeper.py` 62%, `agents/paramutuel_bettor/planner.py` 58%, `service/proposition/dispatch.py` 59%, `service/control_panel/commands.py` 80%, `service/proposition/rss.py` 81%, `agents/paramutuel_bettor/policy.py` 89%, `service/explorer/logic.py` 89%.

The 50-80% band covers the production-critical pure-logic modules. Each has working tests for happy paths and the most likely error branches; the missed lines are typically optional-feature branches (e.g. `synthesize.py` LLM prompts) or rare-error paths.

## Solidity coverage

**Status: blocked.** `forge coverage` (and `forge coverage --ir-minimum`) currently fails to compile `src/ParamutuelWagerV3.sol` with **stack-too-deep** errors when the optimizer / via-IR are disabled (which `forge coverage` does to keep source mappings accurate). This is a known Foundry limitation against complex contracts.

**Status of the contract logic itself:** all 65 Foundry tests pass under the production compile (`forge test`). Functional coverage is high — `test/ParamutuelV3Enumerated.t.sol` alone has 26 tests covering all five payoff policies plus seed / lifecycle / fee paths, with two fuzz tests. Worked-example tests pin the documentation (`docs/PAYOUT-CALCULATION.md`) to specific named regression tests per `LESSONS.md` L-003.

**Path forward** (follow-up, not blocking ADR-0013):

1. Split `ParamutuelWagerV3` constructor into a separate factory-callable initializer plus a smaller bytecode constructor, reducing local-variable pressure.
2. Or move pure helpers into a library so the wager itself fits coverage instrumentation.
3. Or use a separate coverage tool (e.g. `solidity-coverage` for Hardhat side) once a Hardhat side exists.

**Recipe (will work once stack-too-deep is resolved):**

```bash
forge coverage --report summary
forge coverage --report lcov   # for tooling consumption
```

## Refresh cadence

- After every commit that adds or removes a non-test Python module.
- After any commit on `master` that changes a sub-50% file (so the rationale stays accurate).
- Before mainnet readiness gate (re-baseline + coverage delta vs prior baseline as a release artifact).
