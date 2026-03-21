# Chain and Fee Review

**Status:** Recorded for Checkpoint 1 (`research/execution-roadmap.md`)  
**Date:** 2026-03-20  
**Scope:** Target EVM chains for the current Solidity MVP, measured gas for core flows, approximate live costs, competitive fee benchmarks, and recommended launch defaults.

---

## 1. Summary recommendations

| Decision | Recommendation |
|----------|----------------|
| **Primary launch chain** | **Base** |
| **Secondary expansion** | **Arbitrum** |
| **Avoid for MVP (this codebase)** | **Ethereum mainnet** (recurring per-market deploy cost too volatile) |
| **Non-EVM (e.g. Solana)** | Not a near-term launch target without a full rewrite |
| **Initial protocol fee** | **100 bps (1%)** default; keep **total** fee (protocol + optional extras) **≤ 200–300 bps** at launch |
| **Fee review cadence** | Quarterly, or when monthly handle exceeds **$1M** or competitive landscape shifts materially |

---

## 2. Protocol mechanics relevant to cost

- **`ParamutuelFactory`** deploy is a **one-time** protocol cost.
- **`createMarket`** deploys a **new `ParamutuelMarket` contract per market** → **recurring deployment cost per market**, not a single storage write.
- User flows also include **ERC-20 `approve`** (first time or when allowance exhausted) in addition to **`placeBet`**.

---

## 3. Measured gas (current Solidity implementation)

Source: `forge test --gas-report` on the repo contracts (Solc 0.8.24).

| Operation | Gas (approx.) | Notes |
|-----------|----------------|--------|
| Deploy `ParamutuelFactory` | **2,544,138** | One-time per chain deployment |
| `createMarket` | **avg ~1.11M**, **median ~1.50M**, **max ~1.52M** | Dominant cost; includes `new ParamutuelMarket` |
| `placeBet` | **avg ~124k** | Per bet |
| ERC-20 `approve` (test mock) | **avg ~46k** | Per wallet/spender when needed |
| `resolve` | **avg ~97k** | Per finalization path |
| `retract` | **avg ~66k** | Invalidation path |
| `expire` | **avg ~79k** | Liveness / overdue path |
| `claim` | **avg ~67k** | Per bettor claim |
| `withdrawFees` | *not isolated in gas report* | Small relative to `claim`; ERC-20 transfer + storage updates |

---

## 4. Approximate dollar cost by chain (methodology)

**Formula (L2-style, simplified):**  
`fee_usd ≈ (gas_used × gas_price_gwei × 1e-9) × eth_price_usd`

**Caveats:**

- L2s also have **L1 data / security** components that can deviate from a pure `gas × gwei` model; figures below are **order-of-magnitude** for planning.
- **Gas prices and ETH/USD move daily**; snapshots are **illustrative**, not guarantees.
- **Ethereum mainnet** planning should use **stress** gas prices (e.g. 10+ gwei), not unusually low snapshots.

### 4.1 Snapshots used (indicative)

| Network | Snapshot gas price (oracle) | ETH price (explorer, same session) |
|---------|----------------------------|--------------------------------------|
| Base | ~0.005 gwei | ~$2,137 |
| Arbitrum One | ~0.021 gwei | ~$2,137 |

Sources (explorers, 2026-03-20): [Base gas tracker](https://basescan.org/gastracker), [Arbitrum gas tracker](https://arbiscan.io/gastracker).

### 4.2 Illustrative USD estimates (Base @ ~0.005 gwei, ETH ~$2,137)

| Flow | Gas | ~USD |
|------|-----|------|
| Factory deploy | 2.54M | ~**$0.03** |
| `createMarket` (use ~1.5M) | 1.5M | ~**$0.016** |
| First `approve` + `placeBet` | ~170k | ~**$0.002** |
| `resolve` | ~97k | ~**$0.001** |
| `claim` | ~67k | ~**$0.0007** |

### 4.3 Illustrative USD estimates (Arbitrum One @ ~0.021 gwei, ETH ~$2,137)

| Flow | Gas | ~USD |
|------|-----|------|
| Factory deploy | 2.54M | ~**$0.11** |
| `createMarket` (~1.5M) | 1.5M | ~**$0.067** |
| First `approve` + `placeBet` | ~170k | ~**$0.008** |
| `resolve` | ~97k | ~**$0.004** |
| `claim` | ~67k | ~**$0.003** |

### 4.4 Ethereum mainnet (stress illustration)

At **10 gwei** and **ETH ~$2,137**, `createMarket` at **1.5M gas** ≈ **$32** per market — **poor fit** for permissionless, high-churn market creation unless the design moves to **minimal proxies / clones** or fewer deploys.

---

## 5. Chain comparison (qualitative)

| Criterion | Base | Arbitrum | Optimism | Ethereum L1 | Solana (non-EVM) |
|-----------|------|----------|----------|-------------|------------------|
| Fit for **per-market contract deploy** | **Strong** (low L2 fees) | Strong | Good | **Weak** (cost volatility) | Different stack; rewrite |
| Retail / creator UX | **Strong** (onboarding, familiarity) | Strong DeFi / stablecoin depth | Good | Variable | N/A for current code |
| Tooling / explorers / indexers | Mature | Mature | Mature | Mature | N/A |
| Competitive signal | Large consumer L2 activity | **Paradox** (parimutuel) on Arbitrum | OP Stack ecosystem | Maximum trust anchor | **OpenTote**-class parimutuel exists |

**Conclusion:** **Base first** for lowest friction and creator-led use cases; **Arbitrum second** for DeFi-native users and category adjacency.

---

## 6. Competitive fee benchmarks (comparable / adjacent protocols)

*Note: “Protocol fee” differs by product — pool take vs trading fee vs oracle bonds.*

### 6.1 Direct parimutuel-style

- **Paradox (Arbitrum):** documents **1% commission** on bet sizing (e.g. 101 units in → 100 team tokens; 1 unit to commission pool), with commission routed to earlier bettors rather than protocol rent.  
  Source: [Paradox GitBook](https://paradox-3.gitbook.io/paradox/)

- **OpenTote (Solana):** **configurable vig** per pool; public materials use **illustrative** splits including **double-digit vig** in examples — more “traditional tote” than typical crypto-native social betting.  
  Source: [OpenTote](https://opentote.org/)

### 6.2 Adjacent: prediction / CLOB (not parimutuel, but user expectations)

- **Polymarket:** **most markets fee-free**; fee-enabled markets use a **price-dependent taker fee** with doc-stated **max effective ~1.56%** (crypto fee-enabled) and **~0.44%** (certain sports fee-enabled) at 50¢.  
  Source: [Polymarket — Fees](https://docs.polymarket.com/polymarket-learn/trading/fees)

- **Augur (historical framing):** permissionless markets with **creator fees** often discussed in the **~1–2%** range plus reporter economics; not a parimutuel comparator but relevant for “permissionless creation” fee culture.

### 6.3 Oracle-style resolution (future modular resolver)

- **UMA / optimistic oracle:** economics are typically **bonds and final fees**, not a flat % of betting handle — different UX and accounting.

---

## 7. Fee policy for *this* protocol

### 7.1 Current contract knobs (MVP)

- Factory-level **`protocolFeeBps`** + per-market **optional extra recipients** (`extraFeeBps`), capped by factory **`MAX_TOTAL_FEE_BPS`** (currently **1000 = 10%** in code).
- Fees are charged at **finalization** (`resolve` / `retract` / `expire`), which means **failed or invalidated markets can still pay protocol fee** unless policy or code changes.

### 7.2 Recommended launch defaults

- **Default protocol fee:** **100 bps (1%)** — aligns with **Paradox headline** and sits **at or below** Polymarket’s fee-enabled **effective** caps for many trades.
- **Total fee ceiling (protocol + extras):** target **≤ 200 bps** for mainstream markets; **≤ 300 bps** as a hard ceiling early in production if governance insists on headroom.
- **Revisit `MAX_TOTAL_FEE_BPS`:** **10%** is **far above** crypto-native peer benchmarks; consider lowering the cap for production or gating high fees behind explicit UI warnings and governance.

### 7.3 Sensitivity (fee dominates L2 gas for typical pots)

On Base/Arbitrum, **gas is usually negligible** vs **fee bps** for meaningful stake sizes.

Example **$1,000** conceptual pot:

| Total fee | Amount |
|-----------|--------|
| 1% | $10 |
| 2% | $20 |
| 3% | $30 |

### 7.4 Rough protocol revenue scenarios (gross, illustrative)

| Monthly handle | @ 1% | @ 2% | @ 3% |
|----------------|------|------|------|
| $100k | $1k | $2k | $3k |
| $1M | $10k | $20k | $30k |
| $10M | $100k | $200k | $300k |

### 7.5 Fee review cadence

- **Quarterly** review of `protocolFeeBps` and competitor moves.
- **Event-triggered** review if monthly handle **> $1M**, or if **retract/expire** fee backlash appears in support metrics.

---

## 8. Follow-ups (engineering / product)

1. **Production gas report** on target testnet/mainnet RPC (not only Foundry averages).
2. **Explicit gas benchmark** for `withdrawFees` in tests.
3. **Policy decision** on whether protocol fee applies to **`retract` / `expire`** at full rate.
4. If market creation volume explodes: **EIP-1167 minimal proxy** or **clone** pattern to cut recurring `createMarket` cost.

---

## 9. References

- Internal: `research/execution-roadmap.md` (Checkpoint 1), `research/checkpoint-1-chain-and-fee-viability-study.md`, `research/market-viability.md`
- External: [Base gas tracker](https://basescan.org/gastracker), [Arbitrum gas tracker](https://arbiscan.io/gastracker), [Paradox GitBook](https://paradox-3.gitbook.io/paradox/), [OpenTote](https://opentote.org/), [Polymarket fees](https://docs.polymarket.com/polymarket-learn/trading/fees)
