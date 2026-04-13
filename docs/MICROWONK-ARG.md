# Microwonk ARG: Diegetic Prediction Market Campaign

**Date:** 2026-04-12
**Status:** Draft — for review prior to execution
**Depends on:** `docs/WAGER-LIFECYCLE.md`, `docs/PROPOSITION-SERVICE.md`, `docs/RESOLUTION-SERVICE.md`, `research/go-to-market-strategy.md`

---

## 1. Concept

The Microwonk ARG is a month-long media event that presents Paramutuel as though it already exists inside the ctrlcreep fictional universe. Automated Twitter/X accounts — the "microwonks" — propose wagers, place bets, and comment upon events from *Cataclysm* and the broader ctrlcreep corpus, creating a fourth-wall-breaking simulation of a vibrant diegetic commentator community visible from our world through the Internet.

All wagers are real on-chain transactions against the Paramutuel testnet deployment (Base Sepolia). The campaign doubles as a stress test, a demonstration, and a narrative art project.

**On mechanism fit:** The Cataclysm microwonks operate prediction markets in the traditional sense — order books, binary contracts, continuous trading. The Paramutuel protocol is a parimutuel prop betting system, which is not identical. However, parimutuel mechanics are *advantageous* for this ARG: they function effectively at low liquidity (which the constrained supply of bot accounts and testnet funds necessitates), require no market makers, and settle cleanly. Thematically, there is no reason microwonks — inveterate gamblers who use every available instrument — would not use parimutuel mechanisms alongside other betting systems. The in-universe framing should treat Paramutuel as one of many wagering primitives available to wonks, neither dominant nor anomalous.

**Core principles:**

- Wagers, bets, and commentary are released on a steady month-long schedule, not all at once.
- Not all wagers resolve — open threads maintain the illusion of a living world.
- All microwonk posts are tagged `#microwonk` and do not explicitly reference "Paramutuel" by name, to simulate generic ubiquity of the protocol in-universe.
- All bot accounts are legitimately labeled as automated per X policy, and linked to a human-managed parent account.
- Infrastructure is testnet/mainnet agnostic: a single configuration toggle switches all activity from Base Sepolia to Base Mainnet.

---

## 2. The Co-ordinator

A central planning entity (operated by the project team, potentially augmented by scheduled Claude Cowork or Grok tasks) that:

1. **Drafts and dispatches wagers** via the Proposition Service.
2. **Devises the resolution plan** — some outcomes predetermined, some extemporaneous, some contingent on external ctrlcreep activity.
3. **Authors all microwonk commentary** — each persona's voice, bets, and reactions are centrally scripted, then dispatched to individual Twitter accounts.
4. **Maintains the master schedule** — a calendar of wager proposals, betting windows, resolution events, and commentary beats across the full month.

### 2.1 Resolution delegation

All wagers use the **Resolution Service** (`service/resolution/`) as the on-chain `resolver` address. The Co-ordinator populates the decision file (`config/resolution-decisions.base-sepolia.json`) according to the master plan:

| Resolution type | Mechanism |
|-----------------|-----------|
| **Predetermined** | Winning outcome recorded in the master plan at wager creation. Decision file pre-populated, executed on schedule. |
| **Extemporaneous** | Co-ordinator decides after betting closes, based on narrative considerations. Decision file updated before resolution window ends. |
| **External-contingent** | Outcome depends on a real-world event (ctrlcreep posting to Twitter, continuing a story, etc.). A monitoring task watches for the trigger; decision file updated when the condition is met. For these wagers, use `bettingCloseTime = 0` with a `bettingCloser` address (authority-managed windows), so betting and resolution are not bounded by fixed timestamps but by the Co-ordinator's judgment. |

### 2.2 Scheduling infrastructure

| Layer | Tool | Purpose |
|-------|------|---------|
| **Static schedule** | Cron jobs / GitHub Actions scheduled workflows | Predetermined posts and wager dispatches at fixed times |
| **Reactive tasks** | Claude Cowork scheduled tasks or Grok recurring tasks | Monitor ctrlcreep feeds for external-contingent triggers; draft extemporaneous commentary |
| **Manual override** | Proposition Service control panel + Resolution Service `/run-once` | Operator intervention for edge cases |

**Preference:** Maximize non-agentic (cron-based) scheduling. Use agentic tasks only where judgment is required (drafting novel commentary, evaluating external triggers).

---

## 3. Microwonk Personas

8 microwonk personas, each with a distinct voice, specialization, and betting style. Names mix alphabetical and numerical components in a Vernor Vinge register, as though each name were also a functional designation.

### 3.1 Cast

| Handle | Designation | Specialization | Betting style | Voice |
|--------|-------------|---------------|---------------|-------|
| `@SRCE_01_echo` | Source-Echo Unit 01 | Cetacean politics, ACI dynamics, deep-ocean intelligence | Conservative; large positions on long-odds events she believes in | Calm, philosophical, prone to whale metaphors. Sympathizes with Sourceless. |
| `@CRTX_7_prime` | Cortez-Watcher Prime-7 | Embodied-soul dynamics, archaic-human survival odds, clone hierarchies | Aggressive; many small bets, always doubles down | Bombastic, competitive, addresses other wonks as inferiors. Admires the Cortezes. |
| `@TRBN_44_null` | Tribunal Null-44 | God-machine jurisprudence, stewardship precedent, alignment taxonomy | Hedged; bets both sides, profits on information asymmetry | Legalistic, dry, cites precedents from previous nootechnic incidents. |
| `@FROG_sat_ix` | Frog-Satellite IX | SIMFAT analysis, amphibian conservation indices, orbital platform behavior | Contrarian; bets against consensus, loves underdog outcomes | Earnest, slightly naïve, genuinely concerned about frogs. Comedy relief. |
| `@DSMR_00_flux` | Desidereification Meter Flux-00 | Mirabilisk dream activity, wish-granting field intensity, material coherence | Volatility trader; bets on extreme outcomes | Breathless, mystical, speaks in sensory metaphors. Reports "field readings." |
| `@WKDL_k8_arb` | WonkDollar Arbitrageur K8 | Wonk economy, exchange rates, market microstructure | Pure arbitrageur; exploits price discrepancies between correlated wagers | Terse, numerical, speaks mostly in ratios and percentages. |
| `@MMTH_03_edge` | Mmm-Threat Monitor Edge-03 | 8/mmm incursion tracking, Onanistic Terror defense, border integrity | Risk-averse on defense wagers, aggressive on offense predictions | Paranoid, urgent, uses military jargon. Always warning about 8/mmm. |
| `@ARCH_v2_root` | Archive Root V2 | Historical precedent, cross-corpus references, Fragnemt/Talisnam allusions | Long-term bets; patient accumulator | Scholarly, references obscure histories. Occasionally quotes from "the archives" (other ctrlcreep works). |

### 3.2 Infrastructure per persona

Each microwonk requires:

- **Twitter/X account** — labeled as automated, linked to the Paramutuel parent account, with a signal-sprite avatar (generated from `signal-sprites-3.html` with unique color seeds).
- **Ethereum wallet** — a fresh EOA on Base Sepolia, funded from the master treasury.
- **Bettor sub-agent instance** — a configured `paramutuel-bettor` process (or equivalent `cast`-based script) with that wallet's private key, pointed at the testnet indexer.

### 3.3 Additional accounts

| Account | Purpose | Posts tagged `#microwonk`? |
|---------|---------|---------------------------|
| `@paramutuel` (existing or new) | Official protocol account. Announces wagers, retweets interesting microwonk activity. | No — this is the "real world" account. |
| `@resonance_xchg` | The in-universe Paramutuel equivalent. Broadcasts wagers as though from inside the ctrlcreep world. Uses Resonance Exchange branding. | Yes |

---

## 4. Wager Design

### 4.1 Wager categories

Wagers are drawn from the Cataclysm narrative and the broader ctrlcreep corpus. Each wager specifies its full lifecycle.

#### Category A: Cataclysm plot wagers (predetermined resolution)

These bet on events whose outcomes are known from the published text. Betting windows are set to close before resolution is "revealed" by the narrative schedule.

| # | Proposition | Outcomes | Winning | Betting window | Resolution |
|---|------------|----------|---------|---------------|------------|
| A1 | "Will Mirabilisk's stewardship be awarded to a known entity?" | Yes / No / Stewardship Denied | No (SIMFAT was unknown) | Days 1-4 | Day 5 (predetermined) |
| A2 | "How many Cortezes survive the initial Cataclysm?" | 0 / 1-2 / 3-5 / 6+ | 3-5 (three survived) | Days 2-5 | Day 6 (predetermined) |
| A3 | "Will a neo-whale volunteer to enter the Mirabilisk Core Station?" | Yes / No / Coerced | Yes (Sourceless consented) | Days 3-7 | Day 8 (predetermined) |
| A4 | "Does SIMFAT successfully locate an archaic human for the Faraday labyrinth?" | Yes, via broadcast / Yes, already present / No | Yes, already present (Cortez) | Days 5-9 | Day 10 (predetermined) |
| A5 | "What is SIMFAT's primary non-stewardship concern?" | Military defense / Resource allocation / Frog conservation / Self-preservation | Frog conservation | Days 1-3 | Day 4 (predetermined) |

#### Category B: Speculative wagers (extemporaneous resolution)

These bet on interpretive or extrapolative questions about the fiction. The Co-ordinator resolves them based on narrative judgment after betting closes.

| # | Proposition | Outcomes | Betting window | Resolution |
|---|------------|----------|---------------|------------|
| B1 | "Is SIMFAT genuinely weak, or performing weakness as a strategy?" | Genuinely weak / Strategic deception / Partially both | Days 4-10 | Day 12 (extemporaneous) |
| B2 | "Will 8/mmm breach Mirabilisk's autonomic defenses during stewardship?" | Yes, catastrophically / Yes, partially / No / Inconclusive | Days 6-13 | Day 15 (extemporaneous) |
| B3 | "What is the true nature of the Mirabilisk's 'dream activity'?" | Death spasms / Subconscious repair / Deliberate communication / Unclassifiable | Days 8-15 | Day 18 (extemporaneous) |
| B4 | "Rank the factions by likelihood of betraying the stewardship agreement" (freeform) | Freeform text entries | Days 7-14 | Day 17 (extemporaneous) |
| B5 | "What percentage of embodied souls within Mirabilisk will survive the month?" | 0-10% / 10-30% / 30-60% / 60%+ | Days 10-18 | Day 22 (extemporaneous) |

#### Category C: External-contingent wagers (trigger-based resolution)

These depend on real ctrlcreep activity. They use authority-managed windows (no fixed timestamps).

| # | Proposition | Outcomes | Trigger |
|---|------------|----------|---------|
| C1 | "Will ctrlcreep publish new fiction referencing god-machines within 30 days?" | Yes / No | Monitor @ctrlcreep and ctrlcreep.net |
| C2 | "Will the next ctrlcreep Substack post contain a named AI character?" | Yes / No / No post within window | Monitor ctrlcreep.substack.com |
| C3 | "Will Invisible Networks 2026 feature a prediction-market-themed network?" | Yes / No / Event not held | Monitor ctrlcreep.net/invisible-networks |

#### Category D: Meta-wagers and engagement bait

These are designed to attract outside participation or create amusing cross-referential loops.

| # | Proposition | Outcomes | Notes |
|---|------------|----------|-------|
| D1 | "Will any non-microwonk entity place a bet on this market within 7 days?" | Yes / No | Self-referential; incentivizes outside participation |
| D2 | "Which microwonk will have the highest WonkDollar balance at month-end?" | One outcome per microwonk | Meta-competition |
| D3 | "Will the Paramutuel protocol process more than 50 bets this month?" | Yes / No / Exactly 50 | Real on-chain metric |

### 4.2 Beneficiary mechanics for engagement

Selected wagers designate external beneficiaries using the `extraFeeRecipients` / `extraFeeBps` fields:

- **D1** and similar engagement-bait wagers: a portion of the pot goes to the wallet of the first non-microwonk bettor, as a "finder's fee."
- **Charity wagers** (optional): wagers whose entire pot (100% fee, using the elevated `MAX_TOTAL_FEE_BPS`) goes to a designated beneficiary wallet, making them donation vehicles dressed as prediction markets.
- **Creator wagers**: if ctrlcreep or other fiction authors create wallets, they can be listed as fee recipients on wagers about their work — a direct financial incentive for engagement.

### 4.3 Protocol version usage

| Wager type | Protocol version | Rationale |
|------------|-----------------|-----------|
| Binary/multi-choice (A, B, D series) | v1 | Simple enumerated outcomes |
| Multi-winner possible (B4 "rank factions") | v2 (ADR-0008) | Bitmask resolution allows multiple correct answers |
| Freeform text entries | Freeform (ADR-0009) | Open-ended speculation |

---

## 5. Commentary and Narrative Schedule

### 5.1 Arc structure (4 weeks)

| Week | Theme | Wagers active | Narrative beat |
|------|-------|---------------|----------------|
| **Week 1: The Fall** | Cataclysm occurs. Microwonks awaken to the crisis. Initial wagers. | A1-A3, A5, C1-C3 | Introductions, initial bets, frantic commentary on the "breaking news" of Mirabilisk's collapse. |
| **Week 2: The Stewardship** | SIMFAT's appointment. Debate over its competence. Speculative wagers open. | A4, B1-B3, D1 | Deep analysis, factional disagreements, microwonks tag each other with challenges. |
| **Week 3: The Expedition** | Cortez and Sourceless prepare to enter the Core Station. Tension builds. | B4-B5, D2 | Betting intensifies. Alliances and rivalries among microwonks become public. Some Category A wagers resolve. |
| **Week 4: Resolution and Aftermath** | Wagers resolve (most, not all). Aftermath commentary. Seeds for future activity. | D3 | Resolutions, payouts, post-mortem analysis. Several wagers deliberately left open — "the story continues." |

### 5.2 Daily cadence

| Time (UTC) | Activity |
|------------|----------|
| 08:00 | `@resonance_xchg` broadcasts any new wagers or resolution announcements |
| 10:00-12:00 | 2-3 microwonks post commentary on the day's wagers or previous day's events |
| 14:00-16:00 | 1-2 microwonks place and announce bets, tagging relevant wagers and each other |
| 18:00-20:00 | Evening discussion thread: microwonks debate, argue, and make predictions |
| 22:00 | `@resonance_xchg` posts daily summary: active wagers, odds movements, notable bets |

### 5.3 Commentary patterns

Each microwonk follows characteristic patterns:

- **Direct bet announcements:** "@CRTX_7_prime: Placing 500 WKD on 'Yes' for A3. No whale turns down the chance to enter a god's brain. #microwonk"
- **Cross-tagging debate:** "@TRBN_44_null: @FROG_sat_ix Your position on B1 is naive. SIMFAT's weakness is calculated. I cite the Waterloo precedent — stewards always downplay their resources. #microwonk"
- **Field reports:** "@DSMR_00_flux: Field intensity reading 0.73 in quadrant south-by-east. The dream is thickening. Revise your B3 positions. #microwonk"
- **Market commentary:** "@WKDL_k8_arb: A5 odds have shifted 3:1 → 7:1 on 'Frog conservation' after @FROG_sat_ix's thread yesterday. Still underpriced. #microwonk"
- **Archival references:** "@ARCH_v2_root: For those betting B4, recall the Saharan Dream Array incident (cf. SIMFAT's own monograph). Stewards who publish amphibian papers do not betray. #microwonk"

---

## 6. Website: Microwonk Mode

### 6.1 Implementation

The Paramutuel website (`site/`) gains a "Microwonk Mode" toggle that reskins the interface using the Resonance Exchange aesthetic:

- **Color scheme:** `--void: #0a0a0f`, `--glow-cyan: #00ffd5`, `--glow-magenta: #ff00aa`, `--glow-amber: #ffaa00` (from `resonance-exchange.html`)
- **Typography:** VT323 for headers, Space Mono for body
- **Noise overlay:** Fractal noise SVG filter at low opacity
- **Header:** "THE RESONANCE EXCHANGE" replacing "Paramutuel"

### 6.2 Aggregated microwonk feed

A new section (or page) embeds a feed of `#microwonk`-tagged tweets, either via:

- **X Embedded Timeline** (no API cost; uses X's publish widget for a hashtag or list)
- **Server-side fetch** (if more control is needed; requires API access; cached and rendered as styled cards matching the Resonance Exchange theme)

The feed is displayed in the Resonance Exchange style: dark background, glowing borders, signal-sprite avatars inline.

### 6.3 Route

`/microwonk` or `/resonance` — a standalone page or a toggle on the main site. The toggle persists via URL parameter or local state (in-memory, not localStorage per artifact constraints).

---

## 7. Wallet and Treasury Infrastructure

### 7.1 Testnet treasury

A single master wallet serves as the funding source:

1. Obtain Base Sepolia ETH from faucets (Alchemy, Chainlink).
2. Obtain Base Sepolia USDC from Circle faucet.
3. Distribute ETH (for gas) and USDC (for bets) to each microwonk wallet.

### 7.2 Wallet generation

Generate 8 microwonk wallets + 1 `@resonance_xchg` proposer wallet + 1 Resolution Service wallet. Store keys in `config/microwonk-wallets.json` (gitignored, like `service.env`).

### 7.3 Testnet governance

Mirror the mainnet governance intent on testnet:

- **Proxy beacon pattern** for upgradeable factory (if desired for testnet iteration).
- **Safe multi-sig** as factory treasury and/or proposer, using Gnosis Safe on Base Sepolia.
- Document the testnet Safe address in `config/deployments.json` alongside `factoryAddress`.

### 7.4 Network agnosticism

All scripts, services, and configuration reference `config/deployments.json`'s `defaultNetwork` key. Switching from `baseSepolia` to `baseMainnet` requires:

1. Deploying contracts to mainnet.
2. Populating mainnet fields in `deployments.json`.
3. Setting `"defaultNetwork": "baseMainnet"`.
4. Re-funding microwonk wallets with real assets.

No code changes — only configuration.

---

## 8. Twitter/X Bot Infrastructure

### 8.1 Account setup

| Step | Details |
|------|---------|
| 1. Create X developer account | Via developer.x.com; associate with X Premium subscription |
| 2. Create X App | Single app for all bot accounts; obtain API key, secret, bearer token |
| 3. Create 8 microwonk accounts + 1 @resonance_xchg | Each with unique email; all labeled as "Automated" via X's bot labeling feature; all linked to the managing human account |
| 4. Generate per-account OAuth tokens | Each account authenticates via OAuth 1.0a for posting on its behalf |
| 5. Configure avatars | Generate unique signal sprites per account; set as profile images |
| 6. Write bios | In-character bios referencing microwonk designation and specialization |

### 8.2 Posting infrastructure

| Component | Implementation |
|-----------|---------------|
| **Tweet scheduler** | Python script using `tweepy` library; reads from a schedule file (JSON/YAML); posts at designated times via cron |
| **Schedule file** | `config/microwonk-schedule.json` — array of `{timestamp, account, text, reply_to?, quote?}` entries |
| **Pre-generated content** | Bulk of the month's tweets drafted by the Co-ordinator in advance; stored in schedule file |
| **Reactive content** | Claude Cowork scheduled tasks or manual operator input for extemporaneous commentary; appended to schedule file |
| **Rate limiting** | Respect X API limits: max 100 posts per 15 min per user; stagger across accounts |

### 8.3 Grok integration

Grok recurring tasks (via X Premium) can be used for:

- Monitoring @ctrlcreep for new posts (Category C wager triggers).
- Drafting suggested commentary based on trending topics in the fiction community.
- Summarizing daily microwonk activity for the Co-ordinator.

Grok cannot post directly to Twitter; it feeds analysis to the Co-ordinator, who dispatches via the posting infrastructure.

### 8.4 API cost estimate

With X's pay-per-use pricing (post-February 2026), estimate ~10-15 tweets/day across all accounts, ~300-450 tweets/month total. Cost depends on the per-tweet rate under the new pricing model. Budget for $100-300/month as a conservative estimate; validate against current X API pricing at signup.

---

## 9. Technical Implementation Plan

### Phase 0: Infrastructure (Days -14 to -7)

- [ ] Generate microwonk wallets and store securely.
- [ ] Set up testnet Safe multi-sig for treasury/governance.
- [ ] Fund treasury from faucets; distribute to microwonk wallets.
- [ ] Obtain X API access; create bot accounts; configure OAuth tokens.
- [ ] Generate signal-sprite avatars; set up account profiles and bios.
- [ ] Deploy and configure the tweet scheduler (`tweepy` + cron).
- [ ] Configure Resolution Service with microwonk resolver address.
- [ ] Create `config/microwonk-wallets.json` template (gitignored).

### Phase 1: Content preparation (Days -7 to 0)

- [ ] Draft all Category A and D wager propositions with outcomes and resolution plan.
- [ ] Draft Category B propositions with outcomes; note resolution criteria.
- [ ] Draft Category C propositions; configure monitoring triggers.
- [ ] Write Week 1 and Week 2 commentary scripts (all 8 personas).
- [ ] Pre-populate `config/microwonk-schedule.json` for Weeks 1-2.
- [ ] Pre-populate `config/resolution-decisions.base-sepolia.json` for Category A wagers.
- [ ] Test end-to-end: propose a test wager, place bets from 2+ microwonk wallets, resolve, claim.

### Phase 2: Launch and Week 1 (Days 1-7)

- [ ] `@resonance_xchg` posts opening broadcast: "Cataclysm detected. Markets opening."
- [ ] Dispatch Category A1, A2, A3, A5, C1-C3 wagers via Proposition Service.
- [ ] Begin automated tweet schedule.
- [ ] Microwonks place initial bets and post commentary.
- [ ] Monitor for engagement; adjust Week 2 content if needed.

### Phase 3: Weeks 2-3 (Days 8-21)

- [ ] Resolve Category A wagers on schedule.
- [ ] Open Category B and D wagers.
- [ ] Draft and schedule Weeks 3-4 commentary (can be partially reactive).
- [ ] Monitor Category C triggers.
- [ ] Intensify cross-tagging and debate patterns.

### Phase 4: Week 4 and wrap (Days 22-30)

- [ ] Resolve remaining Category B wagers (extemporaneous decisions).
- [ ] Resolve Category D wagers based on actual on-chain data.
- [ ] Leave 2-3 wagers deliberately unresolved (C-series, plus one speculative).
- [ ] Post "aftermath" commentary; seed future activity.
- [ ] Collect metrics: total wagers, bets, unique participants, tweet impressions.

### Phase 5: Website integration (parallel track)

- [ ] Implement Microwonk Mode CSS toggle on `site/`.
- [ ] Add `#microwonk` tweet feed to `/microwonk` or `/resonance` page.
- [ ] Test Resonance Exchange theming across all site pages.

---

## 10. Open questions

1. **X API pricing validation:** The new pay-per-use model needs concrete cost estimates before committing to tweet volume. Should we start with a smaller pilot (3-4 accounts, 1 week) to calibrate costs?

2. **ctrlcreep coordination:** Are there any existing communication channels with ctrlcreep for coordinating the ARG? Category C wagers work best if there's some awareness (even informal) that this activity exists, to increase the chance of trigger events.

3. **Legal framing:** Even on testnet with no real money, the ARG involves automated accounts betting on fictional events. Should there be a disclaimer page? How does this interact with the "testnet / not an offer" framing noted in `docs/PROJECT-REVIEW.md`?

4. **Mainnet transition trigger:** What conditions must be met before switching the ARG from testnet to mainnet? Contract audit? Legal review? A minimum engagement threshold?

5. **Content moderation:** If the ARG attracts outside participants (the goal), who moderates? The microwonks are scripted, but replies and quote-tweets are not.

6. **Intellectual property:** The ARG uses ctrlcreep's fictional universe. Is there an agreement or understanding in place regarding derivative creative work?

---

## 11. Success criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Wagers created | 15-20 | On-chain count via indexer |
| Total bets placed | 100+ | On-chain count via indexer |
| Unique betting addresses | 10+ (ideally beyond the 8 microwonks) | On-chain count |
| Tweets posted | 300-450 | Twitter Analytics |
| External engagement (likes, replies, retweets from non-bots) | 50+ interactions | Twitter Analytics |
| Website microwonk mode visits | 100+ | Analytics (if configured) |
| Wagers left open for future activity | 2-3 | By design |

---

## 12. File manifest (new files this effort produces)

| Path | Purpose |
|------|---------|
| `docs/MICROWONK-ARG.md` | This document |
| `docs/MICROWONK-FEATURE-REQUEST.md` | Cleaned-up original feature request |
| `config/microwonk-wallets.json` | Wallet addresses and labels (gitignored; keys in service.env) |
| `config/microwonk-schedule.json` | Tweet schedule for all personas |
| `config/microwonk-wagers.json` | Wager definitions with lifecycle parameters |
| `config/resonance-exchange-theme.css` | Microwonk Mode CSS (or inline in site files) |
| `site/microwonk.html` | Microwonk Mode page with tweet feed |
| `script/microwonk/generate_sprites.sh` | Generate unique signal-sprite avatars |
| `script/microwonk/fund_wallets.sh` | Distribute testnet funds from treasury |
| `script/microwonk/tweet_scheduler.py` | Tweepy-based scheduled poster |
| `script/microwonk/monitor_triggers.py` | External-contingent wager trigger monitor |
