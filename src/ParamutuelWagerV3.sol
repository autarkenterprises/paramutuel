// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";
import {ReentrancyGuard} from "./utils/ReentrancyGuard.sol";

/// @title Paramutuel wager v3 — enumerated (ADR-0008) or freeform text (ADR-0009) in one deployable
/// @notice Immutable `MODE` at construction. Breaking ABI vs v2/freeform: V3-prefixed events; freeform
///         `answerId` uses domain-separated hash (see `_answerId`).
contract ParamutuelWagerV3 is ReentrancyGuard {
    enum State {
        Open,
        Resolved,
        Retracted
    }

    enum WagerMode {
        Enumerated,
        Freeform
    }

    enum PayoffPolicy {
        SINGLE_WINNER,
        ANY_OF,
        EXACT_SET,
        AT_LEAST_K,
        WEIGHTED_OVERLAP
    }

    event BetPlacedV3Enumerated(address indexed bettor, uint256 ticketMask, uint256 amount);
    event BetPlacedV3Freeform(address indexed bettor, bytes32 indexed answerId, uint256 amount);
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
    error TooManyDistinctAnswers();
    error InvalidDistinctCap();

    uint256 public constant BPS_DENOMINATOR = 10_000;
    uint256 public constant MAX_ANSWER_BYTES = 1024;
    uint256 public constant MAX_DISTINCT_TICKETS = 1024;
    /// @dev Prepended to `bytes(answer)` before keccak — isolates freeform ids from other `bytes32` uses.
    bytes1 public constant FREEFORM_ANSWER_DOMAIN = bytes1(0x03);

    WagerMode public immutable MODE;

    address public immutable factory;
    address public immutable proposer;
    address public immutable resolver;
    address public immutable bettingCloser;
    address public immutable resolutionCloser;
    IERC20 public immutable collateralToken;

    uint64 public immutable bettingCloseTime;
    uint64 public immutable resolutionWindow;
    uint64 public immutable resolutionDeadline;

    string public proposition;
    State public state;

    PayoffPolicy public immutable payoffPolicy;
    uint256 public immutable policyParam;

    string[] private _outcomes;
    uint256 public immutable numOptions;

    uint256 public immutable maxDistinctAnswers;

    uint256 public totalPot;

    uint256[] private _usedMasks;
    mapping(uint256 => uint256) public ticketPoolByMask;
    mapping(address => mapping(uint256 => uint256)) public betsByMask;
    mapping(address => uint256[]) private _userMasks;
    mapping(address => uint256) public userTotalBet;

    mapping(bytes32 => uint256) public ticketPoolByAnswerId;
    bytes32[] private _usedAnswerIds;
    mapping(address => mapping(bytes32 => uint256)) public betsByAnswer;
    mapping(address => bytes32[]) private _userAnswerIds;

    address[] public feeRecipients;
    uint16[] public feeBps;
    uint256 public totalFeeBps;

    mapping(address => uint256) public feeBalances;
    bool public feesCharged;

    uint256 public winningMask;
    bytes32 public winningAnswerId;
    uint256 public payoutDenominator;

    mapping(address => bool) public hasClaimed;

    bool public bettingClosedByAuthority;
    uint64 public bettingClosedAtByAuthority;
    bool public resolutionWindowClosedByAuthority;

    constructor(
        WagerMode mode_,
        address factory_,
        address proposer_,
        address resolver_,
        address bettingCloser_,
        address resolutionCloser_,
        address collateralToken_,
        string memory proposition_,
        string[] memory outcomes_,
        PayoffPolicy payoffPolicy_,
        uint256 policyParam_,
        uint64 bettingCloseTime_,
        uint64 resolutionWindow_,
        uint64 resolutionDeadline_,
        address[] memory feeRecipients_,
        uint16[] memory feeBps_,
        uint256 maxDistinctAnswers_
    ) {
        MODE = mode_;
        factory = factory_;
        proposer = proposer_;
        resolver = resolver_;
        bettingCloser = bettingCloser_;
        resolutionCloser = resolutionCloser_;
        collateralToken = IERC20(collateralToken_);
        proposition = proposition_;
        payoffPolicy = payoffPolicy_;
        policyParam = policyParam_;
        bettingCloseTime = bettingCloseTime_;
        resolutionWindow = resolutionWindow_;
        resolutionDeadline = resolutionDeadline_;

        if (feeRecipients_.length != feeBps_.length) revert FeeConfigMismatch();
        feeRecipients = feeRecipients_;
        feeBps = feeBps_;
        uint256 sum;
        for (uint256 i; i < feeBps_.length; i++) sum += feeBps_[i];
        if (sum > BPS_DENOMINATOR) revert FeeTooHigh();
        totalFeeBps = sum;

        if (mode_ == WagerMode.Enumerated) {
            require(outcomes_.length >= 2, "OUTCOMES_MIN");
            require(outcomes_.length <= 256, "OUTCOMES_MAX");
            _outcomes = outcomes_;
            numOptions = outcomes_.length;
            maxDistinctAnswers = 0;
            if (payoffPolicy_ == PayoffPolicy.AT_LEAST_K) {
                if (policyParam_ < 1 || policyParam_ > outcomes_.length) revert InvalidPolicyParam();
            } else if (policyParam_ != 0) {
                revert InvalidPolicyParam();
            }
        } else {
            if (outcomes_.length != 0) revert InvalidOutcome();
            numOptions = 0;
            if (maxDistinctAnswers_ == 0 || maxDistinctAnswers_ > 1024) revert InvalidDistinctCap();
            maxDistinctAnswers = maxDistinctAnswers_;
            if (policyParam_ != 0) revert InvalidPolicyParam();
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

    function _bettingClosed() internal view returns (bool) {
        return bettingClosedByAuthority || (bettingCloseTime != 0 && block.timestamp >= bettingCloseTime);
    }

    function _bettingClosedAt() internal view returns (uint64) {
        if (bettingClosedByAuthority) return bettingClosedAtByAuthority;
        if (bettingCloseTime != 0 && block.timestamp >= bettingCloseTime) return bettingCloseTime;
        return 0;
    }

    function _resolutionWindowOpen() internal view returns (bool) {
        if (resolutionWindowClosedByAuthority) return false;
        if (resolutionWindow == 0) return true;
        uint64 closedAt = _bettingClosedAt();
        if (closedAt == 0) return false;
        return block.timestamp <= uint256(closedAt) + uint256(resolutionWindow);
    }

    function _resolutionWindowOver() internal view returns (bool) {
        if (resolutionWindowClosedByAuthority) return true;
        if (resolutionWindow == 0) return false;
        uint64 closedAt = _bettingClosedAt();
        if (closedAt == 0) return false;
        return block.timestamp > uint256(closedAt) + uint256(resolutionWindow);
    }

    function closeBetting() external {
        if (msg.sender != bettingCloser) revert NotBettingCloser();
        if (_bettingClosed()) return;
        bettingClosedByAuthority = true;
        bettingClosedAtByAuthority = uint64(block.timestamp);
        emit BettingClosedByAuthorityV3(bettingClosedAtByAuthority);
    }

    function closeResolutionWindow() external {
        if (msg.sender != resolutionCloser) revert NotResolutionCloser();
        if (!_bettingClosed()) revert BettingNotClosed();
        if (resolutionWindowClosedByAuthority) return;
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

    function _popcount(uint256 x) internal pure returns (uint256 c) {
        unchecked {
            while (x != 0) {
                x &= x - 1;
                c++;
            }
        }
    }

    function _validateMask(uint256 mask) internal view {
        if (mask == 0) revert InvalidTicketMask();
        if (mask >> numOptions != 0) revert InvalidTicketMask();
    }

    function _policyAllowsTicket(PayoffPolicy policy, uint256 mask) internal pure {
        if (policy == PayoffPolicy.SINGLE_WINNER) {
            if (_popcount(mask) != 1) revert InvalidTicketMask();
        }
    }

    function _validateAnswer(string calldata answer) internal pure {
        bytes memory b = bytes(answer);
        if (b.length == 0) revert EmptyAnswer();
        if (b.length > MAX_ANSWER_BYTES) revert AnswerTooLong();
    }

    function _answerId(string calldata answer) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(FREEFORM_ANSWER_DOMAIN, bytes(answer)));
    }

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

    function placeBets(uint256[] calldata ticketMasks, uint256[] calldata amounts) external nonReentrant onlyEnumerated {
        if (state != State.Open) revert NotOpen();
        if (_bettingClosed()) revert BettingClosed();
        if (ticketMasks.length == 0 || ticketMasks.length != amounts.length) revert ArrayLengthMismatch();

        uint256 totalAmount;
        for (uint256 i; i < amounts.length; i++) {
            _validateMask(ticketMasks[i]);
            _policyAllowsTicket(payoffPolicy, ticketMasks[i]);
            require(amounts[i] > 0, "AMOUNT");
            totalAmount += amounts[i];
        }

        bool ok = collateralToken.transferFrom(msg.sender, address(this), totalAmount);
        require(ok, "TRANSFER_FROM");

        for (uint256 i; i < ticketMasks.length; i++) {
            _recordBetMask(msg.sender, ticketMasks[i], amounts[i]);
        }
    }

    function placeBet(string calldata answer, uint256 amount) external nonReentrant onlyFreeform {
        if (state != State.Open) revert NotOpen();
        if (_bettingClosed()) revert BettingClosed();
        _validateAnswer(answer);
        require(amount > 0, "AMOUNT");

        bool ok = collateralToken.transferFrom(msg.sender, address(this), amount);
        require(ok, "TRANSFER_FROM");

        _recordBetAnswer(msg.sender, answer, amount);
    }

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

    function _recordBetMask(address bettor, uint256 ticketMask, uint256 amount) internal {
        uint256 prevGlobal = ticketPoolByMask[ticketMask];
        ticketPoolByMask[ticketMask] += amount;
        if (prevGlobal == 0) {
            if (_usedMasks.length >= MAX_DISTINCT_TICKETS) revert TooManyDistinctTickets();
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

    function _recordBetAnswer(address bettor, string calldata answer, uint256 amount) internal {
        bytes32 id = _answerId(answer);
        uint256 prevGlobal = ticketPoolByAnswerId[id];
        ticketPoolByAnswerId[id] += amount;
        if (prevGlobal == 0) {
            if (_usedAnswerIds.length >= maxDistinctAnswers) revert TooManyDistinctAnswers();
            _usedAnswerIds.push(id);
        }

        uint256 prevUser = betsByAnswer[bettor][id];
        betsByAnswer[bettor][id] += amount;
        userTotalBet[bettor] += amount;
        totalPot += amount;
        if (prevUser == 0) {
            _userAnswerIds[bettor].push(id);
        }

        emit BetPlacedV3Freeform(bettor, id, amount);
    }

    function _ticketWins(uint256 T, uint256 W) internal view returns (bool wins, uint256 overlap) {
        overlap = T & W;
        if (overlap == 0) return (false, 0);

        if (payoffPolicy == PayoffPolicy.SINGLE_WINNER) {
            return (_popcount(W) == 1 && _popcount(T) == 1 && T == W, overlap);
        }
        if (payoffPolicy == PayoffPolicy.ANY_OF) {
            return (true, overlap);
        }
        if (payoffPolicy == PayoffPolicy.EXACT_SET) {
            return (T == W, overlap);
        }
        if (payoffPolicy == PayoffPolicy.AT_LEAST_K) {
            return (_popcount(overlap) >= policyParam, overlap);
        }
        if (payoffPolicy == PayoffPolicy.WEIGHTED_OVERLAP) {
            return (true, overlap);
        }
        return (false, 0);
    }

    function _validateWinningMask(uint256 W) internal view onlyEnumerated {
        if (W == 0) revert InvalidWinningMask();
        if (W >> numOptions != 0) revert InvalidWinningMask();
        if (payoffPolicy == PayoffPolicy.SINGLE_WINNER && _popcount(W) != 1) {
            revert InvalidWinningMask();
        }
    }

    function _accumulateWinningUnits(uint256 W) internal view returns (uint256 units) {
        uint256 len = _usedMasks.length;
        for (uint256 i; i < len; i++) {
            uint256 mask = _usedMasks[i];
            uint256 pool = ticketPoolByMask[mask];
            if (pool == 0) continue;
            (bool wins, uint256 overlap) = _ticketWins(mask, W);
            if (!wins) continue;

            if (payoffPolicy == PayoffPolicy.WEIGHTED_OVERLAP) {
                uint256 ov = _popcount(overlap);
                units += pool * ov;
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

        _chargeFeesOnce();

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

        _chargeFeesOnce();

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

        _chargeFeesOnce();
        state = State.Retracted;
        emit RetractedV3();
    }

    function expire() external nonReentrant {
        if (state != State.Open) revert AlreadyFinalized();
        if (!_bettingClosed()) revert BettingNotClosed();
        if (!_resolutionWindowOver()) revert ResolutionWindowOver();

        _chargeFeesOnce();
        state = State.Retracted;
        emit ExpiredV3();
    }

    function claim() external nonReentrant returns (uint256 paid) {
        if (state == State.Open) revert NotOpen();
        if (hasClaimed[msg.sender]) revert NothingToClaim();

        hasClaimed[msg.sender] = true;

        uint256 grossUserStake = userTotalBet[msg.sender];
        if (grossUserStake == 0) revert NothingToClaim();

        uint256 netPot = totalPot - _totalFeesAmount();

        if (state == State.Retracted) {
            paid = (grossUserStake * netPot) / totalPot;
        } else if (MODE == WagerMode.Enumerated) {
            uint256 W = winningMask;
            uint256 denom = payoutDenominator;
            if (denom == 0) revert NothingToClaim();

            uint256[] storage masks = _userMasks[msg.sender];
            uint256 n = masks.length;
            for (uint256 i; i < n; i++) {
                uint256 mask = masks[i];
                uint256 amt = betsByMask[msg.sender][mask];
                if (amt == 0) continue;
                (bool wins, uint256 overlap) = _ticketWins(mask, W);
                if (!wins) continue;

                if (payoffPolicy == PayoffPolicy.WEIGHTED_OVERLAP) {
                    uint256 ov = _popcount(overlap);
                    uint256 weight = amt * ov;
                    paid += (weight * netPot) / denom;
                } else {
                    paid += (amt * netPot) / denom;
                }
            }
            if (paid == 0) revert NothingToClaim();
        } else {
            uint256 userWinStake = betsByAnswer[msg.sender][winningAnswerId];
            if (userWinStake == 0) revert NothingToClaim();
            if (payoutDenominator == 0) revert NothingToClaim();
            paid = (userWinStake * netPot) / payoutDenominator;
        }

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

    function _chargeFeesOnce() internal {
        if (feesCharged) return;
        feesCharged = true;
        if (totalFeeBps == 0 || totalPot == 0) return;

        uint256 feesTotal = _totalFeesAmount();

        uint256 paid;
        for (uint256 i; i < feeRecipients.length; i++) {
            uint256 slice;
            if (i + 1 == feeRecipients.length) {
                slice = feesTotal - paid;
            } else {
                slice = (feesTotal * feeBps[i]) / totalFeeBps;
                paid += slice;
            }
            if (slice > 0) {
                feeBalances[feeRecipients[i]] += slice;
                emit FeeAccruedV3(feeRecipients[i], slice);
            }
        }
    }

    function _totalFeesAmount() internal view returns (uint256) {
        return (totalPot * totalFeeBps) / BPS_DENOMINATOR;
    }
}
