// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ParamutuelMarket} from "./ParamutuelMarket.sol";

contract ParamutuelFactory {
    /// @param resolver The address that may `resolve` / `retract` (same as proposer if `resolver == address(0)` at creation).
    event MarketCreated(
        address indexed market,
        address indexed proposer,
        address indexed resolver,
        address collateralToken,
        uint64 bettingCloseTime,
        uint64 resolutionDeadline
    );

    error BadFeeConfig();
    error BadOutcomes();
    error WindowTooShort();
    error TooManyOutcomes();

    uint256 public constant BPS_DENOMINATOR = 10_000;
    uint16 public constant MAX_TOTAL_FEE_BPS = 1_000; // 10% cap for MVP
    uint256 public constant MAX_OUTCOMES = 64;

    uint64 public immutable minBettingWindow;
    uint64 public immutable minResolutionWindow;

    address public treasury;
    uint16 public protocolFeeBps;

    address[] public markets;

    constructor(address treasury_, uint16 protocolFeeBps_, uint64 minBettingWindow_, uint64 minResolutionWindow_) {
        require(treasury_ != address(0), "TREASURY");
        require(protocolFeeBps_ <= MAX_TOTAL_FEE_BPS, "FEE");
        treasury = treasury_;
        protocolFeeBps = protocolFeeBps_;
        minBettingWindow = minBettingWindow_;
        minResolutionWindow = minResolutionWindow_;
    }

    function marketsCount() external view returns (uint256) {
        return markets.length;
    }

    /// @param resolver If `address(0)`, the resolver is the caller (`msg.sender`). Otherwise must be non-zero.
    function createMarket(
        address collateralToken,
        string memory question,
        string[] memory outcomes,
        uint64 bettingCloseTime,
        uint64 resolutionWindow,
        address resolver,
        address[] memory extraFeeRecipients,
        uint16[] memory extraFeeBps
    ) external returns (address market) {
        if (outcomes.length < 2) revert BadOutcomes();
        if (outcomes.length > MAX_OUTCOMES) revert TooManyOutcomes();

        uint64 nowTs = uint64(block.timestamp);
        if (bettingCloseTime < nowTs + minBettingWindow) revert WindowTooShort();
        if (resolutionWindow < minResolutionWindow) revert WindowTooShort();

        (address[] memory feeRecipients, uint16[] memory feeBps, uint256 totalFeeBps) = _buildFeeConfig(
            extraFeeRecipients,
            extraFeeBps
        );
        if (totalFeeBps > MAX_TOTAL_FEE_BPS) revert BadFeeConfig();

        uint64 resolutionDeadline = bettingCloseTime + resolutionWindow;

        address resolvedResolver = resolver == address(0) ? msg.sender : resolver;

        ParamutuelMarket m = new ParamutuelMarket(
            address(this),
            msg.sender,
            resolvedResolver,
            collateralToken,
            question,
            outcomes,
            bettingCloseTime,
            resolutionDeadline,
            feeRecipients,
            feeBps
        );

        market = address(m);
        markets.push(market);
        emit MarketCreated(market, msg.sender, resolvedResolver, collateralToken, bettingCloseTime, resolutionDeadline);
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

