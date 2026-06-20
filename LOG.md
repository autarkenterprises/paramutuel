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

## 2026-05-07 — ADR-0014 sub-agents land + gap-fill closes the audit

Four Opus-class sub-agents launched in isolated worktrees executed Groups A–D in parallel. All four made on-target diffs but each was cut off by an external usage cap before reaching its commit step; the diffs were committed manually from each worktree, then merged into `master` in order (A → B → C → D), running `script/test-fast.sh` after each merge. All four merges passed.

Two findings worth surfacing:

1. **One latent regression** in Group B's diff: the agent replaced the body of `service/indexer/indexer.py:_decode_abi_string` with only a docstring, deleting twelve lines of ABI-decoding logic. Caught at merge review (the fast suite missed it because only the live testnet enrichment path exercises the helper). Restored before commit. New durable lesson recorded as `LESSONS.md` L-006: treat "comment-only" sub-agent diffs as suspect, verify by tooling — a structural check that strips comments and diffs the remainder is straightforward to add and would have caught this.
2. **Bounded scope by module list, not per-file deadline** meant the late files in each group's list were never reached. Group C only completed resolution before the cap; Group D only completed the first three of eight bet-scout files; neither reached `dapp/{logic,app}.js`. A gap-fill commit on `master` covers the missing files in: `service/proposition/{dispatch,ingest,json_sources,rss,synthesize,server}.py`; all of `service/explorer/`; all of `service/control_panel/`; `mcp_server/__init__.py`; `agents/paramutuel_bettor/{config,indexer_client,odds,planner,policy}.py`; `dapp/{logic,app}.js`. `mcp_server/{__main__,server}.py` already carried complete docstrings and were left untouched per AGENTS.md #8.

Phase 4 closed. ADR-0014 AAR will be filled in shortly with the per-group results and the L-006 lesson reference.

## 2026-05-07 — practices-review cadence established (AGENTS.md #12)

`AGENTS.md` practice #12 ("review these practices regularly, to keep them in context") is operationalised as a calendar cadence: a one-line `## YYYY-MM-DD — practices review` entry appended to `LOG.md` on the first business day of each month. The entry records which practices were re-read (default: all 15), any observed drift between charter and live tree, and any updates to the charter itself.

The cadence is anchored at this entry. **Next scheduled review: 2026-06-01.** Skipping a month is itself a logged event — silence is the failure mode the cadence exists to prevent.

This closes Phase 5 of the bring-the-codebase-up-to-AGENTS.md plan. All five phases shipped: Phase 0 (commit pending tree), Phase 1 (ADR-0011 documentation layer scaffolding), Phase 2 (ADR-0012 ADR/AAR template + retroactive AARs), Phase 3 (ADR-0013 test stratification + coverage baseline), Phase 4 (ADR-0014 codebase-wide comment audit), Phase 5 (this entry). Plus one L-003 follow-through commit (worked-example regression tests). New durable lessons since the bring-up began: L-006 (verify "comment-only" sub-agent diffs by tooling) and L-007 (calendar-driven practices review).

## 2026-05-07 — testnet-as-production recalibration triggered by Resonance Exchange ARG framing

User flagged that the Resonance Exchange (formerly Microwonk ARG, `docs/MICROWONK-ARG.md`) is a **live testnet launch indistinguishable from production modulo mainnet**, not a closed rehearsal. Several AARs landed in earlier phases under-weighted this and treated Base Sepolia as a downgraded posture vs mainnet for safety / observability / coverage purposes. Revisions appended (per ADR-0012's `Revisited YYYY-MM-DD` discipline, append-only, no rewrite):

- **ADR-0002 AAR (governance + Safe):** Safe-controlled treasury required on **both** Base Sepolia and Base Mainnet, not just mainnet. Tracked under ADR-0015.
- **ADR-0003 AAR (testnet certification):** dual-rehearsal artifact reframed as live ARG post-mortem in `docs/log/`, dated entries appended throughout the campaign — the ARG is public-facing, not a closed rehearsal.
- **ADR-0007 AAR (assisted UX):** deferral is more costly than the original AAR implied — human onlookers without ETH drop out at `site/resonance-bet.html`. Architectural shape unchanged; *implementation* lifted into ADR-0016 with a focus on the funds-management question (how the relayer sponsors gas without exhausting its float when settling arbitrary ERC-20 collateral).
- **`docs/COVERAGE-BASELINE.md`:** the 0%-covered server / dispatch entrypoints in `service/{resolution,proposition}` run **live** during the ARG; rationale updated, follow-up is "lift coverage with deterministic shims," not "exercised by manual ops."

`MEMORY.md` updated with the testnet-as-production framing and the active design ADR list (ADR-0015 / ADR-0016 / ADR-0017).

## 2026-05-07 — ADR-0014 site follow-up: Resonance pages commented

Closing the gap the original ADR-0014 scope under-weighted: `site/resonance-*.html` is the live ARG launch surface (the most user-visible code in the tree) and was treated as marketing chrome rather than production code. Each of the five Resonance pages (`resonance.html`, `resonance-bet.html`, `resonance-place.html`, `resonance-propose.html`, `resonance-explorer.html`) acquires a leading HTML comment block explaining its role, wallet binding, and iframe-skin contract with the explorer / dApp. `site/propose-templates.js` and `site/network-context.js` already carried sufficient JSDoc.

The `resonance-bet.html` comment also flags the human-onlooker-without-ETH UX gap as a known issue tracked under ADR-0007 / ADR-0016, so a future reader can find the planned fix from the file.

## 2026-05-07 — ADR-0015 proposed: Safe-controlled treasuries on both networks

Design ADR landing the testnet-as-production implication of ADR-0002's revisited AAR: Safe multisig treasuries on **both** Base Sepolia and Base Mainnet, with no EOA in the production-exposure path. New V3 factory deployed per network with the Safe as `treasury_`; the existing Base Sepolia factory remains immutable on-chain but is deprecated for new ARG dispatch after cutover. Operational role wallets (proposer / resolver / individual microwonks) remain EOAs by design — Safe is for accumulated protocol fees, not bot-frequency signing.

Cutover runbook in `docs/ADR-0015-IMPLEMENTATION.md`. Implementation gated on operator input: signer set + threshold per network, whether Sepolia and Mainnet share signers, retention or retirement of the legacy factory address in `config/deployments.json`, public disclosure of Safe addresses on the Resonance landing.

## 2026-05-07 — ADR-0016 proposed: assisted-UX gateway with funds management

Design ADR addressing ADR-0007's revisited AAR. Specifies two runtime modes: **sponsored** (ARG / testnet, project absorbs gas costs from a Safe-budgeted float, daily and per-address caps) and **reimbursed** (mainnet retail, bettor pays a small surcharge in collateral, scheduled DEX swaps replenish the ETH float). The "how not to run out of funds when facilitating arbitrary ERC-20" question gets an explicit answer: **Tier-1 collateral is assisted; Tier-2 is explicitly unassisted** — the gateway refuses sponsorship for collateral with no deep DEX liquidity rather than holding it indefinitely.

Service shape: `service/atg/` as a peer to the existing services (indexer / proposition / resolution / control_panel / explorer). Same Cloud Run / Python pattern.

Implementation runbook in `docs/ADR-0016-IMPLEMENTATION.md`, ordered TDD: intent encoding → tier policy → caps → oracle → relay → replenishment → server → site integration. Gated on operator input on caps, tier list per network, markup, DEX choice, and AA-vs-traditional-relayer.

## 2026-05-07 — ADR-0017 proposed: Paramutuel Service Provider concept

Design ADR pinning down the project's operating role. Until now, "service entity" was a load-bearing phrase in `research/go-to-market-strategy.md` without a single ADR specifying which services are *offered* (a creator can rely on them) vs *operator-only* (project-internal tooling). ADR-0017 establishes the catalog: indexer + JSON API and explorer are public; resolver address is a public **resolver-by-reference** product; MCP server and bet scout are public packages; assisted-tx gateway (ADR-0016) is public when live; proposition service and control panel are operator-only.

Hosting is uniform Cloud Run for hosted services per `docs/CLOUD-RUN-HOSTING.md`; Render is no longer used (per `LESSONS.md` L-004). PyPI for distributed packages. GitHub Pages for the static marketing site.

Discoverability primitive: a single JSON manifest at `agents/service-provider-manifest.json` (mirroring the existing `agents/subagent-manifest.json` posture), served at a stable raw URL on the project's GitHub. The manifest enumerates per-network factory address, indexer URL, explorer homepage, resolver address + policy URL, ATG URL when live, plus PyPI package names.

The resolver address being a *product* requires a separate doc: `docs/SERVICE-PROVIDER-RESOLVER-POLICY.md` (not yet written) — names policy scope, fee, rotation rules, dispute escalation. Without that doc, naming the resolver address is just trust; with it, the resolver address is a product with a stated contract.

Implementation runbook in `docs/ADR-0017-IMPLEMENTATION.md`. Gated on operator input on resolver fee, policy scope, manifest URL, rotation policy, SLA disclaimer.

This concludes the testnet-as-production recalibration round. Three design ADRs (0015 / 0016 / 0017) propose, with implementation gated on operator input. AAR revisions on 0002 / 0003 / 0007 / 0014 already landed; site Resonance comment audit closed; `MEMORY.md` carries the active design ADR list. All five branches preserved on origin per practice #5.

## 2026-06-19 — ADR-0018 proposed: collateral curation as an opt-in overlay

A codebase review (2026-06-19) re-examined the "any ERC-20" claim against the frozen-bytecode standard the Resonance Exchange ARG imposes (the testnet deploy *is* the mainnet bytecode; there is no post-mint patch path). Finding: the core guarantees non-custody and solvency for *standard* ERC-20 only — no-bool-return tokens (USDT-class) revert (**fail-safe**), while fee-on-transfer / rebasing tokens break pot solvency (**fail-unsafe**). The policy answer already exists and is accepted: ADR-0006 §4 ratified "collateral-agnostic core, curated happy paths," and its own AAR records the curation as "copy, not flow code."

ADR-0018 records the implementation under the project's standing **"neutral core, safety as opt-in overlay"** principle — the same pattern already used for resolution (the resolver is a swappable per-wager address, not baked into the core). Key decision: **no `src/` change.** An off-chain `config/collateral-allowlist.json` (network-keyed, mirroring `config/deployments.json`) is consumed by the dApp create/bet flows and the bet surfaces; the universal-fallback path is preserved behind a warned opt-in (permissionlessness intact); the core's boundary is pinned by two regression tests (no-bool revert; fee-on-transfer solvency-break); and the "any ERC-20" claim is narrowed to "any *standard* ERC-20." Implementation gated on operator input on the curated token set per network. Branch `adr-0018-collateral-curation-overlay`; implementation runbook (`docs/ADR-0018-IMPLEMENTATION.md`) to follow on acceptance.
