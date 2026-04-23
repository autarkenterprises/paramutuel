## Architecture Decision Records (ADR)

- `ADR-0001-core-immutability-and-delegated-resolution.md`
  - Immutable-core posture, delegated resolver model, pairing workflows, and security implications.
- `ADR-0002-governance-fees-and-treasury-safe.md`
  - Governance requirement, adjustable fee policy, and treasury Safe setup/testing.
- `ADR-0003-testnet-certification-multi-wager.md`
  - Mandatory testnet certification matrix across multiple wagers and lifecycle states.
- `ADR-0004-indexer-and-odds-calculator.md`
  - Minimal custom indexer scope and odds/payout preview requirements.
- `ADR-0005-delegated-betting-and-resolution-window-closure.md`
  - Optional `bettingCloser` / `resolutionCloser` roles, early `closeBetting` / `closeResolutionWindow`, and indexer/sweeper implications.
- `ADR-0006-surface-separation-self-custody-vs-assisted-ux.md`
  - Product-layer boundary: advanced self-custody dApp vs assisted website UX, with no core contract coupling.
- `ADR-0007-assisted-transaction-gateway-and-approval-paths.md`
  - Upper-layer gas abstraction via an assisted transaction gateway and pluggable permit/approval paths.
- `ADR-0008-multi-winner-and-settlement-generalization.md`
  - Multi-winner resolution and policy-driven payout semantics (any-of, exact-set, `AT_LEAST_K`, weighted overlap) without mutating v1. **On `master`** (`experiment/adr-0008-multi-winner-v2` integration history). Docs: `docs/ADR-0008-IMPLEMENTATION.md`, **glossary** `docs/PAYOUT-CALCULATION.md` Part B.
- `ADR-0009-freeform-text-wagers.md`
  - Freeform text-answer wagers: no enumerated outcomes at creation; bettors stake on arbitrary strings; resolver submits the winning string; exact byte match; single-winner parimutuel semantics; separate contract surface from bitmask v2. Implementation + outcome-cap discussion: `docs/ADR-0009-IMPLEMENTATION.md`.
- `ADR-0010-unified-wager-enumerated-and-freeform.md`
  - **Implemented** on `master` as `ParamutuelFactoryV3` + `ParamutuelWagerV3` (immutable `WagerMode` enum: `Enumerated` / `Freeform`). Unifies ADR-0008 bitmask + payoff policies and ADR-0009 freeform text answers behind one factory and one wager implementation with mode-dispatched external surface. The legacy standalone V1 / V2 / Freeform contracts have been **deleted from the tree**; indexer / MCP / dApp / site / agents / testnet suites are V3-only. Implementation notes: `docs/ADR-0010-IMPLEMENTATION.md`.

