// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";
import {ReentrancyGuard} from "./utils/ReentrancyGuard.sol";

/// @title Paramutuel wager with freeform text answers (ADR-0009)
/// @notice Tickets are `keccak256(bytes(answer))`; resolver submits the winning string; exact byte match only.
contract ParamutuelWagerFreeform is ReentrancyGuard {
    enum State {
        Open,
        Resolved,
        Retracted
    }

    event BetPlacedFreeform(address indexed bettor, bytes32 indexed answerId, uint256 amount);
    event BettingClosedByAuthority(uint64 closedAt);
    event ResolutionWindowClosedByAuthority(uint64 closedAt);
    event ResolvedFreeform(bytes32 indexed winningAnswerId);
    event Retracted();
    event Expired();
    event Claimed(address indexed bettor, uint256 amount);
    event FeeAccrued(address indexed recipient, uint256 amount);
    event FeeWithdrawn(address indexed recipient, uint256 amount);

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
    error EmptyAnswer();
    error AnswerTooLong();
    error TooManyDistinctAnswers();
    error NoWinningStake();
    error InvalidDistinctCap();

    uint256 public constant BPS_DENOMINATOR = 10_000;
    /// @dev Max UTF-8 byte length of `answer` / `winningAnswer` (calldata bound).
    uint256 public constant MAX_ANSWER_BYTES = 1024;
    /// @dev Factory supplies this (typically 1024); tests may use a lower cap.
    uint256 public immutable maxDistinctAnswers;

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

    uint256 public totalPot;

    mapping(bytes32 => uint256) public ticketPoolTotal;
    bytes32[] private _usedAnswerIds;

    mapping(address => mapping(bytes32 => uint256)) public bets;
    mapping(address => uint256) public userTotalBet;
    mapping(address => bytes32[]) private _userAnswerIds;

    address[] public feeRecipients;
    uint16[] public feeBps;
    uint256 public totalFeeBps;

    mapping(address => uint256) public feeBalances;
    bool public feesCharged;

    bytes32 public winningAnswerId;
    uint256 public totalWinningStake;

    mapping(address => bool) public hasClaimed;

    bool public bettingClosedByAuthority;
    uint64 public bettingClosedAtByAuthority;
    bool public resolutionWindowClosedByAuthority;

    constructor(
        address factory_,
        address proposer_,
        address resolver_,
        address bettingCloser_,
        address resolutionCloser_,
        address collateralToken_,
        string memory proposition_,
        uint64 bettingCloseTime_,
        uint64 resolutionWindow_,
        uint64 resolutionDeadline_,
        address[] memory feeRecipients_,
        uint16[] memory feeBps_,
        uint256 maxDistinctAnswers_
    ) {
        if (maxDistinctAnswers_ == 0 || maxDistinctAnswers_ > 1024) revert InvalidDistinctCap();
        maxDistinctAnswers = maxDistinctAnswers_;
        factory = factory_;
        proposer = proposer_;
        resolver = resolver_;
        bettingCloser = bettingCloser_;
        resolutionCloser = resolutionCloser_;
        collateralToken = IERC20(collateralToken_);
        proposition = proposition_;
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

        state = State.Open;
    }

    /// @dev For indexers that probe `outcomesCount()`; freeform has no enumerated outcomes.
    function outcomesCount() external pure returns (uint256) {
        return 0;
    }

    function usedAnswerIdsCount() external view returns (uint256) {
        return _usedAnswerIds.length;
    }

    function usedAnswerId(uint256 i) external view returns (bytes32) {
        return _usedAnswerIds[i];
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
        emit BettingClosedByAuthority(bettingClosedAtByAuthority);
    }

    function closeResolutionWindow() external {
        if (msg.sender != resolutionCloser) revert NotResolutionCloser();
        if (!_bettingClosed()) revert BettingNotClosed();
        if (resolutionWindowClosedByAuthority) return;
        resolutionWindowClosedByAuthority = true;
        emit ResolutionWindowClosedByAuthority(uint64(block.timestamp));
    }

    function _validateAnswer(string calldata answer) internal pure {
        bytes memory b = bytes(answer);
        if (b.length == 0) revert EmptyAnswer();
        if (b.length > MAX_ANSWER_BYTES) revert AnswerTooLong();
    }

    function _answerId(string calldata answer) internal pure returns (bytes32) {
        return keccak256(bytes(answer));
    }

    function placeBet(string calldata answer, uint256 amount) external nonReentrant {
        if (state != State.Open) revert NotOpen();
        if (_bettingClosed()) revert BettingClosed();
        _validateAnswer(answer);
        require(amount > 0, "AMOUNT");

        bool ok = collateralToken.transferFrom(msg.sender, address(this), amount);
        require(ok, "TRANSFER_FROM");

        _recordBet(msg.sender, answer, amount);
    }

    function _recordBet(address bettor, string calldata answer, uint256 amount) internal {
        bytes32 id = _answerId(answer);
        uint256 prevGlobal = ticketPoolTotal[id];
        ticketPoolTotal[id] += amount;
        if (prevGlobal == 0) {
            if (_usedAnswerIds.length >= maxDistinctAnswers) revert TooManyDistinctAnswers();
            _usedAnswerIds.push(id);
        }

        uint256 prevUser = bets[bettor][id];
        bets[bettor][id] += amount;
        userTotalBet[bettor] += amount;
        totalPot += amount;
        if (prevUser == 0) {
            _userAnswerIds[bettor].push(id);
        }

        emit BetPlacedFreeform(bettor, id, amount);
    }

    function resolve(string calldata winningAnswer) external nonReentrant {
        if (msg.sender != resolver) revert NotResolver();
        if (state != State.Open) revert AlreadyFinalized();
        if (!_bettingClosed()) revert BettingNotClosed();
        if (!_resolutionWindowOpen()) revert ResolutionWindowOver();

        _validateAnswer(winningAnswer);
        bytes32 winId = _answerId(winningAnswer);
        uint256 winPool = ticketPoolTotal[winId];
        if (winPool == 0) revert NoWinningStake();

        _chargeFeesOnce();

        state = State.Resolved;
        winningAnswerId = winId;
        totalWinningStake = winPool;
        emit ResolvedFreeform(winId);
    }

    function retract() external nonReentrant {
        if (msg.sender != resolver) revert NotResolver();
        if (state != State.Open) revert AlreadyFinalized();
        if (!_bettingClosed()) revert BettingNotClosed();
        if (!_resolutionWindowOpen()) revert ResolutionWindowOver();

        _chargeFeesOnce();
        state = State.Retracted;
        emit Retracted();
    }

    function expire() external nonReentrant {
        if (state != State.Open) revert AlreadyFinalized();
        if (!_bettingClosed()) revert BettingNotClosed();
        if (!_resolutionWindowOver()) revert ResolutionWindowOver();

        _chargeFeesOnce();
        state = State.Retracted;
        emit Expired();
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
        } else {
            uint256 userWinStake = bets[msg.sender][winningAnswerId];
            if (userWinStake == 0) revert NothingToClaim();
            if (totalWinningStake == 0) revert NothingToClaim();
            paid = (userWinStake * netPot) / totalWinningStake;
        }

        bool ok = collateralToken.transfer(msg.sender, paid);
        require(ok, "TRANSFER");
        emit Claimed(msg.sender, paid);
    }

    function withdrawFees() external nonReentrant returns (uint256 amount) {
        amount = feeBalances[msg.sender];
        if (amount == 0) revert NothingToClaim();
        feeBalances[msg.sender] = 0;
        bool ok = collateralToken.transfer(msg.sender, amount);
        require(ok, "TRANSFER");
        emit FeeWithdrawn(msg.sender, amount);
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
                emit FeeAccrued(feeRecipients[i], slice);
            }
        }
    }

    function _totalFeesAmount() internal view returns (uint256) {
        return (totalPot * totalFeeBps) / BPS_DENOMINATOR;
    }
}
