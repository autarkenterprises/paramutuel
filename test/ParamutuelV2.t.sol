// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import {ParamutuelFactoryV2} from "../src/ParamutuelFactoryV2.sol";
import {ParamutuelWagerV2} from "../src/ParamutuelWagerV2.sol";

contract MockERC20V2 {
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

contract ParamutuelV2Test is Test {
    ParamutuelFactoryV2 factory;
    MockERC20V2 token;

    address treasury = address(0x1000);
    address proposer = address(0x2000);
    address alice = address(0x3000);
    address bob = address(0x4000);
    address carol = address(0x5000);

    uint16 protocolFeeBps = 0; // simplify payout checks
    uint64 minBettingWindow = 1 hours;
    uint64 minResolutionWindow = 1 hours;

    uint256 constant M0 = 1; // bit 0
    uint256 constant M1 = 2; // bit 1
    uint256 constant M2 = 4; // bit 2

    function setUp() public {
        vm.warp(1000);
        factory = new ParamutuelFactoryV2(treasury, protocolFeeBps, minBettingWindow, minResolutionWindow);
        token = new MockERC20V2();
        token.mint(proposer, 1e24);
        token.mint(alice, 1e24);
        token.mint(bob, 1e24);
        token.mint(carol, 1e24);
    }

    function _threeOutcomes() internal pure returns (string[] memory o) {
        o = new string[](3);
        o[0] = "A";
        o[1] = "B";
        o[2] = "C";
    }

    function _create(
        ParamutuelWagerV2.PayoffPolicy policy,
        uint256 policyParam,
        uint64 bettingClose,
        uint64 resWindow
    ) internal returns (ParamutuelWagerV2 w) {
        string[] memory outcomes = _threeOutcomes();
        address[] memory extraR = new address[](0);
        uint16[] memory extraB = new uint16[](0);
        vm.prank(proposer);
        address wa = factory.createWager(
            address(token),
            "which tickers up?",
            outcomes,
            policy,
            policyParam,
            bettingClose,
            resWindow,
            address(0),
            proposer,
            proposer,
            extraR,
            extraB
        );
        w = ParamutuelWagerV2(wa);
    }

    function testSingleWinner_resolveAndClaim() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.SINGLE_WINNER, 0, uint64(block.timestamp + 2 hours), 2 hours);

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

    function testAnyOf_bothOverlappingTicketsSharePot() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.ANY_OF, 0, uint64(block.timestamp + 2 hours), 2 hours);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);

        // W = {A,B} = M0|M1
        uint256 wab = M0 | M1;
        vm.prank(alice);
        w.placeBet(M0, 100 ether); // hits W
        vm.prank(bob);
        w.placeBet(wab, 300 ether); // hits W

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(wab);

        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();

        assertEq(token.balanceOf(alice), 1e24 - 100 ether + 100 ether, "alice stake returned as share");
        // alice 100/400 of 400 = 100, bob 300/400 = 300 — full pot back
        assertEq(token.balanceOf(bob), 1e24, "bob net neutral full return");
    }

    function testExactSet_onlyExactTicketWins() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.EXACT_SET, 0, uint64(block.timestamp + 2 hours), 2 hours);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);

        uint256 wab = M0 | M1;
        vm.prank(alice);
        w.placeBet(wab, 100 ether); // exact
        vm.prank(bob);
        w.placeBet(M0, 300 ether); // subset, not exact

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(wab);

        vm.prank(alice);
        w.claim();
        assertEq(token.balanceOf(alice), 1e24 + 300 ether, "alice gets entire pot incl bob losing stake");

        vm.prank(bob);
        vm.expectRevert(ParamutuelWagerV2.NothingToClaim.selector);
        w.claim();
    }

    function testAtLeastK_overlapThreshold() public {
        // k=2: need at least 2 winning bits in intersection
        ParamutuelWagerV2 w =
            _create(ParamutuelWagerV2.PayoffPolicy.AT_LEAST_K, 2, uint64(block.timestamp + 2 hours), 2 hours);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);

        uint256 wabc = M0 | M1 | M2;
        vm.prank(alice);
        w.placeBet(M0 | M1, 100 ether); // intersection size 2 with W — wins
        vm.prank(bob);
        w.placeBet(M0, 400 ether); // intersection size 1 — loses

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(wabc);

        vm.prank(alice);
        w.claim();
        assertEq(token.balanceOf(alice), 1e24 + 400 ether);

        vm.prank(bob);
        vm.expectRevert(ParamutuelWagerV2.NothingToClaim.selector);
        w.claim();
    }

    function testWeightedOverlap_partialCreditByOverlapSize() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.WEIGHTED_OVERLAP, 0, uint64(block.timestamp + 2 hours), 2 hours);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);

        // W = {A,B}
        uint256 wab = M0 | M1;
        // Alice: 100 on {A} -> weight 100 * 1
        vm.prank(alice);
        w.placeBet(M0, 100 ether);
        // Bob: 100 on {A,B} -> weight 100 * 2
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

        // Integer division rounding on weighted claims may leave 1 wei dust in the contract.
        assertApproxEqAbs(token.balanceOf(alice), 1e24 - 100 ether + aliceShare, 2);
        assertApproxEqAbs(token.balanceOf(bob), 1e24 - 100 ether + bobShare, 2);
    }

    function testSingleWinner_rejectsMultiBitTicket() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.SINGLE_WINNER, 0, uint64(block.timestamp + 2 hours), 2 hours);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV2.InvalidTicketMask.selector);
        w.placeBet(M0 | M1, 1 ether);
    }

    function testResolve_revertsWhenNoWinningStake_ExactSet() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.EXACT_SET, 0, uint64(block.timestamp + 2 hours), 2 hours);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0 | M1, 100 ether);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        vm.expectRevert(ParamutuelWagerV2.NoWinningStake.selector);
        w.resolve(M2); // no ticket exactly {C}
    }

    function testRetracted_proRataRefund() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.ANY_OF, 0, uint64(block.timestamp + 2 hours), 2 hours);
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

    function testUsedMasksTracked() public {
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.ANY_OF, 0, uint64(block.timestamp + 2 hours), 2 hours);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0, 10 ether);
        vm.prank(alice);
        w.placeBet(M0, 5 ether);
        assertEq(w.usedMasksCount(), 1);
        assertEq(w.usedMaskAt(0), M0);
    }

    function testFuzz_anyOf_claimConservesPot(uint128 aAmt, uint128 bAmt) public {
        vm.assume(aAmt > 0 && bAmt > 0 && uint256(aAmt) + uint256(bAmt) < 1e21);
        ParamutuelWagerV2 w = _create(ParamutuelWagerV2.PayoffPolicy.ANY_OF, 0, uint64(block.timestamp + 2 hours), 2 hours);

        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(bob);
        token.approve(address(w), type(uint256).max);

        vm.prank(alice);
        w.placeBet(M0, uint256(aAmt));
        vm.prank(bob);
        w.placeBet(M1, uint256(bAmt));

        uint256 wBoth = M0 | M1;
        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve(wBoth);

        uint256 before = token.balanceOf(alice) + token.balanceOf(bob);
        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();
        uint256 afterSum = token.balanceOf(alice) + token.balanceOf(bob);
        assertEq(afterSum - before, uint256(aAmt) + uint256(bAmt), "full pot distributed");
    }
}
