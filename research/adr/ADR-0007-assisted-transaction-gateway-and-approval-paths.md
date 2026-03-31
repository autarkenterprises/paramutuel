# ADR-0007: Assisted transaction gateway with pluggable approval paths

## Status

Accepted

## Date

2026-03-30

## Context

Website users need reduced friction (ideally no ETH requirement) while interacting with unchanged Paramutuel contracts.

Gas abstraction introduces multiple moving parts:

- user operation execution (relayer/bundler/paymaster stack)
- allowance setup for market contracts
- fee recovery and abuse controls

Asset behavior varies:

- Some assets implement EIP-2612 permit.
- Others can be handled via Permit2.
- Others require regular `approve`.

The system needs a generalized flow that works across many ERC-20 assets, plus safer, operationally stable "happy path" defaults for website users.

## Decision

1. **Adopt an upper-layer Assisted Transaction Gateway (ATG)**:
   - Website sends signed intents to an off-chain gateway service.
   - Gateway chooses execution strategy and submits on-chain transactions.
   - Core protocol contracts remain untouched.

2. **Use pluggable approval paths** in this priority order:
   - **Path A:** Native EIP-2612 permit + sponsored execution.
   - **Path B:** Permit2 signature path + sponsored execution.
   - **Path C:** Sponsored `approve` then sponsored action (two-step fallback).

3. **Execution adapters are replaceable**:
   - Initial adapter may use a relayer with policy controls.
   - Account-abstraction/paymaster adapter can be added later behind the same ATG interface.
   - Website and policy logic call ATG, not a specific execution backend.

4. **Dual collateral support tiers**:
   - **Tier 1 (happy path):** USDC + selected stablecoins with mature liquidity/tooling.
   - **Tier 2 (general):** Any ERC-20 collateral with best-effort path detection and explicit UX warnings.

5. **Safety and economics controls are mandatory**:
   - per-user and per-asset sponsorship limits
   - nonce/replay protections
   - max fee/slippage policy for sponsored actions
   - audit logs and cost attribution per market/user/collateral

## Consequences

### Positive

- Future-proofs gas abstraction by decoupling website UX from a single infra vendor or standard.
- Supports broad ERC-20 compatibility through layered fallbacks.
- Preserves protocol purity and dApp independence.

### Tradeoffs

- Requires backend ops, monitoring, and anti-abuse systems.
- Permit2/relayer integrations add third-party operational dependencies.
- Website UX must communicate sponsorship limits and fallback behavior clearly.
