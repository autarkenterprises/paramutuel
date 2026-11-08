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

## L-006: Treat "comment-only" sub-agent diffs as suspect; verify by tooling

**Why:** During the ADR-0014 codebase-wide comment audit, a sub-agent (Group B, indexer + proposition) was instructed explicitly that its diff must be comment-only. The agent mostly complied — most of the 457 inserted lines were valid module / function rationale — but in one place it replaced the body of `service/indexer/indexer.py:_decode_abi_string` with only a docstring, silently deleting twelve lines of ABI-decoding logic. The fast suite did not catch it because that helper is only exercised by the live testnet enrichment path; the regression would have shipped to production indexer if not caught at merge review. Restored before commit; recorded in `docs/ADR-0014-IMPLEMENTATION.md` post-mortem.

**How to apply:** A "comment-only" claim on an LLM-authored diff is not self-validating. Before merging such a diff, run a simple structural check: drop all blank lines and lines whose first non-whitespace character is `#`, `//`, `/*`, ` *`, `"""`, or `'''`, then `diff` the remainder against the parent commit — that diff must be empty. A pre-merge hook or `script/`-side helper is the right home for this check; a follow-up ADR can land it. Until then, manual verification (`git diff` plus search for non-comment deletions) is the discipline.

## L-007: Re-read the practices charter on a calendar, not on demand

**Why:** AGENTS.md practice #12 mandates "review these practices regularly, to keep them in context." Without a fixed cadence the review never happens — practice charters drift out of working context within weeks of being adopted, especially as new ADRs add their own conventions. The 2026-05-06 adoption of AGENTS.md as the project-wide charter is the natural starting point for a cadence; the first scheduled review on 2026-06-06 establishes the rhythm.

**How to apply:** A `## YYYY-MM-DD — practices review` entry is appended to `LOG.md` on the first business day of each month. The entry records: which practices were re-read (default: all 15), any drift observed (a practice that has slipped vs the live tree), and any update to the charter itself. If a review uncovers no drift, the entry is one line saying so. Skipping a month is also recorded — silence is the failure mode this lesson exists to prevent.

## L-005: Documentation layers must be enforced by structure, not goodwill

**Why:** Before ADR-0011, `docs/TASKS.md` was carrying chronological history (the 2026-04 "historical checkboxes left intact as a record of shipped work" annotation is the symptom). `README.md` was carrying setup runbook material. Without explicit `LOG.md` / `LESSONS.md` / `MEMORY.md` files, retrospective and durable material accreted into whichever doc was already open.

**How to apply:** Every project of nontrivial duration needs the four-layer split (chronological / durable / working-context / navigational) named explicitly *before* material starts to accrete. AGENTS.md practice #11 codifies this; ADR-0011 is the implementation. New material's home is decided by **purpose**, not by which file is already open.

## L-008: An AAR "Met" claim is only as good as the test it names

**Why:** ADR-0005's backfilled AAR asserted "default-to-proposer behavior implemented and tested" for both closers. It was neither: `bc8e4a8` had deliberately changed `address(0)` to mean "role disabled" weeks earlier, and no test covered either behavior. The claim was written from the ADR text, not from the code, and survived until the ADR-0019 audit. Downstream readers (and agents) trusting the ADR would have mis-configured wagers.

**How to apply:** Every "Met" line in an AAR cites the test (or file:line) that proves it. If no such test exists, the line says "Unverified" and a test is added in the same unit of work. Extends L-003 from worked examples to AAR claims.

## L-009: When a migration deletes a superseded implementation, port its tests by behavior, not by file

**Why:** ADR-0010 correctly deleted the V1 / V2 contracts (L-002), and commit `b2a2f28` deleted `test/Paramutuel.t.sol` with them. The V2 suites were ported; the V1 suite was not — yet V1 was the only suite pinning the lifecycle / access-control / fee-cap / token-failure behavior that V3 inherited verbatim. For months 15 V3 custom errors and every string `require` had no test, invisible because `forge coverage` is blocked (ADR-0013). ADR-0019 restored 40 tests and proved them by mutation.

**How to apply:** Before deleting a test file during a migration, list the behaviors it pins (one line per test) and map each to a surviving test or a new port; commit the map in the migration's implementation notes. A cheap backstop that needs no coverage tooling: every custom error / `require` string in `src/` must appear in at least one `expectRevert` in `test/`.

## L-010: Assert at the outermost boundary you can reach

**Why:** ADR-0019's byte-exact test asserted on the argument handed to `cast`, and `cast` then stripped trailing spaces and quotes on the way to the chain. The test passed while an operator could resolve the wrong pool (ADR-0020 O0). A test that stops at your own boundary proves only that you called the next layer the way you meant to.

**How to apply:** For anything that crosses a process, a wire or a chain, assert on what arrives: decode the calldata, read the chain, read the page. When the last hop is a third-party tool, test that tool's behaviour too, as `test_mined_revert_is_reported_as_failure` does for `cast`'s exit code.

## L-011: Each deliverable needs a test of the thing that ships

**Why:** Unit tests were green while the hosted propose flow returned 404s (the deploy copied a hard-coded file list), while every fresh install of the MCP server failed (an unbounded dependency), and while no browser could resolve a wager (ethers rejected an overloaded call). Each was invisible to tests of the code alone (ADR-0020 D1, D9, W14).

**How to apply:** Test the artifact as delivered: the assembled site, the built wheel installed outside the repo, the page in a real browser. Run these in CI on a clean checkout, which also catches what a developer machine has cached.

## L-012: Measure gas the way the chain charges it, against the limits the chain has today

**Why:** Foundry runs a test in one warm transaction and understated a griefed `resolve` by about 4M gas. Base's per-transaction cap (EIP-7825, 2^24) arrived after the gas profile was written. Together they hid a market that could never be resolved (ADR-0020 C1).

**How to apply:** Bound worst cases with cold storage (the `cool` cheatcode) or a real receipt, and assert the bound in the fast suite against the current per-transaction cap. Re-check platform limits whenever the chain upgrades.

## L-013: A guard needs a reason it protects something

**Why:** The freeform answer cap was copied from enumerated mode, where `resolve` iterates the masks. Freeform `resolve` never iterates the answers, so the cap protected nothing, and it let anyone lock out the correct answer for about $1.30 (ADR-0020 C2).

**How to apply:** Write the cost a limit bounds next to the limit, and test that cost. If nothing in the code pays the cost, remove the limit instead of tuning it.

## L-014: An exit code is not an outcome

**Why:** `cast send` exits 0 for a mined transaction that reverted. Three services recorded such failures as successes, one of them marking a wager as created when it did not exist (ADR-0020 O1).

**How to apply:** Decide success from the result itself: the receipt's status, the response body, the state on chain. Treat a tool's exit code as "the tool ran".

## L-015: "Fixed" means fixed at every call site and in every client

**Why:** ADR-0019 fixed answer stripping in one service, but two other surfaces still stripped. It fixed staking after close in one function, and another function undid it (ADR-0020 O5, W4, W1).

**How to apply:** Before recording a fix, search for every path that does the same thing: each service, CLI, page and agent. Name the test for each path in the AAR, or say which ones remain.

## L-016: Find build artifacts by exact identity

**Why:** The end-to-end tests looked contracts up by name across `out/`. On one machine that found a stale artifact of a deleted test, and on CI the real mock. The stale one happened to have `decimals()`, so the local run passed and hid that the mock lacked it (ADR-0020 T2).

**How to apply:** Address artifacts by source path and contract name. When a test passes locally and fails on CI, suspect state that only one of them has.

## L-017: An expected value copied from the code's output pins the bug

**Why:** Two tests asserted exactly what the code returned, and so locked its defects in. One expected the answer id `0xaa` for a quote of "hello"; `0xaa` was the id of whatever row sat at the index, not of "hello". The other expected `total_winning_stake` to hold weighted units, which every reader displays as tokens. An outside review found both (ADR-0021 U1, U3).

**How to apply:** Derive each expected value from what the result means: compute the answer's id from the answer, or ask what the field's readers do with it. When a test needs a literal, say in a comment where the number comes from.
