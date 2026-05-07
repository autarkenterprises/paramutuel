# ADR-0017 implementation notes (Service Provider concept)

**Status:** Design ADR — implementation gated on operator input on §Open questions, primarily the resolver policy details.
**ADR:** [`research/adr/ADR-0017-service-provider-concept.md`](../research/adr/ADR-0017-service-provider-concept.md)

This file is the runbook side of ADR-0017. Today it is a checklist of work-not-yet-done; entries become checked off as each step lands.

## Implementation order

1. **Author `agents/service-provider-manifest.json`.** Schema per ADR-0017 §Decision item 4. Populated from `config/deployments.json` (factory addresses, indexer URLs, explorer URLs), `config/microwonk-wallets.json` (resolver address), `pyproject.toml` (PyPI package names). One file, validates against an inline JSON schema.
2. **Author `docs/SERVICE-PROVIDER-RESOLVER-POLICY.md`.** Policy scope (in-policy / out-of-policy categories), fee, rotation rules, dispute escalation, response-window. Per ADR-0017 §Decision item 5 the resolver address is a product; this doc is its product spec.
3. **`site/index.html` and `site/resonance.html` link cards.** Public-facing summary section pointing at the manifest URL + the resolver policy doc. Stylistically aligned with the Resonance skin on `resonance.html` and the bare-protocol skin on `index.html`.
4. **Bet scout integration.** `paramutuel-bettor health` reports the manifest contents (canonical factory, resolver, indexer per network) so an LLM-driven agent gets the same discoverability path as a human.
5. **Manifest validator.** Tiny CI-shaped check that schema is valid and URLs/addresses resolve. Lands as `script/check-service-manifest.py` plus a CI step.

## Open questions (mirror of ADR-0017 §Decision points)

Each must be resolved by operator input before the corresponding step lands:

1. Resolver fee value (suggested 0 bps for ARG; revisit at mainnet).
2. Resolver policy scope — in / out of policy categories.
3. Manifest URL on the GitHub Pages domain.
4. Resolver-address rotation policy (overlap window length).
5. SLA or no-SLA disclaimer.
6. Whether to flag "proposition-as-a-service" as a forthcoming offering.

## Out of scope

- Public proposition-as-a-service — see ADR-0017 §Follow-ups.
- Resolver-as-DAO — see ADR-0017 Rejected alternatives.
- Per-category resolver addresses — see ADR-0017 Rejected alternatives.
