# ADR-0012: ADR template and After Action Report discipline

Date: 2026-05-06
Status: **Proposed** — meta / process ADR. No protocol-layer change.
Builds on: [`AGENTS.md`](../../AGENTS.md) project-generic practice **#4**, ADR-0011 (documentation layer scaffolding).

## Context

`AGENTS.md` practice **#4** mandates that ADRs:

1. Precede all feature implementation.
2. Document **motivations**, **decision points**, and **success / failure criteria** for each feature.
3. Receive an **After Action Report (AAR)** once complete.
4. Have AARs **revisited as new information becomes available** — particularly for features whose effect can only be assessed after a period of operation.

Existing ADRs (0001–0010) precede their implementations and document motivations and decisions, but they do **not** uniformly carry explicit success / failure criteria, and **none** has an AAR. ADR-0011 (documentation layer scaffolding) is the first ADR to ship the success / failure / AAR sections natively.

Two things are needed:

- **Going forward:** a single template every new ADR conforms to.
- **Retroactively:** an AAR appended to each shipped ADR (0001–0010) so the historical record matches the practice. The retroactive pass does **not** rewrite existing ADR bodies (per `AGENTS.md` practice #8 — no unrelated changes); it only **appends** the AAR section.

## Decision

1. **Adopt a uniform ADR section structure** for all new ADRs:

   - **Title, Date, Status** (header).
   - **Context** — motivation; what changed in the world or repo that requires a decision now.
   - **Decision** — numbered list of the choices being committed to.
   - **Decision points** — the subsidiary choices worth recording (defaults, naming, format, scope boundaries).
   - **Success criteria** — concrete, observable conditions under which the ADR is judged successful. Prefer falsifiable ("X exists at path Y", "metric Z is below W", "test T passes") over aspirational ("better UX").
   - **Failure criteria** — concrete conditions under which the ADR is judged failed, including drift / decay modes.
   - **Rejected alternatives** *(when material)*.
   - **After Action Report** — initially a placeholder; populated when the ADR cycle completes; revisited per practice #4.

2. **Adopt a uniform AAR shape** within each ADR:

   - **AAR date** and **AAR status** (`Pending` / `In progress` / `Final` / `Revisited YYYY-MM-DD`).
   - **Outcome vs success criteria** — for each success criterion, mark **Met** / **Partially met** / **Not met** with a one-line evidence pointer (commit, file, test, dashboard).
   - **Outcome vs failure criteria** — for each failure criterion, mark **Avoided** / **Triggered** / **Mitigated** with the same evidence form.
   - **Lessons** — link to `LESSONS.md` entries the ADR generated; new lessons created as a result of the AAR are added to `LESSONS.md` in the same commit as the AAR write-up.
   - **Follow-ups** — open questions, follow-on ADR numbers, or backlog items.
   - **Revision schedule** — when to revisit. Acceptable values: `none required`, `next major release`, `at YYYY-MM-DD`, `after metric X is observed for N days`. `none required` is reserved for ADRs whose effect is immediate and binary (e.g. file scaffolding, contract deletion sweeps).

3. **Backfill posture for ADR-0001 … 0010:**

   - **Append** an AAR section to each existing ADR. **Do not** rewrite Context, Decision, or Consequences — those are historical record.
   - Each retroactive AAR explicitly states `**AAR status:** Backfilled YYYY-MM-DD` so a reader can see it was written after the fact rather than concurrently with completion.
   - Where the original ADR has no explicit success / failure criteria, the AAR articulates the criteria that were **implicit** in the Context / Decision / Consequences sections and assesses against those, flagging any ambiguity.
   - For ADRs whose ideas were **superseded** before completion (specifically ADR-0008 V2 contracts and ADR-0009 standalone freeform contracts, both subsumed by ADR-0010), the AAR records both the partial outcome of the original ADR and the supersession.

4. **Cross-references:**

   - `docs/ADR-0012-IMPLEMENTATION.md` carries the actual ADR / AAR template text in copy-pasteable form, plus a short "writing an ADR" how-to.
   - `research/adr/README.md` gains a one-line entry for ADR-0012.
   - `LOG.md` and `LESSONS.md` are updated only if material lessons emerge from the retroactive AARs.

5. **TDD exception (per practice #1, #2).** Same as ADR-0011: documentation has no executable behavior to red/green. Future ADRs that ship code re-enter TDD discipline.

## Decision points

- **Append vs rewrite for retroactive AARs:** append-only, per practice #8.
- **AAR location:** within the ADR file itself, as the last section. Rejected alternative: a separate `AAR-NNNN.md` file — that doubles the surface area without making the AAR easier to find.
- **Template location:** the canonical copy lives in `docs/ADR-0012-IMPLEMENTATION.md`. Authors may copy-paste; the template is plain Markdown, not a script-generated scaffold (low value for the scaffolding given the cadence of new ADRs).

## Success criteria

- Every ADR (0001–0011, plus 0012 itself) has an AAR section on `master` after this ADR merges.
- A new ADR written after 0012 conforms to the template structure (sections, names, AAR placeholder).
- A reader can locate the success / failure criteria for any ADR by searching `## Success criteria` within `research/adr/`.

## Failure criteria

- Retroactive AARs are written and never updated (deadwood). Mitigation: the revision schedule field is mandatory; ADRs with `next major release` or dated revisions appear in a sweep at that time.
- New ADRs are written without the template (drift). Mitigation: ADR-0013 onward will use the template explicitly; the template is concrete enough that copy-paste is the path of least resistance.
- AARs become hagiographic ("everything went perfectly") rather than honest. Mitigation: the **Outcome vs failure criteria** section forces engagement with what could / did go wrong.

## Rejected alternatives

- **Rewrite existing ADR bodies to include explicit success / failure criteria.** Rejected per `AGENTS.md` practice #8 (no unrelated changes), and because the ADR body is a historical artifact — the AAR can articulate the criteria after the fact without rewriting the source.
- **Auto-generate AAR scaffolds via a tool.** Rejected as premature given the project's ADR cadence (≤ one per week-cluster).
- **Maintain ADRs and AARs in separate files (`AAR-NNNN.md`).** Rejected — doubles the file count and makes it easier to skip writing the AAR.

## After Action Report

*To be completed after one full ADR cycle (e.g. when ADR-0013 lands using the template) confirms the structure works in practice. Record: actual conformance of new ADRs, drift between template and reality, and whether the retroactive AARs are revisited per their revision schedules.*

**Revision schedule:** at ADR-0013 merge.
