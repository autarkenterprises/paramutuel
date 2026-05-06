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
