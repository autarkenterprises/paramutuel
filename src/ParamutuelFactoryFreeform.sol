// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ParamutuelWagerFreeform} from "./ParamutuelWagerFreeform.sol";

/// @notice Factory for ADR-0009 freeform text-answer wagers (no enumerated outcomes at create).
contract ParamutuelFactoryFreeform {
    event WagerCreatedFreeform(
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
    error WindowTooShort();
    error InvalidLifecycleConfig();

    uint256 public constant BPS_DENOMINATOR = 10_000;
    uint16 public constant MAX_TOTAL_FEE_BPS = 10_000;
    /// @dev Passed to each wager; bounds worst-case resolve/claim iteration.
    uint256 public constant WAGER_MAX_DISTINCT_ANSWERS = 1024;

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

    function createFreeformWager(
        address collateralToken,
        string memory proposition,
        uint64 bettingCloseTime,
        uint64 resolutionWindow,
        address resolver,
        address bettingCloser,
        address resolutionCloser,
        address[] memory extraFeeRecipients,
        uint16[] memory extraFeeBps
    ) external returns (address wager) {
        uint64 nowTs = uint64(block.timestamp);
        if (bettingCloseTime != 0 && bettingCloseTime < nowTs + minBettingWindow) revert WindowTooShort();
        if (resolutionWindow != 0 && resolutionWindow < minResolutionWindow) revert WindowTooShort();
        if (bettingCloseTime == 0 && bettingCloser == address(0)) revert InvalidLifecycleConfig();
        if (resolutionWindow == 0 && resolutionCloser == address(0)) revert InvalidLifecycleConfig();

        (address[] memory feeRecipients, uint16[] memory feeBps, uint256 totalFeeBps) =
            _buildFeeConfig(extraFeeRecipients, extraFeeBps);
        if (totalFeeBps > MAX_TOTAL_FEE_BPS) revert BadFeeConfig();

        uint64 resolutionDeadline =
            (bettingCloseTime == 0 || resolutionWindow == 0) ? uint64(0) : bettingCloseTime + resolutionWindow;

        address resolvedResolver = resolver == address(0) ? msg.sender : resolver;

        ParamutuelWagerFreeform w = new ParamutuelWagerFreeform(
            address(this),
            msg.sender,
            resolvedResolver,
            bettingCloser,
            resolutionCloser,
            collateralToken,
            proposition,
            bettingCloseTime,
            resolutionWindow,
            resolutionDeadline,
            feeRecipients,
            feeBps,
            WAGER_MAX_DISTINCT_ANSWERS
        );

        wager = address(w);
        wagers.push(wager);
        emit WagerCreatedFreeform(
            wager,
            msg.sender,
            resolvedResolver,
            collateralToken,
            bettingCloseTime,
            resolutionWindow,
            resolutionDeadline,
            bettingCloser,
            resolutionCloser
        );
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
