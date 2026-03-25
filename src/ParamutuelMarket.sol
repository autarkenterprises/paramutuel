// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";
import {ReentrancyGuard} from "./utils/ReentrancyGuard.sol";

contract ParamutuelMarket is ReentrancyGuard {
    enum State {
        Open,
        Resolved,
        Retracted
    }

    event BetPlaced(address indexed bettor, uint256 indexed outcomeIndex, uint256 amount);
    /// @notice Emitted when `bettingCloser` ends the betting period (needed for no-max markets).
    event BettingClosedByAuthority(uint64 closedAt);
    /// @notice Emitted when `resolutionCloser` ends the resolver window.
    event ResolutionWindowClosedByAuthority(uint64 closedAt);
    event Resolved(uint256 indexed outcomeIndex);
    event Retracted();
    event Expired();
    event Claimed(address indexed bettor, uint256 amount);
    event FeeAccrued(address indexed recipient, uint256 amount);
    event FeeWithdrawn(address indexed recipient, uint256 amount);

    error InvalidOutcome();
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

    uint256 public constant BPS_DENOMINATOR = 10_000;

    address public immutable factory;
    /// @notice Address that created the market via the factory (may differ from `resolver`).
    address public immutable proposer;
    /// @notice Address authorized to `resolve` and `retract` before the deadline.
    address public immutable resolver;
    /// @notice May call `closeBetting` to stop new bets before `bettingCloseTime` (OR with timestamp; whichever comes first).
    address public immutable bettingCloser;
    /// @notice May call `closeResolutionWindow` after betting has ended to end the resolver window early (enables `expire`).
    address public immutable resolutionCloser;
    IERC20 public immutable collateralToken;

    uint64 public immutable bettingCloseTime;
    /// @notice Resolution window duration counted from actual betting close time. Zero means no time cap.
    uint64 public immutable resolutionWindow;
    /// @notice Scheduled deadline from creation-time inputs (zero when no scheduled max exists).
    uint64 public immutable resolutionDeadline;

    string public question;
    State public state;

    string[] private _outcomes;
    uint256[] public outcomeTotals;
    uint256 public totalPot;

    // bettor => outcomeIndex => amount
    mapping(address => mapping(uint256 => uint256)) public bets;
    mapping(address => uint256) public userTotalBet;

    // fee recipients and bps are fixed at creation
    address[] public feeRecipients;
    uint16[] public feeBps;
    uint256 public totalFeeBps;

    mapping(address => uint256) public feeBalances;
    bool public feesCharged;

    uint256 public winningOutcome;
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
        string memory question_,
        string[] memory outcomes_,
        uint64 bettingCloseTime_,
        uint64 resolutionWindow_,
        uint64 resolutionDeadline_,
        address[] memory feeRecipients_,
        uint16[] memory feeBps_
    ) {
        factory = factory_;
        proposer = proposer_;
        resolver = resolver_;
        bettingCloser = bettingCloser_;
        resolutionCloser = resolutionCloser_;
        collateralToken = IERC20(collateralToken_);
        question = question_;
        bettingCloseTime = bettingCloseTime_;
        resolutionWindow = resolutionWindow_;
        resolutionDeadline = resolutionDeadline_;

        require(outcomes_.length >= 2, "OUTCOMES_MIN");
        _outcomes = outcomes_;
        outcomeTotals = new uint256[](outcomes_.length);

        if (feeRecipients_.length != feeBps_.length) revert FeeConfigMismatch();
        feeRecipients = feeRecipients_;
        feeBps = feeBps_;
        uint256 sum;
        for (uint256 i; i < feeBps_.length; i++) sum += feeBps_[i];
        if (sum > BPS_DENOMINATOR) revert FeeTooHigh();
        totalFeeBps = sum;

        state = State.Open;
    }

    /// @dev Betting stops at timestamp OR when `bettingCloser` signals (whichever happens first).
    ///      `bettingCloseTime == 0` means no timestamp cap.
    function _bettingClosed() internal view returns (bool) {
        return bettingClosedByAuthority || (bettingCloseTime != 0 && block.timestamp >= bettingCloseTime);
    }

    /// @dev Returns the effective betting close timestamp, or 0 if betting is still open.
    function _bettingClosedAt() internal view returns (uint64) {
        if (bettingClosedByAuthority) return bettingClosedAtByAuthority;
        if (bettingCloseTime != 0 && block.timestamp >= bettingCloseTime) return bettingCloseTime;
        return 0;
    }

    /// @dev Resolver may act until window timeout and until `resolutionCloser` has not closed it early.
    ///      `resolutionWindow == 0` means no time cap.
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

    /// @notice Stop accepting new bets before the scheduled `bettingCloseTime`.
    /// @dev Callable only by `bettingCloser`. Idempotent. Does not charge fees.
    function closeBetting() external {
        if (msg.sender != bettingCloser) revert NotBettingCloser();
        if (_bettingClosed()) return;
        bettingClosedByAuthority = true;
        bettingClosedAtByAuthority = uint64(block.timestamp);
        emit BettingClosedByAuthority(bettingClosedAtByAuthority);
    }

    /// @notice End the resolver window early so anyone may `expire` if still open.
    /// @dev Callable only by `resolutionCloser`, only after betting has ended (`_bettingClosed`). Idempotent.
    function closeResolutionWindow() external {
        if (msg.sender != resolutionCloser) revert NotResolutionCloser();
        if (!_bettingClosed()) revert BettingNotClosed();
        if (resolutionWindowClosedByAuthority) return;
        resolutionWindowClosedByAuthority = true;
        emit ResolutionWindowClosedByAuthority(uint64(block.timestamp));
    }

    function outcomesCount() external view returns (uint256) {
        return _outcomes.length;
    }

    function outcomeText(uint256 index) external view returns (string memory) {
        if (index >= _outcomes.length) revert InvalidOutcome();
        return _outcomes[index];
    }

    function placeBet(uint256 outcomeIndex, uint256 amount) external nonReentrant {
        if (state != State.Open) revert NotOpen();
        if (_bettingClosed()) revert BettingClosed();
        if (outcomeIndex >= _outcomes.length) revert InvalidOutcome();
        require(amount > 0, "AMOUNT");

        bool ok = collateralToken.transferFrom(msg.sender, address(this), amount);
        require(ok, "TRANSFER_FROM");

        bets[msg.sender][outcomeIndex] += amount;
        userTotalBet[msg.sender] += amount;
        outcomeTotals[outcomeIndex] += amount;
        totalPot += amount;

        emit BetPlaced(msg.sender, outcomeIndex, amount);
    }

    /// @notice Finalize the market to a winning outcome.
    /// @dev Callable only by `resolver`, after betting closes and while resolution window is open.
    ///      Fees are charged once at finalization.
    /// @param outcomeIndex The winning outcome index in `outcomes`.
    function resolve(uint256 outcomeIndex) external nonReentrant {
        if (msg.sender != resolver) revert NotResolver();
        if (state != State.Open) revert AlreadyFinalized();
        if (!_bettingClosed()) revert BettingNotClosed();
        if (!_resolutionWindowOpen()) revert ResolutionWindowOver();
        if (outcomeIndex >= _outcomes.length) revert InvalidOutcome();

        _chargeFeesOnce();

        state = State.Resolved;
        winningOutcome = outcomeIndex;
        totalWinningStake = outcomeTotals[outcomeIndex];
        emit Resolved(outcomeIndex);
    }

    /// @notice Invalidate the market during the resolver window.
    /// @dev Callable only by `resolver`, after betting closes and while resolution window is open.
    ///      Retracted markets allow bettors to claim stake minus fee share.
    function retract() external nonReentrant {
        if (msg.sender != resolver) revert NotResolver();
        if (state != State.Open) revert AlreadyFinalized();
        if (!_bettingClosed()) revert BettingNotClosed();
        if (!_resolutionWindowOpen()) revert ResolutionWindowOver();

        _chargeFeesOnce();
        state = State.Retracted;
        emit Retracted();
    }

    /// @notice Liveness fallback if resolver does not finalize in time.
    /// @dev Callable by anyone only after betting is closed and the resolution window is over:
    ///      either by timeout (if configured) or by `resolutionCloser` calling
    ///      `closeResolutionWindow`. Moves to `Retracted` so refunds (minus fees) are available.
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
            // Refund pro-rata after fees, which simplifies to each user getting their stake minus fee share.
            // fee share = userStake * totalFeeBps / 10_000
            uint256 feeShare = (grossUserStake * totalFeeBps) / BPS_DENOMINATOR;
            paid = grossUserStake - feeShare;
        } else {
            uint256 userWinStake = bets[msg.sender][winningOutcome];
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

        // Split by bps; last recipient gets remainder to avoid dust loss.
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

