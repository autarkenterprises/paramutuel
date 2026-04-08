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
  - Versioned path for multi-winner resolution and policy-driven payout semantics (any-of, exact-set, and beyond) without mutating v1 deployments. **Canonical integration branch:** `experiment/adr-0008-multi-winner-v2` (merge to `master` after certification). Doc: `docs/ADR-0008-IMPLEMENTATION.md`.
- `ADR-0009-freeform-text-wagers.md`
  - Freeform text-answer wagers: no enumerated outcomes at creation; bettors stake on arbitrary strings; resolver submits the winning string; exact byte match; single-winner parimutuel semantics; separate contract surface from bitmask v2. Implementation + outcome-cap discussion: `docs/ADR-0009-IMPLEMENTATION.md`.

