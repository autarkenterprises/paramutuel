# LOG

Chronological spine of Paramutuel development. Append-only. Newest entry at the bottom. Entries dated `YYYY-MM-DD`. Long-form notes live under [`docs/log/`](docs/log/) and are linked from here. `git log` remains the authoritative commit-grain record; this file captures *process* — exploration, dead ends, decisions, retrospectives — at the granularity of phases and weeks, not individual commits.

See `AGENTS.md` practice #11 for the contract this file satisfies.

---

## 2026-03-19 — (backfill) project genesis

Initial Foundry project. `ParamutuelFactory` + `ParamutuelWager` MVP contracts and comprehensive Foundry tests landed in a single seed commit. Deployment script and runbook followed the same day. dApp scaffolded as a static page with syntax-checkable JS.

## 2026-03-20 — (backfill) research and execution roadmap

First market-viability memo, competitive landscape, configurable-resolver thesis, and execution-roadmap checkpoints (initialization, chain/fee viability, governance/treasury Safe, indexer spec, odds-calculator spec). Initial ADR-0001 / ADR-0002 / ADR-0003 / ADR-0004 drafts. Delegated-resolver wagers and dApp odds preview shipped end of week.

## 2026-03-25 — (backfill) lifecycle controls and service ops stack

Lifecycle controls hardened (close-betting, close-resolution-window, time-only windows). First service-layer scaffolding (indexer, control panel, proposition, resolution as separate Python services).

## 2026-03-29 — (backfill) Base Sepolia, testnet suites, GTM

Base testnet launch flow reconciled. Live Base Sepolia integration suite added. Multi-market stress suite plus wallet-pool tooling. `docs/TASKS.md` introduced as the cross-cutting backlog. Research expanded with GTM strategy, outreach targets, investor pitch outline, and deck.

## 2026-03-30 — (backfill) protocol website + hosted indexer

Protocol website on GitHub Pages, self-contained ABI loading, seeded creation, batched multi-outcome bets, MCP server for LLM agents, text-searchable markets, market ordering and pagination in the explorer. Render → Cloud Run hosting transition for the indexer (Render dropped as too constrained on the free tier).

## 2026-03-31 — (backfill) terminology refactor + ADR-0008

Project-wide `market` → `wager` terminology refactor across user-facing surfaces, then the core protocol and services (with `!` breaking-change marker on the protocol commit). ADR-0008 multi-winner settlement track started; 100% fee cap landed to enable charity / full-beneficiary wagers.

## 2026-04-01 — (backfill) delegated resolution service + site UX

Delegated resolution service deployed to Cloud Run. Live wager ticker on the homepage. Dedicated bet page with indexer loading UX and explorer auto-refresh. MCP unified bet/bets quote tools.

## 2026-04-03 — (backfill) bet scout, AGENTS.md v1, ADR-0008 V2 contracts

`paramutuel_bettor` scout agent introduced. First version of `AGENTS.md` (agent-surface integration index) published alongside subagent manifest for distribution and discovery. Bet scout distributed via PyPI and GHCR with CI fleet deploy. Operator hub + production-readiness docs. ADR-0008 implementation: `ParamutuelFactoryV2` + `ParamutuelWagerV2` (bitmask tickets + payoff policies) on the experiment branch.

## 2026-04-05 — (backfill) retail-first website pivot

Homepage wager search, retail-first nav, About page, infra docs hidden from public UI. ERC-20 symbol surfaced consistently across dApp, bet page, explorer.

## 2026-04-06 — (backfill) testnet/mainnet toggle

Site-level testnet/mainnet banner toggle with `network-context.js` centralizing presentation. Stub mainnet path. Homepage flow reorganized: propose / bet → feed → lifecycle.

## 2026-04-08 — (backfill) ADR-0008 V2 worked example + integration policy

ANY_OF worked example pinned by Foundry regression test (Alice/Bob/Carol stakes). ADR-0008 integration branch policy documented; `experiment/adr-0008-multi-winner-v2` continues to follow `master`.

## 2026-04-13 — (backfill) ADR-0009 freeform text wagers

ADR-0009 implementation: `ParamutuelFactoryFreeform` + `ParamutuelWagerFreeform` shipped as a *third* parallel surface alongside V1 and V2. UTF-8 answer with `keccak256(0x03 || answer)` ticket identity, exact byte match, single-winner parimutuel.

## 2026-04-14 — (backfill) ADR-0010 unification proposal

ADR-0010 proposed unifying the three surfaces (V1 enumerated, V2 bitmask, Freeform) under a single `ParamutuelFactoryV3` + `ParamutuelWagerV3` with an immutable `WagerMode` discriminator. Motivation: parallel surfaces fragment ABIs, docs, indexer, MCP, bet scout, and operator mental models.

## 2026-04 → 2026-05 — (backfill) ADR-0010 implementation and V3-only sweep

`ParamutuelFactoryV3` + `ParamutuelWagerV3` implemented. Tree-wide propagation: dApp, services, agents, site rewritten V3-only. Legacy V1 / V2 / Freeform contracts and the `WagerV2Masks` library **deleted** from the tree (immutable on-chain history preserved off-tree). Testnet live + stress suites rewritten V3-only. Site received the Resonance explorer skin; API shell and protocol metadata hidden from the public-facing UI.

## 2026-05-06 — AGENTS.md becomes the practices charter

`AGENTS.md` rewritten from agent-surface integration index to a project-wide mandatory development practices charter (TDD, coverage, comments, ADR + AAR discipline, branch and commit discipline, documentation layers, extended-suite cadence, structured tools). Agent-surface content remains authoritative in `docs/MACHINE.md`, `docs/AGENT-LOOP.md`, `docs/BET-AGENT.md`, `agents/subagent-manifest.json`.

`docs/PAYOUT-CALCULATION.md` expanded with worked examples for `SINGLE_WINNER`, `AT_LEAST_K`, `WEIGHTED_OVERLAP`, and freeform mode. Each example pins to a named regression test in the V3 suite. Some referenced regression test stubs are not yet landed; subsequent ADR work syncs the test file to match.

## 2026-05-06 — ADR-0011: documentation layer scaffolding

This file (and `LESSONS.md`, `MEMORY.md`, `docs/log/`) created on branch `adr-0011-doc-layers` to satisfy `AGENTS.md` practice #11. See `research/adr/ADR-0011-documentation-layer-scaffolding.md` and `docs/ADR-0011-IMPLEMENTATION.md` for the rationale and conventions. The lengthy backfill above is the one-time retrospective spine; from this point forward entries are written contemporaneously with the events they describe.

## 2026-05-06 — ADR-0012: ADR template + retroactive AAR sweep

`AGENTS.md` practice #4 mandates ADRs document success / failure criteria and receive AARs once complete. ADR-0012 adopts a uniform ADR section structure (template at `research/adr/ADR-TEMPLATE.md`) and **appends** After Action Reports to ADR-0001 through ADR-0010, without rewriting any pre-existing ADR body (per practice #8).

Findings worth surfacing from the AAR sweep:

- **ADR-0002 (governance + Safe):** treasury is currently an EOA on Base Sepolia; no on-chain fee setters in `ParamutuelFactoryV3`. Acceptable for testnet, must resolve before mainnet.
- **ADR-0003 (testnet certification):** no formal "rehearsal-1 / rehearsal-2 / post-mortem" artifact exists despite multiple iterative testnet runs. Capture as a doc gap.
- **ADR-0007 (assisted transaction gateway):** marked Accepted in 2026-03-30; **not implemented**. Decide deferral vs rejection at next product roadmap review.
- **ADR-0008 experiment branch:** `experiment/adr-0008-multi-winner-v2` is fully merged into `master` (merge-base = branch tip `bbef4367`). Per practice #5 the branch is **preserved** locally and on `origin`; **no deletion**.
- **ADR-0009 / ADR-0010 supersession:** V2 and standalone Freeform contracts are deleted from the tree; immutable on-chain bytecode preserved by Ethereum, historical tooling preserved by `git log`.

No new entries added to `LESSONS.md` from this sweep — the durable lessons (L-001, L-002, L-003, L-004, L-005) all predate the AAR write-up.

## 2026-05-06 — ADR-0013: test stratification + coverage baseline

`script/test-fast.sh` and `script/test-extended.sh` introduced as the top-level cadence runners per `AGENTS.md` #13/#14. Fast suite is forge + the four Python unit-test groups + dApp Node tests; aborts on first failure; runs in ≈ 12 seconds on the development machine. Extended suite wraps the existing `script/testnet/run_live_suite.sh` and `script/testnet/run_stress_suite.sh`.

Coverage baseline captured at `docs/COVERAGE-BASELINE.md`:

- **Python: 3463 statements, 1355 missed, 61% covered.** Every 0%-covered and sub-50%-covered file has documented rationale (entrypoints / servers / CLIs exercised by the extended suite or manual ops).
- **Solidity: blocked.** `forge coverage --ir-minimum` fails with stack-too-deep on `src/ParamutuelWagerV3.sol`. Functional 65/65 pass under the production compile. Path forward (constructor refactor / library extraction / alternative tool) tracked in `docs/COVERAGE-BASELINE.md` and ADR-0013 follow-ups.

Known follow-up before ADR-0014: land the regression test stubs that `docs/PAYOUT-CALCULATION.md` worked examples reference (`testSingleWinner_documentationWorkedExample_threeOutcomes`, etc.). This is L-003 work and should ship as its own commit before any further ADR.

## 2026-05-06 — L-003 follow-through: pin worked examples to regression tests

Closing the gap left by the 2026-05-06 PAYOUT-CALCULATION.md expansion. Four new worked-example regression tests landed:

- `testSingleWinner_documentationWorkedExample_threeOutcomes` — Alice with split-stake (one losing, one winning ticket); single `claim()` aggregates and pays only the winning portion.
- `testAtLeastK_documentationWorkedExample_fourOutcomes_k2` — four outcomes, `W = {A,B,C}`, `k = 2`. Bob (2-bit ticket but only 1-bit overlap) loses; Dave (3-bit ticket including `D ∉ W` but 2-bit overlap with `W`) wins. Documents that `AT_LEAST_K` keys on overlap, not subset or ticket size.
- `testWeightedOverlap_documentationWorkedExample_fourOutcomes` — same `W`, equal stakes; payouts scale exactly with `popcount(T & W)`. Dave's zero-overlap ticket funds the pot and never claims.
- `testFreeform_documentationWorkedExample_rosebud` — `"rosebud"` vs `"Rosebud"` hash to distinct `answerId`s; case-mismatched bettor loses despite being semantically correct. Fee-free factory deployed locally to bypass the suite's default 1% fee.

Total fast-suite count: 65 → 69 forge tests (4 new). All previously-existing tests untouched. `script/test-fast.sh` exits 0.

L-003 commitment closed. ADR-0013 follow-up entry updated.

## 2026-05-06 — ADR-0014: codebase-wide comment audit (kicked off)

Per `AGENTS.md` practice #3 every non-test source file should carry comments sufficient for transfer to a competent stranger. The current tree's commenting is uneven (NatSpec on V3 contracts is good for external functions but light on module rationale; Python services are mixed; `dapp/app.js` is dense pure-helper code with minimal explanation). ADR-0014 codifies the audit standard and decomposes the work into four disjoint module groups so sub-agents can run in parallel per practice #6 without merge conflicts.

Groups: A (Solidity contracts), B (indexer + proposition), C (resolution / explorer / control_panel / mcp_server), D (bet scout agent + dApp). Each group's sub-agent receives the ADR's success/failure criteria as part of its bounded scope; comment-only diffs; `script/test-fast.sh` is the merge gate. Per-group merge log lives in `docs/ADR-0014-IMPLEMENTATION.md`.
