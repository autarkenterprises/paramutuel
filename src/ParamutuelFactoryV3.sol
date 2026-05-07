// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ParamutuelWagerV3} from "./ParamutuelWagerV3.sol";
import {IERC20} from "./interfaces/IERC20.sol";

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
/// @dev Storage layout invariant: `treasury` and `protocolFeeBps` are mutable in source
///      but have no setter — they are effectively immutable post-deploy and any future
///      governance change requires deploying a new factory (ADR-0002 §"fee-setting
///      authority"). `minBettingWindow` / `minResolutionWindow` are true `immutable`
///      and constrain every wager this factory ever produces.
/// @dev The two `createEnumeratedWager` overloads exist solely so the simpler signature
///      does not force callers to pass empty seed arrays — the seeded form is the
///      canonical one and the un-seeded form delegates into it with zero-length arrays.
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
    /// @dev Capped at 255 (not 256) so the bitmask fits comfortably in `uint256` and
    ///      so a single `uint8` index can address every option off-chain. The wager
    ///      enforces its own ceiling (256) — the factory's tighter cap leaves headroom
    ///      for the indexer's `option_index = uint8` columns.
    uint256 public constant MAX_OUTCOMES = 255;
    /// @dev Default cap on distinct freeform answer ids per wager. Identical to the
    ///      wager's own `MAX_DISTINCT_TICKETS` ceiling — chosen to bound the storage
    ///      cost of the resolution-time accumulation loop and the claim-time replay.
    uint256 public constant WAGER_MAX_DISTINCT_ANSWERS = 1024;

    /// @dev Per-environment minimum windows: prevents accidentally-immediate or
    ///      vanishingly-short wagers in production while allowing tests to deploy a
    ///      factory with `(0, 0)` so they can exercise edge cases without sleeping.
    uint64 public immutable minBettingWindow;
    uint64 public immutable minResolutionWindow;

    /// @dev `treasury` and `protocolFeeBps` are mutable-by-syntax but have no setter;
    ///      they are effectively immutable for the life of the factory. Any change of
    ///      protocol-fee policy requires a new factory deployment (ADR-0002).
    address public treasury;
    uint16 public protocolFeeBps;

    /// @dev Append-only registry of wagers this factory has produced. Indexer / explorer
    ///      services treat this as a discovery surface in addition to the events above —
    ///      events are the primary path; this array is a fallback for cold reads.
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

    /// @dev Centralised enumerated-wager construction path. Both public overloads
    ///      funnel here so the validation and event-emission logic exists in exactly
    ///      one place. Validation order is deliberate: cheap shape checks first
    ///      (outcomes count, seed array parity), then policy / mask validation, then
    ///      lifecycle-config checks, then fee-config — this fails fast on the most
    ///      common misconfigurations before any bytecode is deployed.
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
        // ADR-0005: a zero-time lifecycle is permitted only when the corresponding
        // human authority is configured. Without one, the wager would be unable to
        // ever transition state — `expire()` requires `_resolutionWindowOver()` and
        // `resolve()` requires `_bettingClosed()`, both of which gate on these values.
        if (bettingCloseTime == 0 && bettingCloser == address(0)) revert InvalidLifecycleConfig();
        if (resolutionWindow == 0 && resolutionCloser == address(0)) revert InvalidLifecycleConfig();

        (address[] memory feeRecipients, uint16[] memory feeBps, uint256 totalFeeBps) =
            _buildFeeConfig(extraFeeRecipients, extraFeeBps);
        if (totalFeeBps > MAX_TOTAL_FEE_BPS) revert BadFeeConfig();

        // Resolution deadline is only meaningful when both windows are time-bounded;
        // if either is delegated to a human authority, `0` signals "no automatic
        // expiry" and the wager relies on `closeBetting()` / `closeResolutionWindow()`.
        uint64 resolutionDeadline =
            (bettingCloseTime == 0 || resolutionWindow == 0) ? uint64(0) : bettingCloseTime + resolutionWindow;

        // Default the resolver to the proposer (msg.sender) when zero is passed. ADR-0001
        // makes the resolver immutable post-construction; defaulting here lets the
        // simplest case ("I propose and I resolve") skip an explicit argument.
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

        // Seed-bet flow: the factory pulls collateral from `msg.sender` directly into
        // the freshly-deployed wager, then invokes the factory-only seeder on the
        // wager. This shape preserves the proposer's allowance scope (the proposer
        // approves the factory once, not the not-yet-existent wager) and keeps the
        // wager itself unable to pull funds from arbitrary addresses. Ordering is
        // post-event so external observers see creation before the seed bets are
        // recorded; the seeder emits its own per-bet events from inside the wager.
        if (seedAmounts.length > 0) {
            bool ok = IERC20(collateralToken).transferFrom(msg.sender, wager, seedTotal);
            require(ok, "TRANSFER_FROM");
            ParamutuelWagerV3(wager).seedInitialBetsFromFactory(msg.sender, seedTicketMasks, seedAmounts);
        }
    }

    /// @notice Deploy a freeform-text wager (ADR-0009 lineage, hosted in V3 under
    ///         `WagerMode.Freeform`). No `outcomes[]`, no payoff-policy parameter, no
    ///         seed-bets — answer space is unbounded UTF-8 and bettors create new
    ///         answer ids by placing the first bet on a string. The wager is
    ///         constructed with `WAGER_MAX_DISTINCT_ANSWERS` as the cap on how many
    ///         distinct answer ids it will record before reverting further bets.
    /// @dev The freeform path duplicates the lifecycle/fee validation from
    ///      `_createEnumerated` rather than sharing it because the seed-bet branch and
    ///      the policy-param validation are enumerated-only; sharing would require
    ///      threading a mode flag through helper functions for marginal LoC savings.
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

        // Freeform mode requires zero outcomes at construction; the wager's
        // constructor enforces that as well, but passing an empty memory array here
        // keeps the call shape uniform with the enumerated path.
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

    /// @dev Composes the wager's immutable fee-recipient list. The protocol's own
    ///      `(treasury, protocolFeeBps)` is prepended at slot 0 when `protocolFeeBps`
    ///      is non-zero; proposer-supplied extras follow. The order matters at claim
    ///      time: `_chargeFeesOnce` in the wager pays each slice in declared order
    ///      with the last slice taking the rounding remainder, so slot 0 (the
    ///      protocol) absorbs the smallest dust on average.
    function _buildFeeConfig(address[] memory extraRecipients, uint16[] memory extraBps)
        internal
        view
        returns (address[] memory feeRecipients, uint16[] memory feeBps, uint256 totalFeeBps)
    {
        if (extraRecipients.length != extraBps.length) revert BadFeeConfig();

        // Pre-size the output once. A protocol slot is reserved iff `protocolFeeBps > 0`
        // — keeping a zero-bps protocol slot in the array would force the wager to
        // emit a `FeeAccruedV3(treasury, 0)` event for every wager that opts the
        // protocol out, polluting the indexer.
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

    /// @dev Brian Kernighan bit-count. Used only for seed-mask validation, where the
    ///      mask is bounded by `MAX_OUTCOMES` so the loop is small. Duplicated rather
    ///      than imported from the wager because keeping the factory free of internal
    ///      cross-imports simplifies the deployment graph.
    function _popcount(uint256 x) internal pure returns (uint256 c) {
        unchecked {
            while (x != 0) {
                x &= x - 1;
                c++;
            }
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
        if (policy == ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER && _popcount(mask) != 1) {
            revert BadSeedConfig();
        }
    }
}
