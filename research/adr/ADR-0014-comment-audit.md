# ADR-0014: Comment audit pass — codebase-wide rationale comments

Date: 2026-05-06
Status: **Proposed** — Implemented across multiple sub-agent branches that converge on `adr-0014-comment-audit` then `master`.
Builds on: [`AGENTS.md`](../../AGENTS.md) project-generic practice **#3** (thorough comments), **#6** (parallel sub-agents), **#8** (no unrelated changes), ADR-0012 (template), ADR-0013 (test stratification).

## Context

`AGENTS.md` practice #3 mandates that the codebase carry comments "sufficient that the codebase might be transferred to another developer who, though competent, is entirely unfamiliar with the software, its rationale, and its history." The current state of the tree is uneven: `src/ParamutuelWagerV3.sol` and `src/ParamutuelFactoryV3.sol` carry NatSpec on most external functions and state variables, but module-level rationale, lifecycle invariants, and "why this layout" notes are sparse; the Python services are similarly mixed (some files have docstrings, others have none); `dapp/logic.js` is dense pure-helper code with minimal explanation; `agents/paramutuel_bettor/*.py` is reasonably well-named but under-explained on the *why*.

Practice #6 mandates that when multiple independent tasks can be pursued concurrently on separate branches with no cross-branch dependency, sub-agents should be proposed (with the most powerful model and highest reasoning available). A comment-audit pass is exactly this shape: every module is independent of every other, no logic changes, no test changes, no cross-cutting decisions.

## Decision

1. **Audit scope is comments only.** No logic changes, no refactors, no test changes, no rename, no structural moves. The fast suite (`script/test-fast.sh`) must exit 0 before and after each module's audit; a comment-only change cannot break it.

2. **Comment standard per file.** Every non-test source file in scope acquires (where missing):

   - **Module-level header** explaining the module's role, the rationale for its existence, and how it fits with its neighbours. For Solidity, this is a NatSpec block above `contract`/`library`/`interface`. For Python, a module docstring. For JS, a leading `/** */` block.
   - **Function-level rationale** above non-trivial functions explaining *why* the function exists and any non-obvious invariants, gas-shape rationale, or "this is the surface contract" notes. For trivially named getters / one-liners with self-evident behaviour, no comment is required.
   - **Inline rationale** only where a reader would otherwise be confused: workarounds for known bugs, intentional ordering constraints (e.g. CEI patterns), magic numbers tied to off-chain conventions, "this branch exists because contract X behaves Y", and similar.

3. **What to NOT write.** Restating identifier names ("// increment counter" above `counter += 1`), narration of "the current task", references to specific PRs or callers (those go in the commit message and rot), boilerplate license headers (already present and correct), or speculative "TODO future" comments without an associated `docs/TASKS.md` or follow-up ADR.

4. **Module groups (parallel sub-agent assignment).**

   - **Group A — Solidity contracts.** `src/ParamutuelFactoryV3.sol`, `src/ParamutuelWagerV3.sol`, `src/utils/*.sol`, `src/interfaces/*.sol`. Highest risk surface; rationale on lifecycle invariants, CEI ordering, mode dispatch, fee accounting, immutable storage layout.
   - **Group B — Indexer + proposition services.** `service/indexer/` (excluding tests), `service/proposition/` (excluding tests). Rationale on event ingestion idempotency, reorg handling, proposition synthesis pipeline.
   - **Group C — Resolution / explorer / control-panel services + MCP server.** `service/resolution/`, `service/explorer/`, `service/control_panel/`, `mcp_server/`. Rationale on operator-facing flows, security gating (`--allow-execute`), MCP tool encoders.
   - **Group D — Bet-scout agent + dApp.** `agents/paramutuel_bettor/`, `dapp/logic.js`, `dapp/app.js`. Rationale on stateless subagent contract, JSON I/O shape, EIP-1193 patterns, calldata encoders.

   Groups have **no file overlap** so sub-agents can run in parallel without merge conflicts. Per practice #6 the sub-agents should default to the most powerful model with high reasoning effort.

5. **TDD posture.** Same exception as ADR-0011/0012: comment-only changes have no behaviour to red/green. The discipline check is the fast suite — `script/test-fast.sh` must exit 0 after each group's branch lands. This is enforced at merge time (per practice #7's "passing, regression-free test suite evaluation").

6. **Cross-references.**

   - `docs/ADR-0014-IMPLEMENTATION.md` carries the per-group merge log and any deferred items.
   - `research/adr/README.md` gains a one-line entry for ADR-0014.
   - `LOG.md` gains an entry per group merged, plus a closing entry when all four groups are integrated.

## Decision points

- **No comment density target (lines-of-comment / lines-of-code).** Density targets reward filler. The standard is "a fresh competent reader can transfer-in" — judged by the auditor's reading.
- **NatSpec for Solidity vs free-form comments.** NatSpec where it applies (`@notice`, `@param`, `@return`, `@dev`); free-form Solidity comments for module-level rationale that doesn't fit the tag schema.
- **Docstrings vs `# ` comments in Python.** Docstrings for module / class / function. `# ` comments only for inline rationale at the line level. PEP 257 conventions.
- **Sub-agent commits per group, not per file.** Each group is one logical unit of work; the agent commits once per group with a descriptive message.

## Success criteria

- After ADR-0014 lands, every non-test source file in the four groups has a module-level header explaining its role and rationale (module docstring / NatSpec / leading JSDoc).
- Non-trivial functions have function-level rationale where the *why* is non-obvious to a fresh reader.
- `script/test-fast.sh` exits 0 on `master` HEAD after each group merges.
- A new contributor reading any single source file can answer (a) what the file's role is, (b) which neighbours it talks to, and (c) which non-obvious invariants it relies on, without spelunking through the rest of the tree.

## Failure criteria

- Any group's commit changes logic, test, or signatures (any non-comment change). Mitigation: each sub-agent is instructed explicitly that its diff must be comment-only; the merge step inspects `git diff --stat` and rejects logic-bearing diffs.
- Comments are pedantic / what-comments rather than rationale. Mitigation: explicit "DO NOT" list in this ADR §3; sub-agent prompt repeats it; reviewer (the merging engineer) rejects what-comments at merge.
- The fast suite breaks on any group's branch. Mitigation: practice #7 — passing-suite is the merge gate.
- Comments drift from code as future commits land. Mitigation: standard maintenance burden; future ADRs that touch a file are expected to update its rationale comments.

## Rejected alternatives

- **Audit serially by one engineer.** Rejected — practice #6 prefers parallel sub-agents when the work is decomposable, and a codebase-wide audit is the canonical case.
- **Single sub-agent for the whole tree.** Rejected — exceeds bounded-context comfort and recovers no parallel speedup.
- **Audit only the highest-risk module (`src/`).** Rejected — partial audit defeats the "any single source file is transfer-ready" success criterion.

## After Action Report

**AAR date:** Pending until all four groups merge to `master`.
**AAR status:** Pending

**Outcome vs success criteria:** to be populated as each group merges; final summary after Group D.

**Outcome vs failure criteria:** to be populated.

**Lessons:** to be populated. Likely candidates: whether per-module comment density correlated with file age (older files have less rationale captured — confirms or refutes the "add comments at write-time" intuition), and whether parallel sub-agent merges produced surprises (they should not, given disjoint file scopes).

**Follow-ups:** to be populated.

**Revision schedule:** at next code-touching ADR (likely ADR-0015) — confirm the comments are being maintained, not just landed.
