# ADR-0015 implementation notes (Safe-controlled treasuries)

**Status:** Design ADR — implementation pending operator input on §Open questions.
**ADR:** [`research/adr/ADR-0015-safe-controlled-treasuries.md`](../research/adr/ADR-0015-safe-controlled-treasuries.md)

This file is the runbook side of ADR-0015. The ADR sets the contract;
this file is where the cutover steps land in concrete order. Today it is
a checklist of work-not-yet-done; entries become checked off as each
step lands and an associated commit / `docs/log/` entry exists.

## Per-network cutover checklist

For each of `baseSepolia` and `baseMainnet`, in this order:

### 1. Provision the Safe

- [ ] Choose signer set + threshold (per ADR-0015 Open questions §1, §2).
- [ ] Deploy Safe via the Safe app on the target network. Save the Safe
      address; record signer identities (no private keys) in
      `docs/log/YYYY-MM-DD-safe-deploy-<network>.md`.
- [ ] Verify Safe owners and threshold by querying on-chain
      (`getOwners()`, `getThreshold()`).

### 2. Deploy the new V3 factory

- [ ] `forge script script/DeployFactoryV3.s.sol --rpc-url <network>
      --broadcast` with `TREASURY=<safe-address>` env var.
- [ ] Capture the new factory address; verify
      `factory.treasury() == <safe-address>` via `cast call`.

### 3. Pre-cutover sweep (testnet — once active ARG funds are at stake)

- [ ] Withdraw accrued protocol fees from settled wagers on the old
      factory's wagers (per-wager `withdrawFees()` from the EOA).
- [ ] Transfer EOA-held ARG operating-float ETH and USDC to the Safe,
      modulo a documented small reserve for closing-out costs.
- [ ] Document sweep in `docs/log/YYYY-MM-DD-treasury-sweep-<network>.md`
      with txhashes, amounts, and remaining reserve rationale.

### 4. Atomic config flip

- [ ] Update `config/deployments.json` `<network>.factoryAddress` to
      the new Safe-treasury factory.
- [ ] Update `config/microwonk-wallets.json` `roles.treasury.address`
      to the Safe address.
- [ ] If retaining the old factory under a `legacy` key (per ADR-0015
      Open question §3), record it; otherwise omit.
- [ ] Single commit; the ARG Co-ordinator's next dispatch picks up the
      new factory.

### 5. Post-cutover smoke

- [ ] Co-ordinator dispatches a small test wager on the new factory.
      Verify the `WagerCreatedV3*` event names the Safe as treasury.
- [ ] Tag the cutover branch (`git tag treasury-safe-<network>-cutover`)
      so it is easy to find later.

## CI / lint hook (recommended follow-up)

A trivial assertion to land alongside the cutover: read
`config/deployments.json`, query each `factoryAddress`'s `treasury()`
on-chain, and fail if the result is not in a whitelist of known Safe
addresses. Cheap to run, catches "someone hard-coded the EOA back into
deployments." Candidate for a `script/check-treasury-is-safe.sh` and a
GitHub Actions step once CI is wired up.

## Out of scope

- Adding a runtime `setTreasury` setter to V3 (rejected in ADR-0015).
- Migrating individual microwonk / proposer / resolver wallets to
  Safes — those are bot-frequency signing keys, not store-of-value
  treasuries, and the Safe model doesn't fit. ADR-0015 is explicit on
  this boundary.
- Cross-chain Safe topology — see ADR-0015 Rejected alternatives.
