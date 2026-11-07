// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";
import {BitMath} from "./utils/BitMath.sol";
import {FullMath} from "./utils/FullMath.sol";
import {ReentrancyGuard} from "./utils/ReentrancyGuard.sol";

/// @title Paramutuel wager v3 — enumerated (ADR-0008) or freeform text (ADR-0009) in one deployable
/// @notice Immutable `MODE` at construction. Breaking ABI vs v2/freeform: V3-prefixed events; freeform
///         `answerId` uses domain-separated hash (see `_answerId`).
/// @notice Lifecycle (ADR-0001 / ADR-0005): `Open` -> `Resolved` (via `resolve` while the
///         resolution window is open) OR `Open` -> `Retracted` (via `retract` by resolver, or
///         `expire` by anyone after the window closes — both land in `Retracted`, the latter
///         emits `ExpiredV3` rather than `RetractedV3` to disambiguate operator-driven cancellation
///         from deadline-driven cleanup). The state machine is one-way: terminal states never
///         transition further. Betting can be closed two ways: time-based (via `bettingCloseTime`
///         elapsing) or authority-driven (via `bettingCloser` calling `closeBetting`); the
///         resolution window mirrors this.
/// @notice Mode dispatch: external functions are partitioned by `onlyEnumerated` /
///         `onlyFreeform` modifiers based on the immutable `MODE`. Calling a wrong-mode entry
///         reverts with `WrongMode`. Two `placeBet` and two `resolve` overloads exist (one per
///         mode); Solidity's overload resolution picks by argument type. State (`_outcomes`,
///         `numOptions`, `_usedMasks`, `betsByMask`, `_userMasks` vs `_usedAnswerIds`,
///         `betsByAnswer`) is intentionally declared for both modes — mappings and dynamic arrays
///         cost nothing until written, so the unused mode's state simply stays empty, in exchange
///         for a single audited contract bytecode.
/// @notice Fee accounting (ADR-0002): fee recipients and bps are immutable post-construction.
///         Fees are charged exactly once, on the single transition out of `Open`, then accrued into
///         per-recipient `feeBalances` for pull-style withdrawal. Bettor claims read `netPot =
///         totalPot - _totalFeesAmount()` to compute the parimutuel split.
/// @notice Storage layout invariants:
///         - `MODE`, `factory`, `proposer`, `resolver`, `bettingCloser`, `resolutionCloser`,
///           `collateralToken`, the three `*Time/Window/Deadline` fields, `payoffPolicy`,
///           `policyParam`, `numOptions`, and `minNewTicketStake` are all `immutable` and
///           live in code rather than storage.
///         - `proposition` and `_outcomes` are `string` / `string[]` and live in storage but
///           are written once in the constructor and never mutated afterwards (no setter).
///         - `_usedMasks` / `_usedAnswerIds` are append-only enumeration arrays that mirror
///           the keys of `ticketPoolByMask` / `ticketPoolByAnswerId`. `_usedMasks` is iterated at
///           enumerated resolution, so it is bounded and that bound is what keeps `resolve` under
///           the per-transaction gas cap. `_usedAnswerIds` is only a read surface for off-chain
///           callers: nothing on-chain iterates it, so it needs no bound (ADR-0020).
contract ParamutuelWagerV3 is ReentrancyGuard {
    /// @dev Three states, two terminal: `Resolved` (a winning outcome was recorded;
    ///      bettors with a winning ticket can claim a parimutuel slice) and
    ///      `Retracted` (no winner was recorded; every bettor can claim back their
    ///      stake net of fees, prorated against the gross `totalPot`). `expire()`
    ///      lands in `Retracted` because economically it is the same outcome:
    ///      everyone gets their stake back. The distinguishing event (`RetractedV3`
    ///      vs `ExpiredV3`) records *why* the wager was retracted for off-chain UIs.
    enum State {
        Open,
        Resolved,
        Retracted
    }

    /// @dev Set once at construction and never changed. The wager's external surface is
    ///      partitioned around this enum via the `onlyEnumerated` / `onlyFreeform`
    ///      modifiers; storage for both modes is allocated but only one is populated.
    enum WagerMode {
        Enumerated,
        Freeform
    }

    /// @dev Inherited from ADR-0008 (V2 enumerated). Each policy decides (a) which
    ///      ticket masks are admissible at bet time and (b) how `_ticketWins` and
    ///      `_accumulateWinningUnits` derive winners and weight from the resolver-
    ///      supplied `winningMask`. Policy is immutable per wager. Numeric ordering
    ///      is wire-stable (off-chain encoders cast to `uint8`) — never re-order.
    enum PayoffPolicy {
        SINGLE_WINNER,
        ANY_OF,
        EXACT_SET,
        AT_LEAST_K,
        WEIGHTED_OVERLAP
    }

    event BetPlacedV3Enumerated(address indexed bettor, uint256 ticketMask, uint256 amount);
    event BetPlacedV3Freeform(address indexed bettor, bytes32 indexed answerId, uint256 amount);
    /// @notice Emitted exactly once per distinct answer, when it receives its first stake. This is
    ///         the only on-chain record of an answer's text: `BetPlacedV3Freeform` carries just the
    ///         hash, and without the text bettors cannot join an existing answer and a resolver
    ///         cannot see what was staked unless they replay calldata (ADR-0009, ADR-0020 C5).
    ///         Emitted before the bet event in the same transaction.
    event FreeformAnswerRevealedV3(bytes32 indexed answerId, string answer);
    event BettingClosedByAuthorityV3(uint64 closedAt);
    event ResolutionWindowClosedByAuthorityV3(uint64 closedAt);
    event ResolvedV3Enumerated(uint256 winningMask);
    event ResolvedV3Freeform(bytes32 indexed winningAnswerId);
    event RetractedV3();
    event ExpiredV3();
    event ClaimedV3(address indexed bettor, uint256 amount);
    event FeeAccruedV3(address indexed recipient, uint256 amount);
    event FeeWithdrawnV3(address indexed recipient, uint256 amount);

    error InvalidOutcome();
    error InvalidTicketMask();
    error NotOpen();
    error BettingClosed();
    error BettingNotClosed();
    error ResolutionWindowOver();
    error NotResolver();
    error NotBettingCloser();
    error NotResolutionCloser();
    error AlreadyFinalized();
    error NothingToClaim();
    error FeeConfigMismatch();
    error FeeTooHigh();
    error NotFactory();
    error ArrayLengthMismatch();
    error TooManyDistinctTickets();
    error InvalidWinningMask();
    error NoWinningStake();
    error InvalidPolicyParam();
    error WrongMode();
    error EmptyAnswer();
    error AnswerTooLong();
    error NewTicketStakeTooLow();

    uint256 public constant BPS_DENOMINATOR = 10_000;
    /// @dev Hard cap on the byte length of a freeform answer string. 1024 bytes is
    ///      enough for any reasonable natural-language answer while bounding the
    ///      keccak input size and protecting against gas-griefing via huge calldata.
    uint256 public constant MAX_ANSWER_BYTES = 1024;
    /// @dev Cap on distinct *multi-outcome* tickets once `_usedMasks` holds this many entries. It
    ///      bounds the `O(n)` loop in `_accumulateWinningUnits`. Single-outcome tickets are exempt
    ///      so basic betting can never be locked out, which makes the true bound on
    ///      `_usedMasks.length` `MAX_DISTINCT_TICKETS + numOptions` (at most 1279). Worst-case cold
    ///      `resolve` is pinned below the 2^24 gas cap by `test_C1_coldResolve_absoluteWorstCase_*`.
    uint256 public constant MAX_DISTINCT_TICKETS = 1024;
    /// @dev Prepended to `bytes(answer)` before keccak so freeform answer ids cannot
    ///      collide with any other domain-separated `bytes32` in the protocol. The
    ///      specific byte `0x03` is fixed by the off-chain convention (see ADR-0009
    ///      and indexer / dApp encoders) — it MUST stay in lockstep across the
    ///      contract, the indexer's answer-id reconstruction, and the dApp's calldata
    ///      builder. Changing this byte is a hard fork of the freeform answer space.
    bytes1 public constant FREEFORM_ANSWER_DOMAIN = bytes1(0x03);

    /// @dev Discriminator for which storage subset is in use. Set in the constructor;
    ///      every external entry point gates on this via `onlyEnumerated` /
    ///      `onlyFreeform` so cross-mode calls revert before touching state.
    WagerMode public immutable MODE;

    /// @dev Role addresses — all immutable per ADR-0001. `factory` is granted the
    ///      seed-bet privilege; `proposer` is informational only at the contract
    ///      layer (off-chain attribution); `resolver` is the sole caller permitted
    ///      to call `resolve` / `retract`; `bettingCloser` and `resolutionCloser`
    ///      are the human authorities for the two lifecycle transitions (ADR-0005).
    address public immutable factory;
    address public immutable proposer;
    address public immutable resolver;
    address public immutable bettingCloser;
    address public immutable resolutionCloser;
    IERC20 public immutable collateralToken;

    /// @dev Lifecycle clocks: `bettingCloseTime == 0` means "no time-based close,
    ///      authority-only", and `resolutionWindow == 0` means "no time-based
    ///      resolution deadline, authority-only". Either value being zero forces the
    ///      corresponding *Closer to be non-zero (factory enforces this). When both
    ///      are non-zero, `resolutionDeadline = bettingCloseTime + resolutionWindow`
    ///      is precomputed for cheap reads.
    uint64 public immutable bettingCloseTime;
    uint64 public immutable resolutionWindow;
    uint64 public immutable resolutionDeadline;

    /// @dev `proposition` is the human-readable question. It lives in storage rather
    ///      than calldata-only because off-chain consumers (indexer, dApp, MCP) read
    ///      it from chain state without relying on log retention. Written once.
    string public proposition;
    State public state;

    PayoffPolicy public immutable payoffPolicy;
    uint256 public immutable policyParam;

    /// @dev Enumerated mode only. Empty in freeform mode.
    string[] private _outcomes;
    uint256 public immutable numOptions;

    /// @dev Minimum stake that may open a *new* ticket mask or answer; zero disables it. Re-betting
    ///      an existing ticket is never restricted. Proposer-chosen because only the proposer knows
    ///      what a meaningful amount of their collateral is. It prices griefing by dust tickets:
    ///      filling the multi-outcome cap costs `1024 * minNewTicketStake` at risk instead of only
    ///      gas, and that stake pays into the pot.
    uint256 public immutable minNewTicketStake;

    /// @dev Gross sum of every recorded bet (including seeds). Net pot at claim time
    ///      is `totalPot - _totalFeesAmount()`. Never decremented after a claim —
    ///      the parimutuel math relies on the gross total being stable post-resolve.
    uint256 public totalPot;

    // --- Enumerated-mode bet storage ---
    // `_usedMasks` is the append-only enumeration of every distinct mask seen; it
    // mirrors the keys of `ticketPoolByMask` so `_accumulateWinningUnits` can iterate
    // the pool without walking a separate index. `_userMasks[bettor]` is the
    // per-user version, used to drive the multi-ticket claim loop in `claim()`.
    uint256[] private _usedMasks;
    mapping(uint256 => uint256) public ticketPoolByMask;
    mapping(address => mapping(uint256 => uint256)) public betsByMask;
    mapping(address => uint256[]) private _userMasks;
    mapping(address => uint256) public userTotalBet;

    // --- Freeform-mode bet storage ---
    // Same shape as the enumerated side but keyed by `bytes32` answer id instead of
    // `uint256` ticket mask. Unlike `_usedMasks`, `_usedAnswerIds` is unbounded: freeform `resolve`
    // and `claim` are O(1) lookups, so a long list costs on-chain logic nothing. An earlier cap on
    // this array protected nothing and let anyone lock out new answers for about a dollar of gas
    // (ADR-0020 C2). There is no per-user answer list either, because `claim` needs only
    // `betsByAnswer[bettor][winningAnswerId]`.
    mapping(bytes32 => uint256) public ticketPoolByAnswerId;
    bytes32[] private _usedAnswerIds;
    mapping(address => mapping(bytes32 => uint256)) public betsByAnswer;

    /// @dev `feeRecipients` / `feeBps` are written once in the constructor and never
    ///      mutated. `totalFeeBps` is the cached sum used to compute `_totalFeesAmount`
    ///      cheaply at claim time without re-walking `feeBps`.
    address[] public feeRecipients;
    uint16[] public feeBps;
    uint256 public totalFeeBps;

    /// @dev Pull-pattern fee accrual: fees are credited to per-recipient balances at finalisation
    ///      (`_chargeFees`) and recipients later call `withdrawFees`. No separate "charged" flag:
    ///      every terminal path checks `state == Open` and leaves it, so charging cannot repeat.
    mapping(address => uint256) public feeBalances;

    /// @dev Resolution outputs. `winningMask` is populated only on enumerated resolve;
    ///      `winningAnswerId` only on freeform resolve. `payoutDenominator` holds the
    ///      pre-fee winning-units total (enumerated: weighted sum from
    ///      `_accumulateWinningUnits`; freeform: `ticketPoolByAnswerId[winId]`) so
    ///      claim math does not have to walk the entire pool a second time.
    uint256 public winningMask;
    bytes32 public winningAnswerId;
    uint256 public payoutDenominator;

    /// @dev One-shot per-bettor flag. `claim()` aggregates every winning ticket the
    ///      bettor holds in a single call (per-mask loop in enumerated mode), then
    ///      sets the flag — partial claiming is not supported by design (cleaner
    ///      accounting, fewer state writes, and matches the pull-once UX).
    mapping(address => bool) public hasClaimed;

    /// @dev Authority-driven betting close (ADR-0005). When set, `bettingClosedAtByAuthority`
    ///      is the timestamp the close happened, which feeds `_resolutionWindowOpen` /
    ///      `_resolutionWindowOver` to anchor the resolution window even when there is
    ///      no time-based `bettingCloseTime`.
    bool public bettingClosedByAuthority;
    uint64 public bettingClosedAtByAuthority;
    bool public resolutionWindowClosedByAuthority;

    /// @notice Everything a wager is constructed with. A struct rather than positional arguments so
    ///         `forge coverage` can instrument the contract: its unoptimised ABI decoder ran out of
    ///         stack on the former 17-argument constructor (ADR-0013, ADR-0020 C10).
    struct InitParams {
        WagerMode mode;
        address factory;
        address proposer;
        address resolver;
        address bettingCloser;
        address resolutionCloser;
        address collateralToken;
        string proposition;
        string[] outcomes;
        PayoffPolicy payoffPolicy;
        uint256 policyParam;
        uint64 bettingCloseTime;
        uint64 resolutionWindow;
        uint64 resolutionDeadline;
        address[] feeRecipients;
        uint16[] feeBps;
        uint256 minNewTicketStake;
    }

    /// @dev The factory is the only sanctioned constructor caller; all validation is
    ///      duplicated here as defence-in-depth in case a future deployment path
    ///      ever bypasses the factory. The constructor branches on `p.mode` to write
    ///      the enumerated discriminator state (`_outcomes`, `numOptions`, `policyParam`), or
    ///      to reject any enumerated-only input in freeform mode.
    constructor(InitParams memory p) {
        MODE = p.mode;
        factory = p.factory;
        proposer = p.proposer;
        resolver = p.resolver;
        bettingCloser = p.bettingCloser;
        resolutionCloser = p.resolutionCloser;
        collateralToken = IERC20(p.collateralToken);
        proposition = p.proposition;
        payoffPolicy = p.payoffPolicy;
        policyParam = p.policyParam;
        bettingCloseTime = p.bettingCloseTime;
        resolutionWindow = p.resolutionWindow;
        resolutionDeadline = p.resolutionDeadline;
        minNewTicketStake = p.minNewTicketStake;

        if (p.feeRecipients.length != p.feeBps.length) revert FeeConfigMismatch();
        feeRecipients = p.feeRecipients;
        feeBps = p.feeBps;
        uint256 sum;
        for (uint256 i; i < p.feeBps.length; i++) sum += p.feeBps[i];
        if (sum > BPS_DENOMINATOR) revert FeeTooHigh();
        totalFeeBps = sum;

        // Mode-specific initialisation. `numOptions` is forced to zero in freeform mode so any
        // stray read of the wrong-mode value is obviously invalid rather than silently degraded.
        if (p.mode == WagerMode.Enumerated) {
            require(p.outcomes.length >= 2, "OUTCOMES_MIN");
            // Same ceiling as the factory's `MAX_OUTCOMES`. It also keeps every mask at most 255
            // bits wide, which is what makes `BitMath.popcount` exact.
            require(p.outcomes.length <= 255, "OUTCOMES_MAX");
            _outcomes = p.outcomes;
            numOptions = p.outcomes.length;
            if (p.payoffPolicy == PayoffPolicy.AT_LEAST_K) {
                if (p.policyParam < 1 || p.policyParam > p.outcomes.length) revert InvalidPolicyParam();
            } else if (p.policyParam != 0) {
                revert InvalidPolicyParam();
            }
        } else {
            if (p.outcomes.length != 0) revert InvalidOutcome();
            numOptions = 0;
            if (p.policyParam != 0) revert InvalidPolicyParam();
        }

        state = State.Open;
    }

    modifier onlyEnumerated() {
        if (MODE != WagerMode.Enumerated) revert WrongMode();
        _;
    }

    modifier onlyFreeform() {
        if (MODE != WagerMode.Freeform) revert WrongMode();
        _;
    }

    /// @dev Betting is closed if either the authority closed it (sticky) or the
    ///      timed deadline has elapsed. The two close mechanisms are independent and
    ///      either suffices; whichever fires first wins.
    function _bettingClosed() internal view returns (bool) {
        return bettingClosedByAuthority || (bettingCloseTime != 0 && block.timestamp >= bettingCloseTime);
    }

    /// @dev The timestamp betting closed at, which anchors the resolution window. Only meaningful
    ///      once `_bettingClosed()` is true; every terminal path checks that first. An authority
    ///      close can only happen before the timed close (later calls are no-ops), so when the
    ///      flag is set its timestamp is the true close.
    function _bettingClosedAt() internal view returns (uint64) {
        return bettingClosedByAuthority ? bettingClosedAtByAuthority : bettingCloseTime;
    }

    /// @dev `resolutionWindow == 0` means "no time bound" and the window is open
    ///      indefinitely until the authority closes it. Otherwise the window opens
    ///      at `_bettingClosedAt()` and runs for `resolutionWindow` seconds. Callers must already
    ///      have established that betting is closed.
    function _resolutionWindowOpen() internal view returns (bool) {
        if (resolutionWindowClosedByAuthority) return false;
        if (resolutionWindow == 0) return true;
        return block.timestamp <= uint256(_bettingClosedAt()) + uint256(resolutionWindow);
    }

    /// @dev Strict complement of `_resolutionWindowOpen`, so there is no gap and no overlap between
    ///      "the resolver may act" and "anyone may expire". `expire()` gates on this.
    function _resolutionWindowOver() internal view returns (bool) {
        return !_resolutionWindowOpen();
    }

    /// @notice Authority-driven betting close (ADR-0005). Idempotent: re-calls after
    ///         betting has already closed (by either path) are silent no-ops, not
    ///         reverts — this matches the operator UX where retrying a tx after a
    ///         time-based close fired in between should not error.
    function closeBetting() external {
        if (msg.sender != bettingCloser) revert NotBettingCloser();
        if (_bettingClosed()) return;
        bettingClosedByAuthority = true;
        // Capture the wall-clock close time so the resolution window has a stable
        // anchor even when `bettingCloseTime` is zero.
        bettingClosedAtByAuthority = uint64(block.timestamp);
        emit BettingClosedByAuthorityV3(bettingClosedAtByAuthority);
    }

    /// @notice Authority-driven resolution-window close (ADR-0005). Forces the
    ///         resolution window to terminate so `expire()` becomes callable
    ///         immediately. Requires betting to already be closed (you cannot close
    ///         the resolution window before betting has ended).
    function closeResolutionWindow() external {
        if (msg.sender != resolutionCloser) revert NotResolutionCloser();
        if (!_bettingClosed()) revert BettingNotClosed();
        // Silent no-op when already closed, or when the wager is finalised and the window no longer
        // means anything, so retried transactions neither fail nor emit a misleading event.
        if (resolutionWindowClosedByAuthority || state != State.Open) return;
        resolutionWindowClosedByAuthority = true;
        emit ResolutionWindowClosedByAuthorityV3(uint64(block.timestamp));
    }

    function outcomesCount() external view returns (uint256) {
        return _outcomes.length;
    }

    function outcomeText(uint256 index) external view returns (string memory) {
        if (index >= _outcomes.length) revert InvalidOutcome();
        return _outcomes[index];
    }

    function usedMasksCount() external view onlyEnumerated returns (uint256) {
        return _usedMasks.length;
    }

    function usedMaskAt(uint256 i) external view onlyEnumerated returns (uint256) {
        return _usedMasks[i];
    }

    function userMasksCount(address bettor) external view onlyEnumerated returns (uint256) {
        return _userMasks[bettor].length;
    }

    function userMaskAt(address bettor, uint256 i) external view onlyEnumerated returns (uint256) {
        return _userMasks[bettor][i];
    }

    function usedAnswerIdsCount() external view onlyFreeform returns (uint256) {
        return _usedAnswerIds.length;
    }

    function usedAnswerId(uint256 i) external view onlyFreeform returns (bytes32) {
        return _usedAnswerIds[i];
    }

    /// @dev Mask must be non-zero (the empty ticket has no semantics) and must not
    ///      have any bit set above the legal option range. Shifting by `numOptions`
    ///      isolates the high bits; if any survive, the mask references a non-
    ///      existent option.
    function _validateMask(uint256 mask) internal view {
        if (mask == 0) revert InvalidTicketMask();
        if (mask >> numOptions != 0) revert InvalidTicketMask();
    }

    /// @dev Per-policy admissibility for bet tickets. SINGLE_WINNER demands exactly
    ///      one bit set (the canonical "I bet on option X" ticket). Every other
    ///      policy admits any non-empty mask — multi-bit tickets are the whole
    ///      point of `ANY_OF` / `EXACT_SET` / `AT_LEAST_K` / `WEIGHTED_OVERLAP`.
    function _policyAllowsTicket(PayoffPolicy policy, uint256 mask) internal pure {
        if (policy == PayoffPolicy.SINGLE_WINNER && !BitMath.isSingleBit(mask)) revert InvalidTicketMask();
    }

    /// @dev Bound the freeform answer string. Empty answers are rejected (would map
    ///      to a degenerate hash); over-length answers are rejected for gas safety.
    function _validateAnswer(string calldata answer) internal pure {
        uint256 length = bytes(answer).length;
        if (length == 0) revert EmptyAnswer();
        if (length > MAX_ANSWER_BYTES) revert AnswerTooLong();
    }

    /// @dev Domain-separated answer id. The `FREEFORM_ANSWER_DOMAIN` byte (0x03)
    ///      MUST appear here, in the indexer's id reconstruction, and in the dApp's
    ///      calldata builder — they are the same hash function in three languages.
    ///      `abi.encodePacked` is correct here because the prefix is a fixed-width
    ///      `bytes1` and the variable-length `bytes` follows; there is no ambiguity.
    function _answerId(string calldata answer) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(FREEFORM_ANSWER_DOMAIN, bytes(answer)));
    }

    /// @notice Enumerated-mode single-ticket bet. Collateral is pulled before the bet is recorded,
    ///         so bookkeeping can never exceed custody for a standard token. That is the reverse of
    ///         checks-effects-interactions, so `nonReentrant` is what stops a hostile token from
    ///         re-entering any state-changing entry point during the pull.
    function placeBet(uint256 ticketMask, uint256 amount) external nonReentrant onlyEnumerated {
        if (state != State.Open) revert NotOpen();
        if (_bettingClosed()) revert BettingClosed();

        _validateMask(ticketMask);
        _policyAllowsTicket(payoffPolicy, ticketMask);
        require(amount > 0, "AMOUNT");

        bool ok = collateralToken.transferFrom(msg.sender, address(this), amount);
        require(ok, "TRANSFER_FROM");

        _recordBetMask(msg.sender, ticketMask, amount);
    }

    /// @notice Batched enumerated-mode bet. Validates and sums every entry first, then
    ///         pulls collateral once for the batch total, then records each bet. Doing
    ///         a single `transferFrom` saves one external call per extra ticket.
    function placeBets(uint256[] calldata ticketMasks, uint256[] calldata amounts) external nonReentrant onlyEnumerated {
        if (state != State.Open) revert NotOpen();
        if (_bettingClosed()) revert BettingClosed();
        if (ticketMasks.length == 0 || ticketMasks.length != amounts.length) revert ArrayLengthMismatch();

        // First pass: validate every entry and sum the batch total. If any entry is
        // malformed, the entire batch reverts before any token movement.
        uint256 totalAmount;
        for (uint256 i; i < amounts.length; i++) {
            _validateMask(ticketMasks[i]);
            _policyAllowsTicket(payoffPolicy, ticketMasks[i]);
            require(amounts[i] > 0, "AMOUNT");
            totalAmount += amounts[i];
        }

        bool ok = collateralToken.transferFrom(msg.sender, address(this), totalAmount);
        require(ok, "TRANSFER_FROM");

        // Second pass: record each bet. By this point the collateral is already in
        // the wager so the pool / total updates cannot be inconsistent with custody.
        for (uint256 i; i < ticketMasks.length; i++) {
            _recordBetMask(msg.sender, ticketMasks[i], amounts[i]);
        }
    }

    /// @notice Freeform-mode bet. The answer string is hashed (with the domain byte)
    ///         to a `bytes32` answer id; bets on the exact same byte sequence aggregate into the
    ///         same id. Same pull-then-record / `nonReentrant` posture as the enumerated `placeBet`.
    function placeBet(string calldata answer, uint256 amount) external nonReentrant onlyFreeform {
        if (state != State.Open) revert NotOpen();
        if (_bettingClosed()) revert BettingClosed();
        _validateAnswer(answer);
        require(amount > 0, "AMOUNT");

        bool ok = collateralToken.transferFrom(msg.sender, address(this), amount);
        require(ok, "TRANSFER_FROM");

        _recordBetAnswer(msg.sender, answer, amount);
    }

    /// @notice Factory-only hook used to record proposer-supplied seed bets atomically
    ///         with wager creation. The factory has already pulled collateral from the
    ///         proposer into this contract before calling, so this function only
    ///         records the bookkeeping — it must NOT call `transferFrom` itself or
    ///         the collateral would be double-pulled.
    /// @dev `onlyEnumerated` because seed bets are only supported in enumerated mode
    ///      (freeform has no single canonical seed semantic — every distinct answer
    ///      string would need to be enumerated, which is what enumerated mode is for).
    function seedInitialBetsFromFactory(address bettor, uint256[] memory ticketMasks, uint256[] memory amounts)
        external
        onlyEnumerated
    {
        if (msg.sender != factory) revert NotFactory();
        if (state != State.Open) revert NotOpen();
        if (ticketMasks.length == 0 || ticketMasks.length != amounts.length) revert ArrayLengthMismatch();

        for (uint256 i; i < ticketMasks.length; i++) {
            _validateMask(ticketMasks[i]);
            _policyAllowsTicket(payoffPolicy, ticketMasks[i]);
            require(amounts[i] > 0, "AMOUNT");
            _recordBetMask(bettor, ticketMasks[i], amounts[i]);
        }
    }

    /// @dev Single point that mutates the enumerated-bet bookkeeping. The
    ///      `prevGlobal == 0` and `prevUser == 0` checks make the enumeration arrays
    ///      (`_usedMasks`, `_userMasks[bettor]`) sets-by-construction: a mask is
    ///      pushed exactly once globally and exactly once per bettor, the first time
    ///      it sees a non-zero amount. The minimum stake and the cap apply only at
    ///      first-insert, since later bets on an existing mask do not grow the array.
    ///      Single-outcome tickets skip the cap so griefing can never stop someone
    ///      betting on one outcome; there are at most `numOptions` of them, so the loop
    ///      in `_accumulateWinningUnits` stays bounded. `totalPot` is incremented
    ///      unconditionally because the parimutuel math depends on it tracking gross stake.
    function _recordBetMask(address bettor, uint256 ticketMask, uint256 amount) internal {
        uint256 prevGlobal = ticketPoolByMask[ticketMask];
        ticketPoolByMask[ticketMask] = prevGlobal + amount;
        if (prevGlobal == 0) {
            if (amount < minNewTicketStake) revert NewTicketStakeTooLow();
            if (!BitMath.isSingleBit(ticketMask) && _usedMasks.length >= MAX_DISTINCT_TICKETS) {
                revert TooManyDistinctTickets();
            }
            _usedMasks.push(ticketMask);
        }

        uint256 prevUser = betsByMask[bettor][ticketMask];
        betsByMask[bettor][ticketMask] += amount;
        userTotalBet[bettor] += amount;
        totalPot += amount;
        if (prevUser == 0) {
            _userMasks[bettor].push(ticketMask);
        }

        emit BetPlacedV3Enumerated(bettor, ticketMask, amount);
    }

    /// @dev Freeform mirror of `_recordBetMask`, with no cap and no per-user list (see the storage
    ///      comment). The first stake on an answer publishes its text exactly once.
    function _recordBetAnswer(address bettor, string calldata answer, uint256 amount) internal {
        bytes32 id = _answerId(answer);
        uint256 prevGlobal = ticketPoolByAnswerId[id];
        ticketPoolByAnswerId[id] = prevGlobal + amount;
        if (prevGlobal == 0) {
            if (amount < minNewTicketStake) revert NewTicketStakeTooLow();
            _usedAnswerIds.push(id);
            emit FreeformAnswerRevealedV3(id, answer);
        }

        betsByAnswer[bettor][id] += amount;
        userTotalBet[bettor] += amount;
        totalPot += amount;

        emit BetPlacedV3Freeform(bettor, id, amount);
    }

    /// @dev Whether ticket `T` wins against winning set `W`, under the wager's policy. `overlap` is
    ///      returned so `WEIGHTED_OVERLAP` callers need not recompute it. SINGLE_WINNER shares the
    ///      exact-match rule with EXACT_SET because both `T` and `W` were validated single-bit.
    function _ticketWins(uint256 T, uint256 W) internal view returns (bool wins, uint256 overlap) {
        overlap = T & W;
        if (overlap == 0) return (false, 0);

        PayoffPolicy policy = payoffPolicy;
        if (policy == PayoffPolicy.SINGLE_WINNER || policy == PayoffPolicy.EXACT_SET) {
            return (T == W, overlap);
        }
        if (policy == PayoffPolicy.AT_LEAST_K) {
            return (BitMath.popcount(overlap) >= policyParam, overlap);
        }
        // ANY_OF and WEIGHTED_OVERLAP: any overlap wins.
        return (true, overlap);
    }

    function _validateWinningMask(uint256 W) internal view {
        if (W == 0) revert InvalidWinningMask();
        if (W >> numOptions != 0) revert InvalidWinningMask();
        if (payoffPolicy == PayoffPolicy.SINGLE_WINNER && !BitMath.isSingleBit(W)) {
            revert InvalidWinningMask();
        }
    }

    /// @dev Total payout-weight of all winning tickets, the denominator of every claim. Costs one
    ///      cold mask read, one cold pool read and a constant-time popcount per used mask.
    ///      Every mask in `_usedMasks` has a non-zero pool by construction. `pool * ov` is checked:
    ///      it can only overflow on a pot above about 2^248 under WEIGHTED_OVERLAP, in which case
    ///      `resolve` reverts and `retract` / `expire` remain available, so no funds are locked.
    function _accumulateWinningUnits(uint256 W) internal view returns (uint256 units) {
        uint256 len = _usedMasks.length;
        for (uint256 i; i < len; i++) {
            uint256 mask = _usedMasks[i];
            (bool wins, uint256 overlap) = _ticketWins(mask, W);
            if (!wins) continue;

            uint256 pool = ticketPoolByMask[mask];
            if (payoffPolicy == PayoffPolicy.WEIGHTED_OVERLAP) {
                units += pool * BitMath.popcount(overlap);
            } else {
                units += pool;
            }
        }
    }

    function resolve(uint256 winningMask_) external nonReentrant onlyEnumerated {
        if (msg.sender != resolver) revert NotResolver();
        if (state != State.Open) revert AlreadyFinalized();
        if (!_bettingClosed()) revert BettingNotClosed();
        if (!_resolutionWindowOpen()) revert ResolutionWindowOver();

        _validateWinningMask(winningMask_);

        uint256 units = _accumulateWinningUnits(winningMask_);
        if (units == 0) revert NoWinningStake();

        _chargeFees();

        state = State.Resolved;
        winningMask = winningMask_;
        payoutDenominator = units;
        emit ResolvedV3Enumerated(winningMask_);
    }

    function resolve(string calldata winningAnswer) external nonReentrant onlyFreeform {
        if (msg.sender != resolver) revert NotResolver();
        if (state != State.Open) revert AlreadyFinalized();
        if (!_bettingClosed()) revert BettingNotClosed();
        if (!_resolutionWindowOpen()) revert ResolutionWindowOver();

        _validateAnswer(winningAnswer);
        bytes32 winId = _answerId(winningAnswer);
        uint256 winPool = ticketPoolByAnswerId[winId];
        if (winPool == 0) revert NoWinningStake();

        _chargeFees();

        state = State.Resolved;
        winningAnswerId = winId;
        payoutDenominator = winPool;
        emit ResolvedV3Freeform(winId);
    }

    function retract() external nonReentrant {
        if (msg.sender != resolver) revert NotResolver();
        if (state != State.Open) revert AlreadyFinalized();
        if (!_bettingClosed()) revert BettingNotClosed();
        if (!_resolutionWindowOpen()) revert ResolutionWindowOver();

        _chargeFees();
        state = State.Retracted;
        emit RetractedV3();
    }

    function expire() external nonReentrant {
        if (state != State.Open) revert AlreadyFinalized();
        if (!_bettingClosed()) revert BettingNotClosed();
        if (!_resolutionWindowOver()) revert ResolutionWindowOver();

        _chargeFees();
        state = State.Retracted;
        emit ExpiredV3();
    }

    /// @notice Pays the caller's whole entitlement once. All arithmetic is full-precision, since an
    ///         overflow here would lock funds permanently. A zero payout reverts on every path: a
    ///         losing ticket, dust that rounds to nothing, or a 100% fee (`hasClaimed` then stays
    ///         false). Tokens that revert on zero transfers therefore behave like any other.
    /// @dev `payoutDenominator` is non-zero whenever state is `Resolved`, because `resolve` reverts
    ///      on no winning stake; and `totalPot` is non-zero whenever a stake exists.
    function claim() external nonReentrant returns (uint256 paid) {
        if (state == State.Open) revert NotOpen();
        if (hasClaimed[msg.sender]) revert NothingToClaim();

        hasClaimed[msg.sender] = true;

        uint256 grossUserStake = userTotalBet[msg.sender];
        if (grossUserStake == 0) revert NothingToClaim();

        uint256 netPot = totalPot - _totalFeesAmount();

        if (state == State.Retracted) {
            paid = FullMath.mulDiv(grossUserStake, netPot, totalPot);
        } else if (MODE == WagerMode.Enumerated) {
            uint256 W = winningMask;
            uint256 denom = payoutDenominator;

            uint256[] storage masks = _userMasks[msg.sender];
            uint256 n = masks.length;
            for (uint256 i; i < n; i++) {
                uint256 mask = masks[i];
                (bool wins, uint256 overlap) = _ticketWins(mask, W);
                if (!wins) continue;

                uint256 amt = betsByMask[msg.sender][mask];
                uint256 weight = payoffPolicy == PayoffPolicy.WEIGHTED_OVERLAP ? amt * BitMath.popcount(overlap) : amt;
                paid += FullMath.mulDiv(weight, netPot, denom);
            }
        } else {
            paid = FullMath.mulDiv(betsByAnswer[msg.sender][winningAnswerId], netPot, payoutDenominator);
        }
        if (paid == 0) revert NothingToClaim();

        bool ok = collateralToken.transfer(msg.sender, paid);
        require(ok, "TRANSFER");
        emit ClaimedV3(msg.sender, paid);
    }

    function withdrawFees() external nonReentrant returns (uint256 amount) {
        amount = feeBalances[msg.sender];
        if (amount == 0) revert NothingToClaim();
        feeBalances[msg.sender] = 0;
        bool ok = collateralToken.transfer(msg.sender, amount);
        require(ok, "TRANSFER");
        emit FeeWithdrawnV3(msg.sender, amount);
    }

    /// @dev Called exactly once per wager, on the transition out of `Open`. Each slice is floored
    ///      and the last recipient takes the remainder, so the slices sum to exactly the total.
    function _chargeFees() internal {
        if (totalFeeBps == 0 || totalPot == 0) return;

        uint256 feesTotal = _totalFeesAmount();

        uint256 paid;
        for (uint256 i; i < feeRecipients.length; i++) {
            uint256 slice;
            if (i + 1 == feeRecipients.length) {
                slice = feesTotal - paid;
            } else {
                slice = FullMath.mulDiv(feesTotal, feeBps[i], totalFeeBps);
                paid += slice;
            }
            if (slice > 0) {
                feeBalances[feeRecipients[i]] += slice;
                emit FeeAccruedV3(feeRecipients[i], slice);
            }
        }
    }

    /// @dev Full-precision: with plain math, a pot above `2^256 / totalFeeBps` made every terminal
    ///      path revert and stranded all funds.
    function _totalFeesAmount() internal view returns (uint256) {
        return FullMath.mulDiv(totalPot, totalFeeBps, BPS_DENOMINATOR);
    }
}
