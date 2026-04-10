// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./interfaces/IERC20.sol";
import {ReentrancyGuard} from "./utils/ReentrancyGuard.sol";

/// @title Paramutuel wager with multi-outcome tickets and policy-driven settlement (v2)
/// @notice ADR-0008 prototype: tickets are bitmasks over base options; resolver submits a winning set mask.
///         v1 contracts remain unchanged; this is a separate deployable.
contract ParamutuelWagerV2 is ReentrancyGuard {
    enum State {
        Open,
        Resolved,
        Retracted
    }

    /// @notice How ticket masks are compared to the resolved winning set `winningMask`.
    enum PayoffPolicy {
        /// @dev Resolver's `winningMask` must have exactly one bit. Tickets must be single-bit masks. Win iff `T == W`.
        SINGLE_WINNER,
        /// @dev Win if `(T & W) != 0` (any overlap). Share of `netPot` is proportional to stake among all winning tickets.
        ANY_OF,
        /// @dev Win iff `T == W` (ticket equals the full resolved set).
        EXACT_SET,
        /// @dev Win if `popcount(T & W) >= policyParam` (k-of-overlap). Integer `policyParam` is k (>= 1).
        AT_LEAST_K,
        /// @dev Partial credit: each ticket's weight is `stake * popcount(T & W)`. `netPot` split by weight across all tickets with non-zero overlap.
        WEIGHTED_OVERLAP
    }

    event BetPlaced(address indexed bettor, uint256 ticketMask, uint256 amount);
    event BettingClosedByAuthority(uint64 closedAt);
    event ResolutionWindowClosedByAuthority(uint64 closedAt);
    /// @param winningMask Bit i set means base option i is in the winning set.
    event Resolved(uint256 winningMask);
    event Retracted();
    event Expired();
    event Claimed(address indexed bettor, uint256 amount);
    event FeeAccrued(address indexed recipient, uint256 amount);
    event FeeWithdrawn(address indexed recipient, uint256 amount);

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

    uint256 public constant BPS_DENOMINATOR = 10_000;

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
    /// @notice For `AT_LEAST_K` this is k; ignored for other policies (should be 0).
    uint256 public immutable policyParam;

    string[] private _outcomes;
    uint256 public immutable numOptions;
    uint256 public totalPot;

    /// @notice Distinct ticket masks that have received stake (for O(n) settlement at resolve).
    uint256[] private _usedMasks;
    /// @notice Total stake pooled under each ticket mask.
    mapping(uint256 => uint256) public ticketPoolTotal;
    /// @notice bettor => ticketMask => amount
    mapping(address => mapping(uint256 => uint256)) public bets;
    mapping(address => uint256) public userTotalBet;
    /// @notice Masks each bettor has used (for claim iteration).
    mapping(address => uint256[]) private _userMasks;

    address[] public feeRecipients;
    uint16[] public feeBps;
    uint256 public totalFeeBps;

    mapping(address => uint256) public feeBalances;
    bool public feesCharged;

    /// @notice Set at resolve; bit semantics match ticket masks.
    uint256 public winningMask;
    /// @notice Denominator for resolved payouts: sum of stake (or weighted units) over winning tickets.
    uint256 public totalWinningUnits;

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
        string[] memory outcomes_,
        PayoffPolicy payoffPolicy_,
        uint256 policyParam_,
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
        proposition = proposition_;
        payoffPolicy = payoffPolicy_;
        policyParam = policyParam_;
        bettingCloseTime = bettingCloseTime_;
        resolutionWindow = resolutionWindow_;
        resolutionDeadline = resolutionDeadline_;

        require(outcomes_.length >= 2, "OUTCOMES_MIN");
        require(outcomes_.length <= 256, "OUTCOMES_MAX");
        _outcomes = outcomes_;
        numOptions = outcomes_.length;

        if (payoffPolicy_ == PayoffPolicy.AT_LEAST_K) {
            if (policyParam_ < 1 || policyParam_ > outcomes_.length) revert InvalidPolicyParam();
        } else if (policyParam_ != 0) {
            revert InvalidPolicyParam();
        }

        if (feeRecipients_.length != feeBps_.length) revert FeeConfigMismatch();
        feeRecipients = feeRecipients_;
        feeBps = feeBps_;
        uint256 sum;
        for (uint256 i; i < feeBps_.length; i++) sum += feeBps_[i];
        if (sum > BPS_DENOMINATOR) revert FeeTooHigh();
        totalFeeBps = sum;

        state = State.Open;
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

    function outcomesCount() external view returns (uint256) {
        return _outcomes.length;
    }

    function outcomeText(uint256 index) external view returns (string memory) {
        if (index >= _outcomes.length) revert InvalidOutcome();
        return _outcomes[index];
    }

    function usedMasksCount() external view returns (uint256) {
        return _usedMasks.length;
    }

    function usedMaskAt(uint256 i) external view returns (uint256) {
        return _usedMasks[i];
    }

    function userMasksCount(address bettor) external view returns (uint256) {
        return _userMasks[bettor].length;
    }

    function userMaskAt(address bettor, uint256 i) external view returns (uint256) {
        return _userMasks[bettor][i];
    }

    /// @notice Valid masks are non-zero and only use bits below `numOptions`.
    function _validateMask(uint256 mask) internal view {
        if (mask == 0) revert InvalidTicketMask();
        if (mask >> numOptions != 0) revert InvalidTicketMask();
    }

    function _popcount(uint256 x) internal pure returns (uint256 c) {
        unchecked {
            while (x != 0) {
                x &= x - 1;
                c++;
            }
        }
    }

    function _policyAllowsTicket(PayoffPolicy policy, uint256 mask) internal pure {
        if (policy == PayoffPolicy.SINGLE_WINNER) {
            if (_popcount(mask) != 1) revert InvalidTicketMask();
        }
    }

    function placeBet(uint256 ticketMask, uint256 amount) external nonReentrant {
        if (state != State.Open) revert NotOpen();
        if (_bettingClosed()) revert BettingClosed();

        _validateMask(ticketMask);
        _policyAllowsTicket(payoffPolicy, ticketMask);
        require(amount > 0, "AMOUNT");

        bool ok = collateralToken.transferFrom(msg.sender, address(this), amount);
        require(ok, "TRANSFER_FROM");

        _recordBet(msg.sender, ticketMask, amount);
    }

    function placeBets(uint256[] calldata ticketMasks, uint256[] calldata amounts) external nonReentrant {
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
            _recordBet(msg.sender, ticketMasks[i], amounts[i]);
        }
    }

    function seedInitialBetsFromFactory(address bettor, uint256[] memory ticketMasks, uint256[] memory amounts)
        external
    {
        if (msg.sender != factory) revert NotFactory();
        if (state != State.Open) revert NotOpen();
        if (ticketMasks.length == 0 || ticketMasks.length != amounts.length) revert ArrayLengthMismatch();

        for (uint256 i; i < ticketMasks.length; i++) {
            _validateMask(ticketMasks[i]);
            _policyAllowsTicket(payoffPolicy, ticketMasks[i]);
            require(amounts[i] > 0, "AMOUNT");
            _recordBet(bettor, ticketMasks[i], amounts[i]);
        }
    }

    uint256 public constant MAX_DISTINCT_TICKETS = 1024;

    function _recordBet(address bettor, uint256 ticketMask, uint256 amount) internal {
        uint256 prevGlobal = ticketPoolTotal[ticketMask];
        ticketPoolTotal[ticketMask] += amount;
        if (prevGlobal == 0) {
            if (_usedMasks.length >= MAX_DISTINCT_TICKETS) revert TooManyDistinctTickets();
            _usedMasks.push(ticketMask);
        }

        uint256 prevUser = bets[bettor][ticketMask];
        bets[bettor][ticketMask] += amount;
        userTotalBet[bettor] += amount;
        totalPot += amount;
        if (prevUser == 0) {
            _userMasks[bettor].push(ticketMask);
        }

        emit BetPlaced(bettor, ticketMask, amount);
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

    function _validateWinningMask(uint256 W) internal view {
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
            uint256 pool = ticketPoolTotal[mask];
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

    function resolve(uint256 winningMask_) external nonReentrant {
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
        totalWinningUnits = units;
        emit Resolved(winningMask_);
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
            uint256 W = winningMask;
            uint256 denom = totalWinningUnits;
            if (denom == 0) revert NothingToClaim();

            uint256[] storage masks = _userMasks[msg.sender];
            uint256 n = masks.length;
            for (uint256 i; i < n; i++) {
                uint256 mask = masks[i];
                uint256 amt = bets[msg.sender][mask];
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
