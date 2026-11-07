# MEMORY

High-priority facts a contributor or assistant must know to operate correctly **today**. ≤ 30 lines, bullets only. If a fact stops being current, edit or remove the line — this file is not historical.

See `AGENTS.md` practice #11 for the contract this file satisfies. For history use `LOG.md`; for durable lessons `LESSONS.md`; for navigation `README.md`.

---

- Project-wide development practices charter is **`AGENTS.md`** (TDD, ADR/AAR discipline, branch + commit discipline, doc layers, extended suite, structured tools).
- Canonical protocol = **`ParamutuelFactoryV3` + `ParamutuelWagerV3`** with immutable `WagerMode` enum (`Enumerated` / `Freeform`). V1, V2, standalone Freeform contracts and the `WagerV2Masks` library are **deleted** from the tree (see ADR-0010-IMPLEMENTATION.md).
- Indexer / MCP / dApp / site / agents / testnet suites are **V3-only**. `protocol_version` is reported by the indexer.
- Branch discipline: a new branch per ADR; merges land **locally first** (commit → push branch → merge to local `master`, fast-forward where possible → push `master`). Do **not** open GitHub PRs to drive merges. **Preserve** feature branches (local and remote) after merge.
- Commit discipline: only intentionally modified files; push after every passing logical unit; never amend published commits; never `--no-verify` without explicit user approval.
- ADRs live in **`research/adr/ADR-NNNN-*.md`**. Implementation notes for the same ADR live in **`docs/ADR-NNNN-IMPLEMENTATION.md`**. Both are required for any non-trivial feature.
- Every custom error / `require` string in `src/` must be asserted by a `vm.expectRevert` in `test/` — enforced by `script/check-revert-coverage.py` in the fast suite. `forge coverage --ir-minimum` works since ADR-0020; `docs/COVERAGE-BASELINE.md` explains its false gaps. `python3 script/mutation-check.py` kills 66/66 (about 45 minutes).
- Closer roles: `address(0)` **disables** `bettingCloser` / `resolutionCloser` (only `resolver` defaults to proposer). Resolution service `POST /run-once` needs `RESOLUTION_SERVICE_TOKEN`; its decision file `outcomeIndex` is an index (sent as `1 << i`), or give `winningMask`. The control panel and `resolve(uint256)` take a mask (`winningMask`), never an index.
- `script/test-fast.sh` is the default path. `script/test-local-e2e.sh` runs everything against anvil with real `cast` and real Chrome, needs no secrets, and runs in CI. `test/testnet/` is the live extended suite and needs keys. Run extended in parallel during feature work; block on it before functionality-changing commits.
- Hosted indexer = **Cloud Run** (`docs/INDEXER-HOSTING.md`, `docs/CLOUD-RUN-HOSTING.md`). Render is no longer used. Last checked 2026-11-07 it returned 500/503; see `docs/TASKS.md`.
- Worked examples in `docs/PAYOUT-CALCULATION.md` are pinned by name to regression tests in `test/ParamutuelV3Enumerated.t.sol` and `test/ParamutuelV3Freeform.t.sol`.
- Neither **`paramutuel-mcp`** nor **`paramutuel-bettor-agent`** is on PyPI yet; both run from the repo (`docs/TASKS.md`). Subagent manifest at `agents/subagent-manifest.json`.
- Outstanding stale branch: `experiment/adr-0008-multi-winner-v2` (superseded by V3). Disposition pending ADR-0012 / ADR-0008 AAR.
- **Resonance Exchange ARG = live testnet launch on Base Sepolia, indistinguishable from production modulo mainnet** (`docs/MICROWONK-ARG.md`). Treasury, faucet, microwonk wallet pool, and scheduled Co-ordinator dispatch are real on-chain. Treat Base Sepolia treasury security, indexer uptime, and proposition / resolution dispatch as production exposure — not rehearsal.
- Outstanding design ADRs (active): **ADR-0015** (Safe-controlled treasuries on both nets), **ADR-0016** (assisted UX with funds management — supersedes ADR-0007's implementation), **ADR-0017** (Service Provider concept — names the role, lists offerings, pins discoverability to a JSON manifest at `agents/service-provider-manifest.json`).
- **Base caps a transaction at 16,777,216 gas (EIP-7825).** Forge tests run warm and understate this by millions: use the `cool` cheatcode or a real receipt (`docs/PARAMUTUEL-V3-GAS.md`). Worst-case `resolve` is 6.66M.
- `src/` on `master` is **ahead of the deployed factory** (ADR-0020). Its fixes do nothing until the operator redeploys: `docs/ADR-0020-IMPLEMENTATION.md`.
- **Never trust `cast` with user text.** It alters strings and exits 0 on a mined revert. Encode with `service/control_panel/abi.py`, send raw calldata, check the receipt with `run_cast_send`.
- **ethers v6 cannot pick between same-length overloads.** Call `placeBet` and `resolve` by full signature, as in `contract["resolve(string)"](x)`.
