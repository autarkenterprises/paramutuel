# ADR-0020 implementation notes — second verification pass

Companion to [`research/adr/ADR-0020-verification-remediation.md`](../research/adr/ADR-0020-verification-remediation.md).
Branch: `adr-0020-verification-remediation`.

## Method

1. **ADR-0019's conclusions were treated as hypotheses**, not facts. Each "fixed" or "verified" claim was re-tested against the code, the live chain, the hosted site and a real local chain.
2. **Contracts:** line-by-line review against ADR-0001, 0002, 0005, 0008, 0009 and 0010, plus Foundry proofs of concept. Gas was measured with cold storage, because Foundry tests run in one warm transaction and understate real cost by millions.
3. **Live facts were measured directly**: the deployed factory, the hosted site and indexer, and PyPI. They are listed in the ADR.
4. **Everything else was reviewed by the lead agent.** The Cursor `agent` CLI was unauthenticated, so no sub-agents were used.
5. **Fixes:** red then green, one logical unit per commit. Contract fixes are also proven by mutation testing.
6. **Two new layers test across boundaries**, which is where most of these bugs lived:
   - `test/integration/test_local_e2e.py`: anvil, real `cast`, the real indexer and every service.
   - `test/integration/test_browser_e2e.py`: real Chrome driving the public pages, checked against the chain.

## Findings and disposition

Finding IDs are the ADR's. "Evidence" names the test that failed before the fix and passes after it.

### Contracts — `a84810d`

| # | Disposition | Evidence |
|---|---|---|
| C1 | **Fixed (source).** Constant-time SWAR popcount. Single-outcome tickets are exempt from the 1,024 cap, so `_usedMasks` holds at most 1,279. Worst-case `resolve` falls from 20.1M gas to **6,663,978** in a real transaction, under the 16,777,216 cap. | `test_C1_coldResolve_*_fitsTxGasCap` (5 policies); `test_griefed_resolve_fits_the_real_per_transaction_gas_cap` (real tx) |
| C2 | **Fixed (source).** Freeform answer cap removed: nothing iterates the answers on-chain. | `test_C2_freeform_answerSpaceCannotBeExhausted_resolveAndClaimStayFlat` (1,100 answers) |
| C3 | **Fixed (source).** Single-bit exemption, plus an optional per-wager `minNewTicketStake` through additive creation overloads. | `test_C3_*` (5 tests); `test_min_new_ticket_stake_end_to_end` |
| C4 | **Fixed (source).** 512-bit `mulDiv` for every payout and fee. | `test_C4_*` (3 tests); `test_mulDiv_*` fuzz |
| C5 | **Fixed (source).** `FreeformAnswerRevealedV3(answerId, answer)`, emitted once per answer. | `test_C5_answerRevealed_onceWithExactBytes_beforeBetEvent` |
| C6 | **Fixed (source).** Write-only `_userAnswerIds` removed. | `test_C6_newAnswerBet_gasBound` |
| C7 | **Fixed (source).** Every zero payout reverts `NothingToClaim`. | `test_C7_*` (2 tests) |
| C8 | **Fixed (source).** `closeResolutionWindow` is a no-op once finalised. | `test_C8_closeResolutionWindow_afterFinalisation_isSilentNoOp` |
| C9 | **Fixed (source).** At most 32 extra fee recipients. | `test_C9_*` (2 tests) |
| C10 | **Fixed.** Constructor takes a struct, so `forge coverage` runs again. Ceiling aligned at 255. `treasury` and `protocolFeeBps` are immutable. Dead branches removed and comments corrected. | `docs/COVERAGE-BASELINE.md`; `test_resolve_rejectsWinningMaskAboveOptionRange` |

**"Source"** means fixed in `src/` but not live until the operator deploys the new factory (below). The changes are additive: every existing event and creation signature is unchanged, and the read-only live suite still passes against the deployed factory.

### Hosted and deployment

| # | Disposition | Commit | Evidence |
|---|---|---|---|
| D1 | **Fixed.** The site is copied by glob, and every page reference is checked against the built artifact. | `00ecad3` | `dapp/tests/site-artifact.test.js`; `test_propose_page_creates_the_wager_it_describes_after_refusing_bad_input` |
| D2 | **Fixed in tree.** The key stays in git history: **rotation is an operator step.** | `00ecad3` | `script/tests/test_scripts.py` |
| D3 | **Fixed.** `cast` pinned by checksum in both service images. The resolution image was built and `cast` checked inside it. | `00ecad3` | `script/tests/test_scripts.py` |
| D4, D5 | **Fixed.** V3 deploy script, and records the deploy block; `gcloud builds submit --config`. | `00ecad3` | `script/tests/test_scripts.py` |
| D6 | **Fixed.** `fast-suite.yml` runs the fast suite, the local end-to-end tests and a wheel build on every push, and Pages deploys depend on it. | `00ecad3`, `f8129d2` | CI runs on the branch |
| D7 | **Fixed.** SRI on all five wallet pages. | `52bf101`, `2da7fa4` | `site-artifact.test.js`; `test_every_page_loads_with_its_references_and_a_verified_ethers` |
| D8 | **Fixed.** The wheel bundles the deployments config and falls back to it. | `8a561d1` | CI step "MCP wheel builds and loads outside the repo" |

### Operator services

| # | Disposition | Commit | Evidence |
|---|---|---|---|
| O0, O3, O4 | **Fixed** by one mechanism: a stdlib ABI encoder (`service/control_panel/abi.py`, checked against `eth_abi`), so `cast` only ever receives raw calldata. | `087b51c` | `test_abi.py`; `test_freeform_every_awkward_answer_settles_through_the_service`; `test_outcome_labels_reach_the_chain_and_the_api_exactly` |
| O1 | **Fixed.** Success means a mined receipt with status 1. | `087b51c` | `test_cast_runner.py`; `test_mined_revert_is_reported_as_failure` |
| O2 | **Fixed.** Keys are redacted from every dry-run and every result. | `087b51c` | `test_dry_run_is_default_and_never_prints_the_key` and siblings |
| O5–O11 | **Fixed.** | `087b51c` | `test_adr0020_service.py`, `test_web.py`, `test_cli.py`, proposition `test_adr0020.py` |

### Indexer — `0b005f9`

| # | Disposition | Evidence |
|---|---|---|
| X1, X2 | **Fixed.** Outcome totals derived from ticket pools; `total_winning_stake` written using the policy's own math. (ADR-0021 U3 later split it: the contract's value is now `payout_denominator`, and `total_winning_stake` is plain stake.) | `test_adr0020_state.py`; the five `test_*_settles` end-to-end tests compare it to the contract's `payoutDenominator` |
| X3 | **Fixed.** Incomplete metadata is flagged and backfilled. | `test_adr0020_state.py` |
| X4 | **Fixed.** A skipped log is counted, described in `/health`, and rolled back cleanly by a SAVEPOINT. Timestamps are clamped. | `test_skipped_log_is_counted_and_described` |
| X5 | **Fixed.** Address-filtered `eth_getLogs`. | `test_indexer_ignores_a_contract_spoofing_our_topics` |
| X6 | **Mitigated.** `INDEXER_CONFIRMATIONS` (default 5); the reorg note is now in `docs/INDEXER-HOSTING.md`. A full rewinder is not built. | `test_live_api_runtime.py` |
| X7 | **Fixed.** | `test_adr0020_api.py` |

### Clients

| # | Disposition | Commit | Evidence |
|---|---|---|---|
| W1 | **Fixed.** One writer of the submit button's state. | `52bf101` | `test_bet_page_stays_blocked_after_betting_closes` |
| W2, W3 | **Fixed.** No stake with unknown decimals; amounts parsed as text. | `52bf101` | `site-bet-logic.test.js`; `test_bet_page_stakes_exact_amounts_and_says_so` |
| W4 | **Fixed.** | `52bf101` | `test_dapp_runs_a_freeform_wager_to_payout_with_exact_bytes` |
| W5 | **Fixed.** | `52bf101` | the propose browser test |
| W6, W7 | **Fixed.** | `52bf101` | `site-bet-logic.test.js`; the dApp browser test switches accounts and checks who claimed |
| W8, W9 | **Fixed.** | `8a561d1` | `mcp_server/tests/test_adr0020.py`; `agents/paramutuel_bettor/tests/test_adr0020.py` |
| W10 | **Fixed** by ADR-0018's allowlist: no self-reported symbols, and a warned opt-in. | `52bf101` | `test_bet_page_names_a_listed_token_and_does_not_warn` |
| W11 | **Warned, by decision** (ADR decision 6). | `52bf101` | `site-bet-logic.test.js` |

### Documentation and process

| # | Disposition |
|---|---|
| R1, R2, R3 | **Fixed** in `00ecad3`, `56ac338` and `f3c7f76`. README, MACHINE, lifecycle, workflow, payout, gas, hosting, runbook, service and agent docs now describe V3 and say what is true: neither package is on PyPI, and collateral is "any standard ERC-20". |
| R4 | **Fixed.** The mutation harness is committed (`script/mutation-check.py`), and ADR-0019's AAR is revised. |
| R5 | **Recorded** in `LOG.md` with a practices review. |
| R6 | **Fixed.** ADR-0018 merged in `4f6a443` and implemented. |

## Found during remediation

These are not in the ADR's original tables. Each was found by a test written during this work, and the last column names the test that caught it.

| # | Finding | Severity | Commit | Caught by |
|---|---|---|---|---|
| W14 | **The dApp could not resolve any wager or place a single bet, and the bet page could not take a freeform stake.** ethers v6 cannot choose between overloads of the same length by value, so `contract.placeBet(...)` and `contract.resolve(...)` threw "ambiguous function description". The bet paths failed only after the user had paid for an approve. This dates from V3, and no unit test noticed because every other layer encodes by signature. | **Critical** | `2da7fa4` | The browser test; pinned in the fast suite by `dapp/tests/abi-overloads.test.js` |
| W12 | The bet page erased "placed successfully" at once, then showed stale figures until a manual reload. | Medium | `2da7fa4` | `test_bet_page_stakes_exact_amounts_and_says_so` |
| W13 | The bet and propose pages kept the old account after a wallet switch. The propose page also kept the old account as the suggested resolver. | Medium | `2da7fa4` | `test_*_follows_a_wallet_account_change` |
| W15 | Opening `/explorer/` directly said "Indexer offline", because only a parent page passed the API URL. | Low | `2da7fa4` | `test_explorer_finds_the_indexer_when_opened_directly` |
| W16 | `dapp/logic.js` accepted 256 outcomes; the contracts allow 255. | Low | `2da7fa4` | `logic.test.js` |
| W17 | The home ticker and bet search said "No stakes yet" beside a non-zero pot whenever a wager's detail or outcome labels were not loaded yet. Labels are missing between a wager's creation and the indexer reading them, so X1's false claim survived its fix in that window. Only a zero pot now says "no stakes". | Medium | this unit | Seen intermittently in `test_public_listings_show_real_stakes`; pinned by `test_public_listings_never_claim_no_stakes_when_the_pot_has_some` |
| O12 | A corrupt decision file reset connections on all three resolution routes. Now JSON errors, and the daemon refuses to act on it. | Medium | `ecef7b2` | `CorruptDecisionsFileTests` |
| O13 | The proposition `PATCH` route reset the connection on a body that is not a JSON object, or not UTF-8. | Low | `ecef7b2` | `test_patch_rejects_bodies_that_are_not_json_objects` |
| O14 | `cast`'s poller can log to stdout after the receipt, which made a mined transaction read as failed. This was a bug in this pass's own new code. | High | `8a561d1` | `test_log_noise_after_the_receipt_does_not_hide_success` |
| D9 | `mcp>=1.0.0` was unbounded, and mcp 2.x removed the module the server imports, so every fresh install failed. | High | `56ac338` | The first CI run; `test_mcp_dependency_excludes_the_major_version_that_breaks_the_import` |
| D10 | The tests used ethers 6.16 while the pages load 6.13.5. Now pinned, with a test that each page's SRI hash matches the tested bundle. | Low | `2da7fa4` | `site-artifact.test.js` |
| D11 | A dead dApp link (`../docs/PAYOUT-CALCULATION.md`) and a broken gas-profile script. | Low | `00ecad3` | `site-artifact.test.js`; `script/tests/test_scripts.py` |
| T1 | Python unit coverage was 78%. The live indexer process was at 23%, and RPC bisection, cursor resume and replay were never run by any unit test. Now 99%, with the residue justified. | Process | `ecef7b2` | `docs/COVERAGE-BASELINE.md` |
| T2 | The end-to-end tests found contract artifacts by name, so a stale artifact of a deleted test could stand in for the real mock. That differed between machines and hid that the mock had no `decimals()`. | Process | this unit | CI |
| R7 | ADR-0018's drift mitigation, a schema check on the allowlist, was never written. | Low | this unit | `dapp/tests/collateral-allowlist.test.js`, checked against a corrupted copy |

## Mutation evidence (AGENTS.md #1)

`python3 script/mutation-check.py` reports **66 of 66 killed**, after a baseline run of the unmodified code passes first. It took 2,586 seconds with the optimizer off, which is about five times faster to compile and does not change whether a guard holds. Each mutation is one exact-string replacement, and a pattern that no longer matches fails the run as STALE, so the list cannot rot silently. The harness also covers ADR-0019's 28 mutations, whose script was never committed.

## Verification

| Check | Result |
|---|---|
| `script/test-fast.sh` | Passes. 169 Foundry tests (139 plus 30 invariants over 6 wager shapes), the revert-path check, 548 Python unit tests and 93 node tests. |
| `script/test-local-e2e.sh` | All 38 pass: 18 local-chain tests and 20 browser tests. |
| CI (`fast-suite.yml`) | The fast suite passes on CI. See the AAR for the end-to-end step. |
| Read-only live suite against the deployed factory | 1 run and passed, 8 skipped. The skipped tests need a funded key. |
| `forge build --sizes` | Factory 22,650 B runtime (1,926 B under EIP-170). Wager 11,670 B. |
| Coverage | Solidity 98.9% / 98.5% of lines for factory / wager, with the gaps explained. Python 99%. |
| Docker | `Dockerfile.resolution` built, and `cast` runs inside it. |

**Not run, and why:**

- The `minimal-tx` and `funded-tx` live suites need the operator's key and spend testnet funds.
- `Dockerfile.proposition` was not built. It shares the resolution image's checksummed `cast` install, which was verified.
- No external audit. ADR-0020 is not a substitute for one before mainnet.

## Operator follow-ups

Each step is outward-facing, so it is left to the operator, in this order.

1. **Rotate the Alchemy key** that `README.md` carried. It stays in git history, and rewriting history would not un-leak it. Revoke it in the Alchemy dashboard and put the new one only in `config/service.env` and the Cloud Run secrets.
2. **Deploy the corrected factory.** The live factory has `wagersCount() == 0`, so nobody is stranded. Fill in `config/service.env` (see `config/service.env.example`), then:
   ```bash
   ./script/testnet/launch_testnet.sh     # runs script/DeployFactoryV3.s.sol, then set_factory_address.sh
   git add config/deployments.json && git commit -m "deploy: ADR-0020 factory" && git push origin master
   ```
   To deploy by hand instead: `forge script script/DeployFactoryV3.s.sol --rpc-url "$RPC_URL_BASE_SEPOLIA" --broadcast`, then `./script/testnet/set_factory_address.sh <address> base-sepolia <deploy-block>`.
3. **Redeploy the hosted indexer, on persistent storage.** It currently returns 500/503. Use one instance with a volume, and set `INDEXER_DB_PATH` on the volume (`docs/CLOUD-RUN-HOSTING.md`). Then run `./script/deploy/redeploy_cloud_run_indexer.sh` and check `GET /health`.
4. **Redeploy the resolution service** with `RESOLUTION_SERVICE_TOKEN` set: `./script/deploy/redeploy_cloud_run_resolution.sh`.
5. **Run the live suites** against the new factory: `TESTNET_MODE=minimal-tx`, then `funded-tx ./script/testnet/run_live_suite.sh`.
6. **PyPI.** Configure Trusted Publishing for `paramutuel-bettor-agent`, then push a `bettor-agent-vX.Y.Z` tag. `paramutuel-mcp` has no publish workflow at all yet, so add one or publish by hand.
7. **Alert on the indexer's `/health`.** It was down with nobody notified.
8. **Decide the open questions** in the ADR.
