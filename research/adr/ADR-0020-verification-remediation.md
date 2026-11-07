# ADR-0020: Second verification pass — correct every verified error and deficiency

Date: 2026-11-07
Status: **Implemented** (2026-11-07). The contract fixes are in source and take effect when the operator deploys the new factory; see the AAR.
Builds on: ADR-0001, ADR-0005, ADR-0009, ADR-0010, ADR-0013, ADR-0018, ADR-0019, `AGENTS.md` #1 / #2 / #3 / #4 / #5 / #8 / #9

## Context

The operator asked for the codebase — written largely by weaker agents — to be verified for correctness and validated against the project's intent, then for **all errors and deficiencies to be documented and corrected**.

ADR-0019 (2026-09-26) already claimed such an audit: "contract economics correct", every finding either fixed or recorded. This pass treated those claims as hypotheses and tested them against the code, the live chain, the hosted site, and a real local chain. The result is that ADR-0019 was right about the arithmetic of the happy path and wrong or incomplete in several important places.

### What changed in the world

**Base now enforces a per-transaction gas cap of 16,777,216 (2^24)** — EIP-7825, activated by the Azul upgrade ([Base docs](https://docs.base.org/base-chain/network-information/throughput-and-limits)). `docs/PARAMUTUEL-V3-GAS.md` and ADR-0019 reasoned about block limits. A code path whose worst case exceeds 2^24 is not "expensive", it is *impossible*.

### Facts established by direct measurement on 2026-11-07

| Fact | Evidence |
|---|---|
| Deployed Base Sepolia factory has **zero wagers** (`wagersCount() == 0`). New bytecode strands nobody. | `cast call` against `0x11F0…dCD6` via public RPC |
| Hosted site: `propose-wager.js` and `propose-templates.js` return **404**. | `curl` against the GitHub Pages site |
| Hosted indexer `/health` returns **HTTP 500/503**. | `curl` |
| `paramutuel-mcp` and `paramutuel-bettor-agent` are **not on PyPI** (404), though README / MEMORY / docs say they ship there. | PyPI JSON API |
| `cast send` exits **0** for a mined, reverted transaction. | Local anvil experiment (`status 0 (failed)`, rc=0) |
| `cast send` parses a positional argument such as `--gas-limit=1` as a **flag**. | Local anvil experiment |
| `cast` stores JSON escapes literally: `["café"]` encodes the 9 bytes `café`, not `café`. | `cast abi-encode` byte inspection |
| `resolve()` on 1024 griefing masks costs **20.1M gas** at 255 options and **16.85M** at 200 options (cold storage), over the 2^24 cap. Griefing costs ~96M gas in total (≈ $2 at Base prices). | Foundry PoC with cold storage |
| A stake ≥ 2^128-ish locks `claim` with Panic(0x11); a pot ≥ `2^256 / totalFeeBps` makes `resolve`, `retract` **and** `expire` all revert: permanent loss. | Foundry PoC |

## Findings

Severity reflects impact if the path is used, not current exposure (the deployed factory is empty).

### Contracts (`src/`)

| # | Finding | Severity |
|---|---|---|
| C1 | **`resolve` griefable past the tx gas cap.** `_popcount` costs ~58 gas per set bit; a griefer filling 1024 heavy masks pushes `AT_LEAST_K` / `WEIGHTED_OVERLAP` wagers with ≳ 197 options above 2^24, so the resolver can never finalise. ADR-0019 rated this shape "medium, new answers locked out"; the real effect is an unresolvable market forced to refund-minus-fees. | **High** |
| C2 | **Freeform answer cap protects nothing.** Freeform `resolve` and `claim` are O(1), yet `maxDistinctAnswers = 1024` lets anyone pay ~$1.30 to lock out every new answer, including the correct one. The cap's documented rationale ("bound the resolution-time accumulation loop") does not apply to freeform. | **High** |
| C3 | Multi-bit enumerated wagers: new tickets can be locked out with 1-wei masks; even single-outcome tickets are locked out once the cap fills. | Medium |
| C4 | **Fund-locking overflow on high-supply tokens.** `stake * netPot` and `totalPot * totalFeeBps` use checked 256-bit math. ADR-0019's "no overflow reachable with realistic supplies" holds for mainstream tokens but the thesis is arbitrary collateral, and the failure mode is permanent loss rather than a failed bet. | Medium |
| C5 | **Freeform answers are unrecoverable from logs** (ADR-0019 #15). The contract emits only a hash, so bettors cannot see or join answers without traces; a resolver cannot enumerate what was staked. Contradicts ADR-0009 "keyed by observed answers". | Medium (intent) |
| C6 | `_userAnswerIds` is **write-only** storage with no reader: 27–44k wasted gas on every new per-user answer. | Low |
| C7 | `claim` reverts on a zero payout in enumerated mode but transfers 0 and emits `ClaimedV3(…, 0)` in freeform and retracted paths. | Low |
| C8 | `closeResolutionWindow` still flips its flag and emits after finalisation. | Low |
| C9 | Fee recipient count is unbounded. Not exploitable via ordinary transactions (creation hits the cap first: 545 recipients ≈ 16.77M create vs ≈ 15M terminal), but an L1 deposit transaction is exempt from the cap and can create a wager whose every terminal path then exceeds it. Docs also claim "caps on … fees". | Low |
| C10 | `forge coverage` blocked by the 17-argument constructor (ADR-0013), so contract branch coverage is unmeasured despite AGENTS.md #2. Wager ceiling (256 outcomes) disagrees with factory (255). `treasury` / `protocolFeeBps` are storage though ADR-0002's AAR calls them immutable. Unreachable branches in `claim`. Several misleading comments. | Low |

### Hosted / deployment

| # | Finding | Severity |
|---|---|---|
| D1 | **Hosted propose flow is dead.** `deploy-site.yml` hard-codes a copy list that omits both propose scripts; `propose-a-wager.html` and `resonance-propose.html` load nothing. The project's first verb — "anyone can propose" — does not work on the public site. | **Critical** |
| D2 | **Alchemy API key committed in the public `README.md`** (two places). | **High** |
| D3 | `Dockerfile.resolution` installs no `cast`: startup crashes unless `RESOLUTION_SERVICE_ADDRESS` is set, and `execute` raises an unhandled `FileNotFoundError` mid-request. The service's own image cannot resolve anything. | **High** |
| D4 | `script/testnet/launch_testnet.sh` deploys via the deleted `script/DeployFactory.s.sol` and greps broadcast output for `ParamutuelFactory`. The documented launch path is broken. | **High** |
| D5 | `script/deploy/redeploy_cloud_run_resolution.sh` uses `gcloud builds submit --file`, which does not exist. | Medium |
| D6 | **No CI runs the contracts, services, or fast suite**; only the bet scout has CI. Pages deploys untested code. `site/tests/` is not wired into `script/test-fast.sh`. | Medium |
| D7 | ethers is loaded from a CDN with **no SRI** on every wallet-connected page (`dapp/`, `site/bet`, `site/propose-*`, resonance variants). | Medium |
| D8 | `mcp_server/pyproject.toml` and the published-package story: the wheel omits `config/deployments.json`, so an installed server defaults to `127.0.0.1` with no factory. | Medium |

### Operator services

| # | Finding | Severity |
|---|---|---|
| O0 | **`cast` alters strings, so "byte-exact" `resolve(string)` was false.** `cast` strips trailing whitespace and surrounding quotes: `Paris␠` is encoded as `Paris`, and `"Paris"` (with its quotes) as `Paris`. The resolution service, control panel and bet scout all routed answers through it, so an operator could resolve a **different pool** from the one in their decision, and a bettor could choose an answer to exploit that. ADR-0019's regression test asserted the argv token rather than the bytes on-chain, so it passed while the bug was live. | **High** |
| O1 | **Reverted transactions recorded as success** by the resolution service, sweeper, and proposition dispatch (see the `cast send` fact above). A failed create is marked `dispatched`; a failed resolve reports `ok: true`. | **High** |
| O2 | **Private key printed in clear** by the control-panel CLI dry-run and the sweeper dry-run — dry-run being the default. | **High** |
| O3 | **Outcome labels corrupted on-chain.** `_json_arg` uses `json.dumps` escapes, which `cast` stores verbatim: `café` becomes `café`, `a\b` becomes `a\\b`, and any `"` fails outright. | Medium |
| O4 | **`cast` flag injection.** A freeform answer or proposition beginning with `--` is parsed as a flag. Answers are bettor-controlled; `--help` even exits 0, reading as success. | Medium |
| O5 | Control-panel CLI still `.strip()`s the winning answer, though ADR-0019 finding 8 records it fixed. | Medium |
| O6 | Web control panel silently drops `payoffPolicy` / `policyParam`, creating a `SINGLE_WINNER` wager whatever was requested. | Medium |
| O7 | Resolution service `GET /candidates` is open with CORS `*` and returns pending decisions. A decision file written before betting closes is an insider-trading feed. | Medium |
| O8 | Control panel passes a bitmask through JS `Number` (loses precision above 2^53); the `outcomeIndex` name means *mask* here and *index* in the resolution service. | Medium |
| O9 | Resolution service sees only the newest 1000 open wagers, starving the oldest, which are the ones due. | Low |
| O10 | Proposition dispatch can double-fire under concurrent requests; `dispatch_failed` is terminal with no retry. RSS `pubDate` is never parsed. Feed `javascript:` links render as clickable. Docstrings describe flags and behaviour that do not exist. | Low |
| O11 | Token comparison is not constant-time; subprocesses have no timeout; malformed JSON resets the connection instead of returning 400. | Low |

### Indexer

| # | Finding | Severity |
|---|---|---|
| X1 | **`wager_outcomes` is never written**, so `/wagers/{addr}.outcomes` is always `[]` and the home ticker and search state **"No stakes yet" for every enumerated wager**. | **High** (false public information) |
| X2 | `total_winning_stake` is never written; resolved wagers display "Winning stake 0". | Medium |
| X3 | One transient RPC failure during enrichment permanently blanks a wager's proposition and outcomes and records its fee as 0, because nothing retries. The bet page then refuses the wager. | Medium |
| X4 | Per-log failures are skipped silently with the cursor advanced. `bettingCloseTime ≥ 2^63` (valid on-chain) overflows SQLite's INTEGER, so that wager and all its bets vanish. | Medium |
| X5 | Log scan has no address filter: any contract can emit the wager topics, inflating responses and stalling bisection. | Medium |
| X6 | Syncs to the unsafe head with insert-only derived state; a reorg double-counts or leaves ghost bets. Docstring claims a runbook note that does not exist. | Low |
| X7 | `?now=abc` and DB errors reset the connection; `/wagers/{addr}` payload is unbounded; `/health` has no lag signal. | Low |

### Client surfaces

| # | Finding | Severity |
|---|---|---|
| W1 | **`bet-page.js` `connectWallet` re-enables staking after betting closes**, undoing ADR-0019's `5a82ce1` in the normal flow (load page, then connect). The user pays for an approve, then the bet reverts. | Medium |
| W2 | Bet page keeps its default of **6 decimals** when `decimals()` fails, so an 18-decimal bet is mis-scaled by 10^12. | Medium |
| W3 | Amounts pass through JS `Number`: `0.0000001` becomes `1e-7` and `parseUnits` throws; large values silently lose precision. | Medium |
| W4 | dApp `resolveWager` trims the winning answer (ADR-0019 fixed only the service and panel). | Medium |
| W5 | Propose page silently substitutes the proposer when the resolver address is invalid, violating ADR-0001's required guardrail. | Medium |
| W6 | Bet page shows the immutable `resolutionDeadline` after an early close, when the true deadline is earlier. | Low |
| W7 | dApp keeps the old signer after `accountsChanged` / `chainChanged`. | Low |
| W8 | MCP `quote_place_bet` and the scout CLI strip the answer while MCP `encode_place_bet_freeform` does not; both describe "exact" bytes. | Low |
| W9 | MCP encoders default to arguments that always revert; no bounds check on `outcome_index`; scout `quote` omits `odds_model_exact`; scout raises a non-JSON traceback on a missing field. | Low |
| W10 | Bet page shows a token's self-reported on-chain symbol as if verified (ADR-0018 unbuilt): a fake token can display "USDC". | Medium |
| W11 | No UI warns about zero-time wagers whose closer key is the only way forward (ADR-0019 finding 5). | Low |

### Documentation and process

| # | Finding | Severity |
|---|---|---|
| R1 | **README's CLI section targets the deleted V1 ABI.** `createWager` does not exist; `placeBet 0`, `placeBets [0,2]`, and `resolve 0` all revert on V3. `DeployFactory.s.sol` is gone. A newcomer cannot follow it. | **High** |
| R2 | `docs/MACHINE.md`, `WAGER-LIFECYCLE.md`, `WORKFLOWS.md`, `RESOLUTION-SERVICE.md`, and others carry V1 identifiers. MCP tool count is stated as 16 and 17; it is 21. | Medium |
| R3 | PyPI "ships" claims and the unqualified "any ERC-20" claim are false as stated. | Medium |
| R4 | ADR-0019 records O5, W4 and W1 as fixed or absent; its "12 fixed" and "Met" lines need correcting by AAR revision. Its 28-mutation harness was never committed, so the result cannot be reproduced. The extended suite skips 8 of 9 tests read-only. | Medium |
| R5 | The monthly practices review (L-007) lapsed after 2026-05-07 with no entry, the exact silence that lesson forbids. | Low |
| R6 | ADR-0018 sat on an unmerged branch while master cited it. | Low |

### Found during remediation

Fixing the findings above turned up more defects, recorded with their evidence in [`docs/ADR-0020-IMPLEMENTATION.md`](../../docs/ADR-0020-IMPLEMENTATION.md#found-during-remediation). The worst was **W14 (critical): no browser could resolve a V3 wager, place a single dApp bet, or stake a freeform answer from the bet page.** ethers v6 rejects calls to overloads of the same length, and every layer that unit tests could reach encodes by signature, so only the browser layer could show it. The others are:

- W12, W13, W15, W16, W17: client display, account-tracking and validation bugs. W17 is a remnant of X1.
- O12, O13: two more connection resets (O11's class).
- O14: `cast` log noise read as a failed transaction.
- D9: an unbounded dependency that broke every fresh MCP install.
- D10, D11: test and production running different ethers versions; a dead link and a broken script.
- T1, T2: Python coverage at 78%, and artifact lookup that differed between machines.
- R7: ADR-0018's drift check was never written.

## Decision

1. **Fix every finding above in code, config or docs on this branch, under red → green TDD**, one logical unit per commit, except the operator-only items in decision 7.

2. **Ship corrected contract source, additively, without changing any existing event or creation signature.** Because `wagersCount() == 0`, this is the moment to freeze correct bytecode (ADR-0018's frozen-bytecode concern). Additivity means master keeps working against the currently deployed factory and the cutover is a one-field config change:
   - **C1:** constant-time SWAR `popcount`; worst-case `resolve` falls to roughly 7M gas. A fast-suite test asserts the worst case stays under 2^24 with cold storage.
   - **C2:** remove the freeform answer cap entirely. Nothing iterates `_usedAnswerIds` on-chain, so griefing has nothing left to attack.
   - **C3:** single-outcome tickets are exempt from `MAX_DISTINCT_TICKETS`, so basic betting can never be locked out, and add a per-wager **`minNewTicketStake`** via new creation overloads. Zero preserves today's behaviour; a proposer can price griefing in collateral units only they understand.
   - **C4:** full-precision `mulDiv` for every payout and fee calculation.
   - **C5:** new event `FreeformAnswerRevealedV3(bytes32 indexed answerId, string answer)`, emitted once per distinct answer. Older indexers ignore unknown topics.
   - **C6–C10:** remove `_userAnswerIds`; revert `NothingToClaim` on any zero payout; `closeResolutionWindow` becomes a no-op once finalised; cap extra fee recipients; pass constructor arguments as a struct; align the outcome ceiling at 255; make `treasury` / `protocolFeeBps` immutable; remove unreachable branches; correct comments.

3. **Make the deploy path verifiable, not merely fixed.** Copy site assets by glob, and add a fast-suite test that every script an HTML page references ships in the artifact, so D1's whole class fails CI. Add CI for the fast suite, gate Pages on it, and add SRI with a test that every external script on the site carries it.

4. **Add a real local-chain end-to-end test** (anvil + real `cast` + real indexer + real services) to the extended suite. It needs no secrets, so it can run in CI. The read-only extended suite skipped 8 of 9 tests; nothing proved the layers agree with the chain. Commit the mutation harness so its results are reproducible.

5. **Implement ADR-0018's overlay** (allowlist config, collateral-trust badge, warned opt-in, token-class pin tests, qualified "any standard ERC-20" claim). The narrowed claim and pin tests are corrections, not features; the allowlist uses only tokens the dApp already presets, so it requires no new operator policy.

6. **Keep the neutral-core semantics for zero-time wagers** (W11, ADR-0019 finding 5). A lost closer key still locks a no-max wager. Surfaces warn instead. A hard lifetime backstop would change what "no max" means and is the operator's product decision, recorded as an open question below.

7. **Do not take outward-facing actions on the operator's behalf.** Deploying the new factory, rotating the Alchemy key, publishing to PyPI, and redeploying Cloud Run are listed as follow-ups with exact commands in `docs/ADR-0020-IMPLEMENTATION.md`. Merging to `master` and pushing is the canonical flow under AGENTS.md #5 and is performed.

## Decision points

- **Remove the freeform cap rather than parameterise it** (ADR-0019 proposed the latter). A knob on a guard that protects nothing is worse than no guard. Spam is priced by `minNewTicketStake` and handled off-chain by a bounded API payload.
- **Single-bit exemption instead of reserved capacity:** needs no extra counter. `_usedMasks.length` is bounded by `1024 + numOptions ≤ 1279`, which is what the gas assertion tests.
- **Same contract names (`…V3`), new address:** L-001 warns against new parallel surfaces, and no live state exists to distinguish.
- **Bet-side trimming in human UIs stays** (ADR-0009 §5 allows a UI convention). **Resolve paths and machine surfaces are byte-exact**: a resolver or agent must get exactly the bytes it passed.
- **`cast` remains the signer but no longer parses anything user-supplied.** A small stdlib ABI encoder (`service/control_panel/abi.py`, checked against `eth_abi`) produces raw calldata, which fixes O0, O3 and O4 with one mechanism. Previews show the function and decoded arguments so operators still review readable values. Receipt status is checked via `--json`. `cast` has no environment or stdin path for a raw key, so argv exposure remains; deployment guidance isolates it in a single-purpose container.

## Success criteria

- Every finding is fixed with a test that failed first, or recorded with rationale in the implementation notes.
- `script/test-fast.sh` passes, now including site tests, the site-artifact check, the SRI check, and the cold-storage gas bound.
- The local end-to-end test passes, proving indexer state equals on-chain state (`total_pot`, ticket pools, `total_fee_bps`, `total_winning_stake == payoutDenominator`) for all five policies and freeform, and that a reverted transaction is reported as a failure by every service.
- `script/mutation-check.py` kills every listed mutation.
- `forge coverage` runs, or the remaining obstacle is documented precisely.
- After merge, the hosted propose scripts return 200.

## Failure criteria

- A fix regresses behaviour against the *currently deployed* factory (additivity breach) — caught by keeping old overload tests and by the indexer tolerating a missing `minNewTicketStake()`.
- Factory bytecode exceeds EIP-170 — measured by `forge build --sizes`.
- Another "comment-only" or partial claim survives (L-006, L-008): every "Met" line below must cite a test or a command output.

## Rejected alternatives

- **Exempt nothing and lower `MAX_DISTINCT_TICKETS`.** Treats the symptom; popcount is the actual cost driver, and lower caps make lockout griefing cheaper.
- **Per-outcome accumulators for `WEIGHTED_OVERLAP`.** O(numOptions) resolve, but up to 255 extra SSTOREs per bet, charging honest bettors for a griefing defence.
- **Allow `retract` while betting is open / add a lifetime backstop.** See decision 6.
- **Keep `cast` arguments, adding a `--` separator and careful quoting.** Tried first: it fixes flag injection, but `cast` still strips trailing whitespace and surrounding quotes from plain string arguments, so it cannot be byte-exact.
- **Rewrite git history to purge the API key.** Destructive, breaks every clone, and does not un-leak a public key. Rotation is the real remedy.

## Open questions (operator)

1. **No-max lifetime backstop:** should a future factory allow anyone to `expire()` a zero-time wager after N years, making "funds can never be permanently stuck" unconditional at the cost of a far-off bound on "no max"?
2. **Factory cutover timing** relative to the Resonance ARG and ADR-0015 (Safe treasury).

## After Action Report

**AAR date:** 2026-11-07
**AAR status:** Initial. Revisit after the operator cutover (new factory, indexer and resolution redeploys, live suites), and at the first external audit.

**Outcome vs success criteria:**

- *Every finding fixed with a test that failed first, or recorded with rationale:* **Met.** The implementation notes give each finding's commit and its test. Three are dispositions, not code fixes, each with its reason:
  - X6: confirmations instead of a reorg rewinder.
  - W11: a warning, by decision 6.
  - D2: key rotation, which is an operator step.

  Characterization tests of existing code were shown to detect faults by mutation (contracts) or by corrupting their input (allowlist).
- *`script/test-fast.sh` passes with the site, artifact, SRI and cold-gas checks:* **Met.** It passes locally and on CI. The fast-suite portion of CI run 42354585838 shows 169 Foundry tests, including `test_C1_coldResolve_*`, `site-artifact.test.js` and `abi-overloads.test.js`.
- *The local end-to-end test proves indexer state equals chain state for all five policies and freeform:* **Met.** `test_single_winner_settles` through `test_weighted_overlap_settles` compare `total_winning_stake` with the contract's `payoutDenominator`, and `test_freeform_every_awkward_answer_settles_through_the_service` covers freeform.
- *A reverted transaction is reported as a failure by every service:* **Met.** `test_mined_revert_is_reported_as_failure` shows real `cast` exiting 0 and `run_cast_send` reporting failure. Each service delegates to that verdict, pinned by its own test:
  - resolution: `test_execute_reports_a_mined_revert_as_failed`
  - proposition: `test_mined_revert_is_not_ok`
  - sweeper: `test_sweeper.py`
  - CLI: `test_execute_reports_success_and_failure_through_the_exit_code`
- *`script/mutation-check.py` kills every listed mutation:* **Met.** 66 of 66, after the baseline run passes.
- *`forge coverage` runs:* **Met.** Results and its false gaps are in `docs/COVERAGE-BASELINE.md`.
- *After merge, the hosted propose scripts return 200:* recorded in the LOG entry for the merge.

**Outcome vs failure criteria:**

- *Additivity breach against the deployed factory:* **Avoided.**
  - Original creation signatures are kept and tested (`test_C3_originalOverloads_haveNoMinimum`).
  - The indexer and clients treat a missing `minNewTicketStake()` as zero (`test_adr0020_state.py`; `assertMeetsMinimum` in `bet-page.js`).
  - The read-only live suite passes against the deployed factory.
- *Factory over EIP-170:* **Avoided.** 22,650 B runtime, 1,926 B under the limit.
- *Another partial claim survives:* **Triggered three times, each caught before the merge:**
  - X1's fix stopped at the API, while the pages could still claim "No stakes yet" (W17).
  - A local stale artifact masked a missing `decimals()` (T2).
  - An early count in the implementation notes was wrong.

  The browser and CI layers caught the first two, which is why they now exist. **The headline lesson is that ADR-0019 verified each layer against itself, and most of what this pass found lay between layers:**
  - a page and its wallet library
  - a service and `cast`
  - the indexer and the pages that read it
  - the repository and what actually ships

**Lessons:** L-010 to L-016 in `LESSONS.md`.

**Follow-ups:** the operator steps in the implementation notes and `docs/TASKS.md`: key rotation, factory deploy, indexer and resolution redeploys, live suites, PyPI, a health alert, and the two open questions below.

**Revision schedule:** after the operator cutover; again at the first external audit.
