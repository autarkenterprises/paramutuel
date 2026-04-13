# Feature Request: Microwonk ARG Campaign

**Date:** 2026-04-12
**Author:** jpt4
**Status:** Proposed — launch target April 14, 2026
**Implementation plan:** `docs/MICROWONK-ARG.md`

---

## Context

Several existing aspects of the Paramutuel project require additional work: governance mechanisms for the live net (proxy beacon address, Safe multi-sig), bettor agent publication and distribution, website content and hosting, pitch decks for users/developers/investors, documentation, and the human targets of the go-to-market strategy.

This feature request introduces a new, significant component alongside those efforts.

## Feature: Automated Microwonk Twitter/X Campaign

Automated Twitter/X bot accounts — legitimately labeled as such — which propose wagers, make bets, and comment upon the "current events" of the ctrlcreep body of literature. These bots are based on the "microwonks" of the *Cataclysm* short story: prediction market participants in a post-singularity world who track, debate, and gamble on the affairs of god-machines and embodied souls.

The bots bet in a quasi-fourth-wall-breaking style on the events and features of *Cataclysm* and other ctrlcreep fiction (the *Fragnemt* and *Talisnam* collections, Substack posts, and Tweet archives). The parimutuel mechanism, while distinct from the traditional prediction markets of the fiction, is thematically compatible — microwonks would use any available wagering primitive — and operationally advantageous at the low-liquidity scale this campaign requires.

### Components

**1. Master plan and Co-ordinator**

The Co-ordinator drafts a series of wagers to be proposed by the Paramutuel Proposition Service. Each wager specifies all stages of its lifecycle:

- **Betting window and resolution window:** whether these are time-based, authority-managed, or delegated to other entities (other microwonks, other Paramutuel services).
- **Resolution:** delegated to the Resolution Service. Some winning outcomes are predetermined and registered in the master plan; others are extemporaneously determined by the Co-ordinator once betting closes; others depend on outside events (ctrlcreep posting to Twitter, continuing a story). For event-contingent wagers, time-based windows are not necessarily appropriate — authority-managed windows are used instead.
- **Commentary direction:** The Co-ordinator is the ultimate mind behind each microwonk persona. Microwonks post commentary and discussion, tagging each other about bets they have made or intend to make, and about the substance of the wagers themselves. Personae use separate wallets and bettor sub-agents to place bets, and have separate Twitter accounts, but their choice of bets and commentary is centrally devised and dispatched.

These actions need not all be pre-planned, but must proceed on a regular, engaging timetable. Wagers, bets, and commentary are steadily released over a month-long schedule, with wagers gradually resolved — though not all, leaving paths open to future activity rather than concluding all plot points.

To the greatest extent possible, scheduling uses non-agentic programs (cron, GitHub Actions), though scheduled agentic tasks (Claude Cowork, Grok recurring tasks) are acceptable where judgment is required.

**2. The microwonks**

Each microwonk has:

- A centrally co-ordinated persona with distinct voice and specialization.
- A separate Ethereum wallet on Base Sepolia.
- An individual bettor sub-agent to interact with the Paramutuel protocol.
- An individual automated Twitter account with a signal-sprite avatar.

There is also a Paramutuel Twitter account (the "real world" protocol account) and a parallel account broadcasting wagers as though from inside the ctrlcreep universe (the "Resonance Exchange").

All microwonk-related posts are tagged with `#microwonk` and do not explicitly reference Paramutuel, to maintain a sense of generic ubiquity of the protocol in that world.

**3. Website: Microwonk Mode**

The Paramutuel website gains a separate "Microwonk Mode" in which the style changes to that of the Resonance Exchange aesthetic (dark void background, neon cyan/magenta/amber accents, VT323/Space Mono typography, fractal noise overlay), with an aggregated feed of the `#microwonk`-tagged Twitter posts.

### Constraints

- All ARG behavior takes place on testnet initially.
- Infrastructure must be agnostic to test versus mainnet, switching atomically via `config/deployments.json`.
- This requires setting up governance (contract proxies and Safes) for the testnet contract as well as the mainnet.
- Bot accounts must comply with X's automated account labeling policy.
- Entities other than microwonks (other Twitter users, public figures, passersby) can be made beneficiaries of some or all of the betting pool for certain wagers, using the `extraFeeRecipients` / `extraFeeBps` mechanism.

### Narrative constraints

*Cataclysm* is unfinished and being released on an uncertain timeframe. Predetermined wagers are limited to events within published text. Extemporaneous wagers must carefully preserve optionality — they address only peripheral or interpretive topics that future Cataclysm chapters cannot contradict. External-contingent wagers are explicitly meta (fourth-wall-breaking) and treat the author and publishing schedule as subjects. All extemporaneous resolutions require Co-ordinator review before dispatch.

The wager set is designed so that more wagers are open than closed at the end of the initial month, with long-bridge wagers tied to future Cataclysm developments and unfinished ctrlcreep stories remaining open indefinitely. The ARG does not conclude — it pauses, with threads dangling.

### Posture

The ARG is poker-faced. No disclaimers beyond the standard testnet/mainnet notice on contracts and the required X automated-account labels. All published ctrlcreep work is fair game under fair use. Coordination with ctrlcreep is available if needed but all systems should be agnostic to this channel.

### Relationship to existing work

This feature request is parallel to — not blocking — the existing backlog items in `docs/TASKS.md` and `docs/PROJECT-REVIEW.md`. It exercises the Proposition Service, Resolution Service, bettor agent, indexer, dApp, and website in concert, making it a valuable integration test as well as a marketing event.
