# ADR-0012 implementation notes (ADR template and AAR discipline)

**Status:** Implemented on branch `adr-0012-aar-template`. Process / meta ADR — no protocol or service-layer change.
**ADR:** [`research/adr/ADR-0012-adr-template-and-aar-discipline.md`](../research/adr/ADR-0012-adr-template-and-aar-discipline.md)

## Files touched

| Path | Change |
|------|--------|
| `research/adr/ADR-0001-core-immutability-and-delegated-resolution.md` | Append AAR section. |
| `research/adr/ADR-0002-governance-fees-and-treasury-safe.md` | Append AAR section. |
| `research/adr/ADR-0003-testnet-certification-multi-market.md` | Append AAR section. |
| `research/adr/ADR-0004-indexer-and-odds-calculator.md` | Append AAR section. |
| `research/adr/ADR-0005-delegated-betting-and-resolution-window-closure.md` | Append AAR section. |
| `research/adr/ADR-0006-surface-separation-self-custody-vs-assisted-ux.md` | Append AAR section. |
| `research/adr/ADR-0007-assisted-transaction-gateway-and-approval-paths.md` | Append AAR section. |
| `research/adr/ADR-0008-multi-winner-and-settlement-generalization.md` | Append AAR section. |
| `research/adr/ADR-0009-freeform-text-wagers.md` | Append AAR section. |
| `research/adr/ADR-0010-unified-wager-enumerated-and-freeform.md` | Append AAR section. |
| `research/adr/ADR-0011-documentation-layer-scaffolding.md` | (Already has AAR placeholder; no change.) |
| `research/adr/README.md` | Add ADR-0012 entry. |
| `research/adr/ADR-TEMPLATE.md` | New canonical template (copy-paste source for new ADRs). |
| `LOG.md` | Append entry recording the AAR sweep. |

The retroactive AARs are append-only edits — no Context, Decision, or Consequences text in any existing ADR is modified.

## ADR template

The canonical copy-pasteable template is `research/adr/ADR-TEMPLATE.md`. Reproduced here for convenience:

```markdown
# ADR-NNNN: <title>

Date: YYYY-MM-DD
Status: **Proposed** | **Accepted** | **Implemented** | **Superseded by ADR-MMMM**
Builds on: <links to prior ADRs / runbooks / `AGENTS.md` practices>

## Context

<motivation: what changed in the world or repo that requires a decision now?>

## Decision

1. <numbered, committal>
2. ...

## Decision points

- <subsidiary choices: defaults, naming, format, scope boundaries>

## Success criteria

- <concrete, observable, falsifiable>
- <metric, file existence, test pass, behavior under load, …>

## Failure criteria

- <concrete failure modes including drift / decay>
- <mitigation noted inline if known>

## Rejected alternatives

- <only when material; otherwise omit the section>

## After Action Report

**AAR date:** <YYYY-MM-DD when populated, or "Pending" until then>
**AAR status:** Pending | In progress | Final | Revisited YYYY-MM-DD | Backfilled YYYY-MM-DD

**Outcome vs success criteria:**

- <criterion>: Met | Partially met | Not met — <one-line evidence (commit, file, test, dashboard)>

**Outcome vs failure criteria:**

- <criterion>: Avoided | Triggered | Mitigated — <one-line evidence>

**Lessons:** <link to `LESSONS.md` entries; "none" if no durable lesson emerged>

**Follow-ups:** <open questions, follow-on ADR numbers, backlog items; "none" if closed>

**Revision schedule:** none required | next major release | at YYYY-MM-DD | after metric X observed for N days
```

## Operational checklist (going forward)

- A new ADR is created from `research/adr/ADR-TEMPLATE.md`, not by copying the closest prior ADR (which may not yet conform).
- The author of the ADR populates Success criteria and Failure criteria **before** implementation begins (per `AGENTS.md` practice #4 — ADR precedes feature work).
- The AAR is populated when the ADR cycle completes. If the cycle is open-ended (e.g. operational metric over time), `Revision schedule` records the next checkpoint.
- AARs are **revised**, not appended-then-frozen — when an ADR's effect changes (deprecation, supersession, metric reading), the existing AAR is updated and `AAR status` is set to `Revisited YYYY-MM-DD`.

## Out of scope

- Re-litigating the Context, Decision, or Consequences of any retroactive ADR. The AAR may state that a decision turned out to be costly, but the historical text stands.
- Migrating existing ADRs from `research/adr/` to a different location.
