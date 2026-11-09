// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import {ParamutuelFactoryV3} from "../src/ParamutuelFactoryV3.sol";
import {ParamutuelWagerV3} from "../src/ParamutuelWagerV3.sol";
import {BitMath} from "../src/utils/BitMath.sol";
import {FullMath} from "../src/utils/FullMath.sol";
import {MockERC20, NoReturnToken, FeeOnTransferToken} from "./utils/MockTokens.sol";

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

    /// @dev Fails UNSAFE, by documented design: `totalPot` counts the requested amount while custody
    ///      holds 1% less, so whoever withdraws last cannot be paid (here the fee recipient; the next
    ///      test makes it a winner). This is why README and surfaces say
    ///      "standard ERC-20" and why curated surfaces warn. If this test ever stops failing the
    ///      second claim, update ADR-0018's scope statement.
    function test_ADR0018_feeOnTransferToken_breaksSolvency_failsUnsafe() public {
        FeeOnTransferToken fot = new FeeOnTransferToken();
        fot.mint(alice, 1e18);
        fot.mint(bob, 1e18);
        ParamutuelWagerV3 w = ParamutuelWagerV3(
            factory.createFreeformWager(
                address(fot), "Q?", CLOSE, WINDOW, resolverAddr, closer, closer, new address[](0), new uint16[](0)
            )
        );
        vm.startPrank(alice);
        fot.approve(address(w), 1e18);
        w.placeBet("x", 1e18);
        vm.stopPrank();
        vm.startPrank(bob);
        fot.approve(address(w), 1e18);
        w.placeBet("x", 1e18);
        vm.stopPrank();
        assertEq(w.totalPot(), 2e18);
        assertEq(fot.balanceOf(address(w)), 1.98e18, "custody is short of the credited pot");

        vm.warp(CLOSE);
        vm.prank(resolverAddr);
        w.resolve("x");
        vm.prank(alice);
        w.claim();
        // Each winner is owed 0.99e18 and custody started at 1.98e18, so the second claim only just
        // clears; the 1% protocol fee is what cannot be paid.
        vm.prank(bob);
        w.claim();
        vm.prank(treasury);
        vm.expectRevert();
        w.withdrawFees();
    }

    /// @dev Pins the README's fee-on-transfer description from the other side. The shortfall falls
    ///      on whoever withdraws last, so a winner can be the one left unpaid, and gets nothing
    ///      rather than a partial payment. Topping the balance back up lets the same claim through.
    ///      Every figure comes from the token's 1% skim on each transfer and the factory's 100 bps.
    function test_ADR0018_feeOnTransferToken_lastWinnerUnpaid_untilToppedUp() public {
        FeeOnTransferToken fot = new FeeOnTransferToken();
        fot.mint(alice, 1e18);
        fot.mint(bob, 1e18);
        ParamutuelWagerV3 w = ParamutuelWagerV3(
            factory.createFreeformWager(
                address(fot), "Q?", CLOSE, WINDOW, resolverAddr, closer, closer, new address[](0), new uint16[](0)
            )
        );
        vm.startPrank(alice);
        fot.approve(address(w), 1e18);
        w.placeBet("yes", 1e18);
        vm.stopPrank();
        vm.startPrank(bob);
        fot.approve(address(w), 1e18);
        w.placeBet("no", 1e18);
        vm.stopPrank();

        vm.warp(CLOSE);
        vm.prank(resolverAddr);
        w.resolve("yes");

        // Credited pot 2e18, custody 1.98e18. The treasury is owed 1% of 2e18 and withdraws first.
        vm.prank(treasury);
        assertEq(w.withdrawFees(), 0.02e18);
        assertEq(fot.balanceOf(address(w)), 1.96e18);

        // Alice alone won and is owed the 1.98e18 net pot. The wager holds 1.96e18, so the claim
        // reverts whole: she receives nothing, not the 1.96e18 that is there.
        vm.prank(alice);
        vm.expectRevert();
        w.claim();
        assertEq(fot.balanceOf(alice), 0, "no partial payment");

        // Bob tops the wager up by 0.03e18, of which the token delivers 0.0297e18, which covers the
        // 0.02e18 gap. Alice's claim now goes through, and she receives it less the token's 1%.
        fot.mint(bob, 0.03e18);
        vm.prank(bob);
        fot.transfer(address(w), 0.03e18);
        vm.prank(alice);
        assertEq(w.claim(), 1.98e18, "paid in full by the wager's records");
        assertEq(fot.balanceOf(alice), 1.9602e18, "less the token's own fee on the way out");
    }
}
