// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import {ParamutuelFactoryV3} from "../src/ParamutuelFactoryV3.sol";
import {ParamutuelWagerV3} from "../src/ParamutuelWagerV3.sol";

/// @dev Minimal ERC20 mock — fixed-unit, no rebasing, no fee-on-transfer. The
///      V3 protocol only guarantees correctness against tokens with these
///      properties (see ADR-0010 §Assumptions).
contract MockERC20V3Free {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
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

    function transfer(address to, uint256 amount) external returns (bool) {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

/// @notice Behavioural parity suite for ADR-0010 V3 freeform wagers. Ports the
///         pre-migration `ParamutuelFreeform.t.sol` coverage onto the unified
///         V3 factory (`createFreeformWager`). Cryptographic properties of
///         `answerId` live in `ParamutuelV3AnswerId.t.sol`.
///
///         Freeform mode accepts arbitrary UTF-8 strings bounded by
///         `MAX_ANSWER_BYTES` (1024). The factory hard-codes the pot's
///         `maxDistinctAnswers` to `WAGER_MAX_DISTINCT_ANSWERS` (1024); direct
///         construction is used in one test to validate the distinct-cap path
///         at a smaller bound.
contract ParamutuelV3FreeformTest is Test {
    ParamutuelFactoryV3 factory;
    MockERC20V3Free token;

    address treasury = address(0x1000);
    address proposer = address(0x2000);
    address bettor1 = address(0x3000);
    address bettor2 = address(0x4000);
    // Extra bettors for the four-actor Rosebud worked example. Distinct
    // addresses so each `claim()` resolves cleanly without one bettor's
    // ticket leaking into another's pool view.
    address bettor3 = address(0x5000);
    address bettor4 = address(0x6000);

    uint16 protocolFeeBps = 100; // 1%
    uint64 minBettingWindow = 1 hours;
    uint64 minResolutionWindow = 1 hours;

    function setUp() public {
        vm.warp(1000);
        factory = new ParamutuelFactoryV3(treasury, protocolFeeBps, minBettingWindow, minResolutionWindow);
        token = new MockERC20V3Free();
        token.mint(proposer, 1_000_000 ether);
        token.mint(bettor1, 1_000_000 ether);
        token.mint(bettor2, 1_000_000 ether);
        token.mint(bettor3, 1_000_000 ether);
        token.mint(bettor4, 1_000_000 ether);
    }

    function _futureWindows() internal view returns (uint64 close, uint64 resWin) {
        close = uint64(block.timestamp + 2 hours);
        resWin = 2 hours;
    }

    function _createViaFactory() internal returns (ParamutuelWagerV3 w) {
        (uint64 close, uint64 resWin) = _futureWindows();
        vm.prank(proposer);
        address wa = factory.createFreeformWager(
            address(token),
            "Who wins?",
            close,
            resWin,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        w = ParamutuelWagerV3(wa);
    }

    /// @dev Direct construction lets us dial `maxDistinctAnswers` below the
    ///      factory's 1024 ceiling so we can cover `TooManyDistinctAnswers`
    ///      without generating a thousand bets.
    function _deployWagerDirect(uint256 maxDistinct) internal returns (ParamutuelWagerV3 w) {
        (uint64 close, uint64 resWin) = _futureWindows();
        uint64 deadline = close + resWin;
        string[] memory emptyOutcomes;
        w = new ParamutuelWagerV3(
            ParamutuelWagerV3.WagerMode.Freeform,
            address(this),
            proposer,
            proposer, // resolver
            proposer, // bettingCloser
            proposer, // resolutionCloser
            address(token),
            "direct",
            emptyOutcomes,
            ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER,
            0,
            close,
            resWin,
            deadline,
            new address[](0),
            new uint16[](0),
            maxDistinct
        );
    }

    // ---- Protocol constants ----------------------------------------------

    function test_factory_wager_exposes_protocol_constants() public {
        ParamutuelWagerV3 w = _createViaFactory();
        assertEq(w.MAX_ANSWER_BYTES(), 1024);
        assertEq(w.maxDistinctAnswers(), 1024);
        assertEq(w.outcomesCount(), 0, "freeform wagers publish zero outcomes");
        assertEq(factory.WAGER_MAX_DISTINCT_ANSWERS(), 1024);
        assertEq(uint256(w.MODE()), uint256(ParamutuelWagerV3.WagerMode.Freeform));
    }

    // ---- Answer validation on placeBet -----------------------------------

    function test_placeBet_empty_answer_reverts() public {
        ParamutuelWagerV3 w = _createViaFactory();
        vm.startPrank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.expectRevert(ParamutuelWagerV3.EmptyAnswer.selector);
        w.placeBet("", 1 ether);
        vm.stopPrank();
    }

    function test_placeBet_answer_too_long_reverts() public {
        ParamutuelWagerV3 w = _createViaFactory();
        bytes memory buf = new bytes(1025);
        for (uint256 i; i < 1025; i++) {
            buf[i] = bytes1(uint8(97 + (i % 26)));
        }
        string memory longAnswer = string(buf);
        vm.startPrank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.expectRevert(ParamutuelWagerV3.AnswerTooLong.selector);
        w.placeBet(longAnswer, 1 ether);
        vm.stopPrank();
    }

    function test_placeBet_at_max_length_succeeds() public {
        ParamutuelWagerV3 w = _createViaFactory();
        bytes memory buf = new bytes(1024);
        for (uint256 i; i < 1024; i++) {
            buf[i] = bytes1(uint8(97 + (i % 26)));
        }
        string memory ans = string(buf);
        vm.startPrank(bettor1);
        token.approve(address(w), type(uint256).max);
        w.placeBet(ans, 1 ether);
        vm.stopPrank();
        assertEq(w.totalPot(), 1 ether);
    }

    function test_wrong_mode_placeBet_uint_reverts() public {
        ParamutuelWagerV3 w = _createViaFactory();
        vm.prank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor1);
        vm.expectRevert(ParamutuelWagerV3.WrongMode.selector);
        w.placeBet(uint256(1), 1 ether);
    }

    // ---- Payoff / claim semantics -----------------------------------------

    /// @notice Two bettors on the same answer split the winner pool pro-rata
    ///         to their stakes (after protocol fee).
    function test_two_bettors_same_answer_share_winner_pool() public {
        ParamutuelWagerV3 w = _createViaFactory();
        vm.prank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor2);
        token.approve(address(w), type(uint256).max);

        vm.prank(bettor1);
        w.placeBet("YES", 3 ether);
        vm.prank(bettor2);
        w.placeBet("YES", 1 ether);

        vm.prank(proposer);
        w.closeBetting();
        vm.prank(proposer);
        w.resolve("YES");

        uint256 fee = (4 ether * 100) / 10_000;
        uint256 net = 4 ether - fee;

        uint256 b1Before = token.balanceOf(bettor1);
        vm.prank(bettor1);
        w.claim();
        assertEq(token.balanceOf(bettor1) - b1Before, (net * 3 ether) / 4 ether);

        uint256 b2Before = token.balanceOf(bettor2);
        vm.prank(bettor2);
        w.claim();
        assertEq(token.balanceOf(bettor2) - b2Before, (net * 1 ether) / 4 ether);
    }

    /// @notice Freeform answer IDs are case-sensitive: "YES" and "yes" hash to
    ///         distinct ids. The near-miss bettor cannot claim against the
    ///         winning id.
    function test_near_miss_loser_cannot_claim() public {
        ParamutuelWagerV3 w = _createViaFactory();
        vm.prank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor2);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor1);
        w.placeBet("YES", 1 ether);
        vm.prank(bettor2);
        w.placeBet("yes", 1 ether);

        vm.prank(proposer);
        w.closeBetting();
        vm.prank(proposer);
        w.resolve("YES");

        vm.prank(bettor1);
        w.claim();

        vm.prank(bettor2);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();
    }

    function test_resolve_unbacked_answer_reverts_NoWinningStake() public {
        ParamutuelWagerV3 w = _createViaFactory();
        vm.prank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor1);
        w.placeBet("A", 1 ether);

        vm.prank(proposer);
        w.closeBetting();

        vm.prank(proposer);
        vm.expectRevert(ParamutuelWagerV3.NoWinningStake.selector);
        w.resolve("B");
    }

    function test_TooManyDistinctAnswers_reverts() public {
        ParamutuelWagerV3 w = _deployWagerDirect(3);
        vm.startPrank(bettor1);
        token.approve(address(w), type(uint256).max);
        w.placeBet("a", 1);
        w.placeBet("b", 1);
        w.placeBet("c", 1);
        vm.expectRevert(ParamutuelWagerV3.TooManyDistinctAnswers.selector);
        w.placeBet("d", 1);
        vm.stopPrank();
    }

    function test_retract_pro_rata_refund() public {
        ParamutuelWagerV3 w = _createViaFactory();
        vm.prank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor1);
        w.placeBet("x", 10 ether);

        vm.prank(proposer);
        w.closeBetting();
        vm.prank(proposer);
        w.retract();

        uint256 fee = (10 ether * 100) / 10_000;
        uint256 net = 10 ether - fee;
        uint256 before = token.balanceOf(bettor1);
        vm.prank(bettor1);
        w.claim();
        assertEq(token.balanceOf(bettor1) - before, net, "retract refunds net pot pro-rata");
    }

    function test_expire_after_resolution_window() public {
        ParamutuelWagerV3 w = _createViaFactory();
        vm.prank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor1);
        w.placeBet("x", 5 ether);

        vm.prank(proposer);
        w.closeBetting();
        vm.prank(proposer);
        w.closeResolutionWindow();

        vm.warp(uint256(w.resolutionDeadline()) + 1);
        w.expire();

        uint256 fee = (5 ether * 100) / 10_000;
        uint256 net = 5 ether - fee;
        vm.prank(bettor1);
        w.claim();
        assertEq(token.balanceOf(bettor1), 1_000_000 ether - 5 ether + net);
    }

    function test_double_claim_reverts() public {
        ParamutuelWagerV3 w = _createViaFactory();
        vm.prank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor1);
        w.placeBet("win", 1 ether);
        vm.prank(proposer);
        w.closeBetting();
        vm.prank(proposer);
        w.resolve("win");
        vm.prank(bettor1);
        w.claim();
        vm.prank(bettor1);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();
    }

    function test_non_resolver_cannot_resolve() public {
        ParamutuelWagerV3 w = _createViaFactory();
        vm.prank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor1);
        w.placeBet("z", 1 ether);
        vm.prank(proposer);
        w.closeBetting();
        vm.prank(bettor1);
        vm.expectRevert(ParamutuelWagerV3.NotResolver.selector);
        w.resolve("z");
    }

    function test_usedAnswerIds_tracked() public {
        ParamutuelWagerV3 w = _createViaFactory();
        vm.prank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor1);
        w.placeBet("p", 1);
        vm.prank(bettor1);
        w.placeBet("q", 1);
        assertEq(w.usedAnswerIdsCount(), 2);
    }

    /// @notice Mirrors the freeform worked example in
    ///         `docs/PAYOUT-CALCULATION.md` Part C. The point of the example
    ///         is that `answerId = keccak256(0x03 || bytes(answer))` is
    ///         compared **byte-for-byte** — "rosebud" and "Rosebud" hash to
    ///         distinct ids, so the case-mismatched bettor loses despite
    ///         being semantically correct. Fees are zero so the documented
    ///         numbers (333 / 166 / 1 wei dust) round-trip exactly; the
    ///         setUp() factory bakes in a 1% fee so we deploy a fresh
    ///         fee-free factory here.
    function testFreeform_documentationWorkedExample_rosebud() public {
        ParamutuelFactoryV3 feeFreeFactory =
            new ParamutuelFactoryV3(treasury, 0, minBettingWindow, minResolutionWindow);
        (uint64 close, uint64 resWin) = _futureWindows();
        vm.prank(proposer);
        address wa = feeFreeFactory.createFreeformWager(
            address(token),
            "What was Rosebud?",
            close,
            resWin,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        ParamutuelWagerV3 w = ParamutuelWagerV3(wa);

        vm.prank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor2);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor3);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor4);
        token.approve(address(w), type(uint256).max);

        // bettor1 = Alice, bettor2 = Bob, bettor3 = Carol, bettor4 = Dave
        // (same role assignment as the Markdown example; the on-chain
        // behaviour does not depend on the names, only the bytes).
        vm.prank(bettor1);
        w.placeBet("rosebud", 200); // matches winner
        vm.prank(bettor2);
        w.placeBet("rosebud", 100); // matches winner
        vm.prank(bettor3);
        w.placeBet("Rosebud", 150); // capital R — distinct id, loses
        vm.prank(bettor4);
        w.placeBet("a sled", 50);   // unrelated — loses

        assertEq(w.totalPot(), 500);

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        w.resolve("rosebud");

        // floor(stake * netPot / winningPool) per bettor.
        uint256 b1Before = token.balanceOf(bettor1);
        uint256 b2Before = token.balanceOf(bettor2);
        vm.prank(bettor1);
        w.claim();
        vm.prank(bettor2);
        w.claim();

        assertEq(token.balanceOf(bettor1) - b1Before, 333, "alice: floor(200*500/300)");
        assertEq(token.balanceOf(bettor2) - b2Before, 166, "bob: floor(100*500/300)");

        // Both losers revert with NothingToClaim — Carol because her
        // case-mismatched bytes hash to a non-winning id, Dave because his
        // answer never matched.
        vm.prank(bettor3);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();
        vm.prank(bettor4);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();

        // 333 + 166 = 499; netPot was 500; 1 wei dust as documented.
        assertEq(token.balanceOf(address(w)), 1, "documented integer-division dust");
    }
}
