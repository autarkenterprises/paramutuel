# Microwonk ARG: Diegetic Prediction Market Campaign

**Date:** 2026-04-12
**Status:** Draft v2 — for review prior to execution
**Launch target:** 2026-04-14
**Depends on:** `docs/WAGER-LIFECYCLE.md`, `docs/PROPOSITION-SERVICE.md`, `docs/RESOLUTION-SERVICE.md`, `research/go-to-market-strategy.md`

---

## 1. Concept

The Microwonk ARG is an ongoing media event — launching with a month-long initial arc — that presents Paramutuel as though it already exists inside the ctrlcreep fictional universe. Automated Twitter/X accounts — the "microwonks" — propose wagers, place bets, and comment upon events from *Cataclysm* and the broader ctrlcreep corpus, creating a fourth-wall-breaking simulation of a vibrant diegetic commentator community visible from our world through the Internet.

All wagers are real on-chain transactions against the Paramutuel testnet deployment (Base Sepolia), with mainnet transactions layered on once mainnet is ready. The campaign doubles as an integration test, a demonstration, and a narrative art project.

**On mechanism fit:** The Cataclysm microwonks operate prediction markets in the traditional sense — order books, binary contracts, continuous trading. The Paramutuel protocol is a parimutuel prop betting system, which is not identical. However, parimutuel mechanics are *advantageous* for this ARG: they function effectively at low liquidity (which the constrained supply of bot accounts and testnet funds necessitates), require no market makers, and settle cleanly. Thematically, there is no reason microwonks — inveterate gamblers who use every available instrument — would not use parimutuel mechanisms alongside other betting systems. The in-universe framing should treat Paramutuel as one of many wagering primitives available to wonks, neither dominant nor anomalous.

**On the unfinished nature of Cataclysm:** *Cataclysm* is being released on an uncertain timeframe. Predetermined wagers may only concern events within the *published* text. Extemporaneous wagers must carefully preserve optionality: they may address topics related to — but not central to — the Cataclysm plot, so that future installments cannot contradict their resolutions. Extemporaneous wagers about the broader ctrlcreep literary universe are acceptable, but all resolutions must be reviewed by the Co-ordinator prior to dispatch.

**Core principles:**

- Wagers, bets, and commentary are released on a steady schedule, not all at once.
- Many wagers remain open at the end of the initial month, bridging future activity. The ARG does not conclude — it pauses, with threads dangling.
- All microwonk posts are tagged `#microwonk` and do not explicitly reference "Paramutuel" by name, to simulate generic ubiquity of the protocol in-universe.
- All bot accounts are legitimately labeled as automated per X policy, and linked to a human-managed parent account. No disclaimers beyond that and the standard testnet/mainnet notice on contracts.
- Infrastructure is testnet/mainnet agnostic: a single configuration toggle switches all activity from Base Sepolia to Base Mainnet.

---

## 2. The Co-ordinator

A central planning entity (operated by the project team, augmented by scheduled Claude Cowork or Grok tasks) that:

1. **Drafts and dispatches wagers** via the Proposition Service.
2. **Devises the resolution plan** — some outcomes predetermined, some extemporaneous, some contingent on external ctrlcreep activity.
3. **Authors all microwonk commentary** — each persona's voice, bets, and reactions are centrally scripted, then dispatched to individual Twitter accounts. Replies and quote-tweets from outside entities cannot be controlled, but microwonk responses to them are centrally devised.
4. **Maintains the master schedule** — a calendar of wager proposals, betting windows, resolution events, and commentary beats.

### 2.1 Resolution delegation

All wagers use the **Resolution Service** (`service/resolution/`) as the on-chain `resolver` address. The Co-ordinator populates the decision file (`config/resolution-decisions.base-sepolia.json`) according to the master plan:

| Resolution type | Mechanism |
|-----------------|-----------|
| **Predetermined** | Winning outcome recorded in the master plan at wager creation. Decision file pre-populated, executed on schedule. Applicable only to events within published text. |
| **Extemporaneous** | Co-ordinator decides after betting closes. Resolutions must not contradict potential future Cataclysm developments, and must be reviewed prior to dispatch. Decision file updated before resolution window ends. |
| **External-contingent** | Outcome depends on a real-world event (ctrlcreep posting to Twitter, continuing a story, etc.). These are meta-wagers that break the fourth wall by treating the author as subject. Use `bettingCloseTime = 0` with a `bettingCloser` address (authority-managed windows). |

### 2.2 Scheduling infrastructure

| Layer | Tool | Purpose |
|-------|------|---------|
| **Static schedule** | Cron jobs / GitHub Actions scheduled workflows | Predetermined posts and wager dispatches at fixed times |
| **Reactive tasks** | Claude Cowork scheduled tasks or Grok recurring tasks | Monitor ctrlcreep feeds for external-contingent triggers; draft extemporaneous commentary |
| **Manual override** | Proposition Service control panel + Resolution Service `/run-once` | Operator intervention for edge cases |

**Preference:** Maximize non-agentic (cron-based) scheduling. Use agentic tasks only where judgment is required.

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

### 4.1 Design constraints

- **Predetermined wagers** may only concern events whose outcomes are established in published text.
- **Extemporaneous wagers** must address peripheral, interpretive, or cross-corpus topics — never central unresolved Cataclysm plot points. Resolutions require Co-ordinator review before dispatch.
- **External-contingent wagers** are explicitly meta — they treat the author and publishing schedule as subjects. These are categorized as meta-wagers.
- **Continuation:** The wager set is designed so that more wagers are open than closed at the end of the initial month. Wagers tied to future Cataclysm developments and unfinished ctrlcreep stories are especially valuable, as they bridge indefinitely.

### 4.2 Wager categories

#### Category A: Published-text wagers (predetermined resolution)

These bet on events whose outcomes are known from the published *Cataclysm* text (Chapters 1-3).

| # | Proposition | Outcomes | Winning | Betting window | Resolution |
|---|------------|----------|---------|---------------|------------|
| A1 | "Will Mirabilisk's stewardship be awarded to a known entity?" | Yes / No / Stewardship Denied | No (SIMFAT was unknown) | Days 1-4 | Day 5 |
| A2 | "How many Cortezes survive the initial Cataclysm?" | 0 / 1-2 / 3-5 / 6+ | 3-5 (three survived) | Days 2-5 | Day 6 |
| A3 | "Will a neo-whale volunteer to enter the Mirabilisk Core Station?" | Yes / No / Coerced | Yes (Sourceless consented) | Days 3-7 | Day 8 |
| A4 | "Does SIMFAT locate an archaic human without broadcasting its need?" | Yes, found locally / Yes, via broadcast / No | Yes, via broadcast (Waterloo's letter) | Days 5-9 | Day 10 |
| A5 | "What is SIMFAT's primary non-stewardship concern?" | Military defense / Resource allocation / Frog conservation / Self-preservation | Frog conservation | Days 1-3 | Day 4 |
| A6 | "Does Sourceless profit from insider trading during the stewardship crisis?" | Yes, confirmed / Implied but unconfirmed / No opportunity | Implied but unconfirmed (she fantasized about it) | Days 4-8 | Day 9 |
| A7 | "Which entity provides the blueprint for entering the Faraday labyrinth?" | SIMFAT itself / An allied god-machine / An unknown third party | The Right Regional Municipality of Waterloo | Days 6-10 | Day 11 |

#### Category B: Peripheral speculative wagers (extemporaneous resolution)

These concern interpretive, thematic, or peripheral questions that future Cataclysm chapters cannot straightforwardly contradict.

| # | Proposition | Outcomes | Betting window | Resolution | Notes |
|---|------------|----------|---------------|------------|-------|
| B1 | "What alignment category does SIMFAT most accurately belong to?" | AA (Aligned Altruist) / aa (apotheotics anonymous) / Unaligned / Novel category | Days 4-12 | Day 14 | Interpretive; text provides ambiguous signals |
| B2 | "Is the Cortez replication pattern more analogous to mitosis, feudalism, or franchise?" | Mitosis / Feudalism / Franchise / None of these | Days 3-10 | Day 12 | Literary-critical; no canonical answer exists |
| B3 | "What is the most dangerous entity currently active within Mirabilisk's borders?" | 8/mmm / Mirabilisk itself (dreaming) / Unknown emergent / The Cortezes | Days 6-14 | Day 16 | Defensible either way; future chapters may elaborate but won't negate |
| B4 | "Rank: which ctrlcreep work has the most implications for god-machine economics?" (freeform) | Freeform text entries | Days 5-15 | Day 20 | Cross-corpus; draws on Fragnemt, Talisnam, etc. |
| B5 | "Is ACI (Artificial Cetacean Intelligence) best understood as a symbiont, a parasite, or a government?" | Symbiont / Parasite / Government / Something else | Days 8-16 | Day 19 | Interpretive; text supports multiple readings |
| B6 | "What is the most likely origin of the Cataclysm itself?" | Internal fault / External attack / Deliberate self-sabotage / Unknowable | Days 10-20 | **Open** | Left unresolved — the text does not answer this. Bets remain locked. |

#### Category C: Meta-wagers (fourth-wall, external-contingent)

These break the fourth wall by treating the author and real-world publishing as subjects. They use authority-managed windows (`bettingCloseTime = 0`, `bettingCloser` set).

| # | Proposition | Outcomes | Trigger | Notes |
|---|------------|----------|---------|-------|
| C1 | "Will ctrlcreep publish new fiction referencing god-machines within 60 days?" | Yes / No | Monitor @ctrlcreep and ctrlcreep.net | Long window; stays open past the initial month |
| C2 | "Will the next ctrlcreep Substack post contain a named AI character?" | Yes / No / No post within 60 days | Monitor ctrlcreep.substack.com | Long window |
| C3 | "Will the next installment of Cataclysm be published within 90 days?" | Yes / No | Monitor all ctrlcreep channels | Core bridge wager — stays open indefinitely until triggered |
| C4 | "Will any of the final 7 Invisible Networks 2026 entries feature prediction markets or betting?" | Yes / No | Monitor ctrlcreep.net/invisible-networks; the first 7 are published (none feature prediction markets); the final 7 are due by April 14 | Time-sensitive; research confirms IN2026 runs April 1-14. Phrogger (frog citizen science) is notable but not betting-themed. |
| C5 | "Will a ctrlcreep story reference parimutuel, pooled, or totalizator wagering mechanisms?" | Yes / No | Long-term monitor | Stays open indefinitely; bridge to future |

#### Category D: Engagement and meta-wagers

| # | Proposition | Outcomes | Notes |
|---|------------|----------|-------|
| D1 | "Will any non-microwonk entity place a bet on this market within 14 days?" | Yes / No | Self-referential; first non-microwonk bettor can be added as beneficiary on a subsequent wager |
| D2 | "Which microwonk will have the highest WonkDollar balance at month-end?" | One outcome per microwonk | Meta-competition; stays open past month 1 if extended |
| D3 | "Will the total number of bets placed across all markets exceed 100 by day 30?" | Yes / No / Exactly 100 | Real on-chain metric |
| D4 | "Will @resonance_xchg gain more than 50 followers within 30 days?" | Yes / No | Real-world metric; stays open |

#### Category E: Cross-corpus and long-bridge wagers (open indefinitely)

These are designed to outlast the initial month, tied to unfinished ctrlcreep works and future developments.

| # | Proposition | Outcomes | Resolution |
|---|------------|----------|------------|
| E1 | "Will a character from Fragnemt appear in a future Cataclysm chapter?" | Yes / No / Allusion only | Authority-managed; stays open indefinitely |
| E2 | "Will the Mirabilisk survive the events of the full Cataclysm narrative?" | Yes, fully restored / Yes, diminished / No, destroyed / Transformed into something else | Authority-managed; stays open until Cataclysm concludes |
| E3 | "Will any ctrlcreep story feature a parimutuel or pooled betting system as a plot element?" | Yes / No | Authority-managed; long bridge |
| E4 | "What will be the first nootechnic zone mentioned after Mirabilisk in the Cataclysm continuity?" | Freeform text entries | Authority-managed; freeform; stays open |
| E5 | "Will the Cortezes reach the Core Station?" | Yes, all / Yes, some / No | Authority-managed; stays open until next Cataclysm chapter |
| E6 | "Will Sourceless's ACI be permanently altered by her time in Mirabilisk?" | Yes / No / Partially | Authority-managed; stays open |
| E7 | "Will a new god-machine emerge from the deep ocean (as Sourceless speculates)?" | Yes, within Cataclysm / Yes, in another ctrlcreep work / No | Authority-managed; cross-corpus bridge |

### 4.3 Wager balance at month-end

At the end of the initial 30-day arc:

- **Resolved:** A1-A7 (predetermined), B1-B5 (extemporaneous), D3 (metric). Total: ~14 resolved.
- **Open:** B6, C1-C5, D1 (if not triggered), D2, D4, E1-E7. Total: ~16 open.

More open than closed — by design.

### 4.4 Beneficiary mechanics

Selected wagers designate external beneficiaries using the `extraFeeRecipients` / `extraFeeBps` fields:

- **D1** and similar engagement wagers: a portion of the pot goes to the wallet of the first non-microwonk bettor (retroactively added as beneficiary on a follow-up wager, since beneficiaries are set at creation).
- **Creator wagers**: if ctrlcreep or other participants create wallets, they can be named as fee recipients on future wagers about their work.
- **Charity/public-good wagers**: wagers whose entire pot (100% fee, via `MAX_TOTAL_FEE_BPS`) goes to a designated beneficiary.

### 4.5 Protocol version usage

| Wager type | Protocol version | Rationale |
|------------|-----------------|-----------|
| Binary/multi-choice (A, B, C, D series) | v1 | Simple enumerated outcomes |
| Multi-winner possible (if needed) | v2 (ADR-0008) | Bitmask resolution allows multiple correct answers |
| Freeform text entries (B4, E4) | Freeform (ADR-0009) | Open-ended speculation |

---

## 5. Commentary and Narrative Schedule

### 5.1 Arc structure (initial month, designed for continuation)

| Week | Theme | New wagers | Resolutions | Narrative beat |
|------|-------|------------|-------------|----------------|
| **Week 1: The Fall** | Cataclysm occurs. Microwonks awaken to the crisis. Initial wagers open. | A1-A5, C4, D1, E2, E5 | A5 | Introductions, initial bets, frantic commentary on the "breaking news" of Mirabilisk's collapse. Establish persona voices. |
| **Week 2: The Stewardship** | SIMFAT's appointment. Debate over its competence and alignment. | A6, A7, B1-B3, C1-C3, E1, E3 | A1, A2, A3 | Deep analysis, factional disagreements, microwonks tag each other with challenges. Cross-corpus references begin. |
| **Week 3: The Expedition** | Cortez and Sourceless prepare for the Core Station. Tension builds. Speculative wagers intensify. | B4-B6, C5, D2, D3, E4, E6, E7 | A4, A6, A7 | Betting intensifies. Alliances and rivalries among microwonks become public. Long-bridge wagers open for the first time. |
| **Week 4: Interim** | Some wagers resolve. Many remain open. Commentary shifts to anticipation. | D4 | B1-B5, D3 | Partial resolutions, post-mortem analysis on resolved wagers, anticipatory commentary on the many open threads. NOT a conclusion — a plateau. |

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
- **Urgency:** "@MMTH_03_edge: PERIMETER ALERT. 8/mmm probing intensity up 14% since 0300. If you're still short on B3 'Unknown emergent,' you're not paying attention. #microwonk"

### 5.4 Post-month continuation

After the initial 30-day arc:

- **Reduced cadence:** 2-3 posts per week (down from 10-15/day), maintaining persona voices.
- **Open wagers** remain live; new bets can be placed.
- **New wagers** tied to future ctrlcreep publications are added as they become relevant.
- **Resolutions** of long-bridge wagers (E-series, C-series) occur when triggered by real-world events.
- **Mainnet layering:** When mainnet is ready, parallel mainnet wagers open alongside testnet.

---

## 6. Website: Microwonk Mode

### 6.1 Implementation

The Paramutuel website (`site/`) gains a "Microwonk Mode" toggle that reskins the interface using the Resonance Exchange aesthetic:

- **Color scheme:** `--void: #0a0a0f`, `--glow-cyan: #00ffd5`, `--glow-magenta: #ff00aa`, `--glow-amber: #ffaa00` (from `resonance-exchange.html`)
- **Typography:** VT323 for headers, Space Mono for body
- **Noise overlay:** Fractal noise SVG filter at low opacity
- **Header:** "THE RESONANCE EXCHANGE" replacing "Paramutuel"

### 6.2 Aggregated microwonk feed

A new page embeds a feed of `#microwonk`-tagged tweets, either via:

- **X Embedded Timeline** (no API cost; uses X's publish widget for a list of microwonk accounts)
- **Server-side fetch** (if more control is needed; requires API access; cached and rendered as styled cards matching the Resonance Exchange theme)

Displayed in the Resonance Exchange style: dark background, glowing borders, signal-sprite avatars inline.

### 6.3 Route

`/resonance` — a standalone page. Mode toggle also available on main site pages via URL parameter `?mode=resonance`.

---

## 7. Wallet and Treasury Infrastructure

### 7.1 Testnet treasury

A single master wallet serves as the funding source:

1. Obtain Base Sepolia ETH from faucets (Alchemy, Chainlink).
2. Obtain Base Sepolia USDC from Circle faucet.
3. Distribute ETH (for gas) and USDC (for bets) to each microwonk wallet.

### 7.2 Wallet generation

Generate 8 microwonk wallets + 1 `@resonance_xchg` proposer wallet + 1 Resolution Service wallet. Store keys securely (gitignored `config/microwonk-wallets.json` for addresses; private keys in `config/service.env`).

### 7.3 Testnet governance

Mirror the mainnet governance intent on testnet:

- **Safe multi-sig** as factory treasury and/or proposer, using Gnosis Safe on Base Sepolia.
- Document the testnet Safe address in `config/deployments.json` alongside `factoryAddress`.
- **Proxy beacon pattern** for upgradeable factory, if desired for testnet iteration.

### 7.4 Network agnosticism

All scripts, services, and configuration reference `config/deployments.json`'s `defaultNetwork` key. Switching from `baseSepolia` to `baseMainnet` requires:

1. Deploying contracts to mainnet.
2. Populating mainnet fields in `deployments.json`.
3. Setting `"defaultNetwork": "baseMainnet"`.
4. Re-funding microwonk wallets with real assets.

No code changes — only configuration. Mainnet transactions can layer alongside testnet activity (both networks active simultaneously).

---

## 8. Twitter/X Bot Infrastructure

### 8.1 Account setup

| Step | Details |
|------|---------|
| 1. Create X developer account | Via developer.x.com; associate with X Premium subscription |
| 2. Create X App | Single app for all bot accounts; obtain API key, secret, bearer token |
| 3. Create 8 microwonk accounts + 1 @resonance_xchg | Each with unique email; all labeled as "Automated" via X's bot labeling feature; all linked to the managing human account |
| 4. Generate per-account OAuth tokens | Each account authenticates via OAuth 1.0a (3-legged flow) for posting on its behalf |
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

### 8.4 X API cost summary

X API uses pay-per-use pricing (launched February 2026): **$0.01 per post created**, $0.005 per post read. One app can manage multiple accounts via per-account OAuth tokens.

| Volume scenario | Posts/day (all accounts) | Posts/month | Monthly cost |
|-----------------|------------------------|-------------|-------------|
| Low (quiet phase / post-month continuation) | ~5 | ~150 | ~$1.50 |
| Medium (active campaign) | ~15 | ~450 | ~$4.50 |
| High (launch week / heavy debate) | ~30 | ~900 | ~$9.00 |

API cost is negligible. The constraint is account creation and labeling, not tweet volume.

---

## 9. Technical Implementation Plan

### Critical path to April 14 launch

The April 14 launch requires infrastructure and initial content ready in ~48 hours. This means:

- **Wallet generation and funding** can be scripted and done in minutes.
- **X account creation** is the bottleneck: 9 accounts need creation, labeling, avatar setup, and OAuth configuration. This is a manual process.
- **Initial wager proposals** (A1, A5, and 1-2 bridge wagers from E-series) can be dispatched via Proposition Service on day 1. The full wager set rolls out over the month.
- **Week 1 tweets** must be drafted before launch. Weeks 2-4 can be drafted on a rolling basis.

### Phase 0: Infrastructure (April 12-14)

- [ ] Generate 10 wallets (8 microwonk + proposer + resolver). Script: `cast wallet new`.
- [ ] Fund from faucets and distribute.
- [ ] Set up testnet Safe multi-sig for treasury/governance.
- [ ] Obtain X developer API access; create app; obtain keys.
- [ ] Create 9 Twitter accounts (8 microwonk + @resonance_xchg); label as automated.
- [ ] Generate 9 signal-sprite avatars; set up profiles and bios.
- [ ] Generate per-account OAuth tokens via 3-legged flow.
- [ ] Deploy tweet scheduler (`tweepy` + cron).
- [ ] Configure Resolution Service with resolver wallet address.
- [ ] Create `config/microwonk-wallets.json` (gitignored).

### Phase 1: Launch content (April 13-14)

- [ ] Draft Week 1 commentary scripts (all 8 personas).
- [ ] Draft wager propositions for Week 1: A1, A5, C4, D1, E2, E5.
- [ ] Pre-populate `config/microwonk-schedule.json` for Week 1.
- [ ] Pre-populate resolution decisions for A5 (resolves Day 4).
- [ ] Test end-to-end: propose a test wager, place bets from 2 wallets, verify on indexer.

### Phase 2: Launch (April 14)

- [ ] `@resonance_xchg` posts opening broadcast.
- [ ] Dispatch Week 1 wagers via Proposition Service.
- [ ] Begin automated tweet schedule.
- [ ] Microwonks place initial bets and post commentary.

### Phase 3: Rolling execution (April 15 - May 14)

- [ ] Week 2: Resolve A5; dispatch A6, A7, B1-B3, C1-C3, E1, E3; resolve A1, A2, A3.
- [ ] Week 3: Dispatch B4-B6, C5, D2, D3, E4, E6, E7; resolve A4, A6, A7.
- [ ] Week 4: Resolve B1-B5, D3; dispatch D4; post interim commentary.
- [ ] Draft and schedule commentary on a rolling weekly basis.
- [ ] Monitor Category C triggers.
- [ ] Review and approve all extemporaneous resolutions before dispatch.

### Phase 4: Post-month continuation (May 15+)

- [ ] Reduce to 2-3 posts/week.
- [ ] Add new wagers tied to ctrlcreep publications as they occur.
- [ ] Resolve long-bridge wagers when triggered.
- [ ] Layer mainnet activity when ready.

### Phase 5: Website integration (parallel track, not launch-blocking)

- [ ] Implement Microwonk Mode CSS toggle on `site/`.
- [ ] Add `#microwonk` tweet feed to `/resonance` page.
- [ ] Test Resonance Exchange theming across site pages.

---

## 10. Success criteria

| Metric | Target (month 1) | Measurement |
|--------|-------------------|-------------|
| Wagers created | 25-30 | On-chain count via indexer |
| Total bets placed | 100+ | On-chain count via indexer |
| Unique betting addresses | 10+ (beyond microwonk wallets) | On-chain count |
| Tweets posted | 300-450 | Twitter Analytics |
| External engagement | 50+ interactions (likes, replies, RTs from non-bots) | Twitter Analytics |
| Wagers open at month-end | 15+ | By design |
| Website resonance page visits | 100+ | Analytics (if configured) |

---

## 11. File manifest (new files this effort produces)

| Path | Purpose |
|------|---------|
| `docs/MICROWONK-ARG.md` | This document |
| `docs/MICROWONK-FEATURE-REQUEST.md` | Cleaned-up original feature request |
| `config/microwonk-wallets.json` | Wallet addresses and labels (gitignored; keys in service.env) |
| `config/microwonk-schedule.json` | Tweet schedule for all personas |
| `config/microwonk-wagers.json` | Wager definitions with lifecycle parameters |
| `site/resonance.html` | Microwonk Mode page with tweet feed |
| `site/resonance.css` | Resonance Exchange theme (or inline) |
| `script/microwonk/generate_sprites.sh` | Generate unique signal-sprite avatars |
| `script/microwonk/fund_wallets.sh` | Distribute testnet funds from treasury |
| `script/microwonk/tweet_scheduler.py` | Tweepy-based scheduled poster |
| `script/microwonk/monitor_triggers.py` | External-contingent wager trigger monitor |
