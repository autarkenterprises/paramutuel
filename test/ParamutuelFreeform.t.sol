// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import {ParamutuelFactoryFreeform} from "../src/ParamutuelFactoryFreeform.sol";
import {ParamutuelWagerFreeform} from "../src/ParamutuelWagerFreeform.sol";

contract MockERC20Freeform {
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

/// @notice ADR-0009 freeform wager + factory tests (TDD target suite).
contract ParamutuelFreeformTest is Test {
    ParamutuelFactoryFreeform public factory;
    MockERC20Freeform public token;

    address treasury = address(0x1000);
    address proposer = address(0x2000);
    address bettor1 = address(0x3000);
    address bettor2 = address(0x4000);

    uint16 protocolFeeBps = 100;
    uint64 minBettingWindow = 1 hours;
    uint64 minResolutionWindow = 1 hours;

    function setUp() public {
        vm.warp(1000);
        factory = new ParamutuelFactoryFreeform(treasury, protocolFeeBps, minBettingWindow, minResolutionWindow);
        token = new MockERC20Freeform();
        token.mint(proposer, 1_000_000 ether);
        token.mint(bettor1, 1_000_000 ether);
        token.mint(bettor2, 1_000_000 ether);
    }

    function _futureWindows() internal view returns (uint64 close, uint64 resWin) {
        close = uint64(block.timestamp + 2 hours);
        resWin = 2 hours;
    }

    function _createViaFactory() internal returns (ParamutuelWagerFreeform w) {
        (uint64 close, uint64 resWin) = _futureWindows();
        address[] memory extra = new address[](0);
        uint16[] memory extraBps = new uint16[](0);
        vm.prank(proposer);
        address wa = factory.createFreeformWager(
            address(token),
            "Who wins?",
            close,
            resWin,
            address(0),
            proposer,
            proposer,
            extra,
            extraBps
        );
        w = ParamutuelWagerFreeform(wa);
    }

    /// @dev Direct deploy for tests that need a custom `maxDistinctAnswers` cap.
    function _deployWager(uint256 maxDistinct) internal returns (ParamutuelWagerFreeform w) {
        (uint64 close, uint64 resWin) = _futureWindows();
        uint64 deadline = close + resWin;
        address[] memory fr = new address[](0);
        uint16[] memory fb = new uint16[](0);
        w = new ParamutuelWagerFreeform(
            address(this),
            proposer,
            proposer,
            proposer,
            proposer,
            address(token),
            "direct",
            close,
            resWin,
            deadline,
            fr,
            fb,
            maxDistinct
        );
    }

    function test_factory_wager_exposes_protocol_constants() public {
        ParamutuelWagerFreeform w = _createViaFactory();
        assertEq(w.MAX_ANSWER_BYTES(), 1024);
        assertEq(w.maxDistinctAnswers(), 1024);
        assertEq(w.outcomesCount(), 0);
        assertEq(factory.WAGER_MAX_DISTINCT_ANSWERS(), 1024);
    }

    function test_placeBet_empty_answer_reverts() public {
        ParamutuelWagerFreeform w = _createViaFactory();
        vm.startPrank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.expectRevert(ParamutuelWagerFreeform.EmptyAnswer.selector);
        w.placeBet("", 1 ether);
        vm.stopPrank();
    }

    function test_placeBet_answer_too_long_reverts() public {
        ParamutuelWagerFreeform w = _createViaFactory();
        bytes memory buf = new bytes(1025);
        for (uint256 i; i < 1025; i++) {
            buf[i] = bytes1(uint8(97 + (i % 26)));
        }
        string memory longAnswer = string(buf);
        vm.startPrank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.expectRevert(ParamutuelWagerFreeform.AnswerTooLong.selector);
        w.placeBet(longAnswer, 1 ether);
        vm.stopPrank();
    }

    function test_placeBet_at_max_length_succeeds() public {
        ParamutuelWagerFreeform w = _createViaFactory();
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

    function test_two_bettors_same_answer_share_winner_pool() public {
        ParamutuelWagerFreeform w = _createViaFactory();
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

    function test_near_miss_loser_cannot_claim() public {
        ParamutuelWagerFreeform w = _createViaFactory();
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
        vm.expectRevert(ParamutuelWagerFreeform.NothingToClaim.selector);
        w.claim();
    }

    function test_resolve_unbacked_answer_reverts_NoWinningStake() public {
        ParamutuelWagerFreeform w = _createViaFactory();
        vm.prank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor1);
        w.placeBet("A", 1 ether);

        vm.prank(proposer);
        w.closeBetting();

        vm.prank(proposer);
        vm.expectRevert(ParamutuelWagerFreeform.NoWinningStake.selector);
        w.resolve("B");
    }

    function test_TooManyDistinctAnswers_reverts() public {
        ParamutuelWagerFreeform w = _deployWager(3);
        vm.startPrank(bettor1);
        token.approve(address(w), type(uint256).max);
        w.placeBet("a", 1);
        w.placeBet("b", 1);
        w.placeBet("c", 1);
        vm.expectRevert(ParamutuelWagerFreeform.TooManyDistinctAnswers.selector);
        w.placeBet("d", 1);
        vm.stopPrank();
    }

    function test_retract_pro_rata_refund() public {
        ParamutuelWagerFreeform w = _createViaFactory();
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
        assertEq(token.balanceOf(bettor1) - before, net);
    }

    function test_expire_after_resolution_window() public {
        ParamutuelWagerFreeform w = _createViaFactory();
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
        ParamutuelWagerFreeform w = _createViaFactory();
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
        vm.expectRevert(ParamutuelWagerFreeform.NothingToClaim.selector);
        w.claim();
    }

    function test_non_resolver_cannot_resolve() public {
        ParamutuelWagerFreeform w = _createViaFactory();
        vm.prank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor1);
        w.placeBet("z", 1 ether);
        vm.prank(proposer);
        w.closeBetting();
        vm.prank(bettor1);
        vm.expectRevert(ParamutuelWagerFreeform.NotResolver.selector);
        w.resolve("z");
    }

    function test_usedAnswerIds_tracked() public {
        ParamutuelWagerFreeform w = _createViaFactory();
        vm.prank(bettor1);
        token.approve(address(w), type(uint256).max);
        vm.prank(bettor1);
        w.placeBet("p", 1);
        vm.prank(bettor1);
        w.placeBet("q", 1);
        assertEq(w.usedAnswerIdsCount(), 2);
    }
}
