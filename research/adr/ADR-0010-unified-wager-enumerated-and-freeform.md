# ADR-0010: Unified wager protocol (enumerated v2 + freeform in one contract)

Date: 2026-04-14  
Status: **Proposed** — supersedes the *deployment* posture of ADR-0009 § “distinct protocol surface” for **new** work; does **not** invalidate already-deployed v1 / v2 / freeform factories on-chain.  
Supersedes (for greenfield implementations): the architectural split between **`ParamutuelWagerV2`** and **`ParamutuelWagerFreeform`** as *mandatory* separate contracts.  
Builds on: [ADR-0008](ADR-0008-multi-winner-and-settlement-generalization.md), [ADR-0009](ADR-0009-freeform-text-wagers.md), [ADR-0008 implementation notes](../../docs/ADR-0008-IMPLEMENTATION.md), [ADR-0009 implementation notes](../../docs/ADR-0009-IMPLEMENTATION.md).

## Context

**Original product intent:** the freeform format was proposed so the **same protocol** could eventually cover both:

1. **Enumerated outcome spaces** with resolver-submitted **multi-outcome truth** and **policy-driven** settlement (**ADR-0008** — generalizes v1’s single index to bitmask tickets + `PayoffPolicy`: `SINGLE_WINNER`, `ANY_OF`, `EXACT_SET`, `AT_LEAST_K`, `WEIGHTED_OVERLAP`).
2. **Open-ended text answers** at bet time with **single** winning string resolution (**ADR-0009** — `keccak256(bytes(answer))` ticket identity, exact byte match).

**Current implementation:** three parallel surfaces — v1 (`ParamutuelWager`), v2 (`ParamutuelWagerV2`), freeform (`ParamutuelWagerFreeform`) — each with its own factory, events, and toolchain branches. That reduces risk and shipped quickly, but **fragments** ABI surfaces, documentation, indexer logic, MCP tools, and operator mental models.

**Goal of this ADR:** specify a **single wager contract** (and matching **factory**) that selects **one immutable mode at construction**:

- **`ENUMERATED`** — same capabilities as current v2 (outcomes at create, bitmask tickets, `resolve(winningMask)`, policies, seeds, fee vectors, lifecycle roles).
- **`FREEFORM`** — same capabilities as current freeform (no outcome list, `placeBet(string)`, `resolve(string)`, `answerId` pools, caps on distinct answers / string length).

No third “hybrid” mode within one wager: a given deployment is **either** enumerated **or** freeform for its entire lifetime. *Combining* both *styles* in one *product* means **one codebase and one ABI family** with a **create-time discriminator**, not mixing string tickets and bitmask tickets on the same storage graph in one market.

## Decision

1. **Introduce `ParamutuelWagerUnified` + `ParamutuelFactoryUnified`** (names TBD) as the **canonical** post-unification contracts. They **subsume** the *feature set* of current v2 and freeform for **new** deployments.

2. **Immutable `WagerMode mode` (or equivalent)** set in the wager constructor and **never** changed. All external entrypoints **enforce** the mode:
   - `ENUMERATED`: match current v2 surface — `placeBet(uint256 ticketMask, uint256 amount)`, `placeBets(uint256[] calldata, uint256[] calldata)`, `resolve(uint256 winningMask)`; **no** string ticket APIs. Wrong-mode calls either **revert** (fat ABI) or are **absent** (split external interfaces).
   - `FREEFORM`: match current freeform surface — `placeBet(string calldata answer, uint256 amount)`, `resolve(string calldata winningAnswer)`; **no** bitmask / `PayoffPolicy` / `resolve(winningMask)` on that deployment. Same fat-ABI vs segregated-interface choice as above.

3. **Policy engine** applies **only** to `ENUMERATED`. `FREEFORM` retains **single-winner** parimutuel over `answerId` pools (as ADR-0009). Future extension to “freeform + policy” is **out of scope** for v1 of this ADR unless explicitly added later.

4. **v1 economic / lifecycle parity** remains available as **`ENUMERATED` + `SINGLE_WINNER` + single-bit tickets** (two-outcome lines, etc.). Factory **ABI** may still differ from legacy `ParamutuelFactory.createWager` (calldata shapes, seeding overloads); migration tooling must map old ↔ unified encodings. A separate **v1** contract is not required for **new** deploys once the unified factory ships, unless a network must preserve byte-identical v1 factories for audit/compliance.

5. **Legacy contracts** (`ParamutuelFactory`, `ParamutuelFactoryV2`, `ParamutuelFactoryFreeform`, and their wagers) remain **immutable on-chain**; indexers and tooling **continue** to support them until deprecation windows close.

6. **Deprecation path (off-chain / product):** new UIs and hosted defaults target **unified** addresses in `config/deployments.json`; legacy keys may remain for historical networks.

## Contract sketch (non-normative)

- Factory `createEnumeratedWager(...)` / `createFreeformWager(...)` (or one `createWager` with a mode tag) → `new ParamutuelWagerUnified{ mode: ... }(...)`.
- Shared: collateral, proposition string, windows, resolver / closers, fees, reentrancy, state machine (`Open` → …), `claim` / `withdrawFees`, events for lifecycle.
- Mode-specific storage sections **must not** alias: use **clear layout** (separate structs or namespaced storage if upgradeable patterns appear later; current codebase favors **immutable** contracts — prefer **separate storage slots per mode** with unused branch zeroed).

## Strict test-driven design directive

For **every logical unit** of new or changed code (Solidity function, library pure function, indexer `apply_log` branch, MCP encoder, dApp pure helper, etc.), the team **must** execute, **in order**:

1. **Red —** Write a **non-trivial** automated test that expresses the intended behavior and **assertions** (property, revert reason, event shape, or state delta). The test **must fail** before implementation (missing symbol, wrong revert, wrong value).
2. **Green —** Implement the **minimum** production code to satisfy that test.
3. **Refactor —** Clean up while **keeping the test green**; run the **full** relevant suite (`forge test`, targeted Python `unittest`, `node --test`, etc.) and confirm **no regressions** in tests that are still **in scope**.

### Tests invalidated by the protocol change

- **Retain** historical tests that targeted **`ParamutuelWagerV2`**, **`ParamutuelWagerFreeform`**, or split factories **as long as those contracts remain in the tree** for legacy support. Where behavior is **intentionally** superseded by the unified contract, **do not delete** the old tests without ADR sign-off; instead:
  - Either **migrate** assertions to the unified contract equivalents, **or**
  - Mark the test class/method with an explicit **`@expectedFailure`** / `xfail` / documented skip with reason **`superseded-by-ADR-0010`**, and change the **pass condition** to **“fails as expected”** (CI must treat that as success).
- **Foundry:** there is no `xfail` flag; use **`vm.expectRevert`** on unified bytecode when a fat ABI intentionally rejects wrong-mode calls, or keep **legacy contract tests** as ordinary passing suites against **unchanged** `ParamutuelWagerV2` / `ParamutuelWagerFreeform` artifacts. Do not rely on Python-style `@expectedFailure` in Solidity.

**Rationale:** preserves regression signal for deployed bytecode while making unified behavior the default for new tests.

## Propagation checklist (must be updated or explicitly marked N/A)

Mark each item with owner and PR when executing this ADR.

### Solidity / Foundry

- [ ] `src/ParamutuelWagerUnified.sol` (and factory).
- [ ] `test/` — unified matrix tests; legacy tests migrated or `expectedFailure` as above.
- [ ] `script/` — `DeployFactoryUnified.s.sol` (or split deploy scripts calling one implementation).
- [ ] `script/sync-abi.sh` — emit unified ABIs into `dapp/abi/`, `mcp_server/abi/`.
- [ ] `test/ParamutuelV2Gas.t.sol` / `test/ParamutuelV2Extensive.t.sol` — **re-run gas profiling**; add **`ParamutuelUnifiedGas.t.sol`** (or extend harness) for both modes; update `docs/ADR-0008-GAS.md` or successor **`docs/ADR-0010-GAS.md`**.

### Human-readable specs

- [ ] `docs/PAYOUT-CALCULATION.md` — new **Part C** (or restructure): unified contract; cross-reference ENUMERATED = current Part B, FREEFORM = ADR-0009 economics.
- [ ] `docs/ADR-0008-IMPLEMENTATION.md` / `docs/ADR-0009-IMPLEMENTATION.md` — banners: “superseded for **new** deploys by ADR-0010”; keep as **legacy** reference.
- [ ] **`docs/ADR-0010-IMPLEMENTATION.md`** (new) — encoding, events, mode matrix, migration from v2/freeform ABIs.
- [ ] `docs/MACHINE.md`, `docs/WORKFLOWS.md`, `docs/CONTRACT-UPGRADE-RUNBOOK.md`, `docs/INDEXER-HOSTING.md`, `docs/CLOUD-RUN-HOSTING.md`, `docs/WEBSITE.md`.
- [ ] `research/adr/README.md` — index this ADR.
- [ ] `README.md` (root), `dapp/README.md`, `service/README.md`, `mcp_server/README.md`, `AGENTS.md`, `docs/BET-AGENT.md`, `docs/AGENT-LOOP.md`.

### Indexer / explorer / SQLite schema

- [ ] `service/indexer/schema.sql` — `protocol_version` values: e.g. `unified_enum`, `unified_freeform` **or** single `unified` + `unified_mode` column (prefer **explicit** for query simplicity).
- [ ] `service/indexer/indexer.py` — decode **unified** factory events; map `BetPlaced` / `Resolved` variants.
- [ ] `service/indexer/api.py` — `/health` factory echo; search fields.
- [ ] `service/indexer/live_api.py` — env / `deployments.json` for **one** factory address (or legacy multi-factory during transition).
- [ ] `service/indexer/tests/*` — TDD per checklist above.
- [ ] `service/explorer/static/*` — columns and copy for unified mode.

### Site / static marketing & bet flows

- [ ] `site/*` — ticker, bet page, operator copy: **one** protocol narrative + mode badge.
- [ ] `config/deployments.json` — `factoryUnifiedAddress` (name TBD); deprecate separate v2/freeform keys **per network** when cut over.

### dApp

- [ ] `dapp/app.js`, `dapp/index.html`, `dapp/logic.js`, `dapp/tests/logic.test.js` — single factory selector; mode from chain or create flow.
- [ ] `dapp/abi/*` — unified JSON.

### MCP server

- [ ] `mcp_server/server.py` — tools: `encode_create_wager_unified`, `encode_place_bet_unified`, `encode_resolve_unified` (or mode-parameterized); deprecate duplicate v2/freeform tools **after** transition or keep as aliases with deprecation warnings in tool descriptions.
- [ ] `mcp_server/tests/test_server.py`.
- [ ] `mcp_server/README.md`.

### Bet scout subagent

- [ ] `agents/paramutuel_bettor/*` — `policy.py`, `planner.py`, `calldata.py`, `__main__.py`, manifest, tests.
- [ ] `agents/subagent-manifest.json`, `.cursor/skills/paramutuel-bettor/SKILL.md`.
- [ ] PyPI release channel / version bump per `docs/BET-AGENT-DISTRIBUTION.md`.

### Auxiliary services

- [ ] `service/control_panel/*` — CLI, web, `commands.py`: create + resolve encoders for unified ABI.
- [ ] `service/resolution/service.py` — decision JSON → calldata for unified `resolve` overloads.
- [ ] `service/resolution/tests/*`, `service/control_panel/tests/*`.
- [ ] `Dockerfile` — env defaults for unified factory / from-block.
- [ ] GitHub Actions — `deploy-site.yml` ABI copy list; any CI matrix for `forge test`.

### Testnet / stress

- [ ] `test/testnet/test_live_base_sepolia.py`, `test/testnet/test_stress_base_sepolia.py`, `script/testnet/*.sh` — unified factory env vars; legacy skips documented.

## Acceptance criteria

- [ ] **One** wager implementation (per ADR) deployed to testnet with **both** modes exercised (two wagers minimum: one ENUMERATED multi-policy, one FREEFORM).
- [ ] Full propagation checklist completed or **N/A** with justification.
- [ ] Gas document updated; no unbounded loop regression vs ADR-0008/0009 caps.
- [ ] Security review scheduled before mainnet unified factory.

## Rejected alternatives (for this ADR)

- **Single mode flag without storage isolation:** rejected — risks storage aliasing between bitmask and string pools.
- **Force freeform into bitmask `numOptions`:** rejected — same reasons as ADR-0009 (infinite answer space).
- **Keep three factories forever as the “protocol”:** rejected for **new** development per this ADR; acceptable as **legacy** support.

## Normative relationship to ADR-0009

ADR-0009 remains **Accepted** and is the authoritative description of **freeform semantics** (exact string bytes, `answerId` hashing, caps, revert-on-no-stake). ADR-0010 does **not** redefine those rules; it specifies that **`FREEFORM` mode** in the unified wager **implements** the same behavior as today’s `ParamutuelWagerFreeform`. Wording in ADR-0009 § “Relationship to ADR-0008” (*separate wager types; compositing not in scope*) is **consistent** with ADR-0010: each **deployment** is still one mode; “compositing” there meant **multi-winner policies on string tickets**, which ADR-0010 still excludes from v1.

## Open questions (resolve before / during implementation)

1. **Event topics:** New unified events vs **reuse** `BetPlaced` / `Resolved` names with different signatures (indexer breakage). Prefer explicit **`BetPlacedEnumerated` / `BetPlacedFreeform`** (or namespaced equivalents) and document topic hashes in `docs/ADR-0010-IMPLEMENTATION.md`.
2. **`answerId` domain separation:** ADR-0009 left this open; if unified contract also hashes bitmask ticket ids or other `bytes32` keys, specify **EIP-712-style domain** or fixed **type tags** so `keccak256(bytes(answer))` cannot collide with unrelated uses in the same contract.
3. **Fat ABI vs two interface types:** One bytecode with runtime `revert WrongMode()` vs deploy-time **identical** logic but **different** public interfaces (e.g. via wrapper or minimal proxies) — affects wallet “read contract” UX and MCP tool count.
4. **Indexer transition:** Whether `protocol_version` distinguishes `unified_enum` / `unified_freeform` only, or also maps legacy `v2` / `freeform` rows to the **same** schema for a single codepath (recommended: explicit versions first, then optional normalization layer).
5. **v1 factory retirement:** Whether any network must keep **`ParamutuelFactory`** deployments indefinitely for integrators; affects how aggressively `factoryAddress` in `deployments.json` can point at unified factory only.

## Related

- [`ADR-0008-multi-winner-and-settlement-generalization.md`](ADR-0008-multi-winner-and-settlement-generalization.md)
- [`ADR-0009-freeform-text-wagers.md`](ADR-0009-freeform-text-wagers.md)
- [`docs/PAYOUT-CALCULATION.md`](../../docs/PAYOUT-CALCULATION.md)
