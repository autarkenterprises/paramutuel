## Market Viability Research

Date recorded: 2026-03-20

### Working thesis

The core thesis of this project is:

- **permissionless market creation**
- **on-chain custody and payout**
- **arbitrary propositions rather than a fixed menu of platform-curated markets**
- **eventual decentralized resolution**

This is meant to be to proposition betting what `Augur` was to prediction markets: an on-chain protocol where market creation is not bottlenecked by a platform operator, and where the resolution path is ultimately modular and decentralizable.

This project is **not** primarily trying to replicate prediction markets that require the matching / convergence mechanics common to orderbook or AMM-style prediction products. Instead, it is focused on **parimutuel / pool-based proposition betting**, where participants allocate wagers into outcome pools and winners split the pot pro rata.

### Why this space may still be viable

The category is real: there are already on-chain products that look like direct or partial analogs. That reduces demand risk. However, the market still appears fragmented across:

- traditional tote / racing-style parimutuel products
- sportsbook-style on-chain prop products
- prediction-market protocols that are adjacent but structurally distinct

The main whitespace appears to be the combination of:

- **permissionless arbitrary proposition creation**
- **parimutuel payout mechanics**
- **decentralizable resolution**
- support for **multi-outcome, non-binary, text-defined propositions**

### Direct analogs

#### OpenTote

Source: <https://opentote.org/>

OpenTote explicitly describes itself as a **decentralized parimutuel betting system on Solana**. It is the clearest direct analog found in this research pass.

Relevant characteristics:

- traditional parimutuel framing
- strong focus on horse-racing / tote-style wager types
- supports win/place/show, exacta, trifecta, superfecta, and multi-race wagers
- permissionless pool creation is part of its positioning

Takeaway:

- validates demand for on-chain parimutuel mechanics
- appears more specialized in traditional tote categories than in arbitrary free-form propositions

#### Paradox

Source: <https://paradox-3.gitbook.io/paradox/>

Paradox explicitly describes itself as a **parimutuel betting protocol built on Arbitrum**.

Relevant characteristics:

- pool-based odds
- team-token representation for positions
- protocol emphasizes the parimutuel model as a defense against adverse selection
- fee model designed to reward earlier bettors

Important caveat:

- the docs state that v1 still relies on a **Gnosis multisig** to finalize results, so resolution is not fully decentralized

Takeaway:

- strong confirmation that EVM parimutuel betting has real design-space interest
- also highlights that **resolution centralization remains an open problem** even for protocols that otherwise market themselves as decentralized

#### Poolprops

Source observed through ecosystem references and project listings:

- <https://www.soladex.io/project/poolprops>

Poolprops appears to be a Solana sports prop betting project, though primary-source confirmation was weaker in this research pass than for OpenTote and Paradox.

Takeaway:

- likely evidence that the market is exploring **prop-betting-specific** product forms
- merits deeper follow-up if the project is still active

### Adjacent but indirect competitors

These are not direct substitutes at the mechanism level, but they compete for user attention, sports / event speculation demand, and distribution.

#### Overtime

Source: <https://medium.com/@OvertimeMarkets.xyz/introducing-player-props-on-overtime-135f356c9aea>

Overtime offers **player props on-chain**, but does so through an **AMM / position-token model**, not a parimutuel pool model.

Relevant characteristics:

- player-prop UX
- oracle-based settlement
- ERC-20 position tokens
- much closer to an on-chain sportsbook / trading venue than to open-ended parimutuel pools

Takeaway:

- strong evidence that **on-chain prop demand exists**
- not a direct mechanism competitor, but clearly competes for the same end-user intent

#### Azuro ecosystem / Bookmaker-style apps

Sources:

- <https://blog.azuro.org/game-changer-live-betting-goes-onchain-with-azuro-348ecb8a6362>
- <https://docs.bookmaker.xyz/>

Azuro is better understood as **sports betting infrastructure** and an ecosystem for on-chain bookmaker-style applications. Its associated apps are closer to decentralized sportsbook infrastructure than to permissionless user-created parimutuel proposition pools.

Takeaway:

- indirect but important competitive pressure
- demonstrates that there is serious execution in the broader on-chain betting category
- does not obviously occupy the exact thesis of permissionless arbitrary prop-pool creation

### What is *not* a direct competitor

Prediction markets remain relevant as a peer group, but are not the same product class for this thesis.

This distinction matters because:

- prediction markets often depend on continuous pricing / matching / AMM convergence
- the user experience is often closer to trading than to saying "let's bet"
- many prediction-market designs are weaker fits for arbitrary multi-outcome proposition betting in casual, social, or creator-led contexts

Accordingly, prediction markets should be treated as:

- **indirect competitive pressure**
- **design inspiration**
- but **not** the primary reference class for product-market fit

### MVP rationale: proposer as resolver

The MVP currently uses a model where the **proposer is also the resolver**. This is comparable, in spirit, to a lightweight creator-resolved model such as `Manifold Markets`.

This may remain valuable beyond MVP for three reasons:

#### 1. Simplicity

The design is conceptually and programmatically simple.

Benefits:

- lower smart-contract complexity
- easier UX
- faster iteration
- lower friction for rapid market creation

#### 2. Social / creator distribution

A likely growth strategy is to target:

- streamers
- influencers
- online communities
- event hosts

These users often want to instantiate a bet quickly in the same spirit as a real-world "let's bet" interaction. Heavy resolution procedures or protocol-wide dispute bureaucracy can hinder this mode of use.

**Positioning note (Polymarket):** the **international** Polymarket-style stack is often discussed as having heavier, protocol-level resolution machinery than a lightweight creator-resolved line. Separately, **US-facing** or app-store-constrained offerings sometimes introduce **platform-level** controls (e.g. veto or moderation) that are a different axis from on-chain resolution design. This project’s contrast is with tying **permissionless creation** and **resolution authority** to a **single platform operator**—not a legal classification of any specific product.

This makes creator-resolved markets attractive as a **fast, socially native primitive**, even if a more decentralized resolution path later exists in parallel.

#### 3. Reputation moat

If proposers resolve unfairly, they should become less trusted by future bettors.

This creates room for:

- reputation-based competition among proposers
- repeated-game fairness incentives
- a brand moat for curators / resolvers with strong track records

### Strategic organizational implication

There is a plausible business / ecosystem strategy where a separate organization under the umbrella of the protocol:

- proposes many desirable markets
- resolves them fairly and consistently
- becomes a de facto trusted source of liquidity and recurring market flow

This is analogous to how some platforms become habit-forming not merely because they host markets, but because they reliably seed them.

In this framing:

- the **protocol** remains permissionless
- the **organization** competes on trust, taste, responsiveness, and resolution quality

This may be a stronger strategic position than trying to force all value capture into the base contract layer.

### Architectural refinement: configurable resolver

A strong follow-on design change would be to allow each market to specify a **resolver address** distinct from the proposer address.

Desired behavior:

- the dApp defaults `resolver = proposer`
- advanced users may delegate resolution to another address

Examples:

- a trusted individual
- a project-operated resolver service
- a creator team wallet
- a future oracle adapter
- a future decentralized resolution contract

Why this matters:

- preserves MVP simplicity for ordinary users
- creates forward compatibility for more sophisticated resolution mechanisms
- allows the protocol to support multiple social and technical trust models without rewriting the market primitive

This suggests a long-term architecture where the core market contract is resolution-agnostic:

- it only knows **which address may finalize**
- that address can be a person, committee, bot, or oracle adapter

### Product positioning recommendation

The most defensible positioning currently appears to be:

> A permissionless, on-chain protocol for arbitrary parimutuel prop bets, with lightweight creator-resolved markets today and modular decentralized resolution tomorrow.

This is more precise than:

- "sports betting on-chain"
- "prediction markets for everything"
- "just another decentralized sportsbook"

It emphasizes the actual wedge:

- **free-form proposition creation**
- **pool-based betting**
- **minimal friction**
- **evolution toward decentralized resolution**

### Commercial / go-to-market implication

A likely sequencing strategy is:

1. **MVP**
   - creator-resolved markets
   - simplest possible market creation UX
   - focus on small communities and creator-led use cases

2. **Reputation layer**
   - visible proposer / resolver history
   - identity profiles
   - records of fair / unfair resolution

3. **Resolution modularity**
   - configurable resolver address
   - optional resolver delegation
   - optional oracle-backed or committee-backed resolution modes

4. **Deeper decentralization**
   - permissionless dispute systems
   - bonded reporting
   - challenge windows
   - richer invalid / ambiguous resolution handling

### Open naming question

A project name is still needed. The name should ideally signal some combination of:

- proposition / "prop" betting
- pooled / parimutuel wagering
- permissionless market creation
- open, on-chain, or trust-minimized settlement

The naming problem should be revisited after the desired brand tone is clearer:

- serious protocol infrastructure
- creator-social betting app
- or neutral market primitive

### Bottom line

The research indicates:

- direct analogs already exist, so the category is credible
- the exact thesis of **permissionless arbitrary parimutuel prop creation with modular decentralized resolution** is still not obviously saturated
- creator-resolved markets are not merely an MVP compromise; they may be a strategically important product mode
- configurable resolver support is likely the correct bridge between MVP simplicity and long-term protocol ambition

