// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import {ParamutuelFactoryV2} from "../src/ParamutuelFactoryV2.sol";
import {ParamutuelWagerV2} from "../src/ParamutuelWagerV2.sol";
import {WagerV2Masks} from "../src/libraries/WagerV2Masks.sol";

contract MockERC20V2Ext {
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

/// @notice Broad scenarios: lifecycle, fees, batch bets, seeds, policy edge cases, library helpers.
contract ParamutuelV2ExtensiveTest is Test {
    ParamutuelFactoryV2 factory;
    MockERC20V2Ext token;

    address treasury = address(0x1000);
    address proposer = address(0x2000);
    address alice = address(0x3000);
    address bob = address(0x4000);
    address carol = address(0x5000);
    address dave = address(0x6000);

    uint64 minBettingWindow = 1 hours;
    uint64 minResolutionWindow = 1 hours;

    uint256 constant M0 = 1;
    uint256 constant M1 = 2;
    uint256 constant M2 = 4;

    function setUp() public {
        vm.warp(1000);
        factory = new ParamutuelFactoryV2(treasury, 100, minBettingWindow, minResolutionWindow); // 1% protocol
        token = new MockERC20V2Ext();
        token.mint(proposer, 1e24);
        token.mint(alice, 1e24);
        token.mint(bob, 1e24);
        token.mint(carol, 1e24);
        token.mint(dave, 1e24);
    }

    function _outcomes3() internal pure returns (string[] memory o) {
        o = new string[](3);
        o[0] = "A";
        o[1] = "B";
        o[2] = "C";
    }

    function _outcomes5() internal pure returns (string[] memory o) {
        o = new string[](5);
        o[0] = "A";
        o[1] = "B";
        o[2] = "C";
        o[3] = "D";
        o[4] = "E";
    }

    /// @dev Mirrors the worked **ANY_OF** example in `docs/PAYOUT-CALCULATION.md` (five options A–E, `W = {A,C,E}`).
    function _createAnyOfFiveOutcomesNoFees() internal returns (ParamutuelWagerV2 w) {
        factory = new ParamutuelFactoryV2(treasury, 0, minBettingWindow, minResolutionWindow);
        address[] memory extraR = new address[](0);
        uint16[] memory extraB = new uint16[](0);
        vm.prank(proposer);
        address wa = factory.createWager(
            address(token),
            "doc example A-E",
            _outcomes5(),
            ParamutuelWagerV2.PayoffPolicy.ANY_OF,
            0,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            proposer,
            proposer,
            extraR,
            extraB
        );
        w = ParamutuelWagerV2(wa);
    }

    /// @dev Worked **EXACT_SET** example: three options A–C, `W = {A,C}` (mask 5); see `docs/PAYOUT-CALCULATION.md`.
    function _createExactSetThreeOutcomesNoFees() internal returns (ParamutuelWagerV2 w) {
        factory = new ParamutuelFactoryV2(treasury, 0, minBettingWindow, minResolutionWindow);
        address[] memory extraR = new address[](0);
        uint16[] memory extraB = new uint16[](0);
        vm.prank(proposer);
        address wa = factory.createWager(
            address(token),
            "doc example EXACT_SET A-C",
            _outcomes3(),
            ParamutuelWagerV2.PayoffPolicy.EXACT_SET,
            0,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            proposer,
            proposer,
            extraR,
            extraB
        );
        w = ParamutuelWagerV2(wa);
    }

    function _create(ParamutuelWagerV2.PayoffPolicy policy, uint256 policyParam, uint16 protocolBps)
        internal
        returns (ParamutuelWagerV2 w)
    {
        factory = new ParamutuelFactoryV2(treasury, protocolBps, minBettingWindow, minResolutionWindow);
        string[] memory outcomes = _outcomes3();
        address[] memory extraR = new address[](0);
        uint16[] memory extraB = new uint16[](0);
        vm.prank(proposer);
        address wa = factory.createWager(
            address(token),
            "extensive",
            outcomes,
            policy,
            policyParam,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            proposer,
            proposer,
            extraR,
            extraB
        );
        w = ParamutuelWagerV2(wa);
    }

    function testWagerV2Masks_fullSet_union_single() public pure {
        assertEq(WagerV2Masks.singleOutcome(0), 1);
        assertEq(WagerV2Masks.singleOutcome(2), 4);
        assertEq(WagerV2Masks.union(1, 4), 5);
        assertEq(WagerV2Masks.fullSet(3), 7);
        assertTrue(WagerV2Masks.isValidMask(7, 3));
        assertFalse(WagerV2Masks.isValidMask(8, 3));
    }

    function testPlaceBets_batch_threeDistinctMasks() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.ANY_OF, 0, 0);
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

    function testSeedBets_viaFactory_secondCreateOverload() public {
        string[] memory outcomes = _outcomes3();
        uint256[] memory seeds = new uint256[](2);
        seeds[0] = M0;
        seeds[1] = M1;
        uint256[] memory samt = new uint256[](2);
        samt[0] = 50 ether;
        samt[1] = 50 ether;

        vm.prank(proposer);
        token.approve(address(factory), type(uint256).max);

        vm.prank(proposer);
        address wa = factory.createWager(
            address(token),
            "seeded",
            outcomes,
            ParamutuelWagerV2.PayoffPolicy.ANY_OF,
            0,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0),
            seeds,
            samt
        );

        ParamutuelWagerV2 w = ParamutuelWagerV2(wa);
        assertEq(w.totalPot(), 100 ether);
        assertEq(w.bets(proposer, M0), 50 ether);
    }

    function testFees_protocolOnResolve() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.SINGLE_WINNER, 0, 100);
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
        assertEq(token.balanceOf(treasury) - tBalBefore, fees);
    }

    function testExpire_afterResolutionWindow() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.ANY_OF, 0, 0);
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
        assertEq(token.balanceOf(alice), 1e24);
    }

    function testCloseBetting_blocksFurtherBets() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.ANY_OF, 0, 0);
        vm.prank(proposer);
        w.closeBetting();

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV2.BettingClosed.selector);
        w.placeBet(M0, 1 ether);
    }

    function testInvalidTicketMask_bitOutOfRange() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.ANY_OF, 0, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV2.InvalidTicketMask.selector);
        w.placeBet(1 << 3, 1 ether); // only 3 outcomes 0..2
    }

    function testAtLeastK_k1_behavesLikeOverlap() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.AT_LEAST_K, 1, 0);
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
        assertEq(token.balanceOf(alice) + token.balanceOf(bob), 2e24);
    }

    function testAnyOf_resolveRevertsWhenNoTicketOverlapsWinningSet() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.ANY_OF, 0, 0);
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
        vm.expectRevert(ParamutuelWagerV2.NoWinningStake.selector);
        w.resolve(M2); // only C wins — neither ticket overlaps

        assertEq(uint256(w.state()), uint256(ParamutuelWagerV2.State.Open));
    }

    /// @notice Same stakes and masks as **Worked example (ANY_OF)** in `docs/PAYOUT-CALCULATION.md`.
    /// @dev Stakes **100**, **50**, … are **raw smallest units** (here: literal wei of the mock token), so the doc’s
    ///      integer table matches `claim` exactly. The **2** left on the wager is **2 wei** of dust, not 2 ETH/USDC.
    ///      Real pots use large raw amounts (e.g. `500e6` for 500 USDC); rounding loss stays microscopic vs the pot.
    function testAnyOf_documentationWorkedExample_fiveOutcomes() public {
        uint256 mA = 1; // bit 0
        uint256 mB = 2; // bit 1
        uint256 mC = 4; // bit 2
        uint256 mD = 8; // bit 3
        uint256 mE = 16; // bit 4
        uint256 ticketAC = mA | mC;
        uint256 ticketED = mE | mD;
        uint256 winningACE = mA | mC | mE;

        uint256 stakeAC = 100;
        uint256 stakeED = 50;
        uint256 stakeBob = 200;
        uint256 stakeCarol = 150;

        ParamutuelWagerV2 w = _createAnyOfFiveOutcomesNoFees();

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

        assertEq(w.totalWinningUnits(), 350);

        uint256 netPot = w.totalPot() - w.totalPot() * w.totalFeeBps() / w.BPS_DENOMINATOR();
        assertEq(netPot, 500);

        uint256 balAlice = token.balanceOf(alice);
        uint256 balBob = token.balanceOf(bob);
        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();

        assertEq(token.balanceOf(alice) - balAlice, 213, "Alice: 142 + 71 from doc");
        assertEq(token.balanceOf(bob) - balBob, 285, "Bob share from doc");

        vm.prank(carol);
        vm.expectRevert(ParamutuelWagerV2.NothingToClaim.selector);
        w.claim();

        assertEq(token.balanceOf(address(w)), 2, "integer division dust stays in wager");
    }

    /// @notice Same stakes and masks as **Worked example (EXACT_SET)** in `docs/PAYOUT-CALCULATION.md`.
    function testExactSet_documentationWorkedExample_threeOutcomes() public {
        uint256 ticketAC = M0 | M2; // {A,C} = 5
        uint256 winningAC = ticketAC;

        ParamutuelWagerV2 w = _createExactSetThreeOutcomesNoFees();

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

        assertEq(w.totalWinningUnits(), 100);

        uint256 balAlice = token.balanceOf(alice);
        uint256 balDave = token.balanceOf(dave);
        vm.prank(alice);
        w.claim();
        vm.prank(dave);
        w.claim();

        assertEq(token.balanceOf(alice) - balAlice, 204);
        assertEq(token.balanceOf(dave) - balDave, 136);

        vm.prank(bob);
        vm.expectRevert(ParamutuelWagerV2.NothingToClaim.selector);
        w.claim();
        vm.prank(carol);
        vm.expectRevert(ParamutuelWagerV2.NothingToClaim.selector);
        w.claim();

        assertEq(token.balanceOf(address(w)), 0, "payouts exhaust netPot in this example");
    }

    function testAnyOf_loserAfterSuccessfulResolve_revertsClaim() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.ANY_OF, 0, 0);
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
        w.resolve(M0 | M1); // carol loses

        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();
        vm.prank(carol);
        vm.expectRevert(ParamutuelWagerV2.NothingToClaim.selector);
        w.claim();
    }

    function testAnyOf_sameUser_twoTickets_partialWinPayout() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.ANY_OF, 0, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0, 100 ether);
        vm.prank(alice);
        w.placeBet(M2, 300 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(M0); // only first ticket wins: 100 of 400 in winner pool... total winning = 100, alice has 100 on M0 wins, 300 on M2 loses

        uint256 before = token.balanceOf(alice);
        vm.prank(alice);
        w.claim();
        assertEq(token.balanceOf(alice) - before, 400 ether);
    }

    function testSingleWinner_resolveReverts_multiBitWinningMask() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.SINGLE_WINNER, 0, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0, 1 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        vm.expectRevert(ParamutuelWagerV2.InvalidWinningMask.selector);
        w.resolve(M0 | M1);
    }

    function testPlaceBets_arrayLengthMismatch_reverts() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.ANY_OF, 0, 0);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        uint256[] memory m = new uint256[](1);
        m[0] = M0;
        uint256[] memory a = new uint256[](2);
        a[0] = 1;
        a[1] = 2;
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV2.ArrayLengthMismatch.selector);
        w.placeBets(m, a);
    }

    function testWeightedOverlap_threeBettors_conservesPot() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.WEIGHTED_OVERLAP, 0, 0);
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
        assertApproxEqAbs(sumAfter - sumBefore, 300 ether, 4);
    }

    function testDoubleClaim_reverts() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.SINGLE_WINNER, 0, 0);
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
        vm.expectRevert(ParamutuelWagerV2.NothingToClaim.selector);
        w.claim();
    }

    function testFuzz_exactSet_payoutConserves(uint128 x, uint128 y) public {
        vm.assume(x > 0 && y > 0);
        vm.assume(uint256(x) + uint256(y) < 1e21);
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.EXACT_SET, 0, 0);

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
        vm.expectRevert(ParamutuelWagerV2.NothingToClaim.selector);
        w.claim();
        uint256 afterSum = token.balanceOf(alice) + token.balanceOf(bob);
        assertEq(afterSum - before, uint256(x) + uint256(y));
    }
}
