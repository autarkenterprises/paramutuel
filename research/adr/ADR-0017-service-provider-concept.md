# ADR-0017: Service Provider concept — hosting, offered services, and discoverability

Date: 2026-05-07
Status: **Proposed** (design ADR; implementation tracked separately).
Builds on: [ADR-0001](ADR-0001-core-immutability-and-delegated-resolution.md) (delegated resolution), [ADR-0006](ADR-0006-surface-separation-self-custody-vs-assisted-ux.md) (surface separation), [ADR-0007](ADR-0007-assisted-transaction-gateway-and-approval-paths.md) and [ADR-0016](ADR-0016-assisted-ux-funds-management.md) (assisted UX), [ADR-0010](ADR-0010-unified-wager-enumerated-and-freeform.md) (V3 protocol), [ADR-0015](ADR-0015-safe-controlled-treasuries.md) (Safe treasuries), [`AGENTS.md`](../../AGENTS.md) practice **#4**.

## Context

The Paramutuel protocol is permissionless — any address can be a proposer, resolver, betting closer, or resolution closer of a given wager. The codebase ships a *service layer* (`service/indexer/`, `service/proposition/`, `service/resolution/`, `service/explorer/`, `service/control_panel/`, plus the planned `service/atg/` from ADR-0016) that the project itself operates. These two facts are easy to confuse.

`research/go-to-market-strategy.md` and the implicit posture across `docs/PROJECT-REVIEW.md` use the phrase **"service entity"** for the project's operating role. The phrase has been load-bearing without a single ADR pinning down what the service entity *is*: which services it offers as a product (vs internal tooling), where they live operationally, what wager creators can rely on, and how a creator (human or agent) discovers the service entity in the first place.

The Resonance Exchange ARG (`docs/MICROWONK-ARG.md`) has already surfaced this implicitly — it names a resolver address (`config/microwonk-wallets.json` `roles.resolver`, currently `0xe203533591d3f1B4C4b33ae3047dECEc77454233`) as the resolver on every microwonk-issued wager. The project commits, through that address, to dispatch resolutions per the Co-ordinator's plan. That commitment is what a Service Provider is. Today it is **only documented in ARG-internal files**; an external creator browsing the protocol cannot find it.

This ADR pins the concept down: name it, list its offerings, decide where each lives, and specify how a wager creator (or bettor, or agent) discovers it.

## Decision

1. **Name the role: "Paramutuel Service Provider"** (capitalized when referring to the project's operating role; lowercase "service provider" when referring to the abstract role any other operator could fill). The repo's existing **service layer** is the implementation of the Paramutuel Service Provider's offerings — same code, but the *role* is distinct from the *modules*.

2. **Offered services (the product surface).** Each service is either **public** (a creator / bettor / agent can rely on it as a paid or free product) or **operator-only** (used by the project to run its own ARG dispatch and not exposed as a third-party offering).

   | Service | Today | Public or operator-only | Wager-creator handle |
   |---------|-------|-------------------------|----------------------|
   | **Indexer + JSON API** (`service/indexer/`) | Hosted at Cloud Run; `explorerApiBase` in `config/deployments.json` per network | **Public** (read-only, no SLA) | URL string |
   | **Explorer UI** (`service/explorer/` + `site/explorer.html`, `site/resonance-explorer.html`) | Hosted on Cloud Run + GitHub Pages | **Public** | URL string |
   | **Resolution Service** (`service/resolution/`) | Operator runs the dispatch loop; the *resolver address* on-chain is the public handle | **Public** as a *resolver-by-reference*: a wager creator names the published resolver address; the project commits to resolving that wager per a published policy | **Resolver address (per network)** |
   | **Proposition Service** (`service/proposition/`) | Operator-only ingest scheduler; not exposed as third-party | **Operator-only** today; possibly Public later (out of scope here) | n/a |
   | **Control Panel** (`service/control_panel/`) | Operator-only token-gated CLI / web | **Operator-only** | n/a |
   | **MCP Server** (`mcp_server/`) | Distributed via PyPI as **`paramutuel-mcp`**; agents run their own | **Public** as a *package*, not as a hosted service | PyPI name |
   | **Bet Scout** (`agents/paramutuel_bettor/`) | Distributed via PyPI as **`paramutuel-bettor-agent`** + GHCR fleet image | **Public** as a *package* | PyPI / GHCR name |
   | **Assisted Transaction Gateway** (`service/atg/`, ADR-0016) | Not yet implemented | **Public** when live | URL string + intent EIP-712 domain |

   The above table is the canonical Service Provider catalog. Other entries (a faucet, a search API, etc.) require an ADR amendment to land in the catalog.

3. **Hosting model is uniform: Cloud Run for hosted services.** Indexer, explorer, resolution, proposition, ATG all follow the same Cloud Run pattern documented in `docs/CLOUD-RUN-HOSTING.md` and `docs/INDEXER-HOSTING.md`. PyPI for distributed packages. GitHub Pages for the static marketing site (`site/`). One single `service/<svc>/Dockerfile` per service, env-var configured, with a documented free-tier ceiling and a documented upgrade path (Render is no longer used per the 2026-03-31 transition recorded in `LESSONS.md` L-004).

4. **Discoverability: a public service-provider manifest at a stable URL.** The manifest is structured JSON, mirrors `agents/subagent-manifest.json`'s posture, and lives at `agents/service-provider-manifest.json` in the repo (and at `https://raw.githubusercontent.com/autarkenterprises/paramutuel/master/agents/service-provider-manifest.json` for crawlers / agents that don't clone the repo). Schema:

   ```json
   {
     "schemaVersion": 1,
     "provider": {
       "name": "Paramutuel Service Provider (Autark Enterprises)",
       "homepage": "https://...",
       "contact": "..."
     },
     "networks": {
       "baseSepolia": {
         "factoryAddress": "0x...",          // mirrors deployments.json
         "indexer": { "baseUrl": "https://..." },
         "explorer": { "homepage": "https://..." },
         "resolver": {
           "address": "0x...",
           "policyUrl": "https://...",
           "feeBps": 0
         },
         "atg": { "baseUrl": "https://...", "modes": ["sponsored"] }
       },
       "baseMainnet": { ... }
     },
     "packages": {
       "mcp": "paramutuel-mcp",
       "betScout": "paramutuel-bettor-agent"
     }
   }
   ```

   The manifest is the authoritative discoverability primitive. The `site/` marketing pages link to it; the dApp / Resonance pages link to it; the bet scout's `paramutuel-bettor health` reads it; future external integrators (LLM agents, third-party indexers, alternative UIs) consume it.

5. **The published resolver policy is a separate doc** (suggested path: `docs/SERVICE-PROVIDER-RESOLVER-POLICY.md`). It states: which kinds of wagers the project will resolve as the resolver-by-reference; what evidence sources the resolver consults; how disputes are surfaced (or are not); the fee, if any, taken via `extraFeeRecipients` at wager creation; and the escalation path when a resolver-by-reference wager goes wrong (operator response window, partial-refund commitment via `retract`, etc.). Without this policy doc, naming the resolver address is just trust — with it, the resolver address is a *product* with a stated contract.

6. **Marketing surface integration.** `site/operator.html` already aggregates operator-internal links. A new public-facing summary section on `site/index.html` and `site/resonance.html` points wager creators at the service-provider manifest plus the resolver policy doc. The Resonance landing already routes ARG creators implicitly; this change makes the same offerings available to non-ARG creators.

7. **Services not on the catalog are not committed offerings.** Anything internal to ARG dispatch (the proposition service's microwonk feeds, the control panel) is **operator-only** and not advertised. A wager creator who tries to use those endpoints discovers them only via the operator hub (which is itself operator-only access). Drift — adding an internal service to the public manifest without an ADR amendment — is a failure mode this section exists to prevent.

## Decision points

### Open questions (require user input before implementation)

1. **Resolver fee.** Will the resolver-by-reference resolver charge a fee on resolved wagers (via `extraFeeRecipients` / `extraFeeBps` at wager creation)? Suggested default: 0 bps for the ARG cycle, revisited at mainnet. Confirm.
2. **Resolver policy scope.** Initial policy candidates: ARG / Resonance / ctrlcreep wagers (in-character), wagers with resolution criteria stated in unambiguous English referring to public events (sports, market data, news outcomes). Out of policy: wagers with private-fact resolution criteria, wagers in non-English propositions (operator can't validate). Confirm or adjust.
3. **Manifest URL stability.** Suggested: serve the manifest from the GitHub Pages domain (e.g. `paramutuel.example.com/service-provider-manifest.json`) with a 5-minute cache. The raw GitHub URL is the fallback. Confirm GitHub Pages slot.
4. **Resolver address rotation.** Today the resolver address is a hot-key EOA. Per ADR-0015's boundary, bot-frequency signing keys remain EOAs — but the *committed-to* resolver address is sticky: rotating it invalidates every existing wager that named the old address as resolver. Policy: do not rotate the resolver address except via a documented migration with overlap (publish both addresses for some weeks; new wagers use the new address; old wagers continue under the old address until they all settle). Confirm.
5. **SLA or no SLA on the indexer / explorer / ATG.** Suggested: no SLA at the moment; "best-effort, hosted on Cloud Run free tier" disclaimer in the manifest. A formal SLA only makes sense after revenue exists. Confirm.
6. **Public proposition-as-a-service in a future ADR?** Out of scope for ADR-0017 but worth flagging — the proposition service has the shape of an offer (project ingests feeds, dispatches drafts) that a creator might pay for. If interest materializes, dedicated ADR.

### Settled

- Service Provider name and abstract-vs-concrete distinction.
- Cloud Run as the canonical hosting model for hosted services.
- A single JSON manifest is the authoritative discoverability primitive.
- The resolver address is a product, not just a wallet.

## Success criteria

- `agents/service-provider-manifest.json` exists on `master`, validates against the schema in §Decision item 4, and is referenced from `site/index.html` and `site/resonance.html`.
- `docs/SERVICE-PROVIDER-RESOLVER-POLICY.md` exists, names the policy scope, the fee, the rotation rules, and the dispute-escalation path.
- A wager creator who lands on the marketing site (or who reads only the manifest URL out-of-band) can answer: which network is canonical? what is the factory address? what is the indexer URL? what address can I name as resolver and what will that resolver do? without spelunking through the repo.
- The bet scout's `paramutuel-bettor health` reports the manifest contents, so an LLM-driven agent gets the same discoverability path as a human.
- The manifest survives one Resonance Exchange ARG campaign cycle without drift between catalog and live deployments (audited at the next monthly practices review per L-007).

## Failure criteria

- Manifest claims a service the project does not actually run. Mitigation: every entry in the manifest must point at a working URL or address verified at the time of the commit; manifest is not a wishlist.
- Resolver policy is published, then a wager-in-policy goes unresolved and the operator misses the response window. Mitigation: response-window monitoring and explicit escalation to a `retract` on operator-acknowledged failure; documented in the policy doc and `service/resolution/`.
- Service catalog drift — operator adds a service to `service/` without manifest entry, or a manifest entry without an actual service. Mitigation: ADR-0017 amendment required to add catalog entries; a CI-shaped manifest validator (see §Follow-ups) keeps the schema honest.
- Resolver address compromise. ADR-0015 covers Safe-controlled treasuries but explicitly leaves bot-frequency wallets (resolver, proposer, microwonks) as EOAs. A resolver compromise is a *Service Provider* incident — the policy doc must state that compromise of the resolver triggers an emergency `retract` on outstanding wagers under that address, before the attacker can resolve maliciously.

## Rejected alternatives

- **Make the entire service layer public-facing without a Service Provider concept.** Rejected — conflates internal tooling with offered product. The control panel and proposition service have no mode in which they should be public; the catalog distinction is load-bearing.
- **Discoverability by repo-clone only.** Rejected — locks out integrators who don't want to clone a Foundry / Python repo.
- **One resolver address per wager type / category.** Rejected for now — adds operational complexity (multiple hot keys, multiple rotation schedules) for marginal categorisation benefit. The policy doc handles category boundaries via prose.
- **Resolver-as-DAO** (some on-chain governance over resolver decisions). Rejected for the first cycle — out of scope and presupposes a DAO that does not exist. Future ADR if and when it does.

## Follow-ups

- **Manifest validator.** Tiny CI-shaped check (Python + jsonschema, or a hand-rolled validator) that the manifest matches schema and that every URL/address in it is reachable / has code. Lands as a pre-commit hook or CI step once CI is wired.
- **Resolver policy doc.** `docs/SERVICE-PROVIDER-RESOLVER-POLICY.md` is a follow-up commit on the same branch as the manifest; ADR-0017 specifies what it must contain but does not write it.
- **Public proposition-as-a-service.** If there is third-party demand, dedicated ADR — out of scope here.
- **SLA tier.** When revenue arrives, SLA-tiered offerings ("free best-effort", "paid tier with response-time commitments") are a natural extension. Future ADR.

## After Action Report

**AAR date:** Pending (populated after the manifest + resolver policy doc land and survive one ARG cycle without drift).
**AAR status:** Pending

**Outcome vs success criteria:** to be populated.

**Outcome vs failure criteria:** to be populated.

**Lessons:** to be populated. Likely candidates: whether the catalog distinction (public vs operator-only) holds in practice, whether external integrators discovered the manifest without prompting, whether resolver-by-reference attracted any non-ARG wagers.

**Follow-ups:** to be populated.

**Revision schedule:** at first non-ARG wager that names the project's resolver, then quarterly during operation.
