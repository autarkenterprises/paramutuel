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

Each group's merge appends an entry here.

| Group | Merge commit | Files touched | Test-fast result | Notes |
|-------|--------------|---------------|------------------|-------|
| A | (pending) | | | |
| B | (pending) | | | |
| C | (pending) | | | |
| D | (pending) | | | |

## Out of scope

- Comments in `test/` or any other test directory. ADR-0014 is for source modules only; test files document themselves through assertion names.
- Comments in `docs/`, `research/`, or other Markdown content. Already prose.
- Commenting `lib/` (vendored Foundry forge-std and OpenZeppelin contracts). Vendored code is upstream's responsibility.
- Comments in `out/`, `cache/`, `_site/`, `node_modules/`, or any other build artifact directory.
