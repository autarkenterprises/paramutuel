# Paramutuel

Paramutuel provides permissionless, real crypto, blockchain-powered prop betting. Anyone can propose any wager, in any standard ERC-20 token, with configurable resolution criteria. Proposers, bettors, and resolvers interact on-chain, through a fully distributed protocol, without relying on centralized platforms to approve wagers or authorize payouts. Paramutuel is designed for agents, whether human or artificial: all aspects of the wager lifecycle are fully configurable, enabling a wide variety of uses: friendly bets, forecasting current events, sports betting, and more.

"Standard" has a precise meaning here. The contracts are solvent for ordinary ERC-20 collateral. Tokens that return no value from `transfer` (USDT-style) fail safely: bets cannot be placed. Fee-on-transfer and rebasing tokens are **not** supported: the wager credits the requested amount while custody receives less, so the last claimant cannot be paid. Curated surfaces flag tokens outside [`config/collateral-allowlist.json`](config/collateral-allowlist.json); see [ADR-0018](research/adr/ADR-0018-collateral-curation-overlay.md).

This repository is the reference implementation: smart contracts, dApp, website, indexer, MCP server, bet-scout agent, and operator services.

**Tagline:** "Augur for prop bets". Each wager's resolver, windows, and fee split are chosen at creation, so trust is explicit and per-wager rather than protocol-wide, with room to plug in more decentralized resolution later.

## Where to look

| To… | See |
|---|---|
| Understand states, roles, and timers | [`docs/WAGER-LIFECYCLE.md`](docs/WAGER-LIFECYCLE.md) |
| Understand payouts, with worked examples | [`docs/PAYOUT-CALCULATION.md`](docs/PAYOUT-CALCULATION.md) |
| Integrate a bot or LLM (HTTP API, ABI, MCP) | [`docs/MACHINE.md`](docs/MACHINE.md) |
| Operate services | [`docs/WORKFLOWS.md`](docs/WORKFLOWS.md), [`service/README.md`](service/README.md) |
| Host the indexer | [`docs/INDEXER-HOSTING.md`](docs/INDEXER-HOSTING.md), [`docs/CLOUD-RUN-HOSTING.md`](docs/CLOUD-RUN-HOSTING.md) |
| Run delegated resolution | [`docs/RESOLUTION-SERVICE.md`](docs/RESOLUTION-SERVICE.md) |
| See gas costs and limits | [`docs/PARAMUTUEL-V3-GAS.md`](docs/PARAMUTUEL-V3-GAS.md) |
| Read design decisions | [`research/adr/README.md`](research/adr/README.md) |
| See open work | [`docs/TASKS.md`](docs/TASKS.md) |
| Contribute | [`AGENTS.md`](AGENTS.md) (mandatory practices), [`LOG.md`](LOG.md), [`LESSONS.md`](LESSONS.md) |

## The protocol

One contract pair, `ParamutuelFactoryV3` and `ParamutuelWagerV3` (ADR-0010). Each wager is one of two immutable modes:

- **Enumerated:** 2 to 255 outcomes fixed at creation. A ticket is a bitmask of outcomes, so **mask 1 is outcome 0, mask 2 is outcome 1, and mask 3 is both**. The wager's payoff policy decides which tickets win: `SINGLE_WINNER`, `ANY_OF`, `EXACT_SET`, `AT_LEAST_K`, or `WEIGHTED_OVERLAP`.
- **Freeform:** no outcome list. Bettors stake on any text answer, and the resolver names the winning text. Matching is **byte-exact**: `Paris`, `paris`, and `Paris ` are three different pools.

### Roles

Each is an immutable address chosen at creation.

| Role | Can | If `address(0)` at creation |
|---|---|---|
| **Proposer** | Creates the wager. No powers afterwards. | n/a |
| **Resolver** | `resolve` or `retract`, once betting has closed and while the resolution window is open. | Defaults to the proposer |
| **Betting closer** | `closeBetting()` to end betting early. | Role disabled: time-based close only |
| **Resolution closer** | `closeResolutionWindow()` to end the resolver's window early, once betting has closed. | Role disabled: time-based only |
| **Fee recipients** | `withdrawFees()`. The protocol treasury plus up to 32 proposer-chosen recipients; total at most 100%. | n/a |

### Lifecycle

1. **Create.** `bettingCloseTime` is an absolute timestamp; `resolutionWindow` is a duration measured from when betting actually closes. Either may be `0` for "no time limit", which requires the matching closer, because otherwise the wager could never advance.
2. **Bet.** Until `bettingCloseTime`, or until the betting closer ends betting.
3. **Finalize.** While the resolution window is open the resolver may `resolve` or `retract`. Once it is over, anyone may `expire()`.
4. **Claim.** After a resolve, winners split the net pot. After a retract or expire, bettors get their stake back minus fees. Fee recipients withdraw separately.

Fees are charged once, at finalization, including on refunds.

**Know before you bet on a wager with no time limit.** If `bettingCloseTime` or `resolutionWindow` is `0`, that closer's key is the only way forward. If a no-time-limit betting closer loses its key, stakes are locked: neither `retract` nor `expire` can run while betting is open. Surfaces warn about this.

## Try it on Base Sepolia

You need [Foundry](https://getfoundry.sh), `python3`, `node`, an EVM wallet, and test funds: [USDC](https://faucet.circle.com/) and [ETH](https://www.alchemy.com/faucets/base-sepolia).

```bash
git clone --recurse-submodules https://github.com/autarkenterprises/paramutuel.git
cd paramutuel
forge build
./script/test-fast.sh   # contracts, services, clients; no keys or network needed
```

Base Sepolia wallet settings: RPC `https://sepolia.base.org`, chain ID `84532`, currency `ETH`, explorer `https://sepolia.basescan.org`. The public RPC is rate limited, so use your own provider for anything heavy.

### From a browser

```bash
./script/dapp/launch_dapp.sh   # then open http://localhost:8080/dapp/
```

Any wallet that injects an EIP-1193 provider works (MetaMask, Rabby, Coinbase Wallet, Frame, and others). WalletConnect is not bundled. The factory address fills in from `config/deployments.json`.

The hosted site is at `https://autarkenterprises.github.io/paramutuel/`; see [`docs/WEBSITE.md`](docs/WEBSITE.md).

### From the command line

```bash
export RPC_URL_BASE_SEPOLIA="https://sepolia.base.org"
export PRIVATE_KEY="0xYOUR_PRIVATE_KEY"
source ./script/lib/deployments.sh
ensure_factory_address "base-sepolia" "./config/deployments.json"
export TOKEN=0x036CbD53842c5426634e7929541eC2318f3dCF7e   # Base Sepolia USDC, 6 decimals
```

Create a yes/no wager. Arguments: collateral, proposition, outcomes, payoff policy (`0` = `SINGLE_WINNER`), policy parameter, betting close timestamp, resolution window in seconds, resolver, betting closer, resolution closer, extra fee recipients, extra fee bps. Zero addresses here mean "I resolve" and "no closers".

```bash
cast send "$FACTORY_ADDRESS" \
  "createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,address,address[],uint16[])" \
  "$TOKEN" "Will X happen?" '["YES","NO"]' 0 0 \
  "$(( $(date +%s) + 7200 ))" 7200 \
  0x0000000000000000000000000000000000000000 \
  0x0000000000000000000000000000000000000000 \
  0x0000000000000000000000000000000000000000 \
  "[]" "[]" \
  --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
```

The wager address is in the `WagerCreatedV3Enumerated` event, the first topic after the signature. Then bet. Tickets are masks, so `1` backs outcome 0 ("YES") and `2` backs outcome 1:

```bash
cast send "$TOKEN" "approve(address,uint256)" "$WAGER" 3000000 --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
cast send "$WAGER" "placeBet(uint256,uint256)" 1 1000000 --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
# Several tickets in one transaction:
cast send "$WAGER" "placeBets(uint256[],uint256[])" "[1,2]" "[1000000,1000000]" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
```

After betting closes, finalize and claim. `resolve` takes a winning **mask**, so outcome 0 is `1`:

```bash
cast send "$WAGER" "resolve(uint256)" 1 --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
# or, instead of resolving:
cast send "$WAGER" "retract()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
# or, once the window is over, from any address:
cast send "$WAGER" "expire()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"

cast send "$WAGER" "claim()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
cast send "$WAGER" "withdrawFees()" --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY"
```

Other creation forms, each extending the one before:

```text
createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,address,address[],uint16[],uint256[],uint256[])
    adds seedTicketMasks[] and seedAmounts[]: seed bets in the creation tx. Approve the FACTORY for the total.
createEnumeratedWager(address,string,string[],uint8,uint256,uint64,uint64,address,address,address,address[],uint16[],uint256[],uint256[],uint256)
    adds minNewTicketStake: minimum raw amount to open a new ticket, which prices griefing by dust tickets.
createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[])
createFreeformWager(address,string,uint64,uint64,address,address,address,address[],uint16[],uint256)
    adds minNewTicketStake.
```

**Freeform answers and `cast`:** do not pass answer strings through `cast` arguments. `cast` strips trailing whitespace and surrounding quotes, and parses a leading `--` as a flag, so what it sends may not be what you typed, and answers match byte-exactly. Use the control panel CLI, which encodes them exactly:

```bash
python3 -m service.control_panel.cli wager-action --wager "$WAGER" --action resolve \
  --protocol-version freeform --winning-answer "Paris"              # add --execute to send
```

`placeBet(string,uint256)` has the same constraint; use the dApp, the site, or the MCP server's `encode_place_bet_freeform`.

### Run the stack locally

```bash
cp config/service.env.example config/service.env   # then edit
source script/lib/load_service_env.sh
./script/testnet/launch_testnet.sh
```

This deploys a factory with [`script/DeployFactoryV3.s.sol`](script/DeployFactoryV3.s.sol) and records its address and deploy block in `config/deployments.json`, the shared default for every surface. It then prints the commands to start the indexer API (`:8090`), explorer (`:8091`), control panel (`:8092`), and sweeper.

To deploy only the factory:

```bash
export TREASURY_ADDRESS=0x...        # receives protocol fees
export PROTOCOL_FEE_BPS=100          # optional, default 100 (1%)
export MIN_BETTING_WINDOW=3600       # optional, seconds
export MIN_RESOLUTION_WINDOW=3600    # optional, seconds
forge script script/DeployFactoryV3.s.sol --rpc-url "$RPC_URL_BASE_SEPOLIA" --private-key "$PRIVATE_KEY" --broadcast
```

After contract changes, run `./script/sync-abi.sh` and commit the updated ABIs: the dApp and MCP server ship them, and a test fails if they drift.

## For agents

- **HTTP and ABI reference:** [`docs/MACHINE.md`](docs/MACHINE.md).
- **MCP server:** 21 tools at `mcp_server/`; run `python -m mcp_server`. Write tools return calldata for the caller to sign.
- **Bet scout:** a stdlib subagent at `agents/paramutuel_bettor/`; run `python3 -m agents.paramutuel_bettor`. See [`docs/BET-AGENT.md`](docs/BET-AGENT.md).

Both are packaged for PyPI (`paramutuel-mcp`, `paramutuel-bettor-agent`), but **neither is published yet**, so install them from this repository; see `docs/TASKS.md`.

## Testing

- `script/test-fast.sh`: everything that needs no key or network, and what CI runs.
- `script/test-local-e2e.sh`: every layer against a real local chain, with no secrets needed.
- `script/test-extended.sh`: the above plus the live Base Sepolia suites.
- `script/mutation-check.py`: proves the contract tests fail when guards are weakened.
- `forge coverage --ir-minimum --no-match-test 'C1_coldResolve|test_C2_freeform|test_C6_' --no-match-path 'test/ParamutuelV3Invariant.t.sol'`: contract coverage; see [`docs/COVERAGE-BASELINE.md`](docs/COVERAGE-BASELINE.md).

## Long-term design considerations

Smart contracts cannot observe real-world truth directly. A fully decentralized version of this protocol ultimately requires an oracle or resolution mechanism such as dispute-driven bonded reporting (Augur-style), an optimistic oracle, or restricting wagers to on-chain observable facts. The hard problems to plan for are invalid or ambiguous wagers, liveness when no one reports, spam and sybil resistance, and outcome representation. Because the resolver is just an address chosen per wager, any of these can be adopted later without changing deployed wagers (ADR-0001).
