# Market research & product thesis

> **Working title:** the repository currently uses “Paramutuel” / “paramutuel” as a descriptive label. A distinct **product name** should be chosen before public launch.

This document records competitive research and the strategic thesis for the project: **permissionless market creation** and **decentralized resolution** for **arbitrary propositions**, in analogy to Augur in the prediction-market space—but for **parimutuel / prop-style pooling** rather than order-book or AMM-style prediction markets.

---

## Distinction from prediction markets (peer group, not direct substitute)

**Prediction markets** typically require convergence of willing counterparties or market-making liquidity; they are a **peer group** that competes indirectly for attention and capital, but are **not** treated here as direct functional substitutes for parimutuel prop pools.

---

## Competitive landscape (non-exhaustive)

### Direct or strong analogs: parimutuel / pool-style on-chain betting

| Project | Notes | Source |
|--------|--------|--------|
| **OpenTote** | Describes itself as decentralized **parimutuel** betting on **Solana**; tote-style mechanics (win/place/show, exotics, multi-race). Strong direct analog; oriented toward racing/tote use cases rather than open-ended arbitrary text propositions. | [opentote.org](https://opentote.org/) |
| **Paradox** | **Parimutuel** protocol on **Arbitrum**; pool-based odds, team tokens, fee distribution to earlier bettors. Docs note v1 relies on a **multisig** for results—centralized resolution relative to full decentralization. | [Paradox GitBook](https://paradox-3.gitbook.io/paradox/) |
| **Poolprops** | Described in third-party listings as Solana sports **prop** / pool-style betting; **verify independently** (weaker primary-source confirmation than OpenTote/Paradox). | e.g. [soladex.io/project/poolprops](https://www.soladex.io/project/poolprops) |

### Adjacent: on-chain props / sportsbook (different mechanism, overlapping demand)

| Project | Notes | Source |
|--------|--------|--------|
| **Overtime** | **Player props** on-chain; users trade via an **AMM**, receive ERC-20 positions; oracle settlement. Same *user intent* (props) as some of our markets, different *market structure* than parimutuel. | [Medium: Player Props on Overtime](https://medium.com/@OvertimeMarkets.xyz/introducing-player-props-on-overtime-135f356c9aea) |
| **Azuro** | Infrastructure for on-chain sports / “predictions” apps; live betting, modular contracts. Competes for sports-betting mindshare; not the same as permissionless arbitrary parimutuel props. | [Azuro blog](https://blog.azuro.org/game-changer-live-betting-goes-onchain-with-azuro-348ecb8a6362) |
| **Bookmaker.XYZ** | Decentralized bookmaker-style product (geo restrictions may apply). | [docs.bookmaker.xyz](https://docs.bookmaker.xyz/) |

### Indirect peer group

- **Prediction markets** (e.g. international Polymarket-style systems, Augur-class designs): same broad “bet on outcomes” space, different product mechanics and resolution economics.

---

## Primary thesis (vs. platform-tied offerings)

1. **Permissionless creation**  
   Markets are created **on-chain** without tying proposition flow to a single platform operator’s editorial pipeline—**like Augur** for creation, but for **parimutuel prop pools** and **arbitrary propositions** (including non-binary outcome sets).

2. **Decentralized resolution (north star)**  
   Long-term goal: resolution that does not depend on a single legal entity or app-layer veto—contrasted with offerings that bind resolution to **specific platforms** or **platform operators**.

3. **MVP bridge: proposer-as-resolver (Manifold-like)**  
   The current MVP assigns the **proposer** as the **resolver**, comparable to **Manifold Markets**-style creator resolution. This **does not** satisfy full decentralized resolution yet; it **does** validate accounting, lifecycle, and distribution of the core betting mechanism.

---

## Why proposer-as-resolver may persist in production (hypothesis)

Three reinforcing reasons:

1. **Simplicity**  
   Conceptual and programmatic simplicity: minimal dispute/oracle surface area for v1 and for many informal use cases.

2. **Marketing / growth**  
   **Streamers and influencers** can spin up “let’s bet” moments with audiences quickly. Heavy resolution procedure (as in large international prediction-market stacks) can impede the **fast, lightweight** social interaction that works in the real world.

3. **Reputation moat**  
   Proposers who resolve unfairly lose trust; **fair** proposers accumulate reputation. A **separate organization** under the project umbrella can **populate** the ecosystem with desirable markets and resolve them fairly—accumulating goodwill and becoming a **de facto** source of new markets (analogous to the steady tempo of **platform-proposed** markets on Polymarket et al., but without requiring that *all* markets flow through that org).

*Note:* Reference to “international Polymarket protocol” vs “US-based version with platform-level veto” reflects product/regulatory distinctions often discussed in the ecosystem; treat as **competitive positioning**, not legal advice.

---

## Product direction: configurable resolver address

To support both **informal** (proposer-resolver) and **serious** (oracle / sponsored resolver) paths **without** forking the core contract each time:

- **Contract revision:** allow a **configurable `resolver` address** at market creation (not hard-coded to `msg.sender` as proposer only).
- **dApp default:** resolver = proposer; **optional delegation** to:
  - a **project-sponsored Resolver** org,
  - an **oracle** contract or multisig,
  - or any other address.

This yields **modularity**: the same market shell can later plug in a **Polymarket-style** or **Augur-style** resolution path by pointing `resolver` at the appropriate oracle/controller, while the MVP and influencer use case keep **one-click** proposer resolution.

---

## Open items

- [ ] Choose a **public product name** and domain strategy.
- [ ] Validate **Poolprops** and any other candidates with primary docs / deployments.
- [ ] Legal/compliance review per jurisdiction before promoting to retail users.
