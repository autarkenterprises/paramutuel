// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import {ParamutuelFactoryV3} from "../src/ParamutuelFactoryV3.sol";
import {ParamutuelWagerV3} from "../src/ParamutuelWagerV3.sol";

/// @dev Minimal ERC20 mock — exact copy of the shape legacy V2 tests used.
///      V3 behaviour under non-trivial collateral (rebasing, fee-on-transfer) is
///      explicitly **out of scope** of this protocol (see ADR-0010 §Assumptions).
contract MockERC20V3Enum {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 a = allowance[from][msg.sender];
        require(a >= amount, "ALLOWANCE");
        allowance[from][msg.sender] = a - amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

/// @notice Behavioural parity suite for ADR-0010 V3 enumerated wagers.
///         Ports the pre-migration `ParamutuelV2.t.sol` and
///         `ParamutuelV2Extensive.t.sol` coverage onto the unified V3 factory
///         (`createEnumeratedWager`), exercising every payoff policy and the
///         full wager lifecycle (place, resolve, claim, retract, expire, fees,
///         authority roles, batch bets, seeds).
contract ParamutuelV3EnumeratedTest is Test {
    ParamutuelFactoryV3 factory;
    MockERC20V3Enum token;

    address treasury = address(0x1000);
    address proposer = address(0x2000);
    address alice = address(0x3000);
    address bob = address(0x4000);
    address carol = address(0x5000);
    address dave = address(0x6000);

    uint64 minBettingWindow = 1 hours;
    uint64 minResolutionWindow = 1 hours;

    /// @dev Single-bit outcome masks; V3 packs outcome membership as a uint256 bitmask.
    uint256 constant M0 = 1;
    uint256 constant M1 = 2;
    uint256 constant M2 = 4;

    function setUp() public {
        vm.warp(1000);
        factory = new ParamutuelFactoryV3(treasury, 0, minBettingWindow, minResolutionWindow);
        token = new MockERC20V3Enum();
        token.mint(proposer, 1e24);
        token.mint(alice, 1e24);
        token.mint(bob, 1e24);
        token.mint(carol, 1e24);
        token.mint(dave, 1e24);
    }

    function _threeOutcomes() internal pure returns (string[] memory o) {
        o = new string[](3);
        o[0] = "A";
        o[1] = "B";
        o[2] = "C";
    }

    function _fiveOutcomes() internal pure returns (string[] memory o) {
        o = new string[](5);
        o[0] = "A";
        o[1] = "B";
        o[2] = "C";
        o[3] = "D";
        o[4] = "E";
    }

    /// @dev Used by the AT_LEAST_K and WEIGHTED_OVERLAP worked-example tests:
    ///      four base options are the smallest count that lets us demonstrate
    ///      `popcount(T & W)` ranging across {0, 1, 2, 3} simultaneously.
    function _fourOutcomes() internal pure returns (string[] memory o) {
        o = new string[](4);
        o[0] = "A";
        o[1] = "B";
        o[2] = "C";
        o[3] = "D";
    }

    /// @dev Convenience: create an enumerated wager with three outcomes and no
    ///      protocol fees. Defaults used by the majority of lifecycle tests.
    function _create(ParamutuelWagerV3.PayoffPolicy policy, uint256 policyParam)
        internal
        returns (ParamutuelWagerV3 w)
    {
        return _createWithFee(policy, policyParam, 0);
    }

    /// @dev Variant allowing a non-zero protocol-fee factory to test fee flows.
    function _createWithFee(ParamutuelWagerV3.PayoffPolicy policy, uint256 policyParam, uint16 feeBps)
        internal
        returns (ParamutuelWagerV3 w)
    {
        factory = new ParamutuelFactoryV3(treasury, feeBps, minBettingWindow, minResolutionWindow);
        vm.prank(proposer);
        address wa = factory.createEnumeratedWager(
            address(token),
            "which tickers up?",
            _threeOutcomes(),
            policy,
            policyParam,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        w = ParamutuelWagerV3(wa);
    }

    /// @dev Mirrors the ANY_OF worked example in `docs/PAYOUT-CALCULATION.md`.
    function _createAnyOfFiveOutcomesNoFees() internal returns (ParamutuelWagerV3 w) {
        factory = new ParamutuelFactoryV3(treasury, 0, minBettingWindow, minResolutionWindow);
        vm.prank(proposer);
        address wa = factory.createEnumeratedWager(
            address(token),
            "doc example A-E",
            _fiveOutcomes(),
            ParamutuelWagerV3.PayoffPolicy.ANY_OF,
            0,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        w = ParamutuelWagerV3(wa);
    }

    /// @dev Mirrors the EXACT_SET worked example in `docs/PAYOUT-CALCULATION.md`.
    function _createExactSetThreeOutcomesNoFees() internal returns (ParamutuelWagerV3 w) {
        factory = new ParamutuelFactoryV3(treasury, 0, minBettingWindow, minResolutionWindow);
        vm.prank(proposer);
        address wa = factory.createEnumeratedWager(
            address(token),
            "doc example EXACT_SET A-C",
            _threeOutcomes(),
            ParamutuelWagerV3.PayoffPolicy.EXACT_SET,
            0,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        w = ParamutuelWagerV3(wa);
    }

    /// @dev Helper for the AT_LEAST_K and WEIGHTED_OVERLAP worked-example tests.
    ///      `policyParam` is `k` for AT_LEAST_K and unused (must be zero) for
    ///      WEIGHTED_OVERLAP. The factory is rebuilt fee-free so the
    ///      documentation figures (which assume zero fees) hold byte-for-byte.
    function _createFourOutcomesNoFees(ParamutuelWagerV3.PayoffPolicy policy, uint256 policyParam)
        internal
        returns (ParamutuelWagerV3 w)
    {
        factory = new ParamutuelFactoryV3(treasury, 0, minBettingWindow, minResolutionWindow);
        vm.prank(proposer);
        address wa = factory.createEnumeratedWager(
            address(token),
            "doc example 4-outcome",
            _fourOutcomes(),
            policy,
            policyParam,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        w = ParamutuelWagerV3(wa);
    }

    // ---- Payoff policy happy paths ----------------------------------------

    /// @notice SINGLE_WINNER: the whole pot goes to ticket(s) matching the one
    ///         winning outcome. Here alice (100 on M0) takes bob's 300 losing stake.
    function testSingleWinner_resolveAndClaim() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);

        vm.prank(alice);
        w.placeBet(M0, 100 ether);
        vm.prank(bob);
        w.placeBet(M1, 300 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(M0);

        uint256 balBefore = token.balanceOf(alice);
        vm.prank(alice);
        w.claim();
        assertEq(token.balanceOf(alice) - balBefore, 400 ether, "alice takes full net pot");
    }

    /// @notice ANY_OF: both tickets intersect W, so the net pot is split
    ///         pro-rata by stake (100+300).
    function testAnyOf_bothOverlappingTicketsSharePot() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);

        uint256 wab = M0 | M1;
        vm.prank(alice);
        w.placeBet(M0, 100 ether);
        vm.prank(bob);
        w.placeBet(wab, 300 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(wab);

        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();

        assertEq(token.balanceOf(alice), 1e24 - 100 ether + 100 ether, "alice stake returned as share");
        assertEq(token.balanceOf(bob), 1e24, "bob net neutral full return");
    }

    /// @notice EXACT_SET: only ticket whose mask equals W shares the pot;
    ///         subset tickets lose.
    function testExactSet_onlyExactTicketWins() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.EXACT_SET, 0);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);

        uint256 wab = M0 | M1;
        vm.prank(alice);
        w.placeBet(wab, 100 ether);
        vm.prank(bob);
        w.placeBet(M0, 300 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(wab);

        vm.prank(alice);
        w.claim();
        assertEq(token.balanceOf(alice), 1e24 + 300 ether, "alice gets entire pot incl bob losing stake");

        vm.prank(bob);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();
    }

    /// @notice AT_LEAST_K with k=2: tickets winning require ≥k winning bits in
    ///         the intersection. Alice's 2-bit overlap wins, bob's 1-bit loses.
    function testAtLeastK_overlapThreshold() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.AT_LEAST_K, 2);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);

        uint256 wabc = M0 | M1 | M2;
        vm.prank(alice);
        w.placeBet(M0 | M1, 100 ether);
        vm.prank(bob);
        w.placeBet(M0, 400 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(wabc);

        vm.prank(alice);
        w.claim();
        assertEq(token.balanceOf(alice), 1e24 + 400 ether);

        vm.prank(bob);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();
    }

    /// @notice WEIGHTED_OVERLAP: partial credit proportional to |T ∩ W|.
    ///         Bob (ticket of size 2) receives twice alice's per-stake weight.
    function testWeightedOverlap_partialCreditByOverlapSize() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.WEIGHTED_OVERLAP, 0);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);

        uint256 wab = M0 | M1;
        vm.prank(alice);
        w.placeBet(M0, 100 ether);
        vm.prank(bob);
        w.placeBet(wab, 100 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(wab);

        uint256 netPot = 200 ether;
        uint256 totalW = 100 * 1 + 100 * 2; // 300
        uint256 aliceShare = (100 * 1 * netPot) / totalW;
        uint256 bobShare = netPot - aliceShare;

        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();

        // WEIGHTED_OVERLAP uses integer division twice (weight inside claim +
        // share); dust of up to a few wei can remain in the contract.
        assertApproxEqAbs(token.balanceOf(alice), 1e24 - 100 ether + aliceShare, 2);
        assertApproxEqAbs(token.balanceOf(bob), 1e24 - 100 ether + bobShare, 2);
    }

    // ---- Payoff policy rejection / invariants -----------------------------

    function testSingleWinner_rejectsMultiBitTicket() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV3.InvalidTicketMask.selector);
        w.placeBet(M0 | M1, 1 ether);
    }

    function testResolve_revertsWhenNoWinningStake_ExactSet() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.EXACT_SET, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0 | M1, 100 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        vm.expectRevert(ParamutuelWagerV3.NoWinningStake.selector);
        w.resolve(M2);
    }

    function testAnyOf_resolveRevertsWhenNoTicketOverlapsWinningSet() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0, 100 ether);
        vm.prank(bob);
        w.placeBet(M1, 100 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        vm.expectRevert(ParamutuelWagerV3.NoWinningStake.selector);
        w.resolve(M2);

        assertEq(uint256(w.state()), uint256(ParamutuelWagerV3.State.Open), "resolve failure leaves wager Open");
    }

    function testSingleWinner_resolveReverts_multiBitWinningMask() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0, 1 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        vm.expectRevert(ParamutuelWagerV3.InvalidWinningMask.selector);
        w.resolve(M0 | M1);
    }

    function testInvalidTicketMask_bitOutOfRange() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV3.InvalidTicketMask.selector);
        w.placeBet(1 << 3, 1 ether); // only 3 outcomes (bits 0..2)
    }

    // ---- Retract / expire --------------------------------------------------

    function testRetracted_proRataRefund() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0, 100 ether);
        vm.prank(bob);
        w.placeBet(M1, 300 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.retract();

        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();
        assertEq(token.balanceOf(alice) + token.balanceOf(bob), 2e24, "full pot returned to bettors");
    }

    function testExpire_afterResolutionWindow() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0, 100 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.closeResolutionWindow();

        vm.warp(block.timestamp + 3 hours);
        w.expire();

        vm.prank(alice);
        w.claim();
        assertEq(token.balanceOf(alice), 1e24, "expired pot refunded pro-rata");
    }

    // ---- Used masks / batch placement / closing ---------------------------

    function testUsedMasksTracked() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0, 10 ether);
        vm.prank(alice);
        w.placeBet(M0, 5 ether);
        assertEq(w.usedMasksCount(), 1);
        assertEq(w.usedMaskAt(0), M0);
    }

    function testPlaceBets_batch_threeDistinctMasks() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);

        uint256[] memory masks = new uint256[](3);
        masks[0] = M0;
        masks[1] = M1;
        masks[2] = M2;
        uint256[] memory amts = new uint256[](3);
        amts[0] = 10 ether;
        amts[1] = 20 ether;
        amts[2] = 30 ether;

        vm.prank(alice);
        w.placeBets(masks, amts);
        assertEq(w.usedMasksCount(), 3);
        assertEq(w.totalPot(), 60 ether);
    }

    function testPlaceBets_arrayLengthMismatch_reverts() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        uint256[] memory m = new uint256[](1);
        m[0] = M0;
        uint256[] memory a = new uint256[](2);
        a[0] = 1;
        a[1] = 2;
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV3.ArrayLengthMismatch.selector);
        w.placeBets(m, a);
    }

    function testCloseBetting_blocksFurtherBets() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
        vm.prank(proposer);
        w.closeBetting();

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV3.BettingClosed.selector);
        w.placeBet(M0, 1 ether);
    }

    // ---- Fee flow ----------------------------------------------------------

    /// @notice 1% protocol fee on a 1000-ether SINGLE_WINNER wager charges once
    ///         at resolve and leaves the fee balance withdrawable by the treasury.
    function testFees_protocolOnResolve() public {
        ParamutuelWagerV3 w = _createWithFee(ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, 100);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0, 1000 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(M0);

        uint256 fees = (1000 ether * 100) / 10_000;
        assertEq(w.feesCharged(), true);

        uint256 tBalBefore = token.balanceOf(treasury);
        vm.prank(alice);
        w.claim();
        assertEq(token.balanceOf(address(w)), fees, "collateral left for fee recipients");

        vm.prank(treasury);
        w.withdrawFees();
        assertEq(token.balanceOf(treasury) - tBalBefore, fees, "treasury withdraws the exact fee amount");
    }

    // ---- Documentation worked examples (byte-for-byte parity) -------------

    /// @notice Same scenario and numbers as the ANY_OF worked example in
    ///         `docs/PAYOUT-CALCULATION.md`. Stakes are raw smallest units;
    ///         the 2-wei residual is the documented integer-division dust.
    function testAnyOf_documentationWorkedExample_fiveOutcomes() public {
        uint256 mA = 1;
        uint256 mB = 2;
        uint256 mC = 4;
        uint256 mD = 8;
        uint256 mE = 16;
        uint256 ticketAC = mA | mC;
        uint256 ticketED = mE | mD;
        uint256 winningACE = mA | mC | mE;

        uint256 stakeAC = 100;
        uint256 stakeED = 50;
        uint256 stakeBob = 200;
        uint256 stakeCarol = 150;

        ParamutuelWagerV3 w = _createAnyOfFiveOutcomesNoFees();

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);
        vm.prank(carol);
        token.approve(address(w), type(uint256).max);

        vm.prank(alice);
        w.placeBet(ticketAC, stakeAC);
        vm.prank(alice);
        w.placeBet(ticketED, stakeED);
        vm.prank(bob);
        w.placeBet(mA, stakeBob);
        vm.prank(carol);
        w.placeBet(mB, stakeCarol);

        assertEq(w.totalPot(), 500);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(winningACE);

        // V3 exposes the accumulated winning-unit denominator via
        // `payoutDenominator` after resolve (V2 also published it via
        // `totalWinningUnits()`; both are the same number).
        assertEq(w.payoutDenominator(), 350);

        uint256 netPot = w.totalPot() - (w.totalPot() * w.totalFeeBps()) / w.BPS_DENOMINATOR();
        assertEq(netPot, 500, "fee-less scenario: net == gross");

        uint256 balAlice = token.balanceOf(alice);
        uint256 balBob = token.balanceOf(bob);
        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();

        assertEq(token.balanceOf(alice) - balAlice, 213, "Alice: 142 + 71 from doc");
        assertEq(token.balanceOf(bob) - balBob, 285, "Bob share from doc");

        vm.prank(carol);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();

        assertEq(token.balanceOf(address(w)), 2, "integer division dust stays in wager");
    }

    /// @notice Same scenario and numbers as the EXACT_SET worked example in
    ///         `docs/PAYOUT-CALCULATION.md`.
    function testExactSet_documentationWorkedExample_threeOutcomes() public {
        uint256 ticketAC = M0 | M2;
        uint256 winningAC = ticketAC;

        ParamutuelWagerV3 w = _createExactSetThreeOutcomesNoFees();

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);
        vm.prank(carol);
        token.approve(address(w), type(uint256).max);
        vm.prank(dave);
        token.approve(address(w), type(uint256).max);

        vm.prank(alice);
        w.placeBet(ticketAC, 60);
        vm.prank(bob);
        w.placeBet(M0, 100);
        vm.prank(carol);
        w.placeBet(M0 | M1 | M2, 140);
        vm.prank(dave);
        w.placeBet(ticketAC, 40);

        assertEq(w.totalPot(), 340);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(winningAC);

        assertEq(w.payoutDenominator(), 100, "EXACT_SET denominator = sum of winning ticket stakes");

        uint256 balAlice = token.balanceOf(alice);
        uint256 balDave = token.balanceOf(dave);
        vm.prank(alice);
        w.claim();
        vm.prank(dave);
        w.claim();

        assertEq(token.balanceOf(alice) - balAlice, 204);
        assertEq(token.balanceOf(dave) - balDave, 136);

        vm.prank(bob);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();
        vm.prank(carol);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();

        assertEq(token.balanceOf(address(w)), 0, "payouts exhaust netPot in this example");
    }

    /// @notice Mirrors the SINGLE_WINNER worked example in
    ///         `docs/PAYOUT-CALCULATION.md`. Three outcomes, alice holds two
    ///         tickets (one losing, one winning) so a single `claim()` pays
    ///         out only the winning portion.
    function testSingleWinner_documentationWorkedExample_threeOutcomes() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);
        vm.prank(carol);
        token.approve(address(w), type(uint256).max);

        // Alice splits her stake across two single-bit tickets — one will win,
        // one will lose. The doc's value is showing that `claim()` aggregates
        // tickets and pays the winning portion only.
        vm.prank(alice);
        w.placeBet(M0, 100); // {A} — losing
        vm.prank(alice);
        w.placeBet(M1, 50);  // {B} — winning
        vm.prank(bob);
        w.placeBet(M1, 200); // {B} — winning
        vm.prank(carol);
        w.placeBet(M2, 150); // {C} — losing

        assertEq(w.totalPot(), 500);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(M1);

        // SINGLE_WINNER denominator is the total stake on the winning mask.
        assertEq(w.payoutDenominator(), 250, "denominator = pool[B] = 50 + 200");

        uint256 balAlice = token.balanceOf(alice);
        uint256 balBob = token.balanceOf(bob);
        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();

        // floor(50 * 500 / 250) = 100; alice's losing {A} stake is gone.
        assertEq(token.balanceOf(alice) - balAlice, 100, "alice's winning portion only");
        // floor(200 * 500 / 250) = 400.
        assertEq(token.balanceOf(bob) - balBob, 400);

        vm.prank(carol);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();

        // 100 + 400 == 500 == netPot — no rounding dust in this example.
        assertEq(token.balanceOf(address(w)), 0, "payouts exhaust netPot");
    }

    /// @notice Mirrors the AT_LEAST_K worked example (`k = 2`) in
    ///         `docs/PAYOUT-CALCULATION.md`. Four outcomes; `winningMask =
    ///         {A,B,C}`. Bob loses despite holding a 2-bit ticket because his
    ///         overlap with `W` is only 1; Dave wins despite picking
    ///         `D ∉ W` because `popcount(T & W) = 2`. Documents that
    ///         `AT_LEAST_K` keys on overlap, not subset or ticket size.
    function testAtLeastK_documentationWorkedExample_fourOutcomes_k2() public {
        uint256 mA = 1;
        uint256 mB = 2;
        uint256 mC = 4;
        uint256 mD = 8;
        uint256 winningABC = mA | mB | mC; // = 7

        ParamutuelWagerV3 w = _createFourOutcomesNoFees(ParamutuelWagerV3.PayoffPolicy.AT_LEAST_K, 2);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);
        vm.prank(carol);
        token.approve(address(w), type(uint256).max);
        vm.prank(dave);
        token.approve(address(w), type(uint256).max);

        vm.prank(alice);
        w.placeBet(mA | mB, 100); // overlap 2 — wins
        vm.prank(bob);
        w.placeBet(mA | mD, 60);  // overlap 1 — loses
        vm.prank(carol);
        w.placeBet(mA | mB | mC, 80); // overlap 3 — wins
        vm.prank(dave);
        w.placeBet(mB | mC | mD, 50); // overlap 2 — wins (extra D bit doesn't disqualify)

        assertEq(w.totalPot(), 290);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(winningABC);

        // Three distinct winning masks contribute: {A,B}=3, {A,B,C}=7, {B,C,D}=14.
        // Their pools sum to the AT_LEAST_K denominator.
        assertEq(w.payoutDenominator(), 230);

        uint256 balAlice = token.balanceOf(alice);
        uint256 balCarol = token.balanceOf(carol);
        uint256 balDave = token.balanceOf(dave);
        vm.prank(alice);
        w.claim();
        vm.prank(carol);
        w.claim();
        vm.prank(dave);
        w.claim();

        // floor(stake * netPot / denom) — each on its own ticket pool.
        assertEq(token.balanceOf(alice) - balAlice, 126, "alice: floor(100*290/230)");
        assertEq(token.balanceOf(carol) - balCarol, 100, "carol: floor(80*290/230)");
        assertEq(token.balanceOf(dave) - balDave, 63, "dave: floor(50*290/230)");

        vm.prank(bob);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();

        // 126 + 100 + 63 = 289; netPot was 290; 1 wei of dust as documented.
        assertEq(token.balanceOf(address(w)), 1, "documented integer-division dust");
    }

    /// @notice Mirrors the WEIGHTED_OVERLAP worked example in
    ///         `docs/PAYOUT-CALCULATION.md`. Every bettor stakes the same
    ///         amount; payouts scale with `popcount(T & W)`. Dave's
    ///         zero-overlap ticket contributes to the pot but never to the
    ///         denominator and never receives a payout — this is the
    ///         distinguishing property vs `ANY_OF`.
    function testWeightedOverlap_documentationWorkedExample_fourOutcomes() public {
        uint256 mA = 1;
        uint256 mB = 2;
        uint256 mC = 4;
        uint256 mD = 8;
        uint256 winningABC = mA | mB | mC;

        ParamutuelWagerV3 w =
            _createFourOutcomesNoFees(ParamutuelWagerV3.PayoffPolicy.WEIGHTED_OVERLAP, 0);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);
        vm.prank(carol);
        token.approve(address(w), type(uint256).max);
        vm.prank(dave);
        token.approve(address(w), type(uint256).max);

        vm.prank(alice);
        w.placeBet(mA, 100); // overlap 1, weight 100
        vm.prank(bob);
        w.placeBet(mA | mB, 100); // overlap 2, weight 200
        vm.prank(carol);
        w.placeBet(mA | mB | mC, 100); // overlap 3, weight 300
        vm.prank(dave);
        w.placeBet(mD, 100); // overlap 0 — funds the pot, never claims

        assertEq(w.totalPot(), 400);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(winningABC);

        // WEIGHTED_OVERLAP denominator is the sum of (stake * overlap) across
        // winning tickets only. 100 + 200 + 300 == 600.
        assertEq(w.payoutDenominator(), 600);

        uint256 balAlice = token.balanceOf(alice);
        uint256 balBob = token.balanceOf(bob);
        uint256 balCarol = token.balanceOf(carol);
        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();
        vm.prank(carol);
        w.claim();

        // Numerator per ticket is `stake * overlap`, not raw stake.
        assertEq(token.balanceOf(alice) - balAlice, 66, "alice: floor(100*400/600)");
        assertEq(token.balanceOf(bob) - balBob, 133, "bob: floor(200*400/600)");
        assertEq(token.balanceOf(carol) - balCarol, 200, "carol: floor(300*400/600)");

        vm.prank(dave);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();

        // 66 + 133 + 200 = 399; netPot was 400; 1 wei dust as documented.
        assertEq(token.balanceOf(address(w)), 1, "documented integer-division dust");
    }

    // ---- Additional claim / multi-ticket semantics ------------------------

    function testAnyOf_loserAfterSuccessfulResolve_revertsClaim() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);
        vm.prank(carol);
        token.approve(address(w), type(uint256).max);

        vm.prank(alice);
        w.placeBet(M0, 100 ether);
        vm.prank(bob);
        w.placeBet(M1, 100 ether);
        vm.prank(carol);
        w.placeBet(M2, 100 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(M0 | M1);

        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();
        vm.prank(carol);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();
    }

    /// @notice A bettor with two tickets (one winning, one losing) claims only
    ///         the winning ticket's share but cannot claim twice.
    function testAnyOf_sameUser_twoTickets_partialWinPayout() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0, 100 ether);
        vm.prank(alice);
        w.placeBet(M2, 300 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(M0);

        uint256 before = token.balanceOf(alice);
        vm.prank(alice);
        w.claim();
        assertEq(token.balanceOf(alice) - before, 400 ether, "alice takes whole pot via winning ticket");
    }

    function testAtLeastK_k1_behavesLikeOverlap() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.AT_LEAST_K, 1);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0, 100 ether);
        vm.prank(bob);
        w.placeBet(M2, 100 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(M0 | M2);

        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();
        assertEq(token.balanceOf(alice) + token.balanceOf(bob), 2e24, "k=1: both single-bit winners refunded their share");
    }

    function testWeightedOverlap_threeBettors_conservesPot() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.WEIGHTED_OVERLAP, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);
        vm.prank(carol);
        token.approve(address(w), type(uint256).max);

        uint256 wAll = M0 | M1 | M2;
        vm.prank(alice);
        w.placeBet(M0, 100 ether);
        vm.prank(bob);
        w.placeBet(M0 | M1, 100 ether);
        vm.prank(carol);
        w.placeBet(wAll, 100 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(wAll);

        uint256 sumBefore = token.balanceOf(alice) + token.balanceOf(bob) + token.balanceOf(carol);
        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();
        vm.prank(carol);
        w.claim();
        uint256 sumAfter = token.balanceOf(alice) + token.balanceOf(bob) + token.balanceOf(carol);
        // Small dust allowed due to repeated integer division in WEIGHTED_OVERLAP.
        assertApproxEqAbs(sumAfter - sumBefore, 300 ether, 4);
    }

    function testDoubleClaim_reverts() public {
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0, 100 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(M0);

        vm.prank(alice);
        w.claim();
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();
    }

    // ---- Fuzz properties ---------------------------------------------------

    /// @notice ANY_OF fuzz: whatever the stakes, if W = M0 | M1 then both
    ///         bettors are winners and the full pot is distributed.
    function testFuzz_anyOf_claimConservesPot(uint128 aAmt, uint128 bAmt) public {
        vm.assume(aAmt > 0 && bAmt > 0 && uint256(aAmt) + uint256(bAmt) < 1e21);
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);

        vm.prank(alice);
        w.placeBet(M0, uint256(aAmt));
        vm.prank(bob);
        w.placeBet(M1, uint256(bAmt));

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(M0 | M1);

        uint256 before = token.balanceOf(alice) + token.balanceOf(bob);
        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();
        uint256 afterSum = token.balanceOf(alice) + token.balanceOf(bob);
        assertEq(afterSum - before, uint256(aAmt) + uint256(bAmt), "full pot distributed");
    }

    /// @notice EXACT_SET fuzz: alice (exact ticket) always gets the full pot,
    ///         bob's non-exact ticket never claims.
    function testFuzz_exactSet_payoutConserves(uint128 x, uint128 y) public {
        vm.assume(x > 0 && y > 0);
        vm.assume(uint256(x) + uint256(y) < 1e21);
        ParamutuelWagerV3 w = _create(ParamutuelWagerV3.PayoffPolicy.EXACT_SET, 0);

        uint256 wTarget = M0 | M1;
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);

        vm.prank(alice);
        w.placeBet(wTarget, uint256(x));
        vm.prank(bob);
        w.placeBet(M0, uint256(y));

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(wTarget);

        uint256 before = token.balanceOf(alice) + token.balanceOf(bob);
        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();
        uint256 afterSum = token.balanceOf(alice) + token.balanceOf(bob);
        assertEq(afterSum - before, uint256(x) + uint256(y), "exact winner absorbs loser's stake");
    }
}
