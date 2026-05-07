# ADR-0016 implementation notes (assisted UX gateway, funds-managed)

**Status:** Design ADR — implementation gated on operator input on §Open questions.
**ADR:** [`research/adr/ADR-0016-assisted-ux-funds-management.md`](../research/adr/ADR-0016-assisted-ux-funds-management.md)

This file is the runbook side of ADR-0016. Today it is a checklist of work-not-yet-done; entries become checked off as each step lands.

## Service shape

`service/atg/` (Assisted Transaction Gateway) — new peer to existing
services. Same Python / Cloud Run pattern as
:mod:`service.resolution`:

```
service/atg/
├── __init__.py
├── server.py           # HTTP server (intent submission, status, operator dash)
├── intent.py           # EIP-712 intent encoding / validation
├── relay.py            # cast send wrapper; gas estimation; max-gas-price guard
├── replenish.py        # ETH-balance threshold loop; DEX swap calls
├── oracle.py           # surcharge oracle (TWAP read of designated DEX pair)
├── caps.py             # daily / per-address cap accounting in SQLite
├── tier_policy.py      # Tier-1 whitelist per network; Tier-2 refusal logic
├── tests/
│   └── test_*.py       # unit coverage for math + cap + tier paths
└── README.md           # operator runbook
```

## Implementation order

Per AGENTS.md practice #1 (TDD), each step ships test-first:

1. **`intent.py` + tests.** EIP-712 domain, struct, signature verification. Reject malformed / expired / replayed intents.
2. **`tier_policy.py` + tests.** Per-network Tier-1 list; Tier-2 refusal returns a structured error.
3. **`caps.py` + tests.** SQLite-backed daily / per-address counters. Idempotent under concurrent intent submission (use the indexer's `INSERT OR IGNORE` pattern).
4. **`oracle.py` + tests.** TWAP fetch from designated DEX pair; mocked DEX response in unit tests; live RPC path covered by the extended suite per ADR-0013.
5. **`relay.py` + tests.** Compose `cast send` calldata for the wager + the gas-surcharge transferFrom (reimbursed) or just the wager (sponsored). Max-gas-price guard.
6. **`replenish.py` + tests.** Threshold-driven swap loop. Dry-run mode for operator review (analogous to control_panel's `--allow-execute`).
7. **`server.py`.** HTTP shell wiring the above modules. Intent submission, status query, operator dashboard. Token-gated operator endpoints via `service.control_panel.security.token_authorized`.
8. **`site/resonance-bet.html` integration.** Detect Tier-1 collateral; surface "use assisted path" CTA when the user lacks ETH. Fallback to unassisted on Tier-2 or cap exhaustion. Existing wallet-bound flow remains untouched.

## Open questions (mirror of ADR-0016 §Decision points)

Each must be resolved by operator input before the corresponding step lands:

1. Sponsored mode on Base Sepolia, reimbursed mode on mainnet — or sponsored on mainnet too for an initial period?
2. Daily sponsored-mode ETH cap value (suggested 0.05 ETH/day on Sepolia).
3. Per-address rate limit in sponsored mode (suggested 1 / hour).
4. Tier-1 collateral list per network.
5. Reimbursed-mode markup over instantaneous gas (suggested 15%).
6. DEX choice for Tier-1 swaps (suggested Uniswap V3 on Base).
7. Traditional relayer first vs ERC-4337 path.
8. Whether to refuse sponsorship outside Resonance origin.

## Out of scope

- Account-abstraction (ERC-4337) path — deferred per ADR-0016 §Decision point 7.
- Public mempool relay — see ADR-0016 Rejected alternatives.
- Tier-2 surcharge model — see ADR-0016 Failure criteria mitigation; if Tier-2 demand materialises, dedicated ADR.
