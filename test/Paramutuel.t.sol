// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import {ParamutuelFactory} from "../src/ParamutuelFactory.sol";
import {ParamutuelMarket} from "../src/ParamutuelMarket.sol";

contract MockERC20 {
    string public name = "MockToken";
    string public symbol = "MOCK";
    uint8 public decimals = 18;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= amount, "ALLOWANCE");
        allowance[from][msg.sender] = allowed - amount;
        _transfer(from, to, amount);
        return true;
    }

    function _transfer(address from, address to, uint256 amount) internal {
        require(balanceOf[from] >= amount, "BAL");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }
}

contract ParamutuelTest is Test {
    ParamutuelFactory factory;
    MockERC20 token;

    address treasury = address(0x1000);
    address proposer = address(0x2000);
    address bettor1 = address(0x3000);
    address bettor2 = address(0x4000);
    address bettor3 = address(0x6000);
    address bettor4 = address(0x7000);
    address extraFeeRecipient = address(0x5000);

    uint16 protocolFeeBps = 200; // 2%
    uint64 minBettingWindow = 1 hours;
    uint64 minResolutionWindow = 1 hours;

    function setUp() public {
        vm.warp(1000);

        factory = new ParamutuelFactory(treasury, protocolFeeBps, minBettingWindow, minResolutionWindow);
        token = new MockERC20();

        uint256 initial = 1_000_000 ether;
        token.mint(bettor1, initial);
        token.mint(bettor2, initial);
        token.mint(bettor3, initial);
        token.mint(bettor4, initial);
    }

    function _createBasicMarket() internal returns (ParamutuelMarket market) {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        uint64 bettingCloseTime = uint64(block.timestamp + 2 hours);
        uint64 resolutionWindow = 2 hours;

        address[] memory extraRecipients = new address[](1);
        extraRecipients[0] = extraFeeRecipient;
        uint16[] memory extraBps = new uint16[](1);
        extraBps[0] = 300; // 3%, combined with 2% protocol => 5% total

        vm.prank(proposer);
        address marketAddr = factory.createMarket(
            address(token),
            "Will team A win?",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            extraRecipients,
            extraBps
        );

        market = ParamutuelMarket(marketAddr);
    }

    function testCreateMarketStoresParameters() public {
        ParamutuelMarket market = _createBasicMarket();

        assertEq(market.resolver(), proposer, "resolver");
        assertEq(address(market.collateralToken()), address(token), "collateral");
        assertEq(market.outcomesCount(), 2, "outcomes");
        assertEq(market.bettingCloseTime(), block.timestamp + 2 hours, "bet close");
    }

    function testBetResolveAndClaimPayouts() public {
        ParamutuelMarket market = _createBasicMarket();

        uint256 amount1 = 100 ether;
        uint256 amount2 = 300 ether;

        vm.startPrank(bettor1);
        token.approve(address(market), amount1);
        market.placeBet(0, amount1); // YES
        vm.stopPrank();

        vm.startPrank(bettor2);
        token.approve(address(market), amount2);
        market.placeBet(1, amount2); // NO
        vm.stopPrank();

        // Move past betting close but before resolution deadline
        vm.warp(block.timestamp + 3 hours);

        // Proposer resolves to NO (outcome 1)
        vm.prank(proposer);
        market.resolve(1);

        // total pot = 400
        // total fee = 5% = 20
        // net pot = 380, all to NO bettors (bettor2 with 300 stake)
        uint256 before = token.balanceOf(bettor2);
        vm.prank(bettor2);
        uint256 paid = market.claim();
        uint256 afterBal = token.balanceOf(bettor2);

        assertEq(paid, 380 ether, "paid");
        assertEq(afterBal - before, 380 ether, "balance delta");

        // Bettor1 loses and gets nothing
        vm.expectRevert(ParamutuelMarket.NothingToClaim.selector);
        vm.prank(bettor1);
        market.claim();

        // Fees: 20 total, split 2:3 between treasury and extraFeeRecipient
        // Protocol (2/5 of 20 = 8), extra (12)
        assertEq(market.feeBalances(treasury), 8 ether, "treasury fee balance");
        assertEq(market.feeBalances(extraFeeRecipient), 12 ether, "extra fee balance");
    }

    function testRetractRefundsMinusFees() public {
        ParamutuelMarket market = _createBasicMarket();

        uint256 amount1 = 100 ether;
        uint256 amount2 = 300 ether;

        vm.startPrank(bettor1);
        token.approve(address(market), amount1);
        market.placeBet(0, amount1);
        vm.stopPrank();

        vm.startPrank(bettor2);
        token.approve(address(market), amount2);
        market.placeBet(1, amount2);
        vm.stopPrank();

        vm.warp(block.timestamp + 3 hours);

        vm.prank(proposer);
        market.retract();

        // total pot = 400, total fee 5% = 20
        // bettor1 stake 100 -> fee 5 = refund 95
        // bettor2 stake 300 -> fee 15 = refund 285
        vm.startPrank(bettor1);
        uint256 before1 = token.balanceOf(bettor1);
        uint256 paid1 = market.claim();
        uint256 after1 = token.balanceOf(bettor1);
        vm.stopPrank();

        vm.startPrank(bettor2);
        uint256 before2 = token.balanceOf(bettor2);
        uint256 paid2 = market.claim();
        uint256 after2 = token.balanceOf(bettor2);
        vm.stopPrank();

        assertEq(paid1, 95 ether);
        assertEq(after1 - before1, 95 ether);

        assertEq(paid2, 285 ether);
        assertEq(after2 - before2, 285 ether);
    }

    function testExpireAfterDeadline() public {
        ParamutuelMarket market = _createBasicMarket();

        uint256 amount = 100 ether;
        vm.startPrank(bettor1);
        token.approve(address(market), amount);
        market.placeBet(0, amount);
        vm.stopPrank();

        // Jump beyond resolution deadline
        uint64 bettingCloseTime = market.bettingCloseTime();
        uint64 resolutionDeadline = market.resolutionDeadline();
        vm.warp(resolutionDeadline + 1);

        // Anyone can expire
        vm.prank(address(0xDEAD));
        market.expire();

        // Single bettor receives refund minus fee (5)
        vm.startPrank(bettor1);
        uint256 before = token.balanceOf(bettor1);
        uint256 paid = market.claim();
        uint256 afterBal = token.balanceOf(bettor1);
        vm.stopPrank();

        assertEq(paid, 95 ether);
        assertEq(afterBal - before, 95 ether);
    }

    function testCannotBetAfterCloseOrResolveBeforeClose() public {
        ParamutuelMarket market = _createBasicMarket();

        uint256 amount = 10 ether;
        vm.startPrank(bettor1);
        token.approve(address(market), amount);
        market.placeBet(0, amount);
        vm.stopPrank();

        // Cannot resolve before betting closes
        vm.expectRevert(ParamutuelMarket.BettingNotClosed.selector);
        vm.prank(proposer);
        market.resolve(0);

        // Move past close
        vm.warp(market.bettingCloseTime() + 1);

        // Cannot bet after close
        vm.startPrank(bettor2);
        token.approve(address(market), amount);
        vm.expectRevert(ParamutuelMarket.BettingClosed.selector);
        market.placeBet(0, amount);
        vm.stopPrank();
    }

    function testOnlyResolverCanResolveOrRetract() public {
        ParamutuelMarket market = _createBasicMarket();

        vm.warp(market.bettingCloseTime() + 1);

        vm.expectRevert(ParamutuelMarket.NotResolver.selector);
        vm.prank(bettor1);
        market.resolve(0);

        vm.expectRevert(ParamutuelMarket.NotResolver.selector);
        vm.prank(bettor1);
        market.retract();
    }

    function testMultiOutcomeMultiBettorParimutuelPayouts() public {
        // Create a 3-outcome market
        string[] memory outcomes = new string[](3);
        outcomes[0] = "HOME_WIN";
        outcomes[1] = "DRAW";
        outcomes[2] = "AWAY_WIN";

        uint64 bettingCloseTime = uint64(block.timestamp + 2 hours);
        uint64 resolutionWindow = 2 hours;

        address[] memory extraRecipients = new address[](1);
        extraRecipients[0] = extraFeeRecipient;
        uint16[] memory extraBps = new uint16[](1);
        extraBps[0] = 300; // 3% extra, 2% protocol -> 5% total

        vm.prank(proposer);
        address marketAddr = factory.createMarket(
            address(token),
            "What is the match outcome?",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            extraRecipients,
            extraBps
        );

        ParamutuelMarket market = ParamutuelMarket(marketAddr);

        // Bets:
        // bettor1: 100 on outcome 0 (HOME_WIN)
        // bettor2: 50 on outcome 1 (DRAW)
        // bettor3: 150 on outcome 2 (AWAY_WIN)
        // bettor4: 50 on outcome 2 (AWAY_WIN)
        //
        // Totals:
        // outcome0 = 100
        // outcome1 = 50
        // outcome2 = 200
        // totalPot = 350
        // fees = 5% => 17.5
        // netPot = 332.5
        //
        // Suppose outcome2 wins:
        // totalWinningStake = 200
        // bettor3 stake 150 -> 150/200 * 332.5 = 249.375
        // bettor4 stake 50  -> 50/200 * 332.5 = 83.125

        vm.startPrank(bettor1);
        token.approve(address(market), 100 ether);
        market.placeBet(0, 100 ether);
        vm.stopPrank();

        vm.startPrank(bettor2);
        token.approve(address(market), 50 ether);
        market.placeBet(1, 50 ether);
        vm.stopPrank();

        vm.startPrank(bettor3);
        token.approve(address(market), 150 ether);
        market.placeBet(2, 150 ether);
        vm.stopPrank();

        vm.startPrank(bettor4);
        token.approve(address(market), 50 ether);
        market.placeBet(2, 50 ether);
        vm.stopPrank();

        // Resolve after close
        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        market.resolve(2);

        // Check pot and winning stake as internal sanity
        assertEq(market.totalPot(), 350 ether, "total pot");
        assertEq(market.outcomeTotals(2), 200 ether, "winning outcome total");

        // winner claims
        vm.startPrank(bettor3);
        uint256 b3Before = token.balanceOf(bettor3);
        uint256 paid3 = market.claim();
        uint256 b3After = token.balanceOf(bettor3);
        vm.stopPrank();

        vm.startPrank(bettor4);
        uint256 b4Before = token.balanceOf(bettor4);
        uint256 paid4 = market.claim();
        uint256 b4After = token.balanceOf(bettor4);
        vm.stopPrank();

        // Use approximate checks due to fractional payouts (forge-std's assertApproxEqAbs)
        // Expected: 249.375 and 83.125
        assertApproxEqAbs(paid3, 249.375 ether, 1 wei, "bettor3 payout");
        assertApproxEqAbs(b3After - b3Before, 249.375 ether, 1 wei, "bettor3 balance delta");

        assertApproxEqAbs(paid4, 83.125 ether, 1 wei, "bettor4 payout");
        assertApproxEqAbs(b4After - b4Before, 83.125 ether, 1 wei, "bettor4 balance delta");

        // Losing bettors get NothingToClaim
        vm.expectRevert(ParamutuelMarket.NothingToClaim.selector);
        vm.prank(bettor1);
        market.claim();

        vm.expectRevert(ParamutuelMarket.NothingToClaim.selector);
        vm.prank(bettor2);
        market.claim();
    }

    function testZeroFeeMarketPaysFullPotToWinners() public {
        // Deploy a factory with zero protocol fee
        ParamutuelFactory zeroFeeFactory =
            new ParamutuelFactory(treasury, 0, minBettingWindow, minResolutionWindow);

        string[] memory outcomes = new string[](2);
        outcomes[0] = "A";
        outcomes[1] = "B";

        uint64 bettingCloseTime = uint64(block.timestamp + 2 hours);
        uint64 resolutionWindow = 2 hours;

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address marketAddr = zeroFeeFactory.createMarket(
            address(token),
            "Zero fee market",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            extraRecipients,
            extraBps
        );

        ParamutuelMarket market = ParamutuelMarket(marketAddr);

        // Two bettors on different outcomes, one winner takes all 100% of pot
        vm.startPrank(bettor1);
        token.approve(address(market), 100 ether);
        market.placeBet(0, 100 ether);
        vm.stopPrank();

        vm.startPrank(bettor2);
        token.approve(address(market), 300 ether);
        market.placeBet(1, 300 ether);
        vm.stopPrank();

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        market.resolve(1);

        assertEq(market.totalPot(), 400 ether, "pot");

        uint256 before = token.balanceOf(bettor2);
        vm.prank(bettor2);
        uint256 paid = market.claim();
        uint256 afterBal = token.balanceOf(bettor2);

        // No fees -> full pot to winner
        assertEq(paid, 400 ether);
        assertEq(afterBal - before, 400 ether);
    }

    function testDoubleClaimReverts() public {
        ParamutuelMarket market = _createBasicMarket();

        uint256 amount = 100 ether;
        vm.startPrank(bettor1);
        token.approve(address(market), amount);
        market.placeBet(0, amount);
        vm.stopPrank();

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        market.resolve(0);

        vm.startPrank(bettor1);
        market.claim();
        vm.expectRevert(ParamutuelMarket.NothingToClaim.selector);
        market.claim();
        vm.stopPrank();
    }

    function testNoBetsThenRetractOrExpireLeavesNothingToClaim() public {
        ParamutuelMarket market = _createBasicMarket();

        // No bets placed
        vm.warp(block.timestamp + 3 hours);

        // Retract by resolver
        vm.prank(proposer);
        market.retract();

        // Any claimant should revert because userTotalBet is zero
        vm.expectRevert(ParamutuelMarket.NothingToClaim.selector);
        vm.prank(bettor1);
        market.claim();

        // Create another market and let it expire without bets
        ParamutuelMarket market2 = _createBasicMarket();
        vm.warp(market2.resolutionDeadline() + 1);
        vm.prank(bettor1);
        market2.expire();

        vm.expectRevert(ParamutuelMarket.NothingToClaim.selector);
        vm.prank(bettor1);
        market2.claim();
    }

    function testCannotResolveOrRetractAfterDeadline() public {
        ParamutuelMarket market = _createBasicMarket();

        // Move beyond resolution deadline
        vm.warp(market.resolutionDeadline() + 1);

        vm.expectRevert(ParamutuelMarket.ResolutionWindowOver.selector);
        vm.prank(proposer);
        market.resolve(0);

        vm.expectRevert(ParamutuelMarket.ResolutionWindowOver.selector);
        vm.prank(proposer);
        market.retract();
    }

    function testCannotExpireBeforeDeadline() public {
        ParamutuelMarket market = _createBasicMarket();

        // Before deadline, expire should revert
        vm.expectRevert(ParamutuelMarket.ResolutionWindowOver.selector);
        vm.prank(bettor1);
        market.expire();
    }

    function testInvalidOutcomeIndexReverts() public {
        ParamutuelMarket market = _createBasicMarket();

        // index 2 is invalid for 2-outcome market
        vm.startPrank(bettor1);
        token.approve(address(market), 10 ether);
        vm.expectRevert(ParamutuelMarket.InvalidOutcome.selector);
        market.placeBet(2, 10 ether);
        vm.stopPrank();

        vm.warp(block.timestamp + 3 hours);
        vm.expectRevert(ParamutuelMarket.InvalidOutcome.selector);
        vm.prank(proposer);
        market.resolve(2);
    }

    function testFeeConfigTooHighReverts() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        uint64 bettingCloseTime = uint64(block.timestamp + 2 hours);
        uint64 resolutionWindow = 2 hours;

        // protocolFeeBps = 200; extra 900 => 1100 > MAX_TOTAL_FEE_BPS (1000)
        address[] memory extraRecipients = new address[](1);
        extraRecipients[0] = extraFeeRecipient;
        uint16[] memory extraBps = new uint16[](1);
        extraBps[0] = 900;

        vm.expectRevert(ParamutuelFactory.BadFeeConfig.selector);
        vm.prank(proposer);
        factory.createMarket(
            address(token),
            "Too high fee",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            extraRecipients,
            extraBps
        );
    }

    function testTooManyOutcomesReverts() public {
        uint256 n = 65; // > MAX_OUTCOMES (64)
        string[] memory outcomes = new string[](n);
        for (uint256 i; i < n; i++) {
            outcomes[i] = "O";
        }

        uint64 bettingCloseTime = uint64(block.timestamp + 2 hours);
        uint64 resolutionWindow = 2 hours;

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.expectRevert(ParamutuelFactory.TooManyOutcomes.selector);
        vm.prank(proposer);
        factory.createMarket(
            address(token),
            "Too many outcomes",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            extraRecipients,
            extraBps
        );
    }

    function testMismatchedFeeArraysReverts() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        uint64 bettingCloseTime = uint64(block.timestamp + 2 hours);
        uint64 resolutionWindow = 2 hours;

        address[] memory extraRecipients = new address[](2);
        extraRecipients[0] = extraFeeRecipient;
        extraRecipients[1] = address(0x9999);
        uint16[] memory extraBps = new uint16[](1);
        extraBps[0] = 300;

        vm.expectRevert(ParamutuelFactory.BadFeeConfig.selector);
        vm.prank(proposer);
        factory.createMarket(
            address(token),
            "Mismatched fee arrays",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            extraRecipients,
            extraBps
        );
    }

    function testBettingAndResolutionWindowsTooShortRevert() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        uint64 nowTs = uint64(block.timestamp);

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        // Betting window too short
        vm.expectRevert(ParamutuelFactory.WindowTooShort.selector);
        vm.prank(proposer);
        factory.createMarket(
            address(token),
            "Short betting window",
            outcomes,
            nowTs + minBettingWindow - 1,
            minResolutionWindow,
            extraRecipients,
            extraBps
        );

        // Resolution window too short
        vm.expectRevert(ParamutuelFactory.WindowTooShort.selector);
        vm.prank(proposer);
        factory.createMarket(
            address(token),
            "Short resolution window",
            outcomes,
            nowTs + minBettingWindow,
            minResolutionWindow - 1,
            extraRecipients,
            extraBps
        );
    }
}

