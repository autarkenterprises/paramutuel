// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @dev **Test-only** mirror of `src/ParamutuelFactoryV2.sol` with `MAX_OUTCOMES = 64` for legacy-boundary tests.
///      Not deployed in production. If the real factory changes, update this file to match (except the cap).
import {ParamutuelWagerV2} from "../../src/ParamutuelWagerV2.sol";
import {IERC20} from "../../src/interfaces/IERC20.sol";

contract ParamutuelFactoryV2Max64 {
    event WagerCreatedV2(
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

    error BadFeeConfig();
    error BadOutcomes();
    error WindowTooShort();
    error TooManyOutcomes();
    error InvalidLifecycleConfig();
    error BadSeedConfig();
    /// @dev Mirrors `ParamutuelWagerV2.InvalidPolicyParam` (same selector) for early validation before deploy.
    error InvalidPolicyParam();

    uint256 public constant BPS_DENOMINATOR = 10_000;
    uint16 public constant MAX_TOTAL_FEE_BPS = 10_000;
    /// @dev Historical cap for regression tests only (production factory uses 255).
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

    function createWager(
        address collateralToken,
        string memory proposition,
        string[] memory outcomes,
        ParamutuelWagerV2.PayoffPolicy payoffPolicy,
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
        return _createWager(
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

    function createWager(
        address collateralToken,
        string memory proposition,
        string[] memory outcomes,
        ParamutuelWagerV2.PayoffPolicy payoffPolicy,
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
        return _createWager(
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

    function _createWager(
        address collateralToken,
        string memory proposition,
        string[] memory outcomes,
        ParamutuelWagerV2.PayoffPolicy payoffPolicy,
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

        (address[] memory feeRecipients, uint16[] memory feeBps, uint256 totalFeeBps) = _buildFeeConfig(
            extraFeeRecipients,
            extraFeeBps
        );
        if (totalFeeBps > MAX_TOTAL_FEE_BPS) revert BadFeeConfig();

        uint64 resolutionDeadline =
            (bettingCloseTime == 0 || resolutionWindow == 0) ? uint64(0) : bettingCloseTime + resolutionWindow;

        address resolvedResolver = resolver == address(0) ? msg.sender : resolver;

        ParamutuelWagerV2 w = new ParamutuelWagerV2(
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
            feeBps
        );

        wager = address(w);
        wagers.push(wager);
        emit WagerCreatedV2(
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
            w.seedInitialBetsFromFactory(msg.sender, seedTicketMasks, seedAmounts);
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

    function _validatePolicyParam(ParamutuelWagerV2.PayoffPolicy policy, uint256 policyParam_, uint256 numOutcomes)
        internal
        pure
    {
        if (policy == ParamutuelWagerV2.PayoffPolicy.AT_LEAST_K) {
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

    function _validateSeedTicketMask(uint256 mask, ParamutuelWagerV2.PayoffPolicy policy, uint256 numOptions_)
        internal
        pure
    {
        if (mask == 0) revert BadSeedConfig();
        if (mask >> numOptions_ != 0) revert BadSeedConfig();
        if (policy == ParamutuelWagerV2.PayoffPolicy.SINGLE_WINNER && _popcount(mask) != 1) {
            revert BadSeedConfig();
        }
    }
}
