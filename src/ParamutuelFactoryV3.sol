// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ParamutuelWagerV3} from "./ParamutuelWagerV3.sol";
import {IERC20} from "./interfaces/IERC20.sol";

/// @notice Single factory for Paramutuel v3 — enumerated (bitmask + policies) or freeform text wagers.
contract ParamutuelFactoryV3 {
    event WagerCreatedV3Enumerated(
        address indexed wager,
        address indexed proposer,
        address indexed resolver,
        address collateralToken,
        uint8 payoffPolicy,
        uint256 policyParam,
        uint64 bettingCloseTime,
        uint64 resolutionWindow,
        uint64 resolutionDeadline,
        address bettingCloser,
        address resolutionCloser
    );

    event WagerCreatedV3Freeform(
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
    error InvalidPolicyParam();

    uint256 public constant BPS_DENOMINATOR = 10_000;
    uint16 public constant MAX_TOTAL_FEE_BPS = 10_000;
    uint256 public constant MAX_OUTCOMES = 255;
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

    function createEnumeratedWager(
        address collateralToken,
        string memory proposition,
        string[] memory outcomes,
        ParamutuelWagerV3.PayoffPolicy payoffPolicy,
        uint256 policyParam,
        uint64 bettingCloseTime,
        uint64 resolutionWindow,
        address resolver,
        address bettingCloser,
        address resolutionCloser,
        address[] memory extraFeeRecipients,
        uint16[] memory extraFeeBps
    ) external returns (address wager) {
        uint256[] memory seedMasks = new uint256[](0);
        uint256[] memory seedAmounts = new uint256[](0);
        return _createEnumerated(
            collateralToken,
            proposition,
            outcomes,
            payoffPolicy,
            policyParam,
            bettingCloseTime,
            resolutionWindow,
            resolver,
            bettingCloser,
            resolutionCloser,
            extraFeeRecipients,
            extraFeeBps,
            seedMasks,
            seedAmounts
        );
    }

    function createEnumeratedWager(
        address collateralToken,
        string memory proposition,
        string[] memory outcomes,
        ParamutuelWagerV3.PayoffPolicy payoffPolicy,
        uint256 policyParam,
        uint64 bettingCloseTime,
        uint64 resolutionWindow,
        address resolver,
        address bettingCloser,
        address resolutionCloser,
        address[] memory extraFeeRecipients,
        uint16[] memory extraFeeBps,
        uint256[] memory seedTicketMasks,
        uint256[] memory seedAmounts
    ) external returns (address wager) {
        return _createEnumerated(
            collateralToken,
            proposition,
            outcomes,
            payoffPolicy,
            policyParam,
            bettingCloseTime,
            resolutionWindow,
            resolver,
            bettingCloser,
            resolutionCloser,
            extraFeeRecipients,
            extraFeeBps,
            seedTicketMasks,
            seedAmounts
        );
    }

    function _createEnumerated(
        address collateralToken,
        string memory proposition,
        string[] memory outcomes,
        ParamutuelWagerV3.PayoffPolicy payoffPolicy,
        uint256 policyParam,
        uint64 bettingCloseTime,
        uint64 resolutionWindow,
        address resolver,
        address bettingCloser,
        address resolutionCloser,
        address[] memory extraFeeRecipients,
        uint16[] memory extraFeeBps,
        uint256[] memory seedTicketMasks,
        uint256[] memory seedAmounts
    ) internal returns (address wager) {
        if (outcomes.length < 2) revert BadOutcomes();
        if (outcomes.length > MAX_OUTCOMES) revert TooManyOutcomes();
        if (seedTicketMasks.length != seedAmounts.length) revert BadSeedConfig();

        uint256 seedTotal;
        for (uint256 i; i < seedAmounts.length; i++) {
            if (seedAmounts[i] == 0) revert BadSeedConfig();
            seedTotal += seedAmounts[i];
        }

        uint256 nOpt = outcomes.length;
        _validatePolicyParam(payoffPolicy, policyParam, nOpt);
        for (uint256 s; s < seedTicketMasks.length; s++) {
            _validateSeedTicketMask(seedTicketMasks[s], payoffPolicy, nOpt);
        }

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

        ParamutuelWagerV3 w = new ParamutuelWagerV3(
            ParamutuelWagerV3.WagerMode.Enumerated,
            address(this),
            msg.sender,
            resolvedResolver,
            bettingCloser,
            resolutionCloser,
            collateralToken,
            proposition,
            outcomes,
            payoffPolicy,
            policyParam,
            bettingCloseTime,
            resolutionWindow,
            resolutionDeadline,
            feeRecipients,
            feeBps,
            0
        );

        wager = address(w);
        wagers.push(wager);
        emit WagerCreatedV3Enumerated(
            wager,
            msg.sender,
            resolvedResolver,
            collateralToken,
            uint8(payoffPolicy),
            policyParam,
            bettingCloseTime,
            resolutionWindow,
            resolutionDeadline,
            bettingCloser,
            resolutionCloser
        );

        if (seedAmounts.length > 0) {
            bool ok = IERC20(collateralToken).transferFrom(msg.sender, wager, seedTotal);
            require(ok, "TRANSFER_FROM");
            ParamutuelWagerV3(wager).seedInitialBetsFromFactory(msg.sender, seedTicketMasks, seedAmounts);
        }
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

        string[] memory emptyOutcomes;
        ParamutuelWagerV3 w = new ParamutuelWagerV3(
            ParamutuelWagerV3.WagerMode.Freeform,
            address(this),
            msg.sender,
            resolvedResolver,
            bettingCloser,
            resolutionCloser,
            collateralToken,
            proposition,
            emptyOutcomes,
            ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER,
            0,
            bettingCloseTime,
            resolutionWindow,
            resolutionDeadline,
            feeRecipients,
            feeBps,
            WAGER_MAX_DISTINCT_ANSWERS
        );

        wager = address(w);
        wagers.push(wager);
        emit WagerCreatedV3Freeform(
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

    function _validatePolicyParam(ParamutuelWagerV3.PayoffPolicy policy, uint256 policyParam_, uint256 numOutcomes)
        internal
        pure
    {
        if (policy == ParamutuelWagerV3.PayoffPolicy.AT_LEAST_K) {
            if (policyParam_ < 1 || policyParam_ > numOutcomes) revert InvalidPolicyParam();
        } else if (policyParam_ != 0) {
            revert InvalidPolicyParam();
        }
    }

    function _popcount(uint256 x) internal pure returns (uint256 c) {
        unchecked {
            while (x != 0) {
                x &= x - 1;
                c++;
            }
        }
    }

    function _validateSeedTicketMask(uint256 mask, ParamutuelWagerV3.PayoffPolicy policy, uint256 numOptions_)
        internal
        pure
    {
        if (mask == 0) revert BadSeedConfig();
        if (mask >> numOptions_ != 0) revert BadSeedConfig();
        if (policy == ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER && _popcount(mask) != 1) {
            revert BadSeedConfig();
        }
    }
}
