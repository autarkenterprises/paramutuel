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

    function approve(address spender, uint256 amount) external virtual returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external virtual returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external virtual returns (bool) {
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

contract FalseReturnERC20 is MockERC20 {
    bool public failTransferFrom;
    bool public failTransfer;

    function setFailTransferFrom(bool v) external {
        failTransferFrom = v;
    }

    function setFailTransfer(bool v) external {
        failTransfer = v;
    }

    function transfer(address to, uint256 amount) external override returns (bool) {
        if (failTransfer) return false;
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external override returns (bool) {
        if (failTransferFrom) return false;
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= amount, "ALLOWANCE");
        allowance[from][msg.sender] = allowed - amount;
        _transfer(from, to, amount);
        return true;
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
    address delegatedResolver = address(0x8888);

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
            address(0), // resolver defaults to proposer
            address(0), // bettingCloser defaults to proposer
            address(0), // resolutionCloser defaults to proposer
            extraRecipients,
            extraBps
        );

        market = ParamutuelMarket(marketAddr);
    }

    function testCreateMarketStoresParameters() public {
        ParamutuelMarket market = _createBasicMarket();

        assertEq(market.proposer(), proposer, "proposer");
        assertEq(market.resolver(), proposer, "resolver");
        assertEq(market.bettingCloser(), proposer, "bettingCloser");
        assertEq(market.resolutionCloser(), proposer, "resolutionCloser");
        assertEq(address(market.collateralToken()), address(token), "collateral");
        assertEq(market.outcomesCount(), 2, "outcomes");
        assertEq(market.bettingCloseTime(), block.timestamp + 2 hours, "bet close");
        assertEq(market.resolutionWindow(), 2 hours, "resolution window");
    }

    function testFactoryConstructorValidation() public {
        vm.expectRevert(bytes("TREASURY"));
        new ParamutuelFactory(address(0), protocolFeeBps, minBettingWindow, minResolutionWindow);

        vm.expectRevert(bytes("FEE"));
        new ParamutuelFactory(treasury, 1_001, minBettingWindow, minResolutionWindow);
    }

    function testMarketsCountIncrements() public {
        assertEq(factory.marketsCount(), 0);
        _createBasicMarket();
        assertEq(factory.marketsCount(), 1);
        _createBasicMarket();
        assertEq(factory.marketsCount(), 2);
    }

    function testBadOutcomesRevert() public {
        string[] memory outcomes = new string[](1);
        outcomes[0] = "ONLY";

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.expectRevert(ParamutuelFactory.BadOutcomes.selector);
        vm.prank(proposer);
        factory.createMarket(
            address(token),
            "bad outcomes",
            outcomes,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );
    }

    function testBadFeeConfigForZeroRecipientOrZeroBpsReverts() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";
        uint64 bettingCloseTime = uint64(block.timestamp + 2 hours);
        uint64 resolutionWindow = 2 hours;

        address[] memory recipients = new address[](1);
        recipients[0] = address(0);
        uint16[] memory bps = new uint16[](1);
        bps[0] = 100;

        vm.expectRevert(ParamutuelFactory.BadFeeConfig.selector);
        vm.prank(proposer);
        factory.createMarket(
            address(token),
            "bad recipient",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            address(0),
            address(0),
            address(0),
            recipients,
            bps
        );

        recipients[0] = extraFeeRecipient;
        bps[0] = 0;
        vm.expectRevert(ParamutuelFactory.BadFeeConfig.selector);
        vm.prank(proposer);
        factory.createMarket(
            address(token),
            "bad bps",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            address(0),
            address(0),
            address(0),
            recipients,
            bps
        );
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

    function testOutcomeTextAndInvalidIndex() public {
        ParamutuelMarket market = _createBasicMarket();
        assertEq(market.outcomeText(0), "YES");
        assertEq(market.outcomeText(1), "NO");

        vm.expectRevert(ParamutuelMarket.InvalidOutcome.selector);
        market.outcomeText(2);
    }

    function testPlaceBetZeroAmountReverts() public {
        ParamutuelMarket market = _createBasicMarket();

        vm.startPrank(bettor1);
        token.approve(address(market), 1 ether);
        vm.expectRevert("AMOUNT");
        market.placeBet(0, 0);
        vm.stopPrank();
    }

    function testPlaceBetWhenClosedRevertsNotOpen() public {
        ParamutuelMarket market = _createBasicMarket();

        vm.warp(market.bettingCloseTime() + 1);
        vm.prank(proposer);
        market.retract();

        vm.startPrank(bettor1);
        token.approve(address(market), 1 ether);
        vm.expectRevert(ParamutuelMarket.NotOpen.selector);
        market.placeBet(0, 1 ether);
        vm.stopPrank();
    }

    function testClaimWhileOpenRevertsNotOpen() public {
        ParamutuelMarket market = _createBasicMarket();
        vm.expectRevert(ParamutuelMarket.NotOpen.selector);
        vm.prank(bettor1);
        market.claim();
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
            address(0),
            address(0),
            address(0),
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
            address(0),
            address(0),
            address(0),
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

        // Before betting close, expire should revert.
        vm.expectRevert(ParamutuelMarket.BettingNotClosed.selector);
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
            address(0),
            address(0),
            address(0),
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
            address(0),
            address(0),
            address(0),
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
            address(0),
            address(0),
            address(0),
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
            address(0),
            address(0),
            address(0),
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
            address(0),
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );
    }

    function testDelegatedResolverSeparateFromProposer() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        uint64 bettingCloseTime = uint64(block.timestamp + 2 hours);
        uint64 resolutionWindow = 2 hours;

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address marketAddr = factory.createMarket(
            address(token),
            "Delegated resolver market",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            delegatedResolver,
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );

        ParamutuelMarket market = ParamutuelMarket(marketAddr);
        assertEq(market.proposer(), proposer);
        assertEq(market.resolver(), delegatedResolver);

        vm.startPrank(bettor1);
        token.approve(address(market), 50 ether);
        market.placeBet(0, 50 ether);
        vm.stopPrank();

        vm.warp(block.timestamp + 3 hours);

        vm.expectRevert(ParamutuelMarket.NotResolver.selector);
        vm.prank(proposer);
        market.resolve(0);

        vm.prank(delegatedResolver);
        market.resolve(0);

        vm.startPrank(bettor1);
        uint256 paid = market.claim();
        vm.stopPrank();
        // Protocol fee 2% on factory => net pot 49 ether to sole winner
        assertEq(paid, 49 ether);
    }

    function testAlreadyFinalizedRevertsForResolveRetractExpire() public {
        ParamutuelMarket market = _createBasicMarket();

        vm.startPrank(bettor1);
        token.approve(address(market), 10 ether);
        market.placeBet(0, 10 ether);
        vm.stopPrank();

        vm.warp(market.bettingCloseTime() + 1);
        vm.prank(proposer);
        market.resolve(0);

        vm.expectRevert(ParamutuelMarket.AlreadyFinalized.selector);
        vm.prank(proposer);
        market.resolve(0);

        vm.expectRevert(ParamutuelMarket.AlreadyFinalized.selector);
        vm.prank(proposer);
        market.retract();

        vm.expectRevert(ParamutuelMarket.AlreadyFinalized.selector);
        vm.prank(bettor2);
        market.expire();
    }

    function testResolvedWithoutWinningBetsCausesNoClaims() public {
        ParamutuelMarket market = _createBasicMarket();

        vm.startPrank(bettor1);
        token.approve(address(market), 20 ether);
        market.placeBet(0, 20 ether);
        vm.stopPrank();

        vm.warp(market.bettingCloseTime() + 1);
        vm.prank(proposer);
        market.resolve(1); // no one bet outcome 1

        vm.expectRevert(ParamutuelMarket.NothingToClaim.selector);
        vm.prank(bettor1);
        market.claim();
    }

    function testWithdrawFeesHappyPathAndDoubleWithdrawRevert() public {
        ParamutuelMarket market = _createBasicMarket();

        vm.startPrank(bettor1);
        token.approve(address(market), 100 ether);
        market.placeBet(0, 100 ether);
        vm.stopPrank();

        vm.startPrank(bettor2);
        token.approve(address(market), 100 ether);
        market.placeBet(1, 100 ether);
        vm.stopPrank();

        vm.warp(market.bettingCloseTime() + 1);
        vm.prank(proposer);
        market.resolve(1);

        assertEq(market.feeBalances(treasury), 4 ether);

        vm.startPrank(treasury);
        uint256 before = token.balanceOf(treasury);
        uint256 withdrawn = market.withdrawFees();
        uint256 afterBal = token.balanceOf(treasury);
        assertEq(withdrawn, 4 ether);
        assertEq(afterBal - before, 4 ether);

        vm.expectRevert(ParamutuelMarket.NothingToClaim.selector);
        market.withdrawFees();
        vm.stopPrank();
    }

    function testWithdrawFeesWithoutAccrualReverts() public {
        ParamutuelMarket market = _createBasicMarket();
        vm.expectRevert(ParamutuelMarket.NothingToClaim.selector);
        vm.prank(extraFeeRecipient);
        market.withdrawFees();
    }

    function testMarketConstructorFeeConfigReverts() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "A";
        outcomes[1] = "B";

        address[] memory recipients = new address[](1);
        recipients[0] = treasury;
        uint16[] memory bpsMismatch = new uint16[](0);

        vm.expectRevert(ParamutuelMarket.FeeConfigMismatch.selector);
        new ParamutuelMarket(
            address(factory),
            proposer,
            proposer,
            proposer,
            proposer,
            address(token),
            "q",
            outcomes,
            uint64(block.timestamp + 10),
            uint64(10),
            uint64(block.timestamp + 20),
            recipients,
            bpsMismatch
        );

        uint16[] memory bpsTooHigh = new uint16[](1);
        bpsTooHigh[0] = 10_001;

        vm.expectRevert(ParamutuelMarket.FeeTooHigh.selector);
        new ParamutuelMarket(
            address(factory),
            proposer,
            proposer,
            proposer,
            proposer,
            address(token),
            "q",
            outcomes,
            uint64(block.timestamp + 10),
            uint64(10),
            uint64(block.timestamp + 20),
            recipients,
            bpsTooHigh
        );
    }

    function testPlaceBetRevertsIfTokenTransferFromReturnsFalse() public {
        FalseReturnERC20 badToken = new FalseReturnERC20();
        badToken.mint(bettor1, 100 ether);

        string[] memory outcomes = new string[](2);
        outcomes[0] = "A";
        outcomes[1] = "B";
        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address marketAddr = factory.createMarket(
            address(badToken),
            "bad transferFrom",
            outcomes,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );
        ParamutuelMarket market = ParamutuelMarket(marketAddr);

        badToken.setFailTransferFrom(true);
        vm.startPrank(bettor1);
        badToken.approve(address(market), 10 ether);
        vm.expectRevert("TRANSFER_FROM");
        market.placeBet(0, 10 ether);
        vm.stopPrank();
    }

    function testClaimRevertsIfTokenTransferReturnsFalse() public {
        FalseReturnERC20 badToken = new FalseReturnERC20();
        badToken.mint(bettor1, 100 ether);

        string[] memory outcomes = new string[](2);
        outcomes[0] = "A";
        outcomes[1] = "B";
        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address marketAddr = factory.createMarket(
            address(badToken),
            "bad transfer claim",
            outcomes,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );
        ParamutuelMarket market = ParamutuelMarket(marketAddr);

        vm.startPrank(bettor1);
        badToken.approve(address(market), 10 ether);
        market.placeBet(0, 10 ether);
        vm.stopPrank();

        vm.warp(market.bettingCloseTime() + 1);
        vm.prank(proposer);
        market.resolve(0);

        badToken.setFailTransfer(true);
        vm.expectRevert("TRANSFER");
        vm.prank(bettor1);
        market.claim();
    }

    function testWithdrawFeesRevertsIfTokenTransferReturnsFalse() public {
        FalseReturnERC20 badToken = new FalseReturnERC20();
        badToken.mint(bettor1, 100 ether);

        string[] memory outcomes = new string[](2);
        outcomes[0] = "A";
        outcomes[1] = "B";

        address[] memory extraRecipients = new address[](1);
        extraRecipients[0] = extraFeeRecipient;
        uint16[] memory extraBps = new uint16[](1);
        extraBps[0] = 300;

        vm.prank(proposer);
        address marketAddr = factory.createMarket(
            address(badToken),
            "bad transfer withdraw",
            outcomes,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );
        ParamutuelMarket market = ParamutuelMarket(marketAddr);

        vm.startPrank(bettor1);
        badToken.approve(address(market), 100 ether);
        market.placeBet(0, 100 ether);
        vm.stopPrank();

        vm.warp(market.bettingCloseTime() + 1);
        vm.prank(proposer);
        market.resolve(0);

        badToken.setFailTransfer(true);
        vm.expectRevert("TRANSFER");
        vm.prank(treasury);
        market.withdrawFees();
    }

    function testCloseBettingEarlyStopsPlaceBet() public {
        ParamutuelMarket market = _createBasicMarket();

        vm.prank(proposer);
        market.closeBetting();
        assertTrue(market.bettingClosedByAuthority());

        vm.startPrank(bettor1);
        token.approve(address(market), 1 ether);
        vm.expectRevert(ParamutuelMarket.BettingClosed.selector);
        market.placeBet(0, 1 ether);
        vm.stopPrank();
    }

    function testOnlyBettingCloserCanCloseBetting() public {
        ParamutuelMarket market = _createBasicMarket();

        vm.expectRevert(ParamutuelMarket.NotBettingCloser.selector);
        vm.prank(bettor1);
        market.closeBetting();
    }

    function testCloseResolutionWindowAllowsEarlyExpire() public {
        ParamutuelMarket market = _createBasicMarket();

        vm.startPrank(bettor1);
        token.approve(address(market), 10 ether);
        market.placeBet(0, 10 ether);
        vm.stopPrank();

        vm.warp(market.bettingCloseTime() + 1);
        vm.prank(proposer);
        market.closeResolutionWindow();
        assertTrue(market.resolutionWindowClosedByAuthority());

        vm.expectRevert(ParamutuelMarket.ResolutionWindowOver.selector);
        vm.prank(proposer);
        market.resolve(0);

        vm.prank(bettor2);
        market.expire();

        assertEq(uint256(market.state()), uint256(ParamutuelMarket.State.Retracted));
    }

    function testCloseResolutionWindowBeforeBettingClosedReverts() public {
        ParamutuelMarket market = _createBasicMarket();

        vm.expectRevert(ParamutuelMarket.BettingNotClosed.selector);
        vm.prank(proposer);
        market.closeResolutionWindow();
    }

    function testDelegatedBettingAndResolutionClosers() public {
        address bettingOracle = address(0xA11);
        address resolutionOracle = address(0xA12);

        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        uint64 bettingCloseTime = uint64(block.timestamp + 2 hours);
        uint64 resolutionWindow = 2 hours;

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address marketAddr = factory.createMarket(
            address(token),
            "Delegated closers",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            address(0),
            bettingOracle,
            resolutionOracle,
            extraRecipients,
            extraBps
        );

        ParamutuelMarket market = ParamutuelMarket(marketAddr);
        assertEq(market.bettingCloser(), bettingOracle);
        assertEq(market.resolutionCloser(), resolutionOracle);

        vm.expectRevert(ParamutuelMarket.BettingNotClosed.selector);
        vm.prank(resolutionOracle);
        market.closeResolutionWindow();

        vm.prank(bettingOracle);
        market.closeBetting();

        vm.startPrank(bettor1);
        token.approve(address(market), 1 ether);
        vm.expectRevert(ParamutuelMarket.BettingClosed.selector);
        market.placeBet(0, 1 ether);
        vm.stopPrank();

        vm.prank(resolutionOracle);
        market.closeResolutionWindow();

        vm.prank(bettor2);
        market.expire();
        assertEq(uint256(market.state()), uint256(ParamutuelMarket.State.Retracted));
    }

    function testNoMaxBettingAndResolutionRequireClosers() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address marketAddr = factory.createMarket(
            address(token),
            "No max windows",
            outcomes,
            0, // no betting time cap
            0, // no resolution time cap
            address(0),
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );
        ParamutuelMarket market = ParamutuelMarket(marketAddr);
        assertEq(market.bettingCloseTime(), 0);
        assertEq(market.resolutionWindow(), 0);
        assertEq(market.resolutionDeadline(), 0);

        vm.startPrank(bettor1);
        token.approve(address(market), 10 ether);
        market.placeBet(0, 10 ether);
        vm.stopPrank();

        vm.warp(block.timestamp + 365 days);
        vm.startPrank(bettor2);
        token.approve(address(market), 1 ether);
        market.placeBet(1, 1 ether); // still open after one year
        vm.stopPrank();

        vm.expectRevert(ParamutuelMarket.BettingNotClosed.selector);
        vm.prank(proposer);
        market.resolve(0);

        vm.prank(proposer);
        market.closeBetting();

        vm.warp(block.timestamp + 365 days);
        vm.prank(proposer);
        market.resolve(0); // still resolvable after another year (no resolution max)
    }

    function testNoMaxBettingWithFiniteResolutionWindowStartsAtAuthorityClose() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address marketAddr = factory.createMarket(
            address(token),
            "Closer starts resolution timer",
            outcomes,
            0, // no betting cap
            1 hours, // finite resolution window
            address(0),
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );
        ParamutuelMarket market = ParamutuelMarket(marketAddr);
        assertEq(market.resolutionWindow(), 1 hours);
        assertEq(market.resolutionDeadline(), 0); // no scheduled deadline at creation

        vm.startPrank(bettor1);
        token.approve(address(market), 10 ether);
        market.placeBet(0, 10 ether);
        vm.stopPrank();

        vm.warp(block.timestamp + 30 days);
        vm.prank(proposer);
        market.closeBetting();
        uint64 closedAt = market.bettingClosedAtByAuthority();
        assertEq(closedAt, block.timestamp);

        vm.warp(closedAt + 30 minutes);
        vm.prank(proposer);
        market.resolve(0);
    }

    function testNoMaxResolutionCannotExpireUntilResolutionCloserCloses() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address marketAddr = factory.createMarket(
            address(token),
            "No max resolution requires closer",
            outcomes,
            uint64(block.timestamp + 2 hours),
            0, // no resolution time cap
            address(0),
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );
        ParamutuelMarket market = ParamutuelMarket(marketAddr);

        vm.startPrank(bettor1);
        token.approve(address(market), 10 ether);
        market.placeBet(0, 10 ether);
        vm.stopPrank();

        vm.warp(market.bettingCloseTime() + 100 days);
        vm.expectRevert(ParamutuelMarket.ResolutionWindowOver.selector);
        vm.prank(bettor2);
        market.expire();

        vm.prank(proposer);
        market.closeResolutionWindow();
        vm.prank(bettor2);
        market.expire();

        assertEq(uint256(market.state()), uint256(ParamutuelMarket.State.Retracted));
    }

    function testCloseBettingAfterTimestampIsNoopWithoutAuthorityFlag() public {
        ParamutuelMarket market = _createBasicMarket();
        vm.warp(market.bettingCloseTime() + 1);

        vm.prank(proposer);
        market.closeBetting(); // should no-op because already closed by time

        assertFalse(market.bettingClosedByAuthority(), "authority flag unchanged");
        assertEq(market.bettingClosedAtByAuthority(), 0, "no authority close timestamp");
    }

    function testOnlyResolutionCloserCanCloseResolutionWindow() public {
        ParamutuelMarket market = _createBasicMarket();
        vm.warp(market.bettingCloseTime() + 1);

        vm.expectRevert(ParamutuelMarket.NotResolutionCloser.selector);
        vm.prank(bettor1);
        market.closeResolutionWindow();
    }

    function testCloseResolutionWindowIdempotent() public {
        ParamutuelMarket market = _createBasicMarket();
        vm.warp(market.bettingCloseTime() + 1);

        vm.prank(proposer);
        market.closeResolutionWindow();
        assertTrue(market.resolutionWindowClosedByAuthority());

        vm.prank(proposer);
        market.closeResolutionWindow(); // idempotent
        assertTrue(market.resolutionWindowClosedByAuthority());
    }

    function testNoMaxCreationStillAssignsNonZeroLifecycleAuthorities() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address marketAddr = factory.createMarket(
            address(token),
            "No max default authorities",
            outcomes,
            0,
            0,
            address(0),
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );
        ParamutuelMarket market = ParamutuelMarket(marketAddr);

        assertEq(market.resolver(), proposer);
        assertEq(market.bettingCloser(), proposer);
        assertEq(market.resolutionCloser(), proposer);
        assertTrue(market.resolver() != address(0), "resolver non-zero");
        assertTrue(market.bettingCloser() != address(0), "betting closer non-zero");
        assertTrue(market.resolutionCloser() != address(0), "resolution closer non-zero");
    }
}

