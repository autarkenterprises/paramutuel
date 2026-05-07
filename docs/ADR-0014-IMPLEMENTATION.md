# ADR-0014 implementation notes (codebase-wide comment audit)

**Status:** In progress on branch `adr-0014-comment-audit`. Per-group sub-branches merge into the integration branch; the integration branch ff-merges to `master` once all four groups are integrated and `script/test-fast.sh` passes.
**ADR:** [`research/adr/ADR-0014-comment-audit.md`](../research/adr/ADR-0014-comment-audit.md)

## Group assignment

| Group | Sub-branch | Modules | LoC (non-test) |
|-------|------------|---------|----------------|
| A | `adr-0014-group-a-solidity` | `src/*.sol`, `src/utils/*.sol`, `src/interfaces/*.sol` | ≈ 972 |
| B | `adr-0014-group-b-indexer-proposition` | `service/indexer/` (excl. tests), `service/proposition/` (excl. tests) | ≈ 2382 |
| C | `adr-0014-group-c-services-mcp` | `service/resolution/`, `service/explorer/`, `service/control_panel/`, `mcp_server/` (all excl. tests) | ≈ 1986 |
| D | `adr-0014-group-d-agent-dapp` | `agents/paramutuel_bettor/` (excl. tests), `dapp/logic.js`, `dapp/app.js` | ≈ 2610 |

Sub-agents start from the same `master` HEAD that contains ADR-0014 (so each agent reads the ADR-mandated standard before acting). Groups have **no file overlap** so sub-branches can be merged in any order.

## Sub-agent contract (mandatory invariants for each group)

The sub-agent prompt encodes all of:

1. **Comment-only diff.** No logic, test, signature, or whitespace-only change outside comment additions. Verify with `git diff --stat` (only source files changed; tests untouched).
2. **`script/test-fast.sh` exits 0** after the group's commit.
3. **Per-file standard:** module-level header, function-level rationale on non-trivial functions, inline rationale on non-obvious lines.
4. **DO NOT** restate identifier names, narrate the task, or write speculative TODOs.
5. Single commit per group, message format: `docs(comments): <module> rationale comments per ADR-0014`.

## Integration log

| Group | Merge | Files touched | Test-fast result | Notes |
|-------|-------|---------------|------------------|-------|
| A | merge commit on `master` 2026-05-07; sub-branch `adr-0014-group-a-solidity` | `src/ParamutuelFactoryV3.sol`, `src/ParamutuelWagerV3.sol`, `src/interfaces/IERC20.sol`, `src/utils/ReentrancyGuard.sol` | OK | Fully covered the planned Solidity surface; only deletions were two pre-existing comments superseded by longer rationale. |
| B | merge commit on `master` 2026-05-07; sub-branch `adr-0014-group-b-indexer-proposition` | `service/indexer/{__init__,api,indexer,live_api,sweeper}.py`, `service/proposition/{__init__,db}.py` | OK after fix | Sub-agent was cut off before completing proposition/{dispatch,ingest,json_sources,rss,server,synthesize}.py. Sub-agent also accidentally elided the body of `service/indexer/indexer.py:_decode_abi_string` while replacing its existing inline comment with a docstring — restored before commit. |
| C | merge commit on `master` 2026-05-07; sub-branch `adr-0014-group-c-services-mcp` | `service/resolution/{__init__,logic,service}.py` | OK | Sub-agent cut off after Group C's first module. Did not reach explorer / control_panel / mcp_server. |
| D | merge commit on `master` 2026-05-07; sub-branch `adr-0014-group-d-agent-dapp` | `agents/paramutuel_bettor/{__init__,__main__,calldata}.py` | OK | Sub-agent cut off after the first three bet-scout files. Did not reach config/indexer_client/odds/planner/policy or `dapp/logic.js`/`dapp/app.js`. |
| Gap-fill | one direct commit on `master` 2026-05-07 (this commit) | `service/proposition/{dispatch,ingest,json_sources,rss,synthesize,server}.py`; `service/explorer/{__init__,logic,server}.py`; `service/control_panel/{__init__,security,cli,commands,web}.py`; `mcp_server/__init__.py`; `agents/paramutuel_bettor/{config,indexer_client,odds,planner,policy}.py`; `dapp/{logic,app}.js` | OK | Module-level rationale headers and selected function-level rationale on the files the sub-agents did not reach before usage cap. `mcp_server/{__main__,server}.py` already carried complete docstrings — left untouched per AGENTS.md #8. |
| Resonance follow-up | branch `adr-0014-site-resonance-followup` 2026-05-07 | `site/resonance{,-bet,-place,-propose,-explorer}.html` | OK | Initial scope under-weighted `site/resonance-*.html` — the live ARG launch surface (`docs/MICROWONK-ARG.md`) and the most user-visible code in the tree. Each page acquires a leading HTML comment block explaining role / wallet binding / iframe-skin contract. `site/propose-templates.js` and `site/network-context.js` already carried sufficient JSDoc and were left untouched. |

## Sub-agent post-mortem (delta from plan)

Four parallel Opus-class sub-agents launched in isolated worktrees from the
`master` HEAD that contained the ADR. Each agent received the ADR-mandated
contract (comment-only diff, fast-suite gate, single commit per group). All
four agents made well-shaped diffs *up to the point they were cut off by an
external usage cap*. None reached the commit step before being interrupted.

What worked:

- **Disjoint file scopes** prevented merge conflicts. The four worktrees
  modified entirely separate files and merged in any order without rebasing.
- **The ADR-prescribed standard** (module header + function rationale +
  inline rationale; no what-comments; no logic changes) translated directly
  into useful prose — the diffs that did land are uniformly on-target.

What broke:

- **Bounded scope was not enforced finely enough.** Each agent received a
  module *list*, not a per-file deadline. Group C had four modules,
  resolution/explorer/control_panel/mcp_server, and the agent only finished
  resolution before being cut off; Group D had two surfaces (bet scout +
  dApp) and only finished the first three of eight bet-scout files. With
  finer granularity (e.g. one agent per module instead of one per group),
  more files would have completed before the cap.
- **One latent regression** slipped past the comment-only constraint:
  Group B's agent replaced `_decode_abi_string`'s body with only a
  docstring, deleting twelve lines of ABI-decoding logic. The fast suite
  did not catch it because the function is only exercised by the live
  testnet enrichment path. Lesson recorded in `LESSONS.md` L-006.

What this argues for:

- A **lint-shaped post-merge check** that confirms a "comment-only" branch
  did not delete or modify any non-comment line. `git diff` plus a simple
  parser (drop blank lines and lines starting with `#`/`//`/`/*`/` *`) is
  enough to catch the Group B regression. Could be a follow-up ADR or a
  pre-commit hook on `script/`.

## Out of scope (unchanged)

- Comments in `test/` or any other test directory.
- Comments in `docs/`, `research/`, or other Markdown content.
- Commenting `lib/` (vendored Foundry forge-std and OpenZeppelin contracts).
- Comments in `out/`, `cache/`, `_site/`, `node_modules/`.

## Files NOT touched in scope (deliberate or already complete)

- `mcp_server/server.py` and `mcp_server/__main__.py` — already carry complete
  module-level docstrings explaining the V3-only posture, the read/write
  split, the indexer-coupling rules, and the encoder rationale. Re-touching
  them risks adding noise without adding value.
- `service/proposition/db.py` (touched by Group B sub-agent) — completed.
- All `__init__.py` files retouched only when previously empty or carrying
  a single comment line.

## Out of scope

- Comments in `test/` or any other test directory. ADR-0014 is for source modules only; test files document themselves through assertion names.
- Comments in `docs/`, `research/`, or other Markdown content. Already prose.
- Commenting `lib/` (vendored Foundry forge-std and OpenZeppelin contracts). Vendored code is upstream's responsibility.
- Comments in `out/`, `cache/`, `_site/`, `node_modules/`, or any other build artifact directory.
