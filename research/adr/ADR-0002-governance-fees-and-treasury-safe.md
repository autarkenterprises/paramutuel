# ADR-0002: Governance, Adjustable Fees, and Treasury Safe

- **Status:** Accepted (governance required from outset)
- **Date:** 2026-03-20

## Context

Project requirements:

- protocol fees should be adjustable as market research improves
- treasury custody should be secure from day one
- protocol aims for stable core contracts, but governance is still necessary

Current MVP factory sets fee/treasury at deployment time only.

## Decision

1. **Governance is required at launch.**
   - At minimum, governance must control protocol fee and treasury address policy.

2. **Treasury is custody-managed by a Safe multisig from day one.**
   - Start with a conservative threshold (e.g., 2-of-3 or 3-of-5).
   - Avoid raw single-key EOAs for treasury custody.

3. **Fee-setting authority is separated from proposer/resolver service operations.**
   - Aligns with segmented org model (protocol org, service org, treasury org).

4. **Checkpoint sequencing changes:**
   - Fee research and target-chain profiling move earlier (with governance architecture), not later.

## Safe Explanation (Operational)

A Safe is a smart-account wallet on-chain that requires multiple signer approvals before execution.

### Why Safe

- signer rotation without replacing protocol contracts
- threshold approvals reduce single-key risk
- clear audit trail of governance actions

### Testnet Setup Workflow

1. Deploy Safe on testnet.
2. Add owners and threshold.
3. Fund Safe minimally for test operations.
4. Use Safe as treasury in test deployments.
5. Execute and verify at least:
   - fee withdrawal flow
   - governance transaction rehearsal (if governance setters exist)

### Mainnet/L2 Setup Workflow

Repeat testnet process with hardware-wallet signers and published signer policy.

## Governance Surface (Minimum)

- protocol fee BPS parameter
- treasury recipient address
- optional fee bounds (hard caps)

If immutable v1 lacks these setters, launch planning must include:

- v1 fixed fee with explicit migration plan, or
- v1.1/v2 factory with governed parameters before production launch.

## Consequences

### Positive

- enables fee tuning based on evidence
- strengthens custody and trust posture
- supports segmented organizational design

### Tradeoffs

- additional governance complexity
- slower parameter changes if timelocks/multisig review are used

