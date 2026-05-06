# ADR-0002: Governance, Adjustable Fees, and Treasury Safe

- **Status:** Accepted (governance required from outset)
- **Date:** 2026-03-20

## Context

Project requirements:

- protocol fees should be adjustable as wager research improves
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

## After Action Report

**AAR date:** 2026-05-06
**AAR status:** Backfilled 2026-05-06 per ADR-0012

**Outcome vs success criteria** (criteria implicit in original Decision):

- *Treasury custody managed by a Safe multisig from day one.* **Partially met** — testnet deployment uses an EOA treasury (see `config/deployments.json` — no Safe address recorded). Safe testnet workflow exists in the ADR but has not been exercised end-to-end on the canonical Base Sepolia deployment.
- *Fee-setting authority separated from proposer / resolver service operations.* **Met by structure, not by enforcement** — `ParamutuelFactoryV3` carries `treasury` and `protocolFeeBps` as immutable constructor parameters (no on-chain setters), so per-deployment governance is implicit (whoever deploys the factory). Off-chain segmentation between protocol / service / treasury orgs is documented in `docs/PROJECT-REVIEW.md` but not enforced by contract roles.
- *Fee research and target-chain profiling moved earlier.* **Met** — `research/chain-and-fee-review.md` (2026-03-21) and `chore(fees): standardize protocol fee default to 100 bps (1%)` (2026-03-31) confirm sequencing happened before mainnet deploy.
- *Governance surface (fee bps, treasury, fee bounds).* **Not met as runtime governance** — the V3 factory has no setters; changing fees or treasury requires deploying a new factory. `MAX_TOTAL_FEE_BPS = 10_000` (100%) is the only on-chain bound.

**Outcome vs failure criteria:**

- *Single-key EOA treasury risk.* **Triggered for testnet** — current Base Sepolia deployment uses an EOA. Acceptable for testnet; **must be resolved before mainnet** per the ADR's explicit "v1.1/v2 factory with governed parameters before production launch" alternative.
- *Slow parameter changes blocked by multisig review.* **Avoided** — factory is immutable per deploy; "parameter change" = "new factory deploy", which is itself slow but unambiguous.

**Lessons:** none new for `LESSONS.md`. The partial outcome (immutable per-deployment fees, no Safe on testnet) is a known tradeoff that the project chose to defer until mainnet preparation.

**Follow-ups:**

- **Mainnet readiness:** deploy a Safe-controlled treasury and use that address as `treasury_` on the production factory. Capture as a checklist item under `docs/PROJECT-REVIEW.md` "Gaps vs production ready".
- **Decision pending:** whether mainnet factory adds runtime fee setters (governed) or stays immutable like testnet (forcing a redeploy on every fee change). Either is consistent with this ADR; choose explicitly before mainnet.

**Revision schedule:** before mainnet factory deploy.

