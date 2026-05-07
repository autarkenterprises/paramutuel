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
- Extended-suite tests (slow / multi-actor / live testnet) run in **`test/testnet/`**. Foundry fast suite is everything else under `test/`. Run extended in parallel during feature work; block on it before functionality-changing commits.
- Hosted indexer = **Cloud Run** (`docs/INDEXER-HOSTING.md`, `docs/CLOUD-RUN-HOSTING.md`). Render is no longer used.
- Worked examples in `docs/PAYOUT-CALCULATION.md` are pinned by name to regression tests in `test/ParamutuelV3Enumerated.t.sol` and `test/ParamutuelV3Freeform.t.sol`.
- Bet-scout subagent ships as PyPI **`paramutuel-bettor-agent`** (CLI `paramutuel-bettor`); MCP server ships as PyPI **`paramutuel-mcp`**. Subagent manifest at `agents/subagent-manifest.json`.
- Outstanding stale branch: `experiment/adr-0008-multi-winner-v2` (superseded by V3). Disposition pending ADR-0012 / ADR-0008 AAR.
- **Resonance Exchange ARG = live testnet launch on Base Sepolia, indistinguishable from production modulo mainnet** (`docs/MICROWONK-ARG.md`). Treasury, faucet, microwonk wallet pool, and scheduled Co-ordinator dispatch are real on-chain. Treat Base Sepolia treasury security, indexer uptime, and proposition / resolution dispatch as production exposure — not rehearsal.
- Outstanding design ADRs (active): **ADR-0015** (Safe-controlled treasuries on both nets), **ADR-0016** (assisted UX with funds management — supersedes ADR-0007's implementation), **ADR-0017** (Service Provider concept — hosting / offered services / discoverability for wager creators).
