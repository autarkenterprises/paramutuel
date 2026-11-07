// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ParamutuelWagerV3} from "./ParamutuelWagerV3.sol";
import {IERC20} from "./interfaces/IERC20.sol";
import {BitMath} from "./utils/BitMath.sol";

/// @title Paramutuel V3 factory — single deployer for both wager modes
/// @notice Per ADR-0010, V3 collapsed three previously-separate contract surfaces
///         (V1 single-winner, V2 enumerated/bitmask, standalone freeform) into one
///         mode-discriminated `ParamutuelWagerV3`. This factory is the only sanctioned
///         creation path for that wager — both `createEnumeratedWager` (ADR-0008
///         bitmask + payoff-policy lineage) and `createFreeformWager` (ADR-0009 text
///         answer lineage) deploy the same bytecode, differing only by the immutable
///         `WagerMode` written at construction.
/// @notice The factory also owns governance state that is intentionally absent from the
///         per-wager contract: `treasury` and `protocolFeeBps` are read once per
///         deployment and baked into each wager's immutable fee recipient list. The
///         factory itself is deployed once per environment (see `config/deployments.json`).
/// @dev `treasury`, `protocolFeeBps`, `minBettingWindow` and `minResolutionWindow` are all
///      `immutable`: any change of protocol-fee policy means deploying a new factory (ADR-0002 §
///      "fee-setting authority"), and they constrain every wager this factory ever produces.
/// @dev The creation overloads form a ladder so simple callers need not pass empty arrays or a zero
///      minimum. Every overload funnels into the one internal builder for its mode, and the older
///      signatures remain so existing clients and encoders keep working unchanged (ADR-0020).
contract ParamutuelFactoryV3 {
    /// @dev Two distinct creation events (rather than one with a `mode` field) because
    ///      the indexer treats them as separate streams: enumerated wagers carry an
    ///      `outcomes[]` ABI-encoded into the calldata that the indexer back-decodes;
    ///      freeform wagers have no outcomes at construction time. Keeping the events
    ///      shape-distinct avoids a mode-branched decoder in `service/indexer/`.
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
    /// @dev Capped at 255 (not 256) so every mask is at most 255 bits wide, which keeps
    ///      `BitMath.popcount` exact, and a single `uint8` index can address every option off-chain.
    ///      The wager enforces the same ceiling.
    uint256 public constant MAX_OUTCOMES = 255;
    /// @dev Cap on proposer-supplied fee recipients. Every terminal path walks the recipient list,
    ///      at about 27k gas each. Without a cap, an L1 deposit transaction (exempt from the 2^24
    ///      per-transaction gas cap) could create a wager that an ordinary resolver, or anyone
    ///      trying to `expire` it, could never finalise (ADR-0020 C9).
    uint256 public constant MAX_EXTRA_FEE_RECIPIENTS = 32;

    /// @dev Per-environment minimum windows: prevents accidentally-immediate or
    ///      vanishingly-short wagers in production while allowing tests to deploy a
    ///      factory with `(0, 0)` so they can exercise edge cases without sleeping.
    uint64 public immutable minBettingWindow;
    uint64 public immutable minResolutionWindow;

    /// @dev Fixed for the life of the factory; see the contract-level note on ADR-0002.
    address public immutable treasury;
    uint16 public immutable protocolFeeBps;

    /// @dev Append-only registry of wagers this factory has produced, for on-chain discovery.
    ///      The indexer itself discovers wagers through the events above.
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

    /// @notice Enumerated wager with no seed bets and no minimum new-ticket stake.
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
        return _createEnumerated(
            EnumeratedArgs(
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
                new uint256[](0),
                new uint256[](0),
                0
            )
        );
    }

    /// @notice Enumerated wager seeded with the proposer's own bets in the creation transaction.
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
            EnumeratedArgs(
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
                seedAmounts,
                0
            )
        );
    }

    /// @notice Enumerated wager with optional seeds and a minimum stake to open a new ticket, which
    ///         prices griefing by dust tickets in units of the proposer's chosen collateral.
    /// @dev Seed tickets are new tickets, so each seed amount must also meet the minimum.
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
        uint256[] memory seedAmounts,
        uint256 minNewTicketStake
    ) external returns (address wager) {
        return _createEnumerated(
            EnumeratedArgs(
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
                seedAmounts,
                minNewTicketStake
            )
        );
    }

    /// @dev All overloads' arguments, as a struct so the builder stays within the stack limit even
    ///      in the unoptimised build `forge coverage` uses.
    struct EnumeratedArgs {
        address collateralToken;
        string proposition;
        string[] outcomes;
        ParamutuelWagerV3.PayoffPolicy payoffPolicy;
        uint256 policyParam;
        uint64 bettingCloseTime;
        uint64 resolutionWindow;
        address resolver;
        address bettingCloser;
        address resolutionCloser;
        address[] extraFeeRecipients;
        uint16[] extraFeeBps;
        uint256[] seedTicketMasks;
        uint256[] seedAmounts;
        uint256 minNewTicketStake;
    }

    /// @dev Centralised enumerated-wager construction path. Validation order is deliberate: cheap
    ///      shape checks first (outcomes count, seed array parity), then policy / mask validation,
    ///      then lifecycle-config checks, then fee-config. This fails fast on the most common
    ///      misconfigurations before any bytecode is deployed.
    function _createEnumerated(EnumeratedArgs memory a) internal returns (address wager) {
        if (a.outcomes.length < 2) revert BadOutcomes();
        if (a.outcomes.length > MAX_OUTCOMES) revert TooManyOutcomes();
        if (a.seedTicketMasks.length != a.seedAmounts.length) revert BadSeedConfig();

        uint256 seedTotal;
        for (uint256 i; i < a.seedAmounts.length; i++) {
            if (a.seedAmounts[i] == 0) revert BadSeedConfig();
            seedTotal += a.seedAmounts[i];
        }

        _validatePolicyParam(a.payoffPolicy, a.policyParam, a.outcomes.length);
        for (uint256 s; s < a.seedTicketMasks.length; s++) {
            _validateSeedTicketMask(a.seedTicketMasks[s], a.payoffPolicy, a.outcomes.length);
        }

        _validateLifecycle(a.bettingCloseTime, a.resolutionWindow, a.bettingCloser, a.resolutionCloser);
        (address[] memory feeRecipients, uint16[] memory feeBps) = _buildFeeConfig(a.extraFeeRecipients, a.extraFeeBps);

        uint64 resolutionDeadline = _resolutionDeadline(a.bettingCloseTime, a.resolutionWindow);

        // Default the resolver to the proposer (msg.sender) when zero is passed. ADR-0001
        // makes the resolver immutable post-construction; defaulting here lets the
        // simplest case ("I propose and I resolve") skip an explicit argument.
        address resolvedResolver = a.resolver == address(0) ? msg.sender : a.resolver;

        ParamutuelWagerV3 w = new ParamutuelWagerV3(
            ParamutuelWagerV3.InitParams({
                mode: ParamutuelWagerV3.WagerMode.Enumerated,
                factory: address(this),
                proposer: msg.sender,
                resolver: resolvedResolver,
                bettingCloser: a.bettingCloser,
                resolutionCloser: a.resolutionCloser,
                collateralToken: a.collateralToken,
                proposition: a.proposition,
                outcomes: a.outcomes,
                payoffPolicy: a.payoffPolicy,
                policyParam: a.policyParam,
                bettingCloseTime: a.bettingCloseTime,
                resolutionWindow: a.resolutionWindow,
                resolutionDeadline: resolutionDeadline,
                feeRecipients: feeRecipients,
                feeBps: feeBps,
                minNewTicketStake: a.minNewTicketStake
            })
        );

        wager = address(w);
        wagers.push(wager);
        emit WagerCreatedV3Enumerated(
            wager,
            msg.sender,
            resolvedResolver,
            a.collateralToken,
            uint8(a.payoffPolicy),
            a.policyParam,
            a.bettingCloseTime,
            a.resolutionWindow,
            resolutionDeadline,
            a.bettingCloser,
            a.resolutionCloser
        );

        // Seed-bet flow: the factory pulls collateral from `msg.sender` directly into
        // the freshly-deployed wager, then invokes the factory-only seeder on the
        // wager. This shape preserves the proposer's allowance scope (the proposer
        // approves the factory once, not the not-yet-existent wager) and keeps the
        // wager itself unable to pull funds from arbitrary addresses. Ordering is
        // post-event so external observers see creation before the seed bets are
        // recorded; the seeder emits its own per-bet events from inside the wager.
        if (a.seedAmounts.length > 0) {
            bool ok = IERC20(a.collateralToken).transferFrom(msg.sender, wager, seedTotal);
            require(ok, "TRANSFER_FROM");
            ParamutuelWagerV3(wager).seedInitialBetsFromFactory(msg.sender, a.seedTicketMasks, a.seedAmounts);
        }
    }

    /// @notice Deploy a freeform-text wager (ADR-0009 lineage, hosted in V3 under
    ///         `WagerMode.Freeform`). No `outcomes[]`, no payoff-policy parameter, no
    ///         seed-bets: the answer space is open, and bettors create new answer ids
    ///         by placing the first bet on a string.
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
        return _createFreeform(
            collateralToken,
            proposition,
            bettingCloseTime,
            resolutionWindow,
            resolver,
            bettingCloser,
            resolutionCloser,
            extraFeeRecipients,
            extraFeeBps,
            0
        );
    }

    /// @notice Freeform wager with a minimum stake to open a new answer. Without one, dust answers
    ///         cannot harm settlement but can clutter off-chain answer lists.
    function createFreeformWager(
        address collateralToken,
        string memory proposition,
        uint64 bettingCloseTime,
        uint64 resolutionWindow,
        address resolver,
        address bettingCloser,
        address resolutionCloser,
        address[] memory extraFeeRecipients,
        uint16[] memory extraFeeBps,
        uint256 minNewTicketStake
    ) external returns (address wager) {
        return _createFreeform(
            collateralToken,
            proposition,
            bettingCloseTime,
            resolutionWindow,
            resolver,
            bettingCloser,
            resolutionCloser,
            extraFeeRecipients,
            extraFeeBps,
            minNewTicketStake
        );
    }

    function _createFreeform(
        address collateralToken,
        string memory proposition,
        uint64 bettingCloseTime,
        uint64 resolutionWindow,
        address resolver,
        address bettingCloser,
        address resolutionCloser,
        address[] memory extraFeeRecipients,
        uint16[] memory extraFeeBps,
        uint256 minNewTicketStake
    ) internal returns (address wager) {
        _validateLifecycle(bettingCloseTime, resolutionWindow, bettingCloser, resolutionCloser);
        (address[] memory feeRecipients, uint16[] memory feeBps) = _buildFeeConfig(extraFeeRecipients, extraFeeBps);

        uint64 resolutionDeadline = _resolutionDeadline(bettingCloseTime, resolutionWindow);
        address resolvedResolver = resolver == address(0) ? msg.sender : resolver;

        // Freeform mode requires zero outcomes at construction; the wager's constructor enforces
        // that as well.
        string[] memory emptyOutcomes;
        ParamutuelWagerV3 w = new ParamutuelWagerV3(
            ParamutuelWagerV3.InitParams({
                mode: ParamutuelWagerV3.WagerMode.Freeform,
                factory: address(this),
                proposer: msg.sender,
                resolver: resolvedResolver,
                bettingCloser: bettingCloser,
                resolutionCloser: resolutionCloser,
                collateralToken: collateralToken,
                proposition: proposition,
                outcomes: emptyOutcomes,
                payoffPolicy: ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER,
                policyParam: 0,
                bettingCloseTime: bettingCloseTime,
                resolutionWindow: resolutionWindow,
                resolutionDeadline: resolutionDeadline,
                feeRecipients: feeRecipients,
                feeBps: feeBps,
                minNewTicketStake: minNewTicketStake
            })
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

    /// @dev Shared window guardrails. A zero time is permitted only when the matching authority is
    ///      configured (ADR-0005): without one, the wager could never leave its current phase.
    ///      Betting cannot close before `minBettingWindow` from now, and a time-bounded resolution
    ///      window cannot be shorter than `minResolutionWindow`.
    function _validateLifecycle(
        uint64 bettingCloseTime,
        uint64 resolutionWindow,
        address bettingCloser,
        address resolutionCloser
    ) internal view {
        uint64 nowTs = uint64(block.timestamp);
        if (bettingCloseTime != 0 && bettingCloseTime < nowTs + minBettingWindow) revert WindowTooShort();
        if (resolutionWindow != 0 && resolutionWindow < minResolutionWindow) revert WindowTooShort();
        if (bettingCloseTime == 0 && bettingCloser == address(0)) revert InvalidLifecycleConfig();
        if (resolutionWindow == 0 && resolutionCloser == address(0)) revert InvalidLifecycleConfig();
    }

    /// @dev Latest possible deadline, for display only: zero when either window is closer-managed,
    ///      and superseded by an earlier `closeBetting`, which re-anchors the resolution window.
    function _resolutionDeadline(uint64 bettingCloseTime, uint64 resolutionWindow) internal pure returns (uint64) {
        return (bettingCloseTime == 0 || resolutionWindow == 0) ? uint64(0) : bettingCloseTime + resolutionWindow;
    }

    /// @dev Composes the wager's immutable fee-recipient list. The protocol's own
    ///      `(treasury, protocolFeeBps)` is prepended at slot 0 when `protocolFeeBps`
    ///      is non-zero; proposer-supplied extras follow. Order matters at finalisation:
    ///      `_chargeFeesOnce` floors each slice in declared order and gives the last slice
    ///      the rounding remainder.
    function _buildFeeConfig(address[] memory extraRecipients, uint16[] memory extraBps)
        internal
        view
        returns (address[] memory feeRecipients, uint16[] memory feeBps)
    {
        if (extraRecipients.length != extraBps.length) revert BadFeeConfig();
        if (extraRecipients.length > MAX_EXTRA_FEE_RECIPIENTS) revert BadFeeConfig();

        // Pre-size the output once. A protocol slot is reserved iff `protocolFeeBps > 0`
        // — keeping a zero-bps protocol slot in the array would force the wager to
        // emit a `FeeAccruedV3(treasury, 0)` event for every wager that opts the
        // protocol out, polluting the indexer.
        uint256 n = extraRecipients.length + (protocolFeeBps > 0 ? 1 : 0);
        feeRecipients = new address[](n);
        feeBps = new uint16[](n);

        uint256 idx;
        uint256 totalFeeBps;
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
        if (totalFeeBps > MAX_TOTAL_FEE_BPS) revert BadFeeConfig();
    }

    /// @dev Only `AT_LEAST_K` consumes `policyParam` (as the threshold K). For every
    ///      other policy `policyParam` MUST be zero — a non-zero value indicates a
    ///      caller misunderstanding (e.g. confusing `AT_LEAST_K` with `EXACT_SET`),
    ///      so it is rejected rather than silently ignored. The wager constructor
    ///      enforces the same invariant on its own input as defence-in-depth.
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

    /// @dev Pre-flight for seed-bet masks before they reach the wager. Mirrors the
    ///      wager's own `_validateMask` + `_policyAllowsTicket` so a malformed seed
    ///      reverts at creation time rather than after deployment, leaving an
    ///      orphaned wager on chain. The `mask >> numOptions_ != 0` guard rejects
    ///      bits set above the legal option range.
    function _validateSeedTicketMask(uint256 mask, ParamutuelWagerV3.PayoffPolicy policy, uint256 numOptions_)
        internal
        pure
    {
        if (mask == 0) revert BadSeedConfig();
        if (mask >> numOptions_ != 0) revert BadSeedConfig();
        if (policy == ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER && !BitMath.isSingleBit(mask)) {
            revert BadSeedConfig();
        }
    }
}
