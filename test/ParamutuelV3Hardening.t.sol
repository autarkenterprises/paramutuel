// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import {ParamutuelFactoryV3} from "../src/ParamutuelFactoryV3.sol";
import {ParamutuelWagerV3} from "../src/ParamutuelWagerV3.sol";
import {BitMath} from "../src/utils/BitMath.sol";
import {FullMath} from "../src/utils/FullMath.sol";
import {MockERC20, NoReturnToken, FeeOnTransferToken, AdjustableTransferToken} from "./utils/MockTokens.sol";

/// @dev External wrappers so library behaviour, including reverts, can be asserted directly.
contract MathHarness {
    function mulDiv(uint256 a, uint256 b, uint256 c) external pure returns (uint256) {
        return FullMath.mulDiv(a, b, c);
    }

    function popcount(uint256 x) external pure returns (uint256) {
        return BitMath.popcount(x);
    }

    function isSingleBit(uint256 x) external pure returns (bool) {
        return BitMath.isSingleBit(x);
    }
}

/// @dev `vm.cool` postdates the vendored forge-std, so call the cheatcode directly. Foundry runs a
///      whole test in one transaction, so storage already touched stays warm and `gasleft()` deltas
///      understate real cost (by ~4M gas for a 1024-mask resolve, which hid finding C1). Cooling the
///      wager reproduces what a resolver's own transaction actually pays.
interface VmCool {
    function cool(address target) external;
}

/// @notice ADR-0020 regression suite. Each test pins one verified finding from
///         `research/adr/ADR-0020-verification-remediation.md`, and was observed failing against the
///         pre-fix contracts (see `docs/ADR-0020-IMPLEMENTATION.md`).
contract ParamutuelV3HardeningTest is Test {
    /// @dev EIP-7825 per-transaction gas cap, enforced on Base since the Azul upgrade. A path whose
    ///      worst case exceeds this is impossible rather than merely expensive.
    uint256 internal constant TX_GAS_CAP = 16_777_216;
    /// @dev Headroom for intrinsic gas and calldata, which `gasleft()` deltas do not include.
    uint256 internal constant TX_OVERHEAD_MARGIN = 100_000;

    VmCool internal constant VM_COOL = VmCool(address(uint160(uint256(keccak256("hevm cheat code")))));

    uint64 internal constant T0 = 1000;
    uint64 internal constant CLOSE = T0 + 2 hours;
    uint64 internal constant WINDOW = 2 hours;

    ParamutuelFactoryV3 internal factory;
    MockERC20 internal token;

    address internal treasury = address(0xFEE);
    address internal alice = address(0xA11CE);
    address internal bob = address(0xB0B);
    address internal griefer = address(0xBAD);
    address internal resolverAddr = address(0xBEEF);
    address internal closer = address(0xC105E);

    function setUp() public {
        vm.warp(T0);
        factory = new ParamutuelFactoryV3(treasury, 100, 0, 0);
        token = new MockERC20();
        token.mint(alice, type(uint128).max);
        token.mint(bob, type(uint128).max);
        token.mint(griefer, type(uint128).max);
    }

    function _labels(uint256 n) internal pure returns (string[] memory labels) {
        labels = new string[](n);
        for (uint256 i; i < n; i++) {
            labels[i] = "o";
        }
    }

    function _enumerated(uint256 numOptions, ParamutuelWagerV3.PayoffPolicy policy, uint256 param)
        internal
        returns (ParamutuelWagerV3)
    {
        return ParamutuelWagerV3(
            factory.createEnumeratedWager(
                address(token),
                "Q?",
                _labels(numOptions),
                policy,
                param,
                CLOSE,
                WINDOW,
                resolverAddr,
                closer,
                closer,
                new address[](0),
                new uint16[](0)
            )
        );
    }

    function _freeform() internal returns (ParamutuelWagerV3) {
        return ParamutuelWagerV3(
            factory.createFreeformWager(
                address(token), "Q?", CLOSE, WINDOW, resolverAddr, closer, closer, new address[](0), new uint16[](0)
            )
        );
    }

    /// @dev Fills `count` distinct multi-bit masks as a griefer would: 1 wei each, in batches, with
    ///      as many bits set as possible so that any per-bit cost in `resolve` is maximised.
    function _griefMasks(ParamutuelWagerV3 w, uint256 numOptions, uint256 count) internal {
        uint256 full = (uint256(1) << numOptions) - 1;
        vm.startPrank(griefer);
        token.approve(address(w), type(uint256).max);
        uint256 placed;
        uint256 seq = 3; // xor-ing `full` with small values >= 3 never leaves a single-bit or zero mask
        while (placed < count) {
            uint256 k = count - placed < 64 ? count - placed : 64;
            uint256[] memory masks = new uint256[](k);
            uint256[] memory amounts = new uint256[](k);
            for (uint256 i; i < k; i++) {
                masks[i] = full ^ seq;
                amounts[i] = 1;
                seq++;
            }
            w.placeBets(masks, amounts);
            placed += k;
        }
        vm.stopPrank();
    }

    /// @dev Resolve exactly as a real transaction would: all wager storage cold.
    function _coldResolveGas(ParamutuelWagerV3 w, uint256 winningMask) internal returns (uint256 used) {
        vm.warp(CLOSE);
        VM_COOL.cool(address(w));
        vm.prank(resolverAddr);
        uint256 before = gasleft();
        w.resolve(winningMask);
        used = before - gasleft();
        emit log_named_uint("cold resolve gas", used);
    }

    // ------------------------------------------------------------------
    // C1: griefing must not be able to push resolve past the tx gas cap
    // ------------------------------------------------------------------

    function _assertResolveFitsTx(ParamutuelWagerV3.PayoffPolicy policy, uint256 param) internal {
        uint256 numOptions = 255;
        uint256 full = (uint256(1) << numOptions) - 1;
        ParamutuelWagerV3 w = _enumerated(numOptions, policy, param);
        _griefMasks(w, numOptions, 1024);
        // An honest stake on the exact winning set keeps units > 0 under every policy.
        vm.startPrank(griefer);
        vm.expectRevert(ParamutuelWagerV3.TooManyDistinctTickets.selector);
        w.placeBet(full, 1); // the multi-bit cap is full
        vm.stopPrank();
        assertLt(_coldResolveGas(w, full ^ 3), TX_GAS_CAP - TX_OVERHEAD_MARGIN, "resolve must fit one transaction");
    }

    function test_C1_coldResolve_weightedOverlap_fitsTxGasCap() public {
        _assertResolveFitsTx(ParamutuelWagerV3.PayoffPolicy.WEIGHTED_OVERLAP, 0);
    }

    function test_C1_coldResolve_atLeastK_fitsTxGasCap() public {
        _assertResolveFitsTx(ParamutuelWagerV3.PayoffPolicy.AT_LEAST_K, 1);
    }

    function test_C1_coldResolve_anyOf_fitsTxGasCap() public {
        _assertResolveFitsTx(ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
    }

    function test_C1_coldResolve_exactSet_fitsTxGasCap() public {
        _assertResolveFitsTx(ParamutuelWagerV3.PayoffPolicy.EXACT_SET, 0);
    }

    /// @dev The largest `_usedMasks` can ever get: 1024 multi-bit masks plus every single-outcome
    ///      ticket, which the C3 fix exempts from the cap.
    function test_C1_coldResolve_absoluteWorstCase_fitsTxGasCap() public {
        uint256 numOptions = 255;
        uint256 full = (uint256(1) << numOptions) - 1;
        ParamutuelWagerV3 w = _enumerated(numOptions, ParamutuelWagerV3.PayoffPolicy.WEIGHTED_OVERLAP, 0);
        _griefMasks(w, numOptions, 1024);
        vm.startPrank(griefer);
        for (uint256 i; i < numOptions; i++) {
            w.placeBet(uint256(1) << i, 1);
        }
        vm.stopPrank();
        assertEq(w.usedMasksCount(), 1024 + numOptions);
        assertLt(_coldResolveGas(w, full), TX_GAS_CAP - TX_OVERHEAD_MARGIN);
    }

    // ------------------------------------------------------------------
    // C2: the freeform answer space cannot be exhausted
    // ------------------------------------------------------------------

    /// @dev Inverts ADR-0019's `test_freeform_answerSpaceExhaustion_griefingBoundary`: more dust
    ///      answers than the old cap, and an honest bettor can still open the correct answer.
    function test_C2_freeform_answerSpaceCannotBeExhausted_resolveAndClaimStayFlat() public {
        ParamutuelWagerV3 w = _freeform();
        vm.startPrank(griefer);
        token.approve(address(w), type(uint256).max);
        for (uint256 i; i < 1100; i++) {
            w.placeBet(vm.toString(i), 1);
        }
        vm.stopPrank();
        assertEq(w.usedAnswerIdsCount(), 1100);

        vm.startPrank(alice);
        token.approve(address(w), type(uint256).max);
        w.placeBet("the real answer", 1e18);
        vm.stopPrank();

        vm.warp(CLOSE);
        VM_COOL.cool(address(w));
        vm.prank(resolverAddr);
        uint256 before = gasleft();
        w.resolve("the real answer");
        // O(1): nothing iterates the answer list, which is why no cap is needed.
        assertLt(before - gasleft(), 250_000, "freeform resolve must stay flat");

        vm.prank(alice);
        before = gasleft();
        uint256 paid = w.claim();
        assertLt(before - gasleft(), 150_000, "freeform claim must stay flat");
        assertGt(paid, 0.98e18);
    }

    // ------------------------------------------------------------------
    // C3: single-outcome tickets can never be locked out
    // ------------------------------------------------------------------

    function test_C3_singleOutcomeTicket_exemptFromMultiBitCap() public {
        uint256 numOptions = 20;
        ParamutuelWagerV3 w = _enumerated(numOptions, ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
        _griefMasks(w, numOptions, 1024);
        vm.startPrank(alice);
        token.approve(address(w), type(uint256).max);
        // A new multi-bit ticket is refused once the griefer has filled the cap...
        vm.expectRevert(ParamutuelWagerV3.TooManyDistinctTickets.selector);
        w.placeBet(3, 1e18); // mask {0,1}
        // ...but the basic bet on any single outcome always works.
        w.placeBet(uint256(1) << 19, 1e18);
        vm.stopPrank();
        assertEq(w.ticketPoolByMask(uint256(1) << 19), 1e18);
    }

    // ------------------------------------------------------------------
    // C4: arbitrary-supply collateral must not be able to lock funds
    // ------------------------------------------------------------------

    function _bigStake(uint256 stakeA, uint256 stakeB) internal returns (ParamutuelWagerV3 w, MockERC20 big) {
        big = new MockERC20();
        big.mint(alice, stakeA);
        big.mint(bob, stakeB);
        w = ParamutuelWagerV3(
            factory.createFreeformWager(
                address(big), "Q?", CLOSE, WINDOW, resolverAddr, closer, closer, new address[](0), new uint16[](0)
            )
        );
        vm.startPrank(alice);
        big.approve(address(w), stakeA);
        w.placeBet("win", stakeA);
        vm.stopPrank();
        vm.startPrank(bob);
        big.approve(address(w), stakeB);
        w.placeBet("lose", stakeB);
        vm.stopPrank();
    }

    /// @dev Before the fix `stake * netPot` overflowed here and `claim` reverted forever.
    function test_C4_claim_doesNotOverflow_onHighSupplyToken() public {
        uint256 stake = uint256(1) << 130;
        (ParamutuelWagerV3 w, MockERC20 big) = _bigStake(stake, stake);
        vm.warp(CLOSE);
        vm.prank(resolverAddr);
        w.resolve("win");
        vm.prank(alice);
        uint256 paid = w.claim();
        uint256 pot = 2 * stake;
        assertEq(paid, pot - (pot * 100) / 10_000, "winner takes the whole net pot");
        assertEq(big.balanceOf(alice), paid);
    }

    /// @dev Before the fix `totalPot * totalFeeBps` overflowed, so resolve, retract and expire ALL
    ///      reverted and every token was stuck permanently.
    function test_C4_terminalPaths_doNotOverflow_atExtremePot() public {
        uint256 stake = type(uint256).max / 4;
        (ParamutuelWagerV3 w, MockERC20 big) = _bigStake(stake, stake);
        vm.warp(CLOSE + WINDOW + 1);
        w.expire();
        vm.prank(alice);
        uint256 paid = w.claim();
        assertGt(paid, 0);
        assertEq(big.balanceOf(alice), paid);
        // Equal stakes, so each refund is floor(netPot / 2); `pot / 100` cannot overflow here.
        uint256 pot = 2 * stake;
        assertEq(paid, (pot - pot / 100) / 2, "refund is half the net pot");
    }

    function test_C4_retract_refund_doesNotOverflow() public {
        uint256 stake = uint256(1) << 200;
        (ParamutuelWagerV3 w,) = _bigStake(stake, stake);
        vm.warp(CLOSE);
        vm.prank(resolverAddr);
        w.retract();
        uint256 pot = 2 * stake;
        vm.prank(bob);
        assertEq(w.claim(), (pot - pot / 100) / 2, "refund is half the net pot");
    }

    // ------------------------------------------------------------------
    // C7: a zero payout reverts on every path, never transfers 0
    // ------------------------------------------------------------------

    function _hundredPercentFeeFreeform() internal returns (ParamutuelWagerV3 w) {
        address[] memory recipients = new address[](1);
        uint16[] memory bps = new uint16[](1);
        recipients[0] = address(0xCAFE);
        bps[0] = 9900; // plus the 1% protocol fee = 100%
        w = ParamutuelWagerV3(
            factory.createFreeformWager(address(token), "Q?", CLOSE, WINDOW, resolverAddr, closer, closer, recipients, bps)
        );
        vm.startPrank(alice);
        token.approve(address(w), type(uint256).max);
        w.placeBet("x", 1e18);
        vm.stopPrank();
    }

    function test_C7_zeroPayout_freeformResolved_reverts() public {
        ParamutuelWagerV3 w = _hundredPercentFeeFreeform();
        vm.warp(CLOSE);
        vm.prank(resolverAddr);
        w.resolve("x");
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();
        assertFalse(w.hasClaimed(alice));
    }

    function test_C7_zeroPayout_retracted_reverts() public {
        ParamutuelWagerV3 w = _hundredPercentFeeFreeform();
        vm.warp(CLOSE);
        vm.prank(resolverAddr);
        w.retract();
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();
    }

    // ------------------------------------------------------------------
    // C8: closeResolutionWindow is a no-op once finalised
    // ------------------------------------------------------------------

    function test_C8_closeResolutionWindow_afterFinalisation_isSilentNoOp() public {
        ParamutuelWagerV3 w = _enumerated(2, ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0);
        vm.startPrank(alice);
        token.approve(address(w), type(uint256).max);
        w.placeBet(1, 1e18);
        vm.stopPrank();
        vm.warp(CLOSE);
        vm.prank(resolverAddr);
        w.resolve(1);

        vm.recordLogs();
        vm.prank(closer);
        w.closeResolutionWindow();
        assertEq(vm.getRecordedLogs().length, 0, "no event on a finalised wager");
        assertFalse(w.resolutionWindowClosedByAuthority(), "flag must not change after finalisation");
    }

    // ------------------------------------------------------------------
    // C9: extra fee recipients are capped
    // ------------------------------------------------------------------

    function _withRecipients(uint256 n) internal returns (address) {
        address[] memory recipients = new address[](n);
        uint16[] memory bps = new uint16[](n);
        for (uint256 i; i < n; i++) {
            recipients[i] = address(uint160(0x10000 + i));
            bps[i] = 1;
        }
        return factory.createFreeformWager(address(token), "Q?", CLOSE, WINDOW, resolverAddr, closer, closer, recipients, bps);
    }

    function test_C9_extraFeeRecipients_capped_inBothCreatePaths() public {
        assertTrue(_withRecipients(32) != address(0));
        vm.expectRevert(ParamutuelFactoryV3.BadFeeConfig.selector);
        _withRecipients(33);

        address[] memory recipients = new address[](33);
        uint16[] memory bps = new uint16[](33);
        for (uint256 i; i < 33; i++) {
            recipients[i] = address(uint160(0x10000 + i));
            bps[i] = 1;
        }
        vm.expectRevert(ParamutuelFactoryV3.BadFeeConfig.selector);
        factory.createEnumeratedWager(
            address(token),
            "Q?",
            _labels(2),
            ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER,
            0,
            CLOSE,
            WINDOW,
            resolverAddr,
            closer,
            closer,
            recipients,
            bps
        );
    }

    // ------------------------------------------------------------------
    // C3: minNewTicketStake prices griefing by dust tickets
    // ------------------------------------------------------------------

    uint256 internal constant MIN_STAKE = 5e6;

    function _enumeratedWithMin(uint256[] memory seedMasks, uint256[] memory seedAmounts) internal returns (ParamutuelWagerV3) {
        return ParamutuelWagerV3(
            factory.createEnumeratedWager(
                address(token),
                "Q?",
                _labels(12),
                ParamutuelWagerV3.PayoffPolicy.ANY_OF,
                0,
                CLOSE,
                WINDOW,
                resolverAddr,
                closer,
                closer,
                new address[](0),
                new uint16[](0),
                seedMasks,
                seedAmounts,
                MIN_STAKE
            )
        );
    }

    function test_C3_minNewTicketStake_gatesOnlyNewEnumeratedTickets() public {
        ParamutuelWagerV3 w = _enumeratedWithMin(new uint256[](0), new uint256[](0));
        assertEq(w.minNewTicketStake(), MIN_STAKE);
        vm.startPrank(alice);
        token.approve(address(w), type(uint256).max);

        vm.expectRevert(ParamutuelWagerV3.NewTicketStakeTooLow.selector);
        w.placeBet(3, MIN_STAKE - 1);
        w.placeBet(3, MIN_STAKE);
        // Re-betting an open ticket is never restricted; only opening one is.
        w.placeBet(3, 1);
        assertEq(w.ticketPoolByMask(3), MIN_STAKE + 1);

        uint256[] memory masks = new uint256[](2);
        uint256[] memory amounts = new uint256[](2);
        masks[0] = 5;
        masks[1] = 6;
        amounts[0] = MIN_STAKE;
        amounts[1] = MIN_STAKE - 1;
        vm.expectRevert(ParamutuelWagerV3.NewTicketStakeTooLow.selector);
        w.placeBets(masks, amounts);
        vm.stopPrank();
    }

    function test_C3_minNewTicketStake_appliesToSeeds() public {
        uint256[] memory masks = new uint256[](1);
        uint256[] memory amounts = new uint256[](1);
        masks[0] = 1;
        amounts[0] = MIN_STAKE - 1;
        vm.startPrank(alice);
        token.approve(address(factory), type(uint256).max);
        vm.expectRevert(ParamutuelWagerV3.NewTicketStakeTooLow.selector);
        _enumeratedWithMin(masks, amounts);

        amounts[0] = MIN_STAKE;
        ParamutuelWagerV3 w = _enumeratedWithMin(masks, amounts);
        vm.stopPrank();
        assertEq(w.ticketPoolByMask(1), MIN_STAKE);
    }

    function test_C3_minNewTicketStake_gatesNewFreeformAnswers() public {
        ParamutuelWagerV3 w = ParamutuelWagerV3(
            factory.createFreeformWager(
                address(token), "Q?", CLOSE, WINDOW, resolverAddr, closer, closer, new address[](0), new uint16[](0), MIN_STAKE
            )
        );
        assertEq(w.minNewTicketStake(), MIN_STAKE);
        vm.startPrank(alice);
        token.approve(address(w), type(uint256).max);
        vm.expectRevert(ParamutuelWagerV3.NewTicketStakeTooLow.selector);
        w.placeBet("dust", MIN_STAKE - 1);
        w.placeBet("real", MIN_STAKE);
        w.placeBet("real", 1);
        vm.stopPrank();
        assertEq(w.usedAnswerIdsCount(), 1);
    }

    /// @dev Additivity: every signature the deployed factory exposes still means "no minimum".
    function test_C3_originalOverloads_haveNoMinimum() public {
        assertEq(_enumerated(3, ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0).minNewTicketStake(), 0);
        assertEq(_freeform().minNewTicketStake(), 0);
    }

    // ------------------------------------------------------------------
    // C5: every distinct answer's text is recoverable from one event
    // ------------------------------------------------------------------

    event FreeformAnswerRevealedV3(bytes32 indexed answerId, string answer);
    event BetPlacedV3Freeform(address indexed bettor, bytes32 indexed answerId, uint256 amount);

    function test_C5_answerRevealed_onceWithExactBytes_beforeBetEvent() public {
        ParamutuelWagerV3 w = _freeform();
        string memory answer = unicode"  Caf\u00e9 \"au lait\"  ";
        bytes32 id = keccak256(abi.encodePacked(bytes1(0x03), bytes(answer)));
        vm.startPrank(alice);
        token.approve(address(w), type(uint256).max);

        vm.expectEmit(true, false, false, true, address(w));
        emit FreeformAnswerRevealedV3(id, answer);
        vm.expectEmit(true, true, false, true, address(w));
        emit BetPlacedV3Freeform(alice, id, 7);
        w.placeBet(answer, 7);

        vm.recordLogs();
        w.placeBet(answer, 9);
        vm.stopPrank();
        bytes32 revealTopic = keccak256("FreeformAnswerRevealedV3(bytes32,string)");
        Vm.Log[] memory logs = vm.getRecordedLogs();
        for (uint256 i; i < logs.length; i++) {
            assertTrue(logs[i].topics[0] != revealTopic, "second stake must not re-reveal");
        }
    }

    // ------------------------------------------------------------------
    // C6: removing the write-only per-user answer list saved real gas
    // ------------------------------------------------------------------

    /// @dev A second new answer from the same bettor used to spend about 27k on an array nothing
    ///      read. Bound chosen to fail if such a list ever returns.
    function test_C6_newAnswerBet_gasBound() public {
        ParamutuelWagerV3 w = _freeform();
        vm.startPrank(alice);
        token.approve(address(w), type(uint256).max);
        w.placeBet("warmup", 1);
        VM_COOL.cool(address(w));
        uint256 before = gasleft();
        w.placeBet("second answer", 1);
        uint256 used = before - gasleft();
        vm.stopPrank();
        emit log_named_uint("new-answer placeBet gas", used);
        assertLt(used, 95_000);
    }

    // ------------------------------------------------------------------
    // Guard sites the coverage report showed had no test of their own
    // ------------------------------------------------------------------

    function test_bettingEntryPoints_afterFinalisation_revertNotOpen() public {
        ParamutuelWagerV3 enumerated = _enumerated(2, ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
        ParamutuelWagerV3 free = _freeform();
        vm.warp(CLOSE);
        vm.startPrank(resolverAddr);
        enumerated.retract();
        free.retract();
        vm.stopPrank();

        uint256[] memory masks = new uint256[](1);
        uint256[] memory amounts = new uint256[](1);
        masks[0] = 1;
        amounts[0] = 1;
        vm.startPrank(alice);
        vm.expectRevert(ParamutuelWagerV3.NotOpen.selector);
        enumerated.placeBets(masks, amounts);
        vm.expectRevert(ParamutuelWagerV3.NotOpen.selector);
        free.placeBet("x", 1);
        vm.stopPrank();
    }

    function test_usedAnswerId_readsBackInFirstStakeOrder() public {
        ParamutuelWagerV3 w = _freeform();
        vm.startPrank(alice);
        token.approve(address(w), type(uint256).max);
        w.placeBet("first", 1);
        w.placeBet("second", 1);
        w.placeBet("first", 1);
        vm.stopPrank();
        assertEq(w.usedAnswerIdsCount(), 2);
        assertEq(w.usedAnswerId(0), keccak256(abi.encodePacked(bytes1(0x03), "first")));
        assertEq(w.usedAnswerId(1), keccak256(abi.encodePacked(bytes1(0x03), "second")));
    }

    function test_resolve_rejectsWinningMaskAboveOptionRange() public {
        ParamutuelWagerV3 w = _enumerated(2, ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
        vm.startPrank(alice);
        token.approve(address(w), type(uint256).max);
        w.placeBet(1, 1);
        vm.stopPrank();
        vm.warp(CLOSE);
        vm.prank(resolverAddr);
        vm.expectRevert(ParamutuelWagerV3.InvalidWinningMask.selector);
        w.resolve(4);
    }

    /// @dev Exactly at `close + window` only the resolver may act; one second later only `expire`.
    ///      No gap and no overlap, even with no time bound on betting.
    function test_resolutionWindow_hasNoGapOrOverlap_afterAuthorityClose() public {
        ParamutuelWagerV3 w = ParamutuelWagerV3(
            factory.createFreeformWager(
                address(token), "Q?", 0, WINDOW, resolverAddr, closer, closer, new address[](0), new uint16[](0)
            )
        );
        vm.warp(T0 + 100);
        vm.prank(closer);
        w.closeBetting();

        vm.warp(T0 + 100 + WINDOW);
        vm.expectRevert(ParamutuelWagerV3.ResolutionWindowOver.selector);
        w.expire();

        vm.warp(T0 + 100 + WINDOW + 1);
        vm.prank(resolverAddr);
        vm.expectRevert(ParamutuelWagerV3.ResolutionWindowOver.selector);
        w.retract();
        w.expire();
        assertEq(uint256(w.state()), uint256(ParamutuelWagerV3.State.Retracted));
    }

    // ------------------------------------------------------------------
    // C9 / C10: constants and bit/mul helpers
    // ------------------------------------------------------------------

    function test_C9_recipientCapConstant() public view {
        assertEq(factory.MAX_EXTRA_FEE_RECIPIENTS(), 32);
    }

    function test_popcount_matchesNaive_fuzz(uint256 x) public {
        MathHarness h = new MathHarness();
        x = x >> 1; // masks are at most 255 bits wide
        uint256 naive;
        for (uint256 y = x; y != 0; y &= y - 1) {
            naive++;
        }
        assertEq(h.popcount(x), naive);
        assertEq(h.isSingleBit(x), naive == 1);
    }

    function test_popcount_boundaries() public {
        MathHarness h = new MathHarness();
        assertEq(h.popcount(0), 0);
        assertEq(h.popcount(1), 1);
        assertEq(h.popcount(uint256(1) << 254), 1);
        assertEq(h.popcount(type(uint256).max >> 1), 255);
        assertFalse(h.isSingleBit(0));
        assertTrue(h.isSingleBit(uint256(1) << 254));
        assertFalse(h.isSingleBit(3));
    }

    /// @dev Exact agreement with plain arithmetic where plain arithmetic cannot overflow.
    function test_mulDiv_matchesPlainMath_fuzz(uint128 a, uint128 b, uint256 c) public {
        vm.assume(c != 0);
        MathHarness h = new MathHarness();
        assertEq(h.mulDiv(a, b, c), uint256(a) * uint256(b) / c);
    }

    /// @dev Above 256 bits, verify the defining property directly: `r` is the quotient iff
    ///      `r * c + (a * b mod c)` equals the 512-bit product, checked modulo two moduli.
    function test_mulDiv_fullPrecision_fuzz(uint256 a, uint256 b, uint256 c) public {
        vm.assume(c != 0);
        // Keep the quotient in range: payouts have amount <= total, i.e. a <= c.
        a = bound(a, 0, c);
        MathHarness h = new MathHarness();
        uint256 r = h.mulDiv(a, b, c);
        uint256 rem = mulmod(a, b, c);
        assertLe(r, b, "a <= c implies the quotient is at most b");
        unchecked {
            assertEq(r * c + rem, a * b, "exact modulo 2^256");
        }
        assertEq(addmod(mulmod(r, c, type(uint256).max), rem, type(uint256).max), mulmod(a, b, type(uint256).max), "exact modulo 2^256-1");
    }

    function test_mulDiv_reverts_onZeroDenominatorOrOverflow() public {
        MathHarness h = new MathHarness();
        vm.expectRevert(FullMath.MulDivOverflow.selector);
        h.mulDiv(1, 1, 0);
        vm.expectRevert(FullMath.MulDivOverflow.selector);
        h.mulDiv(type(uint256).max, type(uint256).max, 1);
        assertEq(h.mulDiv(type(uint256).max, type(uint256).max, type(uint256).max), type(uint256).max);
    }

    // ------------------------------------------------------------------
    // ADR-0018: token-class boundary pinned as executable fact
    // ------------------------------------------------------------------

    /// @dev Fails SAFE: the bet cannot be placed, so nothing is ever at risk.
    function test_ADR0018_noReturnToken_placeBetReverts_failsSafe() public {
        NoReturnToken usdtLike = new NoReturnToken();
        usdtLike.mint(alice, 1e18);
        ParamutuelWagerV3 w = ParamutuelWagerV3(
            factory.createFreeformWager(
                address(usdtLike), "Q?", CLOSE, WINDOW, resolverAddr, closer, closer, new address[](0), new uint16[](0)
            )
        );
        vm.startPrank(alice);
        usdtLike.approve(address(w), 1e18);
        vm.expectRevert();
        w.placeBet("x", 1e18);
        vm.stopPrank();
        assertEq(usdtLike.balanceOf(alice), 1e18, "nothing moved");
    }

    // ------------------------------------------------------------------
    // ADR-0023: a pull that delivers less than it records reverts, so the
    // fee-on-transfer class fails safe like the no-return class above.
    // ------------------------------------------------------------------

    function _yesNo() internal pure returns (string[] memory outs) {
        outs = new string[](2);
        outs[0] = "yes";
        outs[1] = "no";
    }

    function _enumerated(address collateral) internal returns (ParamutuelWagerV3) {
        return ParamutuelWagerV3(
            factory.createEnumeratedWager(
                collateral,
                "Q?",
                _yesNo(),
                ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER,
                0,
                CLOSE,
                WINDOW,
                resolverAddr,
                closer,
                closer,
                new address[](0),
                new uint16[](0)
            )
        );
    }

    function test_ADR0023_feeOnTransfer_enumeratedPlaceBet_revertsShortfall() public {
        FeeOnTransferToken fot = new FeeOnTransferToken();
        fot.mint(alice, 1e18);
        ParamutuelWagerV3 w = _enumerated(address(fot));
        vm.startPrank(alice);
        fot.approve(address(w), 1e18);
        vm.expectRevert(ParamutuelWagerV3.CollateralShortfall.selector);
        w.placeBet(uint256(1), 1e18);
        vm.stopPrank();
        assertEq(fot.balanceOf(alice), 1e18, "nothing moved");
        assertEq(w.totalPot(), 0, "nothing recorded");
    }

    function test_ADR0023_feeOnTransfer_placeBets_revertsShortfall() public {
        FeeOnTransferToken fot = new FeeOnTransferToken();
        fot.mint(alice, 2e18);
        ParamutuelWagerV3 w = _enumerated(address(fot));
        uint256[] memory masks = new uint256[](2);
        masks[0] = 1;
        masks[1] = 2;
        uint256[] memory amounts = new uint256[](2);
        amounts[0] = 1e18;
        amounts[1] = 1e18;
        vm.startPrank(alice);
        fot.approve(address(w), 2e18);
        vm.expectRevert(ParamutuelWagerV3.CollateralShortfall.selector);
        w.placeBets(masks, amounts);
        vm.stopPrank();
        assertEq(fot.balanceOf(alice), 2e18, "nothing moved");
        assertEq(w.totalPot(), 0, "nothing recorded");
    }

    function test_ADR0023_feeOnTransfer_freeformPlaceBet_revertsShortfall() public {
        FeeOnTransferToken fot = new FeeOnTransferToken();
        fot.mint(alice, 1e18);
        ParamutuelWagerV3 w = ParamutuelWagerV3(
            factory.createFreeformWager(
                address(fot), "Q?", CLOSE, WINDOW, resolverAddr, closer, closer, new address[](0), new uint16[](0)
            )
        );
        vm.startPrank(alice);
        fot.approve(address(w), 1e18);
        vm.expectRevert(ParamutuelWagerV3.CollateralShortfall.selector);
        w.placeBet("x", 1e18);
        vm.stopPrank();
        assertEq(fot.balanceOf(alice), 1e18, "nothing moved");
        assertEq(w.totalPot(), 0, "nothing recorded");
    }

    /// @dev The factory pulls the seed total straight into the new wager, so the factory is the one
    ///      that must check it. The whole creation reverts: no wager, no stake, no tokens moved.
    function test_ADR0023_feeOnTransfer_seededCreate_revertsShortfall() public {
        FeeOnTransferToken fot = new FeeOnTransferToken();
        fot.mint(alice, 1e18);
        uint256[] memory masks = new uint256[](1);
        masks[0] = 1;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = 1e18;
        uint256 before = factory.wagersCount();
        vm.startPrank(alice);
        fot.approve(address(factory), 1e18);
        vm.expectRevert(ParamutuelFactoryV3.CollateralShortfall.selector);
        factory.createEnumeratedWager(
            address(fot),
            "Q?",
            _yesNo(),
            ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER,
            0,
            CLOSE,
            WINDOW,
            resolverAddr,
            closer,
            closer,
            new address[](0),
            new uint16[](0),
            masks,
            amounts
        );
        vm.stopPrank();
        assertEq(fot.balanceOf(alice), 1e18, "nothing moved");
        assertEq(factory.wagersCount(), before, "no wager created");
    }

    /// @dev A fee switched on after the bets refuses new bets, and the wager stays solvent: a fee
    ///      on the way out lowers what each recipient receives, not what the wager holds against its
    ///      records. Every withdrawal succeeds and the wager ends empty. Figures: pot 2e18, 1%
    ///      protocol fee 0.02e18, so Alice (sole winner) is owed 1.98e18 and receives 99% of it.
    function test_ADR0023_feeSwitchedOnAfterBets_refusesNewBets_existingWagerStaysSolvent() public {
        AdjustableTransferToken tok = new AdjustableTransferToken();
        tok.mint(alice, 1e18);
        tok.mint(bob, 2e18);
        ParamutuelWagerV3 w = _enumerated(address(tok));
        vm.startPrank(alice);
        tok.approve(address(w), 1e18);
        w.placeBet(uint256(1), 1e18);
        vm.stopPrank();
        vm.startPrank(bob);
        tok.approve(address(w), 2e18);
        w.placeBet(uint256(2), 1e18);
        vm.stopPrank();

        tok.setDeliveredBps(9_900);
        vm.prank(bob);
        vm.expectRevert(ParamutuelWagerV3.CollateralShortfall.selector);
        w.placeBet(uint256(2), 1e18);

        vm.warp(CLOSE);
        vm.prank(resolverAddr);
        w.resolve(uint256(1));
        vm.prank(alice);
        assertEq(w.claim(), 1.98e18);
        vm.prank(treasury);
        assertEq(w.withdrawFees(), 0.02e18);
        assertEq(tok.balanceOf(address(w)), 0, "every obligation paid from what the wager held");
        assertEq(tok.balanceOf(alice), 1.9602e18, "the token's fee comes out of the payout");
    }

    /// @dev Only a shortfall is refused (ADR-0023 decision point). A token that delivers 1% more is
    ///      accepted, the bet is recorded at the requested amount, every withdrawal succeeds, and the
    ///      excess stays in the wager, which never pays it out.
    function test_ADR0023_tokenDeliveringMore_isAccepted_atRequestedAmount() public {
        AdjustableTransferToken tok = new AdjustableTransferToken();
        tok.setDeliveredBps(10_100);
        tok.mint(alice, 1e18);
        tok.mint(bob, 1e18);
        ParamutuelWagerV3 w = _enumerated(address(tok));
        vm.startPrank(alice);
        tok.approve(address(w), 1e18);
        w.placeBet(uint256(1), 1e18);
        vm.stopPrank();
        vm.startPrank(bob);
        tok.approve(address(w), 1e18);
        w.placeBet(uint256(2), 1e18);
        vm.stopPrank();
        assertEq(w.totalPot(), 2e18, "recorded at the requested amount");
        assertEq(tok.balanceOf(address(w)), 2.02e18);

        vm.warp(CLOSE);
        vm.prank(resolverAddr);
        w.resolve(uint256(1));
        vm.prank(alice);
        assertEq(w.claim(), 1.98e18);
        vm.prank(treasury);
        assertEq(w.withdrawFees(), 0.02e18);
        assertEq(tok.balanceOf(address(w)), 0.02e18, "the excess stays, owed to nobody");
    }
}
