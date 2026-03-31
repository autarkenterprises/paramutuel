# Investor Pitch & Deck Outline

**Date:** 2026-03-29
**Status:** Draft v1
**Depends on:** `research/market-viability.md`, `research/chain-and-fee-review.md`, `research/go-to-market-strategy.md`

This document serves as (a) the narrative pitch for the protocol and (b) a slide-by-slide outline for a 15-20 slide investor deck.

---

## The pitch (narrative form)

### The problem

Every day, millions of people say "I'll bet you that..." — on Twitter, on streams, in group chats, at dinner. Tech moguls make "friendly wagers" about whether AI will pass a benchmark. Streamers ask audiences to predict match outcomes. Friends debate whether a movie will break $1B box office.

Almost none of these bets are formalized. The ones that are get shoehorned into prediction wager platforms designed for trading, not betting. Polymarket is great for "will X happen?" binary wagers with continuous pricing. But it's poorly suited for "let's all throw $20 into a pot and the people who picked the right answer split it" — which is what most real-world prop bets actually look like.

**The parimutuel model** — where participants bet into a shared pool and winners split the pot pro rata — is the natural primitive for this. It's how horse racing has worked for over a century. It needs no wager maker, no order book, no liquidity provider. Just a proposition, outcomes, and bettors.

### The solution

An **immutable, permissionless, on-chain protocol** for arbitrary parimutuel proposition betting on Base (Ethereum L2).

- **Anyone can propose a wager**: "Will SpaceX land on Mars before 2030?" with outcomes "Yes before 2028 / Yes 2028-2030 / No"
- **Anyone can bet**: deposit ERC-20 tokens into the outcome pool of their choice
- **Winners split the pot**: pro-rata, minus a 1% protocol fee
- **No house edge, no order book, no wager maker**: pure peer-to-peer pool mechanics
- **Resolution is modular**: starts with creator-resolved wagers (like Manifold); upgradeable to oracle-backed or DAO-governed resolution without changing the core contracts

### Why now

1. **L2 costs make this viable**: Creating a wager on Base costs ~$0.02. Placing a bet costs ~$0.002. The gas cost barrier that killed earlier attempts is gone.

2. **Creator economy meets crypto**: Streamers on Twitch/Kick/YouTube already use fake-currency prediction features. Real-money on-chain prop bets are the obvious next step, and no one owns this category.

3. **AI agents need betting infrastructure**: LLM-powered agents are beginning to manage portfolios and make decisions. A machine-readable betting protocol with deterministic settlement is natural infrastructure for automated knowledge wagers.

4. **Prediction wagers proved the category, but not the format**: Polymarket's success in 2024-2025 proved massive demand for event-outcome speculation. But the order-book/AMM format excludes casual, multi-outcome, social betting. The parimutuel primitive captures the adjacent demand.

### The wager

**TAM framework:**

| Layer | Description | Estimated size |
|-------|-------------|---------------|
| **Global gambling wager** | All legal gambling worldwide | ~$700B+ annually |
| **Online / digital gambling** | Internet-based betting | ~$100B+ annually |
| **Social / informal betting** | Peer-to-peer casual wagers (largely untracked) | Massive but unmeasured |
| **On-chain speculation** | Prediction wagers + DeFi options + crypto betting | ~$5-20B annually and growing |
| **SAM: Prop betting + parimutuel** | Our addressable slice: informal propositions formalized on-chain | Emerging; no reliable sizing yet |

The honest answer: the SAM is early and hard to size. Our thesis is that **formalizing the "let's bet" moment** is a category-creation opportunity, not a share-steal play against existing sportsbooks.

### Competitive positioning

| | This protocol | Polymarket | Paradox | OpenTote | Twitch Predictions |
|---|---|---|---|---|---|
| **Permissionless creation** | Yes | Limited | Unclear | Yes | No (platform-only) |
| **Arbitrary propositions** | Yes (text-defined, 2-64 outcomes) | Limited to curated | Sports-focused | Racing-focused | Platform-curated |
| **Parimutuel mechanics** | Yes | No (CLOB/AMM) | Yes | Yes | Channel points (no value) |
| **Real money** | Yes (ERC-20) | Yes | Yes | Yes | No |
| **Immutable contracts** | Yes | No (upgradeable) | Unclear | Unclear | N/A |
| **Machine-readable** | Yes (ABI + API + MCP) | API exists | Limited | Limited | No |
| **Creator economics** | Fee sharing via `extraFeeRecipients` | No | No | No | No |
| **Resolution model** | Modular (creator -> oracle -> DAO) | UMA oracle | Gnosis multisig | Configurable | Platform fiat |

**Defensibility:**
- **Immutability**: Core contracts cannot be changed, upgraded, or rug-pulled. This is a trust guarantee competitors with upgradeable proxies cannot offer.
- **Permissionless creation**: No approval needed. Anyone, human or machine, can create a wager.
- **Machine-first interfaces**: ABI, JSON API, and MCP server (built, 16 tools) make this the easiest protocol for agents to integrate.
- **Network effects**: Proposer reputation, bettor history, and integration ecosystem create switching costs.

### Business model

**Protocol fee:** 1% of the total pot, charged at wager finalization.

| Monthly handle | Annual protocol revenue (@ 1%) |
|----------------|-------------------------------|
| $100k | $12k |
| $1M | $120k |
| $10M | $1.2M |
| $100M | $12M |

Revenue accrues to the protocol treasury (governed by a multisig Safe). Additional per-wager fees can be configured for creators, resolvers, or other participants (capped at 100% total by the factory contract to allow charity-style distributions, target <3% in standard consumer flows).

**Revenue growth levers:**
- More wagers (supply-side: creator adoption, machine integration)
- More bettors per wager (demand-side: distribution, UX)
- Larger average bet size (trust, reputation, liquidity depth)
- Multi-chain deployment (Arbitrum, future L2s)

### Go-to-wager

**Phase 1: Creator-led launch**
- Target 20-50 mid-tier streamers and content creators
- White-glove onboarding with Streamer Kit and fee revenue sharing
- Coordinated launch week with simultaneous creator content

**Phase 2: Crypto-native growth**
- Discord/Telegram/Farcaster bots for in-app wager creation
- Protocol-seeded flagship wagers on trending topics
- Hackathon sponsorships and integration bounties

**Phase 3: Machine distribution**
- MCP server for LLM agent integration (built — 16 tools; publish to registries)
- OpenAPI tool spec for function-calling LLMs
- Embeddable SDK/widget for any website

**Phase 4: Mainstream expansion**
- Wallet abstraction and fiat on-ramps
- Mobile-optimized dApp
- Browser extension for "bet on anything" from any webpage

(Full detail in `research/go-to-market-strategy.md`)

### Team & traction

*(To be filled in with actual team bios and traction data)*

**Current status:**
- Core protocol: complete, tested (40+ Solidity tests), deployed on Base Sepolia
- dApp: functional, all lifecycle flows working, hosted on GitHub Pages
- Indexer + API: operational, reorg-safe, deterministic, hosted on Render
- Explorer + control panel: operational
- MCP server: built (16 tools for LLM agent integration)
- Protocol website: live at `https://autarkenterprises.github.io/paramutuel/`
- Live testnet integration + stress suites: passing

### The ask

*(To be calibrated based on fundraising goals)*

**Suggested framing for a seed/pre-seed round:**

| Use of funds | Allocation |
|-------------|-----------|
| **Security audit** | 20-30% |
| **Creator acquisition & grants** | 20-25% |
| **Engineering (integrations, UX, mobile)** | 25-30% |
| **Legal & compliance** | 10-15% |
| **Operations & reserves** | 10-15% |

---

## Deck outline (slide-by-slide)

### Slide 1 — Title
- Protocol name / logo (TBD — see naming question in `market-viability.md`)
- Tagline: "The on-chain prop bet primitive"
- Subtitle: "Permissionless parimutuel betting for humans and machines"

### Slide 2 — The moment
- Visual: screenshot of a Twitter "friendly wager" exchange between public figures
- Text: "Every day, millions of people say 'I'll bet you that...' None of it is formalized."

### Slide 3 — The problem
- Prediction wagers are for traders, not bettors
- Existing tools are platform-locked, fake-currency, or require a house
- No permissionless way to propose an arbitrary multi-outcome real-money bet

### Slide 4 — The solution
- One-sentence: "A permissionless, immutable smart contract protocol for arbitrary parimutuel prop bets"
- Visual: simple flow diagram — Propose -> Bet -> Resolve -> Claim
- Key stats: 2-64 outcomes, any ERC-20, 1% fee, ~$0.02 to create a wager

### Slide 5 — How it works
- Visual walkthrough of wager lifecycle
- Emphasis on simplicity: "As easy as posting a poll, but with real stakes"

### Slide 6 — Demo / product screenshots
- dApp wager creation flow
- Betting interface with odds preview
- Explorer showing live wagers

### Slide 7 — Why parimutuel
- No wager maker needed (vs. AMM/CLOB)
- No adverse selection / informed trader problem
- Natural fit for social, casual, multi-outcome propositions
- 100+ year track record in horse racing

### Slide 8 — Wager opportunity
- TAM/SAM framework
- Polymarket as proof of category demand
- Creator economy + AI agents as new distribution vectors
- Honest about early-stage sizing

### Slide 9 — Competitive landscape
- 2x2 matrix: (permissionless vs. curated) x (parimutuel vs. order book/AMM)
- This protocol occupies the "permissionless + parimutuel" quadrant alone

### Slide 10 — Defensibility
- Immutable contracts (can't be rug-pulled or censored)
- Permissionless (can't be gatekept)
- Machine-readable (first-mover for AI agent integration)
- Network effects (reputation, integrations, liquidity)

### Slide 11 — Business model
- 1% protocol fee on pot at finalization
- Revenue scenarios table
- Path to $1M+ ARR at $10M monthly handle

### Slide 12 — Go-to-wager
- Creator flywheel diagram
- Phase 1-4 summary
- Key insight: creators are the distribution, not just the users

### Slide 13 — Creator economics
- How creators earn: fee sharing, reputation, audience engagement
- Comparison: "Twitch gives you channel points. We give you revenue."
- Streamer Kit concept

### Slide 14 — Machine distribution
- MCP server (built, 16 tools), API, SDK
- "The protocol AI agents bet through"
- Diagram: LLM -> MCP -> Protocol -> Settlement

### Slide 15 — Traction & status
- Base Sepolia deployment: live
- Test coverage: 40+ tests, all passing
- MCP server: built and tested (16 tools)
- Hosted dApp + protocol website: live on GitHub Pages
- Indexer API: hosted on Render
- Architecture: immutable core, modular resolution
- Roadmap checkpoints completed vs. remaining

### Slide 16 — Roadmap
- Checkpoint timeline from execution-roadmap.md
- Near-term: audit, mainnet launch, creator onboarding
- Medium-term: resolver modules, multi-chain, mobile
- Long-term: decentralized resolution, governance

### Slide 17 — Team
- *(Bios, relevant experience, why this team)*

### Slide 18 — The ask
- Round size and terms
- Use of funds breakdown
- Key milestones the funding unlocks

### Slide 19 — Why now, why us
- L2 costs finally make per-wager deployment viable
- Prediction wager mania proved demand; we serve the adjacent unmet need
- Immutable protocol = credible neutrality from day one
- Machine-first design = positioned for the AI agent era

### Slide 20 — Contact / close
- Contact info
- Links: testnet dApp, GitHub, docs
- "Try it now on Base Sepolia: [link]"

---

## Appendix: objection handling

### "Isn't this just gambling?"

The protocol is infrastructure for formalizing propositions and outcomes. Like prediction wagers, it serves knowledge discovery and accountability. A bet on whether a policy achieves its stated goal is a knowledge artifact. The protocol's value increases with broader, more diverse participation — the same principle that makes prediction wagers epistemically valuable.

### "Why not just use Polymarket?"

Polymarket is an order-book prediction wager optimized for binary, high-liquidity, continuously-traded wagers. It requires wager makers and is poorly suited for casual, multi-outcome, social propositions. A group of friends betting on 5 possible outcomes of a local event is not a Polymarket use case. It is a parimutuel use case.

### "What about regulation?"

The protocol is an immutable, permissionless smart contract on a public blockchain. There are no admin keys, no upgrade paths, and no ability to freeze or censor wagers. The protocol layer is analogous to TCP/IP — it is infrastructure. The service entity that proposes and resolves wagers operates transparently and may need to comply with applicable regulations, but the protocol itself is a neutral public good. Legal counsel should be engaged before mainnet launch.

### "What if a resolver cheats?"

In the MVP, resolution trust is social — the same model as Manifold Wagers. Bettors choose who to trust based on on-chain history. This is already better than informal bets (which have no enforcement at all). The architecture supports pluggable resolution: oracle-backed resolution (Chainlink, UMA), DAO/committee resolution, and optimistic/challenge-based resolution are all achievable by deploying a resolver contract and setting it as the wager's resolver address. No protocol upgrade required.

### "Can you handle high volume?"

Each wager is an independent contract. There is no shared state between wagers, so the protocol scales horizontally with the chain's throughput. On Base at current gas prices, creating 1,000 wagers costs ~$20. The bottleneck is demand, not capacity.

### "What about front-running / MEV?"

Parimutuel pools are inherently less vulnerable to front-running than order-book wagers because there is no spread to extract. A last-second bet changes the odds for everyone (including the front-runner) proportionally. The main MEV vector is a resolver who bets and then resolves in their favor — which is addressed by reputation, social accountability, and future resolver modules with challenge windows.

---

## Next steps to produce the actual deck

1. **Resolve naming** (see `market-viability.md` open question) — the deck needs a name and brand
2. **Design**: commission or create visual assets (logo, product screenshots, diagrams)
3. **Team slide**: fill in actual team information
4. **Traction data**: gather testnet metrics (wagers created, bets placed, unique addresses)
5. **Financial model**: build a simple spreadsheet model for revenue projections
6. **Legal review**: have counsel review claims and positioning before sharing with investors
7. **Build the deck**: use the slide outline above as the skeleton; target 15-20 slides, <40 words per slide, heavy on visuals
