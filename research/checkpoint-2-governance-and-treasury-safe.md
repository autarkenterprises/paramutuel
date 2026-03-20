# Checkpoint 2 Implementation: Governance and Treasury Safe

Status: In progress  
Owner: Governance/Treasury track  
Linked roadmap: `research/execution-roadmap.md` (Checkpoint 2)

## Objective

Deploy and rehearse a secure treasury custody setup (Safe multisig) and operational governance process before production launch.

## Scope

- Testnet Safe setup and rehearsal
- Mainnet/L2 Safe setup checklist
- Signer policy and rotation process
- Governance operations template for fee policy updates

---

## A) Safe Primer (for this project)

A Safe is a smart-account wallet that requires M-of-N signatures to execute transactions.

For this protocol:

- Safe treasury receives protocol fees.
- Safe signers approve treasury operations.
- Governance actions (if parameter setters exist) should be executed through Safe, not a single EOA.

Recommended launch posture:

- Start with `2-of-3` or `3-of-5` (risk/availability tradeoff).
- All signers use hardware wallets.

---

## B) Testnet Safe Setup Checklist (must pass first)

1. Create Safe on target testnet.
2. Configure owners and threshold.
3. Record Safe address in project registry.
4. Fund Safe with minimal native gas token.
5. Rehearse two key flows:
   - Treasury fee withdrawal receipt flow
   - Signer rotation flow (remove/add owner, threshold check)

### Evidence to archive

- Safe deployment tx hash
- owner list and threshold screenshot/export
- executed rehearsal tx hashes

---

## C) Signer Policy Template

Minimum policy:

- Hardware wallet required for all signers.
- No private keys stored in cloud password managers.
- Backup phrase custody documented and geographically separated.
- Emergency response contacts and escalation ladder.

Rotation triggers:

- signer departure
- potential key compromise
- periodic scheduled rotation (e.g., every 6-12 months)

---

## D) Governance Ops Template (Fee Policy)

If fee parameters are governable in current/future factory:

1. Draft fee-change proposal:
   - current fee
   - proposed fee
   - rationale and expected impact
2. Internal review window (e.g., 72h).
3. Safe transaction prepared.
4. Threshold approvals collected.
5. Execution and public changelog update.

If current contracts are immutable for fees:

- capture decision as "next deployment parameter update"
- execute only with explicit migration/redeployment plan.

---

## Exit Criteria

- Safe deployed on testnet and rehearsals completed.
- Signer policy approved.
- Governance operation checklist approved.
- Ready for production Safe setup with identical procedure.

