# ADR-0011: Documentation layer scaffolding (LOG / LESSONS / MEMORY / docs/log)

Date: 2026-05-06
Status: **Proposed** — meta / process ADR. No protocol-layer change.
Builds on: [`AGENTS.md`](../../AGENTS.md) project-generic practice **#11**.

## Context

`AGENTS.md` was rewritten on 2026-05-06 from an agent-surface integration index into a project-wide mandatory practices charter. Practice **#11** prescribes a separation of documentation layers by purpose:

- `LOG.md` — inclusive chronological spine: dated process notes, exploration, dead ends, backtracks, scratchpad observations, links to specialized records.
- `MEMORY.md` — high-priority facts that should remain present in future working context.
- `LESSONS.md` — durable lessons learned during the project.
- `docs/log/` — longer notes (conversation captures, design-time scratch) referenced from `LOG.md`.
- `README.md` (and module READMEs) — current public entrypoints and navigational summaries; **not** the primary historical trace.

The repository today has the README/ADR/implementation-notes pieces, but no `LOG.md`, no `LESSONS.md`, no `MEMORY.md`, and no `docs/log/`. Without those layers the chronological spine and durable-lessons material accrete into either commit messages (good for blame, poor for pattern recognition) or `README.md` (which then loses its navigational focus). The 2026-04 `docs/TASKS.md` "historical checkboxes left intact as a record of shipped work" annotation is a symptom of the missing layer — `TASKS.md` is doing a job `LOG.md` should do.

## Decision

1. **Create the four missing surfaces** at the locations and with the purposes prescribed by `AGENTS.md` #11:
   - `/LOG.md` — root-level, project-wide chronological spine. New entries appended dated; existing history backfilled at low resolution (one bullet per logical milestone, not per commit — `git log` remains authoritative for commit-grain detail).
   - `/LESSONS.md` — root-level, durable lessons. Seeded from material already implicit in shipped ADRs and the `docs/PROJECT-REVIEW.md` snapshot.
   - `/MEMORY.md` — root-level, short list of facts a fresh contributor or assistant **must** know to operate correctly (canonical contracts, branch discipline, where the practices live).
   - `/docs/log/` — directory for longer-form log entries that would clutter `LOG.md`. Initial commit ships a `README.md` describing the convention and a `.gitkeep`-style placeholder.

2. **Backfill posture.** `LOG.md` is backfilled as a thin retrospective spine (≈ one entry per major phase / week-cluster), not a re-narration of `git log`. The backfill is explicitly marked as such; future entries are dated as written. `LESSONS.md` is seeded with lessons that already have evidence in the tree (e.g. ADR-0010 unifying parallel surfaces), not speculative ones.

3. **No `README.md` rewrite in this ADR.** Practice #11 is satisfied if `README.md` is navigational and not the primary historical trace. Today's `README.md` is already navigational (links + setup), so this ADR makes no edit there. A separate ADR may revisit if drift becomes evident.

4. **TDD exception (per practice #1, #2).** Documentation scaffolding has no executable behavior to red/green. This ADR explicitly excuses TDD coverage on its own deliverables; the test suite remains untouched. Subsequent ADRs (especially ADR-0013, test stratification) re-enter the TDD discipline for code work.

5. **Cross-references.** `AGENTS.md` is **not** edited by this ADR — practice #11 is already prescriptive. `research/adr/README.md` gains a one-line entry for ADR-0011. `docs/ADR-0011-IMPLEMENTATION.md` records the concrete file list and any operational notes (e.g. how to add a `docs/log/` entry).

## Decision points

- **Format of `LOG.md` entries:** Markdown, reverse-chronological is rejected — entries are append-only chronological so a reader can scroll the project's history top-to-bottom. Each entry is `## YYYY-MM-DD — short title`, body free-form prose or bullets, links to `docs/log/<slug>.md` when the note exceeds ~1 screen.
- **`MEMORY.md` size:** target ≤ 30 lines. Anything that drifts longer is a sign material belongs in `LESSONS.md`, an ADR, or a runbook.
- **`docs/log/` naming:** `YYYY-MM-DD-<slug>.md`. The date is the date written, not the date of the events described.

## Success criteria

- All four files exist on `master` with non-empty initial content.
- `research/adr/README.md` lists ADR-0011.
- A subsequent ADR or commit referencing one of these files (e.g. ADR-0013 linking from `LESSONS.md`) is feasible without further structural work.
- A new contributor can locate the practices charter, current entrypoints, project-historical narrative, durable lessons, and high-priority facts in less than five minutes from the repo root.

## Failure criteria

- `LOG.md` becomes a dumping ground for material that belongs in commits or PR descriptions, ballooning past readability.
- `MEMORY.md` accumulates ephemeral status that goes stale, undermining its purpose as a stable working-context anchor.
- `LESSONS.md` becomes a list of regrets without actionable rules.
- The four files are created and never updated again (deadwood). Mitigation: every ADR's AAR section (per ADR-0012) must explicitly review whether a `LESSONS.md` entry is warranted.

## After Action Report

*To be completed after one full ADR cycle (e.g. when ADR-0013 lands) confirms the layers are being maintained as designed. Record: actual update cadence, any drift between intended and observed contents, and whether the size targets above held.*
