# LESSONS

Durable lessons learned during Paramutuel development. Each lesson is a transferable rule with evidence in the tree, not a regret. If a lesson stops applying, mark it **Retired** with the date and reason rather than deleting it.

See `AGENTS.md` practice #11 for the contract this file satisfies.

---

## L-001: Unify parallel protocol surfaces before they harden into separate ABI families

**Why:** ADR-0008 (V2 bitmask tickets) and ADR-0009 (freeform UTF-8 answers) shipped as standalone factories alongside V1, on the rationale that risk was lower when each surface evolved independently. Within weeks the cost shifted from contract risk to *fragmentation* — separate ABIs in the dApp, separate indexer branches, separate MCP encoders, separate bet-scout decoders, separate operator runbooks, separate worked examples in `PAYOUT-CALCULATION.md`. ADR-0010 unified them under `ParamutuelFactoryV3` + `ParamutuelWagerV3` and the V3-only sweep deleted three contract families from the tree (`docs/ADR-0010-IMPLEMENTATION.md`).

**How to apply:** When a new protocol concept appears headed for a *third* parallel surface, treat that as a strong signal to unify the existing two first — preferably under one immutable mode-discriminated contract — before adding the third. The unification ADR's diff is a one-time cost; the per-surface drift in tooling is recurring and grows superlinearly.

---

## L-002: Delete superseded code from the tree once its replacement is canonical

**Why:** ADR-0010's V3-only sweep removed `ParamutuelFactory`, `ParamutuelFactoryV2`, `ParamutuelFactoryFreeform`, their wagers, and the `WagerV2Masks` library entirely. This is permitted by AGENTS.md practice #8 (revert-or-remove rather than stub) and made the tree dramatically easier to reason about. On-chain immutability of legacy contracts is preserved by Ethereum itself; legacy tests are preserved by `git log`. There is no value in keeping superseded source files in `master` once nothing in the live tree depends on them.

**How to apply:** When an ADR's success criteria are met and tooling is fully migrated, remove the old code in the same merge as the migration sweep — do not leave a "deprecated" dead branch in the source tree. The git history is the historical record.

---

## L-003: Pin worked examples in human-readable specs to named regression tests

**Why:** `docs/PAYOUT-CALCULATION.md` worked examples (ANY_OF five-outcomes, EXACT_SET three-outcomes, and the 2026-05-06 expansion to SINGLE_WINNER, AT_LEAST_K, WEIGHTED_OVERLAP, freeform) each cite a Foundry test by name (e.g. `testAnyOf_documentationWorkedExample_fiveOutcomes`). When the contract math drifts, the test fails *and* a reader of the doc can run the test to confirm the figures. Without that pin, doc and code drift silently.

**How to apply:** Every time a worked example or numerical claim lands in a spec under `docs/`, name the regression test that proves it. If the test does not exist yet, the spec change is incomplete — the test must follow within the same logical unit of work (per AGENTS.md #1, #2).

---

## L-004: Hosted-service vendor lock-in shows up at the free-tier boundary

**Why:** The indexer was first deployed to Render, then moved to Cloud Run within roughly a day (`chore: drop Render indexer; document Cloud Run as canonical host`, 2026-03-31). The Render free tier's chunk-size, RPC, and start-block constraints made the deployment fragile under realistic Base-Sepolia load. Cloud Run with `INDEXER_CHUNK_SIZE=120`, baked-in RPC and from-block in the Dockerfile, and `/health` diagnostics replaced it cleanly.

**How to apply:** When evaluating a managed-service host for a stateful indexer-shaped workload, build the workload against the *real* network's `eth_getLogs` ranges and HTTP-400 bisect behavior before committing to the host's free tier. If a host requires too many free-tier-specific knobs, treat that as evidence to move up a tier or change hosts.

---

## L-005: Documentation layers must be enforced by structure, not goodwill

**Why:** Before ADR-0011, `docs/TASKS.md` was carrying chronological history (the 2026-04 "historical checkboxes left intact as a record of shipped work" annotation is the symptom). `README.md` was carrying setup runbook material. Without explicit `LOG.md` / `LESSONS.md` / `MEMORY.md` files, retrospective and durable material accreted into whichever doc was already open.

**How to apply:** Every project of nontrivial duration needs the four-layer split (chronological / durable / working-context / navigational) named explicitly *before* material starts to accrete. AGENTS.md practice #11 codifies this; ADR-0011 is the implementation. New material's home is decided by **purpose**, not by which file is already open.
