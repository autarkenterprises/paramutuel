# ADR-0011 implementation notes (documentation layer scaffolding)

**Status:** Implemented on branch `adr-0011-doc-layers`. Process / meta ADR — no protocol or service-layer change.
**ADR:** [`research/adr/ADR-0011-documentation-layer-scaffolding.md`](../research/adr/ADR-0011-documentation-layer-scaffolding.md)

## Files created

| Path | Role |
|------|------|
| `LOG.md` | Project-wide dated chronological spine (append-only). |
| `LESSONS.md` | Durable lessons with evidence from shipped work. |
| `MEMORY.md` | Short list of high-priority facts for working-context recall. |
| `docs/log/README.md` | Convention for longer-form log entries linked from `LOG.md`. |
| `research/adr/ADR-0011-documentation-layer-scaffolding.md` | The ADR itself. |
| `docs/ADR-0011-IMPLEMENTATION.md` | This file. |

`research/adr/README.md` gains a one-line entry for ADR-0011 (the only edit to a pre-existing file in this ADR).

## Authoring conventions

### `LOG.md`

- Append-only chronological order. Newest entry at the bottom.
- Entry header: `## YYYY-MM-DD — short title`.
- Body: free-form prose or bullet list. Cross-link any specialized record (ADR, runbook, `docs/log/<slug>.md`).
- For a note longer than roughly one screen, place the body under `docs/log/YYYY-MM-DD-<slug>.md` and leave a one-line link in `LOG.md`.
- Backfill entries — those describing events earlier than the file's creation date — are explicitly marked **(backfill)** in the title.

### `LESSONS.md`

- Each lesson has a short imperative title, a **Why** (evidence: ADR / commit / incident), and a **How to apply** (when this lesson kicks in).
- Lessons are durable. If a lesson stops applying because the underlying constraint was removed, mark it **Retired** with the date and reason rather than deleting it.

### `MEMORY.md`

- ≤ 30 lines. Bullets only.
- Each bullet is something a fresh contributor or assistant must know to act correctly *today*.
- If a fact stops being current, edit or remove the line — `MEMORY.md` is not historical.

### `docs/log/`

- Filenames: `YYYY-MM-DD-<short-slug>.md`. Date is the date written.
- Front matter is optional. Body should open with one paragraph of context so the entry is readable in isolation.
- Reference one or more `LOG.md` entries; reverse links are not required but encouraged.

## Operational checklist (going forward)

- After each merged ADR, the author appends a `LOG.md` entry summarising the ADR cycle and any AAR-adjacent observations, and considers whether a `LESSONS.md` entry is warranted (default: no — only durable, transferable rules).
- After each shipped feature or refactor, the author considers whether `MEMORY.md` needs an edit (typical answer: no).
- Practice #12 review (regular re-read of `AGENTS.md`) is logged in `LOG.md`.

## Out of scope

- Editing `README.md`. Today's `README.md` is already navigational; per ADR-0011 §3 no rewrite is performed in this ADR.
- Migrating historical material from `docs/TASKS.md`, `docs/PROJECT-REVIEW.md`, or commit messages into `LOG.md`. Those documents remain authoritative for their current purposes; `LOG.md` is forward-leaning with a thin backfill spine.
