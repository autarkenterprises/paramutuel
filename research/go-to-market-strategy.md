# Go-to-Market & Adoption Strategy

**Date:** 2026-03-29
**Status:** Draft v1
**Depends on:** `research/market-viability.md`, `research/execution-roadmap.md` (Checkpoints 6-8)

---

## 1. Strategic framing

The goal is not just to ship a working protocol, but to become the **default primitive for on-chain prop bets** — the thing people reach for when someone says "let's bet on it." This requires two things working in parallel:

- **Technical credibility**: immutable, audited, low-fee, well-documented.
- **Social proof and network effects**: visible usage by recognizable people, easy integration into existing workflows, and a self-reinforcing cycle where more bettors attract more proposers.

Polymarket became the default for prediction markets not because it was the only option, but because it achieved critical mass of liquidity and mindshare. This protocol must execute a similar playbook adapted for parimutuel prop betting.

---

## 2. Target audiences (ordered by launch priority)

### Tier 1 — Creator-led communities (launch wave)

**Who:** Streamers, YouTubers, podcasters, Twitter/X personalities who already make informal bets or predictions with their audiences.

**Why first:** They have built-in distribution, their audiences are accustomed to interactive engagement, and the "let's bet on it" moment happens organically in their content. A creator proposing and resolving a market is the simplest possible UX flow.

**Activation pattern:**
- Creator proposes a market during a stream or episode
- Shares a link; audience places bets
- Creator resolves after the outcome is known
- Winner payouts create shareable moments ("I just won 3x on that call")

### Tier 2 — Crypto-native communities

**Who:** DeFi power users, DAO communities, crypto Twitter, on-chain governance participants.

**Why second:** Already comfortable with wallets, ERC-20 tokens, and Base/Arbitrum. Low friction to adopt. Provides early liquidity depth and protocol credibility.

**Activation pattern:**
- Protocol-seeded markets on crypto-native topics (ETH price milestones, governance votes, protocol launches)
- Integration into existing community tools (Discord bots, Telegram bots)
- Composability stories (resolver DAOs, oracle integrations)

### Tier 3 — Automated agents and LLM workflows

**Who:** AI agents, trading bots, LLM-powered applications, MCP-enabled tools.

**Why third (but build infrastructure early):** Machine-readable interfaces and deterministic on-chain state make this protocol naturally suited for automated participation. This is a long-term moat — the protocol that machines can easily bet through wins the automated era.

### Tier 4 — Mainstream casual users

**Who:** People who see a bet shared on social media and want to participate.

**Why last:** Requires the most UX polish (wallet abstraction, fiat on-ramps, mobile-friendly dApp). Build toward this but don't gate launch on it.

---

## 3. Creator & streamer outreach strategy

### 3.1 Competitive landscape: existing streamer betting services

Before outreach, understand what creators currently use:

| Service | Type | Key limitation for our thesis |
|---------|------|-------------------------------|
| **Twitch Predictions** | Platform-native; channel points (not real money) | No real stakes; locked to Twitch; not on-chain |
| **StreamElements / Streamlabs loyalty points** | Fake currency betting within stream overlays | Not real money; no portability; centralized |
| **Kick predictions** | Platform-native predictions | Same limitations as Twitch; platform-locked |
| **Polymarket** | Prediction market (CLOB) | Not designed for quick prop bets; binary-heavy; trading UX, not "let's bet" UX |
| **Stake / Rollbit / crypto casinos** | House-edge gambling | House always wins; not peer-to-peer; regulatory pressure |
| **Twitter/X polls** | Informal sentiment; no stakes | No money; no enforcement; no payout |
| **Manual escrow (PayPal, Venmo)** | Ad-hoc peer bets | Trust-dependent; no multi-party; no transparency |

**Key insight:** No existing service lets a creator **instantly propose an arbitrary multi-outcome real-money bet to their audience, with transparent on-chain settlement and no house edge.** This is the wedge.

### 3.2 Outreach targets by platform

#### Twitch / Kick / YouTube Live streamers

**Profile:** Already use channel point predictions or audience polls. Audiences are engaged and competitive. Categories:

- **Gaming streamers** — "Will I beat this boss in under 10 attempts?" / "Which team wins this tournament match?"
- **IRL / Just Chatting** — Current events debates, challenge outcomes
- **Sports watch-along** — Live game prop bets with the audience
- **Poker / casino streamers** — Already gambling-adjacent; audience understands stakes

**Approach:**
1. Identify 20-50 mid-tier streamers (10k-100k followers) who regularly use Twitch Predictions or audience polls
2. Offer a **white-glove onboarding**: pre-funded test markets, a dedicated support channel, and a stream overlay widget (to be built)
3. Create a **"Streamer Kit"**: landing page explaining the value prop, step-by-step setup guide, and example market templates optimized for live content
4. Revenue share: allow streamers to be `extraFeeRecipients` on their markets — they earn a cut of every bet placed

**Why mid-tier first:** Large streamers are hard to reach and slow to adopt. Mid-tier creators are hungry for differentiation, more responsive, and their adoption creates social proof for larger creators.

#### Podcasters & YouTube creators

**Profile:** Long-form content with recurring audiences. Predictions and debates are natural content.

- **News/politics** — Election outcomes, policy predictions, geopolitical events
- **Tech/crypto** — Product launches, price predictions, "will X ship by date Y"
- **Sports analysis** — Season predictions, player performance props
- **Science/futurism** — Technology milestones, space launches, climate targets

**Approach:**
1. Target shows that regularly make predictions or have "prediction scorecard" segments
2. Offer **co-branded markets** that the show can reference in episodes and link in show notes
3. Build a **prediction leaderboard** that tracks audience members' records across episodes — gamifies the engagement loop

#### Twitter/X personalities

**Profile:** People who make public predictions, challenge each other to bets, or whose followers debate outcomes.

- **Tech founders/VCs** who make product/market predictions
- **Sports commentators** with engaged followings
- **Political commentators** across the spectrum
- **"Friendly wager" culture** — tech moguls, public figures who tweet "I'll bet you X that Y happens"

**Approach:**
1. Monitor Twitter for "I'll bet" / "wanna bet?" / "friendly wager" moments
2. **Reply with a pre-configured market link** — "Here's that bet, on-chain: [link]" — demonstrating the product in context
3. Build a **Twitter bot / browser extension** (future) that detects bet-like language and offers to create a market
4. Target the "tech mogul friendly wager" use case specifically: when public figures propose bets on Twitter, the protocol should be the obvious place to formalize it

### 3.3 Creator incentive structure

| Incentive | Mechanism | Purpose |
|-----------|-----------|---------|
| **Fee revenue** | Creator as `extraFeeRecipient` (50-100 bps) | Direct financial incentive to propose markets |
| **Reputation score** | On-chain resolution history, displayed in explorer | Builds trust; creates competitive moat for reliable resolvers |
| **Verified proposer badge** | Curated list of trusted, high-volume proposers | Social proof; discovery advantage |
| **Grant program** | One-time grants for first N markets or first $X in volume | Lowers adoption risk; funds initial experimentation |
| **Content amplification** | Protocol social accounts RT/share creator markets | Cross-pollination of audiences |

### 3.4 Outreach execution timeline

| Phase | Timing (relative to mainnet) | Actions |
|-------|------------------------------|---------|
| **Pre-launch seeding** | -8 to -4 weeks | Identify and contact 50 target creators; send Streamer Kit; offer testnet demos |
| **Beta access** | -4 to -1 weeks | 5-10 creators get early mainnet access; co-create launch markets; collect feedback |
| **Launch week** | Week 0 | Coordinated "launch day" with beta creators going live simultaneously; PR push |
| **Growth phase** | Weeks 1-12 | Expand to 50+ active creators; iterate on tooling based on feedback; introduce referral program |
| **Scale phase** | Months 3-6 | Large creator outreach using social proof from early adopters; platform partnerships |

---

## 4. Machine & LLM utilization strategy

The `MACHINE.md` doc already positions the protocol for bot/agent interaction. The next steps are to make this a first-class distribution channel.

### 4.1 MCP (Model Context Protocol) server

**What:** Publish an MCP server that exposes paramutuel market operations as tools callable by LLMs (Claude, GPT, etc.).

**Tools to expose:**
- `list_markets` — query open/resolved markets from the indexer API
- `get_market_details` — full market state including outcomes, totals, odds
- `create_market` — propose a new market (requires wallet/signer)
- `place_bet` — bet on an outcome (requires wallet/signer)
- `get_odds` — current implied payout multiples per outcome
- `resolve_market` — finalize a market (resolver only)

**Why this matters:** As LLM agents increasingly manage portfolios, make decisions, and interact with on-chain protocols, being the protocol that agents can natively call is a massive distribution advantage. An agent that can say "I'll create a market for that prediction" during a conversation is powerful.

**Implementation path:**
1. Build MCP server wrapping the existing indexer API (read operations) and ethers.js contract calls (write operations)
2. Publish to MCP registries and package managers
3. Document as a tool spec for agent frameworks (LangChain, CrewAI, AutoGPT, Claude Agent SDK)

### 4.2 LLM tool / function-calling spec

**What:** Publish an OpenAPI-compatible tool specification that any LLM with function calling can use.

**Format:** JSON schema matching OpenAI function-calling format and Anthropic tool-use format.

**Distribution:**
- GitHub repo with tool definitions
- npm/pip packages for easy integration
- Listed in AI tool directories and agent marketplaces

### 4.3 Embeddable SDK / widget

**What:** A lightweight JavaScript SDK that any website or app can embed to create and interact with markets.

**Use cases:**
- Blog post with an embedded "bet on this prediction" widget
- Forum post where the author creates a market inline
- Chat application (Discord, Slack) bot that creates markets from commands
- Browser extension that detects "bet-like" language on any webpage

### 4.4 SEO & discoverability

**Target keywords and content strategy:**

| Keyword cluster | Content type | Purpose |
|-----------------|-------------|---------|
| "on-chain prop bet" / "decentralized prop betting" | Landing page, explainer blog | Capture intent-driven search |
| "parimutuel betting crypto" / "parimutuel smart contract" | Technical docs, protocol spec | Capture developer/researcher interest |
| "bet with friends on-chain" / "crypto friendly wager" | How-to guide, social content | Capture casual user interest |
| "streamer betting tool" / "audience betting" | Creator-focused landing page | Capture creator search |
| "LLM betting tool" / "AI agent betting" | Developer docs, MCP listing | Capture machine/agent builder interest |
| "[competitor] alternative" | Comparison pages | Capture users exploring options |

**Technical SEO:**
- Ensure the dApp is SSR or has static meta tags for market sharing (Open Graph, Twitter Cards)
- Each market should have a shareable URL with preview (question, current odds, total pot)
- Structured data (JSON-LD) for market pages

---

## 5. Launch campaign: testnet to mainnet

### 5.1 Pre-launch (4-8 weeks before mainnet)

**Build anticipation and gather early adopters.**

| Action | Channel | Purpose |
|--------|---------|---------|
| "Testnet challenge" | Twitter/X, Discord, crypto forums | Invite users to create and bet on testnet markets; reward most creative propositions |
| Creator beta program | Direct outreach | 5-10 creators with early access; co-design launch markets |
| Technical blog series | Mirror/blog, dev forums | "How we built an immutable prop betting primitive" — establish credibility |
| Protocol audit announcement | Twitter/X, security community | Signal seriousness; build trust |
| Name/brand reveal | All channels | If a project name is chosen (see `market-viability.md` open question), do a coordinated reveal |

### 5.2 Launch week

**Coordinated spike of visibility.**

| Action | Channel | Purpose |
|--------|---------|---------|
| **Flagship market** | Protocol-seeded, high-interest topic | One marquee market everyone wants to bet on (e.g., a major upcoming event) — the "Polymarket election" moment |
| **Creator simulcast** | 5-10 beta creators go live | Multiple streams/posts featuring the protocol on the same day |
| **CT thread** | Twitter/X | "We just launched the on-chain prop bet protocol. Here's why it matters." — thread with demo GIFs |
| **Hacker News / Reddit** | HN, r/ethereum, r/defi, r/cryptocurrency | Technical launch post emphasizing permissionless, immutable, low-fee |
| **Product Hunt** | producthunt.com | Capture mainstream tech audience |
| **Press/media** | Crypto media (The Block, Decrypt, CoinDesk), tech media | Embargo'd launch coverage |

### 5.3 Post-launch growth (weeks 1-12)

| Action | Cadence | Purpose |
|--------|---------|---------|
| **Weekly flagship market** | Weekly | Protocol-seeded market on trending topic; maintains visibility |
| **Creator spotlight** | Bi-weekly | Feature a creator and their markets; cross-promote |
| **Integration bounties** | Ongoing | Pay developers to build bots, widgets, integrations |
| **Governance proposals** | Monthly | Community involvement in fee policy, feature priorities |
| **Hackathon sponsorship** | Per event | Sponsor tracks at ETH hackathons; "best market" prizes |

---

## 6. Distribution channels & partnerships

### 6.1 Platform integrations (build or partner)

| Platform | Integration type | Priority |
|----------|-----------------|----------|
| **Discord** | Bot: `/bet create "question" "opt1, opt2, opt3"` | High — crypto communities live here |
| **Telegram** | Bot: inline market creation and betting | High — crypto-native messaging |
| **Twitter/X** | Bot that replies to "wanna bet?" tweets with market links; browser extension | High — viral loop |
| **Farcaster** | Frame: inline betting within Farcaster posts | High — crypto-native social, Base-aligned |
| **Twitch** | Overlay widget for streamers | Medium — requires more UX work |
| **Lens** | Social integration | Medium — crypto-native social |
| **Slack** | Bot for team/community bets | Low — niche but sticky |

### 6.2 Protocol partnerships

| Partner type | Value exchange |
|--------------|---------------|
| **Oracle networks (Chainlink, UMA, Pyth)** | Resolution module for price/data-driven markets; credibility |
| **Wallet providers (Coinbase Wallet, Rainbow, MetaMask)** | Featured dApp listing; embedded market discovery |
| **L2 ecosystem (Base, Arbitrum foundations)** | Grant funding; ecosystem promotion; featured project |
| **Stablecoin issuers (Circle/USDC)** | Preferred collateral token; co-marketing |
| **Other DeFi protocols** | Composability stories (e.g., use LP tokens as collateral) |

### 6.3 Farcaster / Base alignment

Given the primary launch on Base, deep Farcaster integration is strategic:

- **Frames**: A Farcaster Frame that lets users bet directly within their feed
- **Channel**: Official protocol channel for market discovery
- **Base ecosystem**: Apply for Base ecosystem grants; participate in Base builder programs
- **Coinbase alignment**: Coinbase Wallet is the default Base wallet; optimize for it

---

## 7. Community & retention

### 7.1 Community structure

| Layer | Platform | Purpose |
|-------|----------|---------|
| **Core contributors** | GitHub, private Discord | Protocol development, governance |
| **Proposer community** | Public Discord, Telegram | Market creators sharing ideas, resolution best practices |
| **Bettor community** | Public Discord, Telegram, Farcaster | Discussion, market discovery, leaderboards |
| **Developer community** | GitHub, developer Discord | Integration builders, resolver module developers |

### 7.2 Retention mechanics

| Mechanism | Description |
|-----------|-------------|
| **Leaderboards** | Track best proposers (volume, resolution fairness) and best bettors (ROI, streak) |
| **Reputation system** | On-chain history visible in explorer; trusted proposer badges |
| **Recurring markets** | Templates for weekly/monthly recurring propositions (e.g., "weekly NFL props") |
| **Notification system** | Alert subscribers when trusted proposers create new markets |
| **Social sharing** | One-click share of bets, wins, and market outcomes with rich previews |

---

## 8. Metrics & milestones

### 8.1 North star metrics

| Metric | Definition | Why it matters |
|--------|-----------|----------------|
| **Monthly handle** | Total value bet across all markets in a month | Primary indicator of protocol traction |
| **Active proposers** | Unique addresses creating markets per month | Measures supply-side health |
| **Active bettors** | Unique addresses placing bets per month | Measures demand-side health |
| **Market completion rate** | % of markets that reach `resolved` (vs retracted/expired) | Measures ecosystem quality |

### 8.2 Milestone targets (illustrative)

| Milestone | Target | Trigger |
|-----------|--------|---------|
| **Proof of life** | 100 markets, $10k cumulative handle | Validates basic product-market fit |
| **Creator traction** | 10 recurring proposers, 500 unique bettors | Validates creator distribution thesis |
| **Machine adoption** | 5 integrations (bots/agents) placing bets | Validates machine distribution thesis |
| **Growth inflection** | $100k monthly handle, 50 active proposers | Ready for aggressive scaling |
| **Category leadership** | $1M+ monthly handle, recognized as default prop bet protocol | Fundraising / expansion trigger |

---

## 9. Risk mitigation

| Risk | Mitigation |
|------|-----------|
| **Regulatory uncertainty** | Immutable, permissionless protocol with no admin keys; protocol itself is infrastructure, not an operator. Service entity operates transparently with clear resolution policies. Legal review before mainnet. |
| **Resolver abuse (unfair resolution)** | Reputation system makes abuse visible and costly; retraction mechanism exists; future dispute/challenge modules planned (Checkpoint 9) |
| **Low initial liquidity** | Protocol-seeded flagship markets; creator incentive grants; focus on small-pot social markets where liquidity depth is less critical |
| **Smart contract risk** | Comprehensive test suite (40+ tests); security audit before mainnet; immutable core means no upgrade risk |
| **Creator churn** | Fee revenue sharing creates ongoing financial incentive; reputation moat rewards long-term commitment |
| **Competitor response** | First-mover advantage in permissionless arbitrary prop betting; immutability means the protocol can't be rug-pulled; machine-readable interfaces create switching costs for integrators |

---

## 10. Budget framework (pre-revenue)

| Category | Estimated range | Notes |
|----------|----------------|-------|
| **Security audit** | $20k-$80k | Scope-dependent; 466 lines of core Solidity is small |
| **Creator grants** | $10k-$30k | Seed 20-50 creators with gas + initial market funding |
| **Integration bounties** | $10k-$20k | Discord bot, Telegram bot, Farcaster Frame |
| **Design & branding** | $5k-$15k | Logo, brand guide, dApp polish, social templates |
| **Content & PR** | $5k-$15k | Launch campaign, blog posts, media outreach |
| **Legal review** | $10k-$30k | Regulatory positioning, terms of service |
| **Total pre-revenue** | **$60k-$190k** | Conservative range for meaningful launch |

---

## 11. Summary: the flywheel

```
Creators propose interesting markets
    -> Audiences bet on them (volume, fees)
        -> Creators earn fees, gain reputation
            -> More creators adopt
                -> More markets, more variety
                    -> More bettors discover the protocol
                        -> Machines integrate for automated betting
                            -> Deeper liquidity attracts bigger bets
                                -> Protocol becomes the default
```

The entire strategy is designed to **start the flywheel with creators** (Tier 1), **deepen it with crypto-native users** (Tier 2), **accelerate it with machines** (Tier 3), and **expand it to mainstream** (Tier 4).
