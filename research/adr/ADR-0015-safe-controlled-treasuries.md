# ADR-0015: Safe-controlled treasuries on Base Sepolia and Base Mainnet

Date: 2026-05-07
Status: **Proposed** (design ADR; implementation tracked separately).
Builds on: [ADR-0002](ADR-0002-governance-fees-and-treasury-safe.md) (governance + Safe), [ADR-0010](ADR-0010-unified-wager-enumerated-and-freeform.md) (V3 factory immutability), [`AGENTS.md`](../../AGENTS.md) practice **#4**, the testnet-as-production posture established by the Resonance Exchange ARG (`docs/MICROWONK-ARG.md`).

## Context

The V3 factory (`src/ParamutuelFactoryV3.sol`) takes `treasury` as a constructor argument and never mutates it. The address that the factory was deployed against on Base Sepolia is currently the same EOA that funds every other ARG role (`config/microwonk-wallets.json` `roles.treasury`, address `0xeBa11b0dE936877ce26B25eF0C1800d3d5bD84cc`). For an EOA-controlled treasury:

- Any leak of the controlling private key drains accumulated protocol fees from every wager that has ever paid out via the factory's deployment.
- Recovery requires deploying a new factory (since `treasury` is immutable per deployment), migrating all client-side configuration (`config/deployments.json`, `config/microwonk-wallets.json`, every UI / explorer / dApp / MCP env var), and abandoning any open wagers on the old factory.

The original ADR-0002 marked the EOA testnet posture as "acceptable for testnet, must resolve before mainnet." That framing was correct *while testnet was a closed rehearsal*. Under the Resonance Exchange ARG (live testnet launch, indistinguishable from production modulo mainnet), the EOA on Base Sepolia is **active production exposure**, not a downgraded posture. ADR-0002's revisited AAR (2026-05-07) reflects this; ADR-0015 specifies the implementation.

## Decision

1. **Both Base Sepolia and Base Mainnet treasuries are controlled by a Safe multisig.** No EOA in the production-exposure path. Same standard on both networks; the testnet treasury is not a downgraded posture.

2. **One Safe per network.** A Base Sepolia Safe protects the ARG treasury today. A Base Mainnet Safe protects the mainnet treasury before the first mainnet wager is created. Signer sets may overlap or differ — see Decision points.

3. **A new V3 factory is deployed per network with the Safe address as `treasury_`.** The current Base Sepolia factory (`0x11F036ab9C2621a21892E37E9d372d1b2Fe1dCD6`) remains immutable on-chain, but is **deprecated** for new ARG dispatch as soon as the Safe-controlled factory is live. Dispatched wagers on the old factory are allowed to settle naturally; the Co-ordinator stops creating new ones against it.

4. **Pre-cutover sweep.** Before pointing tooling at the new factory:
   - Withdraw any accrued protocol fees from existing settled wagers on the old factory to the EOA, then transfer to the Safe.
   - Drain the EOA's spendable balance to the Safe (modulo a documented small reserve for closing-out costs on legacy wagers).
   - Document the sweep transactions in `docs/log/YYYY-MM-DD-treasury-sweep.md`.

5. **`config/deployments.json` and `config/microwonk-wallets.json` updated atomically with the cutover.** Both files name the Safe address (not the EOA) as `treasury` after the new factory is live. The ARG Co-ordinator's dispatch scripts read `factoryAddress` from `deployments.json`, so a single config flip routes new wagers to the Safe-protected factory.

6. **Operational role wallets remain EOAs** (proposer, resolver, individual microwonk wallets). The Safe protects accumulated *protocol fees*; it is not on the per-action signing path. Putting bot-frequency signers behind a Safe defeats their bot-frequency purpose. This boundary is explicit so future work doesn't conflate the two.

## Decision points

The following need user input before implementation lands. Each is captured as an explicit question in §Open questions.

- **Signer set and threshold per Safe.** A 2-of-3 Safe is conservative for testnet operating funds; mainnet may justify 3-of-5 with hardware-wallet signers. The signer identities are not a code question — they are an operations / org-design question.
- **Whether the Base Sepolia and Base Mainnet Safes share signers.** Same identities reduce key-management overhead; different identities make a single compromise less impactful. Reasonable to start with the same signer set on both nets and diverge if the operating model warrants it.
- **Whether to publish the Safe addresses on the marketing site / Resonance Exchange page** for transparency, or leave them as operator-internal config.

## Success criteria

- The Safe address controls `treasury` on the deployed V3 factory on Base Sepolia, verified by reading `factory.treasury()` and matching it against the Safe address from the Safe app.
- The same is true on Base Mainnet before the first mainnet wager is created.
- The previous EOA holds zero (or a documented small reserve) ARG funds after the cutover sweep.
- `config/deployments.json` `baseSepolia.factoryAddress` and `baseMainnet.factoryAddress` both point at Safe-treasury factories.
- A test that fails-loud: a regression that points the factory at an EOA on either network must be caught before merge — see Decision point on a CI assertion.
- The ARG Co-ordinator's first dispatch after cutover lands on the new factory (one observed `WagerCreatedV3*` event).

## Failure criteria

- The Base Sepolia EOA continues to hold ARG funds after cutover. Mitigation: sweep is part of the cutover checklist; documented in `docs/log/`.
- A signer key on either Safe is compromised within the threshold. Mitigation: choose threshold high enough that one compromise is not catastrophic; rotate signers per the Safe's owner-management UX without touching the protocol.
- Tooling drift — some service still reads the old factory address from a hard-coded constant. Mitigation: every service that talks to the factory already reads `config/deployments.json`; the cutover commit must `grep -r '0x11F036ab9C2621a21892E37E9d372d1b2Fe1dCD6'` and clear any hits before the merge.
- Sweep loses funds to a typo'd Safe address. Mitigation: dry-run the sweep first (`cast send` against a localnet fork, or a single small probe transfer to the new Safe).

## Rejected alternatives

- **Add `setTreasury(address)` to the V3 factory.** Rejected — violates ADR-0001's "treat wager contracts as immutable settlement primitives" posture and adds a privileged role to the factory. The migration cost (one redeploy + config flip per network) is small and one-time.
- **Use only one Safe across both networks via a cross-chain message system.** Rejected — operationally complex, single point of failure across nets, no offsetting benefit at our scale.
- **Defer the testnet Safe until mainnet readiness.** Rejected — that was the original ADR-0002 framing; superseded by the testnet-as-production recalibration on 2026-05-07.

## Open questions (user input required before implementation)

1. **Signer set + threshold on Base Sepolia Safe?** Recommend 2-of-3 with the project owner + two designated operators; happy to start there unless you specify otherwise.
2. **Same set on Base Mainnet Safe, or a separate / larger set with hardware-wallet signers?** Mainnet justifies 3-of-5 with HW; testnet probably does not. Confirm before mainnet-Safe deploy.
3. **Whether to retain the old Base Sepolia factory address in `config/deployments.json`** (under a `legacy` key) for read-only tooling that wants to enumerate historical wagers, or fully retire it.
4. **Public disclosure of Safe addresses on the Resonance Exchange landing page?**
5. **Sweep timing.** Cutover during low ARG activity (between Co-ordinator dispatch beats), or coordinated with a planned campaign pause? `docs/MICROWONK-ARG.md` doesn't yet name a pause point; if there isn't one, the sweep happens during the next planned low-activity window.

## After Action Report

**AAR date:** Pending (populated after Base Sepolia Safe is live and the cutover sweep is documented).
**AAR status:** Pending

**Outcome vs success criteria:** to be populated.

**Outcome vs failure criteria:** to be populated.

**Lessons:** to be populated.

**Follow-ups:** to be populated. Likely candidates: the CI assertion guarding factory-treasury type, and any operational learnings from running an active campaign behind a multisig.

**Revision schedule:** at Base Mainnet Safe deploy (cycle two of this ADR), then at the first Safe owner-set rotation (verify rotation works without protocol redeploy).
