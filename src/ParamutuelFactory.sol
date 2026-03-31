// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ParamutuelWager} from "./ParamutuelWager.sol";
import {IERC20} from "./interfaces/IERC20.sol";

contract ParamutuelFactory {
    /// @param resolver The address that may `resolve` / `retract` (proposer if `resolver == address(0)`).
    /// @param bettingCloser May `closeBetting` on the wager (`address(0)` disables authority close).
    /// @param resolutionWindow Resolution window duration after effective betting close. `0` means no timeout.
    /// @param resolutionCloser May `closeResolutionWindow` after betting ends (`address(0)` disables authority close).
    event WagerCreated(
        address indexed wager,
        address indexed proposer,
        address indexed resolver,
        address collateralToken,
        uint64 bettingCloseTime,
        uint64 resolutionWindow,
        uint64 resolutionDeadline,
        address bettingCloser,
        address resolutionCloser
    );

    error BadFeeConfig();
    error BadOutcomes();
    error WindowTooShort();
    error TooManyOutcomes();
    error InvalidLifecycleConfig();
    error BadSeedConfig();

    uint256 public constant BPS_DENOMINATOR = 10_000;
    uint16 public constant MAX_TOTAL_FEE_BPS = 1_000; // 10% cap for MVP
    uint256 public constant MAX_OUTCOMES = 64;

    uint64 public immutable minBettingWindow;
    uint64 public immutable minResolutionWindow;

    address public treasury;
    uint16 public protocolFeeBps;

    address[] public wagers;

    constructor(address treasury_, uint16 protocolFeeBps_, uint64 minBettingWindow_, uint64 minResolutionWindow_) {
        require(treasury_ != address(0), "TREASURY");
        require(protocolFeeBps_ <= MAX_TOTAL_FEE_BPS, "FEE");
        treasury = treasury_;
        protocolFeeBps = protocolFeeBps_;
        minBettingWindow = minBettingWindow_;
        minResolutionWindow = minResolutionWindow_;
    }

    function wagersCount() external view returns (uint256) {
        return wagers.length;
    }

    /// @notice Create wager without seeded bets.
    /// @param bettingCloseTime Absolute betting close timestamp. Use `0` for no time cap (closer-only).
    /// @param resolutionWindow Resolution window duration after effective betting close. Use `0` for no time cap.
    /// @param resolver If `address(0)`, the resolver is the proposer (`msg.sender`).
    /// @param bettingCloser If `address(0)`, authority-based betting close is disabled.
    /// @param resolutionCloser If `address(0)`, authority-based resolution-window close is disabled.
    function createWager(
        address collateralToken,
        string memory proposition,
        string[] memory outcomes,
        uint64 bettingCloseTime,
        uint64 resolutionWindow,
        address resolver,
        address bettingCloser,
        address resolutionCloser,
        address[] memory extraFeeRecipients,
        uint16[] memory extraFeeBps
    ) external returns (address wager) {
        uint256[] memory seedOutcomeIndices = new uint256[](0);
        uint256[] memory seedAmounts = new uint256[](0);
        return _createWager(
            collateralToken,
            proposition,
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            resolver,
            bettingCloser,
            resolutionCloser,
            extraFeeRecipients,
            extraFeeBps,
            seedOutcomeIndices,
            seedAmounts
        );
    }

    /// @notice Create wager with optional initial seeded bets from proposer.
    /// @param seedOutcomeIndices Outcome indices for seeded legs.
    /// @param seedAmounts Raw token amounts for each seeded leg.
    function createWager(
        address collateralToken,
        string memory proposition,
        string[] memory outcomes,
        uint64 bettingCloseTime,
        uint64 resolutionWindow,
        address resolver,
        address bettingCloser,
        address resolutionCloser,
        address[] memory extraFeeRecipients,
        uint16[] memory extraFeeBps,
        uint256[] memory seedOutcomeIndices,
        uint256[] memory seedAmounts
    ) external returns (address wager) {
        return _createWager(
            collateralToken,
            proposition,
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            resolver,
            bettingCloser,
            resolutionCloser,
            extraFeeRecipients,
            extraFeeBps,
            seedOutcomeIndices,
            seedAmounts
        );
    }

    function _createWager(
        address collateralToken,
        string memory proposition,
        string[] memory outcomes,
        uint64 bettingCloseTime,
        uint64 resolutionWindow,
        address resolver,
        address bettingCloser,
        address resolutionCloser,
        address[] memory extraFeeRecipients,
        uint16[] memory extraFeeBps,
        uint256[] memory seedOutcomeIndices,
        uint256[] memory seedAmounts
    ) internal returns (address wager) {
        if (outcomes.length < 2) revert BadOutcomes();
        if (outcomes.length > MAX_OUTCOMES) revert TooManyOutcomes();
        if (seedOutcomeIndices.length != seedAmounts.length) revert BadSeedConfig();

        uint256 seedTotal;
        for (uint256 i; i < seedAmounts.length; i++) {
            uint256 amount = seedAmounts[i];
            if (amount == 0) revert BadSeedConfig();
            seedTotal += amount;
        }

        uint64 nowTs = uint64(block.timestamp);
        if (bettingCloseTime != 0 && bettingCloseTime < nowTs + minBettingWindow) revert WindowTooShort();
        if (resolutionWindow != 0 && resolutionWindow < minResolutionWindow) revert WindowTooShort();
        // Prevent permanently-open wagers:
        // - no betting timeout requires an authority closer
        // - no resolution timeout requires an authority closer
        if (bettingCloseTime == 0 && bettingCloser == address(0)) revert InvalidLifecycleConfig();
        if (resolutionWindow == 0 && resolutionCloser == address(0)) revert InvalidLifecycleConfig();

        (address[] memory feeRecipients, uint16[] memory feeBps, uint256 totalFeeBps) = _buildFeeConfig(
            extraFeeRecipients,
            extraFeeBps
        );
        if (totalFeeBps > MAX_TOTAL_FEE_BPS) revert BadFeeConfig();

        uint64 resolutionDeadline =
            (bettingCloseTime == 0 || resolutionWindow == 0) ? uint64(0) : bettingCloseTime + resolutionWindow;

        address resolvedResolver = resolver == address(0) ? msg.sender : resolver;
        address resolvedBettingCloser = bettingCloser;
        address resolvedResolutionCloser = resolutionCloser;

        ParamutuelWager w = new ParamutuelWager(
            address(this),
            msg.sender,
            resolvedResolver,
            resolvedBettingCloser,
            resolvedResolutionCloser,
            collateralToken,
            proposition,
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            resolutionDeadline,
            feeRecipients,
            feeBps
        );

        wager = address(w);
        wagers.push(wager);
        emit WagerCreated(
            wager,
            msg.sender,
            resolvedResolver,
            collateralToken,
            bettingCloseTime,
            resolutionWindow,
            resolutionDeadline,
            resolvedBettingCloser,
            resolvedResolutionCloser
        );

        if (seedAmounts.length > 0) {
            bool ok = IERC20(collateralToken).transferFrom(msg.sender, wager, seedTotal);
            require(ok, "TRANSFER_FROM");
            w.seedInitialBetsFromFactory(msg.sender, seedOutcomeIndices, seedAmounts);
        }
    }

    function _buildFeeConfig(address[] memory extraRecipients, uint16[] memory extraBps)
        internal
        view
        returns (address[] memory feeRecipients, uint16[] memory feeBps, uint256 totalFeeBps)
    {
        if (extraRecipients.length != extraBps.length) revert BadFeeConfig();

        uint256 n = extraRecipients.length + (protocolFeeBps > 0 ? 1 : 0);
        feeRecipients = new address[](n);
        feeBps = new uint16[](n);

        uint256 idx;
        if (protocolFeeBps > 0) {
            feeRecipients[idx] = treasury;
            feeBps[idx] = protocolFeeBps;
            totalFeeBps += protocolFeeBps;
            idx++;
        }

        for (uint256 i; i < extraRecipients.length; i++) {
            if (extraRecipients[i] == address(0)) revert BadFeeConfig();
            if (extraBps[i] == 0) revert BadFeeConfig();
            feeRecipients[idx] = extraRecipients[i];
            feeBps[idx] = extraBps[i];
            totalFeeBps += extraBps[i];
            idx++;
        }
    }
}

