# docs/log

Long-form chronological notes referenced from `LOG.md`. Convention defined in `docs/ADR-0011-IMPLEMENTATION.md` §"Authoring conventions" → `docs/log/`.

## Filename

`YYYY-MM-DD-<short-slug>.md`. The date is the date the note is written, not the date of the events the note describes.

## Body

- Optional front matter.
- Open with one paragraph of context so the entry is readable in isolation (a future reader may arrive via search rather than via `LOG.md`).
- Reference the corresponding `LOG.md` entry. Reverse links from `LOG.md` to this file are required so the chronological spine remains the canonical index.

## Suitable contents

- Conversation captures (design discussions worth preserving verbatim).
- Multi-screen design-time scratch that would dominate `LOG.md` if inlined.
- Incident post-mortems before the durable lesson lands in `LESSONS.md`.
- Exploration notes for a feature that may or may not ship.

## Unsuitable contents

- Material that belongs in an ADR (use `research/adr/ADR-NNNN-*.md`).
- Implementation notes for a shipped ADR (use `docs/ADR-NNNN-IMPLEMENTATION.md`).
- Setup, runbook, or how-to material (use a top-level `docs/<TOPIC>.md` or `service/<service>/README.md`).
- Durable lessons (use `LESSONS.md`).
