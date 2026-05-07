# ADR-0016: Assisted UX gateway with sustainable funds management

Date: 2026-05-07
Status: **Proposed** (design ADR; implementation tracked separately).
Builds on: [ADR-0006](ADR-0006-surface-separation-self-custody-vs-assisted-ux.md) (surface separation), [ADR-0007](ADR-0007-assisted-transaction-gateway-and-approval-paths.md) (assisted transaction gateway architecture), [ADR-0015](ADR-0015-safe-controlled-treasuries.md) (Safe-controlled treasuries), the testnet-as-production posture of the Resonance Exchange ARG, [`AGENTS.md`](../../AGENTS.md) practice **#4**.

## Context

ADR-0007 specified the assisted-tx gateway's architecture (split surfaces, pluggable approval paths Permit / Permit2 / approve+act, replaceable execution adapter). It explicitly left the **funds-management** question open: how the relayer pays gas in ETH while bettors stake in arbitrary ERC-20 collateral, without the relayer running out of float, without the project absorbing unbounded subsidy, and without exposing the gateway to abuse.

The Resonance Exchange ARG raises the urgency. The ARG's user-visible flow (`site/resonance-bet.html`) lands a curious onlooker on a wallet-bound page; if they don't have Base Sepolia ETH, they drop out. ADR-0007's revisited AAR (2026-05-07) records that the funds question is the load-bearing one for actual deployment and warrants its own ADR — this one. ADR-0007 is **not superseded**; ADR-0016 is the implementation-shaped follow-on.

The funds question has three intertwined sub-questions:

1. **Payment model.** Is the user reimbursing the relayer for gas (sustainable, complex), or is the project absorbing gas costs (simple, capped, only feasible for testnet or a marketing-budget mainnet rollout)?
2. **Float dynamics.** How does the relayer's ETH float stay topped up? Where does it refill from? What triggers an alert / pause?
3. **Token tier policy.** Tier-1 stables (USDC) can be converted back to ETH cheaply via deep liquidity; Tier-2 arbitrary ERC-20 cannot. What does the gateway do when a wager's collateral is Tier-2 — refuse to sponsor, hold the collateral indefinitely, or charge a higher surcharge?

## Decision

1. **Two-mode operation, runtime-configurable per network.** Mode is selected at gateway boot, not per-transaction. **Sponsored mode** (the project absorbs gas costs from a documented float; sustainable only at bounded campaign scale — fits the ARG) versus **Reimbursed mode** (the user pays a small surcharge in the bet's collateral token; sustainable at any scale; necessary for mainnet retail exposure). Both modes share the rest of the gateway architecture.

2. **Float account is a Safe** (per ADR-0015) holding ETH for gas. The gateway service has a *spend-from-Safe* signer with a sub-Safe budget, **not** the full Safe owners. Compromise of the gateway's spending key drains at most the budget allocation since the last refill, never the full Safe.

3. **Sponsored mode (ARG / testnet posture):**
   - Daily ETH-spend cap. When hit, the gateway returns a structured error to `site/resonance-bet.html`; the page falls back to the unassisted "needs Base Sepolia ETH" path. Cap value tunable; default proposed in §Decision points.
   - Per-onlooker rate limit (by wallet address, not IP — Resonance is wallet-bound). One sponsorship per address per hour by default.
   - No collateral surcharge — the user's bet amount is forwarded to the wager unchanged.
   - Sponsored-only token list: gateway refuses to sponsor wagers whose collateral is not on a whitelist (default: USDC on Base Sepolia + Base Mainnet). Arbitrary ERC-20 collateral falls back to unassisted; this is the **explicit** answer to the "how not to run out of funds when facilitating arbitrary ERC-20" question — we don't, in sponsored mode.

4. **Reimbursed mode (mainnet retail / sustainable posture):**
   - Bettor signs an EIP-712 intent that includes `bet_amount` and `gas_surcharge_amount` in the bet's collateral token. The relayer's settlement transaction transfers `bet_amount + gas_surcharge_amount` from the bettor (via Permit / Permit2 / pre-approve), forwards `bet_amount` to the wager's `placeBet`, and retains `gas_surcharge_amount` in the relayer's collateral-balance ledger.
   - Gateway maintains a per-token **surcharge oracle** that prices ETH gas in collateral units. The oracle reads a fixed-window TWAP from a designated DEX pair (Uniswap V3 on Base for the Tier-1 list); for Tier-2 collateral with no deep pool, the gateway **refuses sponsorship** and the page falls back to unassisted.
   - **Float replenishment loop:** on a schedule (default: hourly), the gateway swaps accumulated Tier-1 collateral back to ETH on the same designated DEX, with slippage limits. The schedule is driven by ETH-balance thresholds: low-water triggers a swap; high-water triggers a swap *into* a chosen Tier-1 (so the gateway doesn't hoard ETH it doesn't need).
   - Surcharge includes a small markup over instantaneous gas cost to absorb price volatility between intent signing and execution. Default markup proposed in §Decision points.

5. **Tier policy is explicit (and reuses ADR-0007's tier names):**
   - **Tier 1** — gateway-sponsored or gateway-reimbursed. USDC + a short, named list of stablecoins with deep DEX liquidity. Per network.
   - **Tier 2** — explicitly **unassisted**. Pages display "this wager's collateral is not on the assisted list — wallet must hold Base Sepolia ETH". No sponsorship, no surcharge — the unassisted path is the supported path for Tier 2.

6. **Abuse and observability:**
   - Per-user / per-day sponsorship cap (sponsored mode).
   - Per-user / per-day surcharge cap (reimbursed mode) so a runaway agent can't exhaust the relayer's collateral float in one direction.
   - Replay protection via EIP-712 nonce + expiry on every intent.
   - Max-gas-price ceiling — the gateway refuses to sponsor at gas prices above a configured cap.
   - All gateway actions emit a structured log (intent, executed txhash, gas paid, surcharge collected, slippage on any swap). Operator dashboard at `service/atg/operator.html` (new) reads the log; mirrors the operator-hub pattern in `site/operator.html`.

7. **Service location.** The Assisted Transaction Gateway lives at `service/atg/` as a peer to the existing services (indexer, proposition, resolution, control_panel, explorer). Same hosting model — Cloud Run, env-var config, `service.env` loader. New Python service following the same structure as `service/resolution/`. Implementation gated on Decision-points sign-off below.

## Decision points

### Open questions (require user input before implementation)

1. **Sponsored mode for ARG, reimbursed mode for mainnet retail — confirmed?** Or does the project want sponsored mode on mainnet too (marketing budget) for an initial period?
2. **Daily sponsored-mode ETH cap on Base Sepolia.** Suggested default: 0.05 Base Sepolia ETH/day, sized so a 24-hour exhaustion scenario costs at most one campaign-day of microwonk operation. Confirm or override.
3. **Per-address rate limit in sponsored mode.** Suggested: 1 sponsored bet / wallet / hour. Confirm.
4. **Tier-1 collateral list per network.** Suggested:
   - Base Sepolia: USDC only (the canonical test USDC, address per `config/deployments.json`).
   - Base Mainnet: USDC + USDT (both have deep Base liquidity). Confirm or expand.
5. **Markup over instantaneous gas cost in reimbursed mode.** Suggested: 15% baseline, with a documented post-launch tuning window. Confirm or specify a different starting point.
6. **DEX choice for Tier-1 swaps.** Suggested: Uniswap V3 on Base. Confirm or specify Aerodrome / other.
7. **Account-abstraction (ERC-4337) path** vs **traditional relayer** for the first implementation. AA gives composability and a cleaner UX path for Permit / Permit2; traditional relayer is simpler to ship. Suggested: traditional relayer first, AA path deferred. Confirm.
8. **Whether the gateway refuses sponsorship outside the Resonance Exchange origin** (i.e. only sponsor bets that originate from `resonance-bet.html`, not arbitrary callers). Reduces blast radius but couples the gateway to UI provenance — possibly a soft signal, not a hard refusal.

### Settled

- The architectural shape from ADR-0007 (split surfaces, pluggable paths, replaceable adapter) is unchanged.
- Tier-2 collateral is unassisted on both nets — no exotic-collateral sponsorship attempts.
- Float account is a Safe, with a sub-Safe budget for the gateway's spend-from key.

## Success criteria

- Sponsored-mode gateway live on Base Sepolia in time for the next ARG campaign cycle, refusing to sponsor wagers outside the Tier-1 list and respecting the daily / per-address caps.
- A human onlooker landing on `site/resonance-bet.html` with no Base Sepolia ETH and a bet on a Tier-1-collateral wager can complete the bet via the gateway. The path is observable end-to-end in the operator dashboard.
- Per-day cap exhaustion produces a clear UX fallback (the unassisted path remains functional), not a stuck page.
- Reimbursed-mode gateway on Base Mainnet exists before the first mainnet retail wager, with a documented surcharge oracle and a working replenishment loop. The `service/atg/` test suite has unit coverage for the surcharge math, intent validation, and the replenishment threshold logic. Live RPC paths covered by the extended suite per ADR-0013.

## Failure criteria

- Gateway runs out of float before the daily cap should have triggered. Mitigation: cap is enforced at intent-acceptance time, not at execution time, with a small reserve to absorb in-flight intents.
- Reimbursed-mode surcharge oracle drifts and the gateway becomes a free-ETH faucet. Mitigation: the oracle uses a TWAP, not spot; markup absorbs short-term volatility; an upper bound on `gas_surcharge_amount` per intent prevents runaway.
- A Tier-1 token loses its peg or its DEX liquidity dries up. Mitigation: per-token whitelist is operator-controlled and can be removed without a redeploy; Tier-2 fallback path is the documented behaviour for any removed token.
- Gateway spend-from key is compromised. Mitigation: the key has a budget allocation, not full Safe ownership; the budget is set on the order of one campaign-day of operating cost, refilled via Safe transactions; compromise drains at most one budget cycle.
- Sponsorship is exploited (a single attacker exhausts the daily cap with throwaway addresses). Mitigation: per-address rate limit; signed-intent attestation tied to a wallet address; gateway refusal at the rate-limit threshold.

## Rejected alternatives

- **Subsidy without per-day caps.** Rejected — turns the gateway into a public ETH faucet. Caps are non-negotiable.
- **Sponsorship for arbitrary ERC-20 collateral.** Rejected — no path to refill the relayer's ETH float for Tier-2 collateral without manual intervention; "we don't sponsor exotic collateral" is the explicit, supportable answer to the funds question.
- **Per-transaction collateral selling on every bet.** Rejected as over-frequent — replenishment runs on a schedule, not synchronously per intent. Synchronous swaps would add latency to every bet.
- **Public mempool relay** (let users sign and any relayer pick it up). Rejected for the gateway's first cut — the project-operated path is simpler to reason about; a public-relay extension can land later if there is demand.
- **Storing the gateway's spend-from key as a full Safe owner.** Rejected per the budget-allocation pattern in §Decision item 2 — a hot key on a multisig defeats the multisig.

## After Action Report

**AAR date:** Pending (populated after sponsored-mode goes live on Base Sepolia).
**AAR status:** Pending

**Outcome vs success criteria:** to be populated after first ARG campaign cycle observes the gateway behaviour end-to-end.

**Outcome vs failure criteria:** to be populated.

**Lessons:** to be populated. Likely candidates: per-day cap calibration (was it too low / too high for ARG demand?), oracle drift behaviour, replenishment-loop frequency vs swap-cost tradeoff.

**Follow-ups:** to be populated. Candidates: AA-path adapter, public-relay extension, Tier-2 surcharge model if Tier-2 demand materialises.

**Revision schedule:** at first ARG cycle that includes the gateway, then at mainnet readiness gate (reimbursed mode), then quarterly for cap / markup tuning during operation.
