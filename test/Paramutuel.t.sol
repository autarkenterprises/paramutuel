// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import {ParamutuelFactory} from "../src/ParamutuelFactory.sol";
import {ParamutuelWager} from "../src/ParamutuelWager.sol";

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
        token.mint(proposer, initial);
        token.mint(bettor1, initial);
        token.mint(bettor2, initial);
        token.mint(bettor3, initial);
        token.mint(bettor4, initial);
    }

    function _createBasicWager() internal returns (ParamutuelWager wager) {
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
        address wagerAddr = factory.createWager(
            address(token),
            "Will team A win?",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            address(0), // resolver defaults to proposer
            proposer, // explicit betting closer
            proposer, // explicit resolution closer
            extraRecipients,
            extraBps
        );

        wager = ParamutuelWager(wagerAddr);
    }

    function testCreateWagerStoresParameters() public {
        ParamutuelWager wager = _createBasicWager();

        assertEq(wager.proposer(), proposer, "proposer");
        assertEq(wager.resolver(), proposer, "resolver");
        assertEq(wager.bettingCloser(), proposer, "bettingCloser");
        assertEq(wager.resolutionCloser(), proposer, "resolutionCloser");
        assertEq(address(wager.collateralToken()), address(token), "collateral");
        assertEq(wager.outcomesCount(), 2, "outcomes");
        assertEq(wager.bettingCloseTime(), block.timestamp + 2 hours, "bet close");
        assertEq(wager.resolutionWindow(), 2 hours, "resolution window");
    }

    function testCreateWagerSupportsSeededBets() public {
        string[] memory outcomes = new string[](3);
        outcomes[0] = "A";
        outcomes[1] = "B";
        outcomes[2] = "C";

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        uint256[] memory seedOutcomeIndices = new uint256[](3);
        seedOutcomeIndices[0] = 0;
        seedOutcomeIndices[1] = 1;
        seedOutcomeIndices[2] = 2;
        uint256[] memory seedAmounts = new uint256[](3);
        seedAmounts[0] = 10 ether;
        seedAmounts[1] = 20 ether;
        seedAmounts[2] = 30 ether;

        vm.startPrank(proposer);
        token.approve(address(factory), 60 ether);
        address wagerAddr = factory.createWager(
            address(token),
            "Seeded wager",
            outcomes,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            proposer,
            proposer,
            extraRecipients,
            extraBps,
            seedOutcomeIndices,
            seedAmounts
        );
        vm.stopPrank();

        ParamutuelWager wager = ParamutuelWager(wagerAddr);
        assertEq(wager.totalPot(), 60 ether, "seeded total pot");
        assertEq(wager.outcomeTotals(0), 10 ether, "seeded outcome 0");
        assertEq(wager.outcomeTotals(1), 20 ether, "seeded outcome 1");
        assertEq(wager.outcomeTotals(2), 30 ether, "seeded outcome 2");
        assertEq(wager.userTotalBet(proposer), 60 ether, "seeded proposer user total");
        assertEq(wager.bets(proposer, 0), 10 ether, "seeded proposer stake o0");
        assertEq(wager.bets(proposer, 1), 20 ether, "seeded proposer stake o1");
        assertEq(wager.bets(proposer, 2), 30 ether, "seeded proposer stake o2");
        assertEq(token.balanceOf(address(wager)), 60 ether, "wager token balance includes seeds");
    }

    function testCreateWagerSeedRevertsForInvalidOutcome() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";
        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);
        uint256[] memory seedOutcomeIndices = new uint256[](1);
        uint256[] memory seedAmounts = new uint256[](1);
        seedOutcomeIndices[0] = 2; // invalid
        seedAmounts[0] = 1 ether;

        vm.startPrank(proposer);
        token.approve(address(factory), 1 ether);
        vm.expectRevert(ParamutuelWager.InvalidOutcome.selector);
        factory.createWager(
            address(token),
            "bad seed outcome",
            outcomes,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            proposer,
            proposer,
            extraRecipients,
            extraBps,
            seedOutcomeIndices,
            seedAmounts
        );
        vm.stopPrank();
    }

    function testCreateWagerSeedBadConfigReverts() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";
        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        uint256[] memory seedOutcomeIndices = new uint256[](1);
        seedOutcomeIndices[0] = 0;
        uint256[] memory seedAmountsMismatch = new uint256[](0);

        vm.expectRevert(ParamutuelFactory.BadSeedConfig.selector);
        vm.prank(proposer);
        factory.createWager(
            address(token),
            "seed mismatch",
            outcomes,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            proposer,
            proposer,
            extraRecipients,
            extraBps,
            seedOutcomeIndices,
            seedAmountsMismatch
        );

        uint256[] memory seedAmountsZero = new uint256[](1);
        seedAmountsZero[0] = 0;
        vm.expectRevert(ParamutuelFactory.BadSeedConfig.selector);
        vm.prank(proposer);
        factory.createWager(
            address(token),
            "seed zero amount",
            outcomes,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            proposer,
            proposer,
            extraRecipients,
            extraBps,
            seedOutcomeIndices,
            seedAmountsZero
        );
    }

    function testFactoryConstructorValidation() public {
        vm.expectRevert(bytes("TREASURY"));
        new ParamutuelFactory(address(0), protocolFeeBps, minBettingWindow, minResolutionWindow);

        vm.expectRevert(bytes("FEE"));
        new ParamutuelFactory(treasury, 10_001, minBettingWindow, minResolutionWindow);
    }

    function testWagersCountIncrements() public {
        assertEq(factory.wagersCount(), 0);
        _createBasicWager();
        assertEq(factory.wagersCount(), 1);
        _createBasicWager();
        assertEq(factory.wagersCount(), 2);
    }

    function testBadOutcomesRevert() public {
        string[] memory outcomes = new string[](1);
        outcomes[0] = "ONLY";

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.expectRevert(ParamutuelFactory.BadOutcomes.selector);
        vm.prank(proposer);
        factory.createWager(
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
        factory.createWager(
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
        factory.createWager(
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
        ParamutuelWager wager = _createBasicWager();

        uint256 amount1 = 100 ether;
        uint256 amount2 = 300 ether;

        vm.startPrank(bettor1);
        token.approve(address(wager), amount1);
        wager.placeBet(0, amount1); // YES
        vm.stopPrank();

        vm.startPrank(bettor2);
        token.approve(address(wager), amount2);
        wager.placeBet(1, amount2); // NO
        vm.stopPrank();

        // Move past betting close but before resolution deadline
        vm.warp(block.timestamp + 3 hours);

        // Proposer resolves to NO (outcome 1)
        vm.prank(proposer);
        wager.resolve(1);

        // total pot = 400
        // total fee = 5% = 20
        // net pot = 380, all to NO bettors (bettor2 with 300 stake)
        uint256 before = token.balanceOf(bettor2);
        vm.prank(bettor2);
        uint256 paid = wager.claim();
        uint256 afterBal = token.balanceOf(bettor2);

        assertEq(paid, 380 ether, "paid");
        assertEq(afterBal - before, 380 ether, "balance delta");

        // Bettor1 loses and gets nothing
        vm.expectRevert(ParamutuelWager.NothingToClaim.selector);
        vm.prank(bettor1);
        wager.claim();

        // Fees: 20 total, split 2:3 between treasury and extraFeeRecipient
        // Protocol (2/5 of 20 = 8), extra (12)
        assertEq(wager.feeBalances(treasury), 8 ether, "treasury fee balance");
        assertEq(wager.feeBalances(extraFeeRecipient), 12 ether, "extra fee balance");
    }

    function testRetractRefundsMinusFees() public {
        ParamutuelWager wager = _createBasicWager();

        uint256 amount1 = 100 ether;
        uint256 amount2 = 300 ether;

        vm.startPrank(bettor1);
        token.approve(address(wager), amount1);
        wager.placeBet(0, amount1);
        vm.stopPrank();

        vm.startPrank(bettor2);
        token.approve(address(wager), amount2);
        wager.placeBet(1, amount2);
        vm.stopPrank();

        vm.warp(block.timestamp + 3 hours);

        vm.prank(proposer);
        wager.retract();

        // total pot = 400, total fee 5% = 20
        // bettor1 stake 100 -> fee 5 = refund 95
        // bettor2 stake 300 -> fee 15 = refund 285
        vm.startPrank(bettor1);
        uint256 before1 = token.balanceOf(bettor1);
        uint256 paid1 = wager.claim();
        uint256 after1 = token.balanceOf(bettor1);
        vm.stopPrank();

        vm.startPrank(bettor2);
        uint256 before2 = token.balanceOf(bettor2);
        uint256 paid2 = wager.claim();
        uint256 after2 = token.balanceOf(bettor2);
        vm.stopPrank();

        assertEq(paid1, 95 ether);
        assertEq(after1 - before1, 95 ether);

        assertEq(paid2, 285 ether);
        assertEq(after2 - before2, 285 ether);
    }

    function testRetractRoundingCannotOverpayAndBreakFeeWithdrawals() public {
        ParamutuelWager wager = _createBasicWager();

        // 5% fee wager, low-denomination stakes expose floor-rounding edge cases.
        uint256 amount1 = 1;
        uint256 amount2 = 19;

        vm.startPrank(bettor1);
        token.approve(address(wager), amount1);
        wager.placeBet(0, amount1);
        vm.stopPrank();

        vm.startPrank(bettor2);
        token.approve(address(wager), amount2);
        wager.placeBet(1, amount2);
        vm.stopPrank();

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        wager.retract();

        uint256 netPot = wager.totalPot() - ((wager.totalPot() * wager.totalFeeBps()) / 10_000);

        vm.startPrank(bettor1);
        uint256 paid1 = wager.claim();
        vm.stopPrank();

        vm.startPrank(bettor2);
        uint256 paid2 = wager.claim();
        vm.stopPrank();

        // Total payouts must never exceed net pot.
        assertLe(paid1 + paid2, netPot, "claims overpay net pot");

        uint256 extraFee = wager.feeBalances(extraFeeRecipient);
        assertEq(extraFee, 1, "expected non-zero fee balance");

        vm.startPrank(extraFeeRecipient);
        uint256 withdrawn = wager.withdrawFees();
        vm.stopPrank();
        assertEq(withdrawn, extraFee, "withdraw fee amount mismatch");
    }

    function testExpireAfterDeadline() public {
        ParamutuelWager wager = _createBasicWager();

        uint256 amount = 100 ether;
        vm.startPrank(bettor1);
        token.approve(address(wager), amount);
        wager.placeBet(0, amount);
        vm.stopPrank();

        // Jump beyond resolution deadline
        uint64 resolutionDeadline = wager.resolutionDeadline();
        vm.warp(resolutionDeadline + 1);

        // Anyone can expire
        vm.prank(address(0xDEAD));
        wager.expire();

        // Single bettor receives refund minus fee (5)
        vm.startPrank(bettor1);
        uint256 before = token.balanceOf(bettor1);
        uint256 paid = wager.claim();
        uint256 afterBal = token.balanceOf(bettor1);
        vm.stopPrank();

        assertEq(paid, 95 ether);
        assertEq(afterBal - before, 95 ether);
    }

    function testCannotBetAfterCloseOrResolveBeforeClose() public {
        ParamutuelWager wager = _createBasicWager();

        uint256 amount = 10 ether;
        vm.startPrank(bettor1);
        token.approve(address(wager), amount);
        wager.placeBet(0, amount);
        vm.stopPrank();

        // Cannot resolve before betting closes
        vm.expectRevert(ParamutuelWager.BettingNotClosed.selector);
        vm.prank(proposer);
        wager.resolve(0);

        // Move past close
        vm.warp(wager.bettingCloseTime() + 1);

        // Cannot bet after close
        vm.startPrank(bettor2);
        token.approve(address(wager), amount);
        vm.expectRevert(ParamutuelWager.BettingClosed.selector);
        wager.placeBet(0, amount);

        uint256[] memory outcomeIndices = new uint256[](1);
        outcomeIndices[0] = 0;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = amount;
        vm.expectRevert(ParamutuelWager.BettingClosed.selector);
        wager.placeBets(outcomeIndices, amounts);
        vm.stopPrank();
    }

    function testOnlyResolverCanResolveOrRetract() public {
        ParamutuelWager wager = _createBasicWager();

        vm.warp(wager.bettingCloseTime() + 1);

        vm.expectRevert(ParamutuelWager.NotResolver.selector);
        vm.prank(bettor1);
        wager.resolve(0);

        vm.expectRevert(ParamutuelWager.NotResolver.selector);
        vm.prank(bettor1);
        wager.retract();
    }

    function testOutcomeTextAndInvalidIndex() public {
        ParamutuelWager wager = _createBasicWager();
        assertEq(wager.outcomeText(0), "YES");
        assertEq(wager.outcomeText(1), "NO");

        vm.expectRevert(ParamutuelWager.InvalidOutcome.selector);
        wager.outcomeText(2);
    }

    function testPlaceBetZeroAmountReverts() public {
        ParamutuelWager wager = _createBasicWager();

        vm.startPrank(bettor1);
        token.approve(address(wager), 1 ether);
        vm.expectRevert("AMOUNT");
        wager.placeBet(0, 0);
        vm.stopPrank();
    }

    function testPlaceBetsAcrossMultipleOutcomes() public {
        string[] memory outcomes = new string[](3);
        outcomes[0] = "A";
        outcomes[1] = "B";
        outcomes[2] = "C";

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address wagerAddr = factory.createWager(
            address(token),
            "Batch bet wager",
            outcomes,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            proposer,
            proposer,
            extraRecipients,
            extraBps
        );
        ParamutuelWager wager = ParamutuelWager(wagerAddr);

        uint256[] memory outcomeIndices = new uint256[](3);
        outcomeIndices[0] = 0;
        outcomeIndices[1] = 1;
        outcomeIndices[2] = 2;
        uint256[] memory amounts = new uint256[](3);
        amounts[0] = 5 ether;
        amounts[1] = 15 ether;
        amounts[2] = 25 ether;

        vm.startPrank(bettor1);
        token.approve(address(wager), 45 ether);
        wager.placeBets(outcomeIndices, amounts);
        vm.stopPrank();

        assertEq(wager.totalPot(), 45 ether);
        assertEq(wager.userTotalBet(bettor1), 45 ether);
        assertEq(wager.outcomeTotals(0), 5 ether);
        assertEq(wager.outcomeTotals(1), 15 ether);
        assertEq(wager.outcomeTotals(2), 25 ether);
        assertEq(wager.bets(bettor1, 0), 5 ether);
        assertEq(wager.bets(bettor1, 1), 15 ether);
        assertEq(wager.bets(bettor1, 2), 25 ether);
    }

    function testPlaceBetsRevertsForBadInputs() public {
        ParamutuelWager wager = _createBasicWager();

        uint256[] memory outcomeIndices = new uint256[](2);
        outcomeIndices[0] = 0;
        outcomeIndices[1] = 1;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = 1 ether;

        vm.startPrank(bettor1);
        token.approve(address(wager), 10 ether);
        vm.expectRevert(ParamutuelWager.ArrayLengthMismatch.selector);
        wager.placeBets(outcomeIndices, amounts);
        vm.stopPrank();

        uint256[] memory badIndices = new uint256[](1);
        badIndices[0] = 2; // invalid for binary wager
        uint256[] memory badAmounts = new uint256[](1);
        badAmounts[0] = 1 ether;
        vm.startPrank(bettor1);
        token.approve(address(wager), 10 ether);
        vm.expectRevert(ParamutuelWager.InvalidOutcome.selector);
        wager.placeBets(badIndices, badAmounts);
        vm.stopPrank();

        uint256[] memory zeroAmountIndices = new uint256[](1);
        zeroAmountIndices[0] = 0;
        uint256[] memory zeroAmounts = new uint256[](1);
        zeroAmounts[0] = 0;
        vm.startPrank(bettor1);
        token.approve(address(wager), 10 ether);
        vm.expectRevert(bytes("AMOUNT"));
        wager.placeBets(zeroAmountIndices, zeroAmounts);
        vm.stopPrank();
    }

    function testPlaceBetWhenClosedRevertsNotOpen() public {
        ParamutuelWager wager = _createBasicWager();

        vm.warp(wager.bettingCloseTime() + 1);
        vm.prank(proposer);
        wager.retract();

        vm.startPrank(bettor1);
        token.approve(address(wager), 1 ether);
        vm.expectRevert(ParamutuelWager.NotOpen.selector);
        wager.placeBet(0, 1 ether);
        vm.stopPrank();
    }

    function testClaimWhileOpenRevertsNotOpen() public {
        ParamutuelWager wager = _createBasicWager();
        vm.expectRevert(ParamutuelWager.NotOpen.selector);
        vm.prank(bettor1);
        wager.claim();
    }

    function testMultiOutcomeMultiBettorParimutuelPayouts() public {
        // Create a 3-outcome wager
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
        address wagerAddr = factory.createWager(
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

        ParamutuelWager wager = ParamutuelWager(wagerAddr);

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
        token.approve(address(wager), 100 ether);
        wager.placeBet(0, 100 ether);
        vm.stopPrank();

        vm.startPrank(bettor2);
        token.approve(address(wager), 50 ether);
        wager.placeBet(1, 50 ether);
        vm.stopPrank();

        vm.startPrank(bettor3);
        token.approve(address(wager), 150 ether);
        wager.placeBet(2, 150 ether);
        vm.stopPrank();

        vm.startPrank(bettor4);
        token.approve(address(wager), 50 ether);
        wager.placeBet(2, 50 ether);
        vm.stopPrank();

        // Resolve after close
        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        wager.resolve(2);

        // Check pot and winning stake as internal sanity
        assertEq(wager.totalPot(), 350 ether, "total pot");
        assertEq(wager.outcomeTotals(2), 200 ether, "winning outcome total");

        // winner claims
        vm.startPrank(bettor3);
        uint256 b3Before = token.balanceOf(bettor3);
        uint256 paid3 = wager.claim();
        uint256 b3After = token.balanceOf(bettor3);
        vm.stopPrank();

        vm.startPrank(bettor4);
        uint256 b4Before = token.balanceOf(bettor4);
        uint256 paid4 = wager.claim();
        uint256 b4After = token.balanceOf(bettor4);
        vm.stopPrank();

        // Use approximate checks due to fractional payouts (forge-std's assertApproxEqAbs)
        // Expected: 249.375 and 83.125
        assertApproxEqAbs(paid3, 249.375 ether, 1 wei, "bettor3 payout");
        assertApproxEqAbs(b3After - b3Before, 249.375 ether, 1 wei, "bettor3 balance delta");

        assertApproxEqAbs(paid4, 83.125 ether, 1 wei, "bettor4 payout");
        assertApproxEqAbs(b4After - b4Before, 83.125 ether, 1 wei, "bettor4 balance delta");

        // Losing bettors get NothingToClaim
        vm.expectRevert(ParamutuelWager.NothingToClaim.selector);
        vm.prank(bettor1);
        wager.claim();

        vm.expectRevert(ParamutuelWager.NothingToClaim.selector);
        vm.prank(bettor2);
        wager.claim();
    }

    function testZeroFeeWagerPaysFullPotToWinners() public {
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
        address wagerAddr = zeroFeeFactory.createWager(
            address(token),
            "Zero fee wager",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            address(0),
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );

        ParamutuelWager wager = ParamutuelWager(wagerAddr);

        // Two bettors on different outcomes, one winner takes all 100% of pot
        vm.startPrank(bettor1);
        token.approve(address(wager), 100 ether);
        wager.placeBet(0, 100 ether);
        vm.stopPrank();

        vm.startPrank(bettor2);
        token.approve(address(wager), 300 ether);
        wager.placeBet(1, 300 ether);
        vm.stopPrank();

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        wager.resolve(1);

        assertEq(wager.totalPot(), 400 ether, "pot");

        uint256 before = token.balanceOf(bettor2);
        vm.prank(bettor2);
        uint256 paid = wager.claim();
        uint256 afterBal = token.balanceOf(bettor2);

        // No fees -> full pot to winner
        assertEq(paid, 400 ether);
        assertEq(afterBal - before, 400 ether);
    }

    function testDoubleClaimReverts() public {
        ParamutuelWager wager = _createBasicWager();

        uint256 amount = 100 ether;
        vm.startPrank(bettor1);
        token.approve(address(wager), amount);
        wager.placeBet(0, amount);
        vm.stopPrank();

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        wager.resolve(0);

        vm.startPrank(bettor1);
        wager.claim();
        vm.expectRevert(ParamutuelWager.NothingToClaim.selector);
        wager.claim();
        vm.stopPrank();
    }

    function testNoBetsThenRetractOrExpireLeavesNothingToClaim() public {
        ParamutuelWager wager = _createBasicWager();

        // No bets placed
        vm.warp(block.timestamp + 3 hours);

        // Retract by resolver
        vm.prank(proposer);
        wager.retract();

        // Any claimant should revert because userTotalBet is zero
        vm.expectRevert(ParamutuelWager.NothingToClaim.selector);
        vm.prank(bettor1);
        wager.claim();

        // Create another wager and let it expire without bets
        ParamutuelWager wager2 = _createBasicWager();
        vm.warp(wager2.resolutionDeadline() + 1);
        vm.prank(bettor1);
        wager2.expire();

        vm.expectRevert(ParamutuelWager.NothingToClaim.selector);
        vm.prank(bettor1);
        wager2.claim();
    }

    function testCannotResolveOrRetractAfterDeadline() public {
        ParamutuelWager wager = _createBasicWager();

        // Move beyond resolution deadline
        vm.warp(wager.resolutionDeadline() + 1);

        vm.expectRevert(ParamutuelWager.ResolutionWindowOver.selector);
        vm.prank(proposer);
        wager.resolve(0);

        vm.expectRevert(ParamutuelWager.ResolutionWindowOver.selector);
        vm.prank(proposer);
        wager.retract();
    }

    function testCannotExpireBeforeDeadline() public {
        ParamutuelWager wager = _createBasicWager();

        // Before betting close, expire should revert.
        vm.expectRevert(ParamutuelWager.BettingNotClosed.selector);
        vm.prank(bettor1);
        wager.expire();
    }

    function testInvalidOutcomeIndexReverts() public {
        ParamutuelWager wager = _createBasicWager();

        // index 2 is invalid for 2-outcome wager
        vm.startPrank(bettor1);
        token.approve(address(wager), 10 ether);
        vm.expectRevert(ParamutuelWager.InvalidOutcome.selector);
        wager.placeBet(2, 10 ether);
        vm.stopPrank();

        vm.warp(block.timestamp + 3 hours);
        vm.expectRevert(ParamutuelWager.InvalidOutcome.selector);
        vm.prank(proposer);
        wager.resolve(2);
    }

    function testFeeConfigTooHighReverts() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        uint64 bettingCloseTime = uint64(block.timestamp + 2 hours);
        uint64 resolutionWindow = 2 hours;

        // protocolFeeBps = 200; extra 9900 => 10100 > MAX_TOTAL_FEE_BPS (10000)
        address[] memory extraRecipients = new address[](1);
        extraRecipients[0] = extraFeeRecipient;
        uint16[] memory extraBps = new uint16[](1);
        extraBps[0] = 9900;

        vm.expectRevert(ParamutuelFactory.BadFeeConfig.selector);
        vm.prank(proposer);
        factory.createWager(
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

    function testFactoryConstructorAllowsFullFeeCap() public {
        ParamutuelFactory f = new ParamutuelFactory(treasury, 10_000, minBettingWindow, minResolutionWindow);
        assertEq(f.protocolFeeBps(), 10_000);
        assertEq(f.MAX_TOTAL_FEE_BPS(), 10_000);
    }

    function testFullFeeResolvePathPaysOnlyBeneficiaries() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        uint64 bettingCloseTime = uint64(block.timestamp + 2 hours);
        uint64 resolutionWindow = 2 hours;

        // protocolFeeBps = 200, extra 9800 => 10000 total (100%).
        address[] memory extraRecipients = new address[](1);
        extraRecipients[0] = extraFeeRecipient;
        uint16[] memory extraBps = new uint16[](1);
        extraBps[0] = 9800;

        vm.prank(proposer);
        address wagerAddr = factory.createWager(
            address(token),
            "Charity resolve",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            address(0),
            proposer,
            proposer,
            extraRecipients,
            extraBps
        );
        ParamutuelWager wager = ParamutuelWager(wagerAddr);

        vm.startPrank(bettor1);
        token.approve(address(wager), 100 ether);
        wager.placeBet(0, 100 ether);
        vm.stopPrank();

        vm.startPrank(bettor2);
        token.approve(address(wager), 50 ether);
        wager.placeBet(1, 50 ether);
        vm.stopPrank();

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        wager.resolve(0);

        uint256 winnerBefore = token.balanceOf(bettor1);
        vm.prank(bettor1);
        wager.claim();
        uint256 winnerAfter = token.balanceOf(bettor1);
        assertEq(winnerAfter - winnerBefore, 0, "winner payout must be zero at 100% fees");

        assertEq(wager.feeBalances(treasury), 3 ether, "treasury gets 2%");
        assertEq(wager.feeBalances(extraFeeRecipient), 147 ether, "beneficiary gets 98%");

        uint256 treasuryBefore = token.balanceOf(treasury);
        vm.prank(treasury);
        wager.withdrawFees();
        uint256 treasuryAfter = token.balanceOf(treasury);
        assertEq(treasuryAfter - treasuryBefore, 3 ether);

        uint256 beneficiaryBefore = token.balanceOf(extraFeeRecipient);
        vm.prank(extraFeeRecipient);
        wager.withdrawFees();
        uint256 beneficiaryAfter = token.balanceOf(extraFeeRecipient);
        assertEq(beneficiaryAfter - beneficiaryBefore, 147 ether);

        assertEq(token.balanceOf(address(wager)), 0, "all funds disbursed");
    }

    function testFullFeeRetractPathPaysOnlyBeneficiaries() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        uint64 bettingCloseTime = uint64(block.timestamp + 2 hours);
        uint64 resolutionWindow = 2 hours;

        address[] memory extraRecipients = new address[](1);
        extraRecipients[0] = extraFeeRecipient;
        uint16[] memory extraBps = new uint16[](1);
        extraBps[0] = 9800;

        vm.prank(proposer);
        address wagerAddr = factory.createWager(
            address(token),
            "Charity retract",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            address(0),
            proposer,
            proposer,
            extraRecipients,
            extraBps
        );
        ParamutuelWager wager = ParamutuelWager(wagerAddr);

        vm.startPrank(bettor1);
        token.approve(address(wager), 70 ether);
        wager.placeBet(0, 70 ether);
        vm.stopPrank();

        vm.startPrank(bettor2);
        token.approve(address(wager), 30 ether);
        wager.placeBet(1, 30 ether);
        vm.stopPrank();

        vm.warp(block.timestamp + 3 hours);
        vm.prank(proposer);
        wager.retract();

        uint256 b1Before = token.balanceOf(bettor1);
        vm.prank(bettor1);
        wager.claim();
        assertEq(token.balanceOf(bettor1) - b1Before, 0, "retract claim must be zero at 100% fees");

        uint256 b2Before = token.balanceOf(bettor2);
        vm.prank(bettor2);
        wager.claim();
        assertEq(token.balanceOf(bettor2) - b2Before, 0, "retract claim must be zero at 100% fees");

        assertEq(wager.feeBalances(treasury), 2 ether, "treasury gets 2%");
        assertEq(wager.feeBalances(extraFeeRecipient), 98 ether, "beneficiary gets 98%");
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
        factory.createWager(
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
        factory.createWager(
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
        factory.createWager(
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
        factory.createWager(
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
        address wagerAddr = factory.createWager(
            address(token),
            "Delegated resolver wager",
            outcomes,
            bettingCloseTime,
            resolutionWindow,
            delegatedResolver,
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );

        ParamutuelWager wager = ParamutuelWager(wagerAddr);
        assertEq(wager.proposer(), proposer);
        assertEq(wager.resolver(), delegatedResolver);

        vm.startPrank(bettor1);
        token.approve(address(wager), 50 ether);
        wager.placeBet(0, 50 ether);
        vm.stopPrank();

        vm.warp(block.timestamp + 3 hours);

        vm.expectRevert(ParamutuelWager.NotResolver.selector);
        vm.prank(proposer);
        wager.resolve(0);

        vm.prank(delegatedResolver);
        wager.resolve(0);

        vm.startPrank(bettor1);
        uint256 paid = wager.claim();
        vm.stopPrank();
        // Protocol fee 2% on factory => net pot 49 ether to sole winner
        assertEq(paid, 49 ether);
    }

    function testAlreadyFinalizedRevertsForResolveRetractExpire() public {
        ParamutuelWager wager = _createBasicWager();

        vm.startPrank(bettor1);
        token.approve(address(wager), 10 ether);
        wager.placeBet(0, 10 ether);
        vm.stopPrank();

        vm.warp(wager.bettingCloseTime() + 1);
        vm.prank(proposer);
        wager.resolve(0);

        vm.expectRevert(ParamutuelWager.AlreadyFinalized.selector);
        vm.prank(proposer);
        wager.resolve(0);

        vm.expectRevert(ParamutuelWager.AlreadyFinalized.selector);
        vm.prank(proposer);
        wager.retract();

        vm.expectRevert(ParamutuelWager.AlreadyFinalized.selector);
        vm.prank(bettor2);
        wager.expire();
    }

    function testResolvedWithoutWinningBetsCausesNoClaims() public {
        ParamutuelWager wager = _createBasicWager();

        vm.startPrank(bettor1);
        token.approve(address(wager), 20 ether);
        wager.placeBet(0, 20 ether);
        vm.stopPrank();

        vm.warp(wager.bettingCloseTime() + 1);
        vm.prank(proposer);
        wager.resolve(1); // no one bet outcome 1

        vm.expectRevert(ParamutuelWager.NothingToClaim.selector);
        vm.prank(bettor1);
        wager.claim();
    }

    function testWithdrawFeesHappyPathAndDoubleWithdrawRevert() public {
        ParamutuelWager wager = _createBasicWager();

        vm.startPrank(bettor1);
        token.approve(address(wager), 100 ether);
        wager.placeBet(0, 100 ether);
        vm.stopPrank();

        vm.startPrank(bettor2);
        token.approve(address(wager), 100 ether);
        wager.placeBet(1, 100 ether);
        vm.stopPrank();

        vm.warp(wager.bettingCloseTime() + 1);
        vm.prank(proposer);
        wager.resolve(1);

        assertEq(wager.feeBalances(treasury), 4 ether);

        vm.startPrank(treasury);
        uint256 before = token.balanceOf(treasury);
        uint256 withdrawn = wager.withdrawFees();
        uint256 afterBal = token.balanceOf(treasury);
        assertEq(withdrawn, 4 ether);
        assertEq(afterBal - before, 4 ether);

        vm.expectRevert(ParamutuelWager.NothingToClaim.selector);
        wager.withdrawFees();
        vm.stopPrank();
    }

    function testWithdrawFeesWithoutAccrualReverts() public {
        ParamutuelWager wager = _createBasicWager();
        vm.expectRevert(ParamutuelWager.NothingToClaim.selector);
        vm.prank(extraFeeRecipient);
        wager.withdrawFees();
    }

    function testWagerConstructorFeeConfigReverts() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "A";
        outcomes[1] = "B";

        address[] memory recipients = new address[](1);
        recipients[0] = treasury;
        uint16[] memory bpsMismatch = new uint16[](0);

        vm.expectRevert(ParamutuelWager.FeeConfigMismatch.selector);
        new ParamutuelWager(
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

        vm.expectRevert(ParamutuelWager.FeeTooHigh.selector);
        new ParamutuelWager(
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
        address wagerAddr = factory.createWager(
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
        ParamutuelWager wager = ParamutuelWager(wagerAddr);

        badToken.setFailTransferFrom(true);
        vm.startPrank(bettor1);
        badToken.approve(address(wager), 10 ether);
        vm.expectRevert("TRANSFER_FROM");
        wager.placeBet(0, 10 ether);
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
        address wagerAddr = factory.createWager(
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
        ParamutuelWager wager = ParamutuelWager(wagerAddr);

        vm.startPrank(bettor1);
        badToken.approve(address(wager), 10 ether);
        wager.placeBet(0, 10 ether);
        vm.stopPrank();

        vm.warp(wager.bettingCloseTime() + 1);
        vm.prank(proposer);
        wager.resolve(0);

        badToken.setFailTransfer(true);
        vm.expectRevert("TRANSFER");
        vm.prank(bettor1);
        wager.claim();
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
        address wagerAddr = factory.createWager(
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
        ParamutuelWager wager = ParamutuelWager(wagerAddr);

        vm.startPrank(bettor1);
        badToken.approve(address(wager), 100 ether);
        wager.placeBet(0, 100 ether);
        vm.stopPrank();

        vm.warp(wager.bettingCloseTime() + 1);
        vm.prank(proposer);
        wager.resolve(0);

        badToken.setFailTransfer(true);
        vm.expectRevert("TRANSFER");
        vm.prank(treasury);
        wager.withdrawFees();
    }

    function testCloseBettingEarlyStopsPlaceBet() public {
        ParamutuelWager wager = _createBasicWager();

        vm.prank(proposer);
        wager.closeBetting();
        assertTrue(wager.bettingClosedByAuthority());

        vm.startPrank(bettor1);
        token.approve(address(wager), 1 ether);
        vm.expectRevert(ParamutuelWager.BettingClosed.selector);
        wager.placeBet(0, 1 ether);
        vm.stopPrank();
    }

    function testOnlyBettingCloserCanCloseBetting() public {
        ParamutuelWager wager = _createBasicWager();

        vm.expectRevert(ParamutuelWager.NotBettingCloser.selector);
        vm.prank(bettor1);
        wager.closeBetting();
    }

    function testCloseResolutionWindowAllowsEarlyExpire() public {
        ParamutuelWager wager = _createBasicWager();

        vm.startPrank(bettor1);
        token.approve(address(wager), 10 ether);
        wager.placeBet(0, 10 ether);
        vm.stopPrank();

        vm.warp(wager.bettingCloseTime() + 1);
        vm.prank(proposer);
        wager.closeResolutionWindow();
        assertTrue(wager.resolutionWindowClosedByAuthority());

        vm.expectRevert(ParamutuelWager.ResolutionWindowOver.selector);
        vm.prank(proposer);
        wager.resolve(0);

        vm.prank(bettor2);
        wager.expire();

        assertEq(uint256(wager.state()), uint256(ParamutuelWager.State.Retracted));
    }

    function testCloseResolutionWindowBeforeBettingClosedReverts() public {
        ParamutuelWager wager = _createBasicWager();

        vm.expectRevert(ParamutuelWager.BettingNotClosed.selector);
        vm.prank(proposer);
        wager.closeResolutionWindow();
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
        address wagerAddr = factory.createWager(
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

        ParamutuelWager wager = ParamutuelWager(wagerAddr);
        assertEq(wager.bettingCloser(), bettingOracle);
        assertEq(wager.resolutionCloser(), resolutionOracle);

        vm.expectRevert(ParamutuelWager.BettingNotClosed.selector);
        vm.prank(resolutionOracle);
        wager.closeResolutionWindow();

        vm.prank(bettingOracle);
        wager.closeBetting();

        vm.startPrank(bettor1);
        token.approve(address(wager), 1 ether);
        vm.expectRevert(ParamutuelWager.BettingClosed.selector);
        wager.placeBet(0, 1 ether);
        vm.stopPrank();

        vm.prank(resolutionOracle);
        wager.closeResolutionWindow();

        vm.prank(bettor2);
        wager.expire();
        assertEq(uint256(wager.state()), uint256(ParamutuelWager.State.Retracted));
    }

    function testNoMaxBettingAndResolutionRequireClosers() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address wagerAddr = factory.createWager(
            address(token),
            "No max windows",
            outcomes,
            0, // no betting time cap
            0, // no resolution time cap
            address(0),
            proposer,
            proposer,
            extraRecipients,
            extraBps
        );
        ParamutuelWager wager = ParamutuelWager(wagerAddr);
        assertEq(wager.bettingCloseTime(), 0);
        assertEq(wager.resolutionWindow(), 0);
        assertEq(wager.resolutionDeadline(), 0);

        vm.startPrank(bettor1);
        token.approve(address(wager), 10 ether);
        wager.placeBet(0, 10 ether);
        vm.stopPrank();

        vm.warp(block.timestamp + 365 days);
        vm.startPrank(bettor2);
        token.approve(address(wager), 1 ether);
        wager.placeBet(1, 1 ether); // still open after one year
        vm.stopPrank();

        vm.expectRevert(ParamutuelWager.BettingNotClosed.selector);
        vm.prank(proposer);
        wager.resolve(0);

        vm.prank(proposer);
        wager.closeBetting();

        vm.warp(block.timestamp + 365 days);
        vm.prank(proposer);
        wager.resolve(0); // still resolvable after another year (no resolution max)
    }

    function testNoMaxBettingWithFiniteResolutionWindowStartsAtAuthorityClose() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address wagerAddr = factory.createWager(
            address(token),
            "Closer starts resolution timer",
            outcomes,
            0, // no betting cap
            1 hours, // finite resolution window
            address(0),
            proposer,
            address(0),
            extraRecipients,
            extraBps
        );
        ParamutuelWager wager = ParamutuelWager(wagerAddr);
        assertEq(wager.resolutionWindow(), 1 hours);
        assertEq(wager.resolutionDeadline(), 0); // no scheduled deadline at creation

        vm.startPrank(bettor1);
        token.approve(address(wager), 10 ether);
        wager.placeBet(0, 10 ether);
        vm.stopPrank();

        vm.warp(block.timestamp + 30 days);
        vm.prank(proposer);
        wager.closeBetting();
        uint64 closedAt = wager.bettingClosedAtByAuthority();
        assertEq(closedAt, block.timestamp);

        vm.warp(closedAt + 30 minutes);
        vm.prank(proposer);
        wager.resolve(0);
    }

    function testNoMaxResolutionCannotExpireUntilResolutionCloserCloses() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address wagerAddr = factory.createWager(
            address(token),
            "No max resolution requires closer",
            outcomes,
            uint64(block.timestamp + 2 hours),
            0, // no resolution time cap
            address(0),
            address(0),
            proposer,
            extraRecipients,
            extraBps
        );
        ParamutuelWager wager = ParamutuelWager(wagerAddr);

        vm.startPrank(bettor1);
        token.approve(address(wager), 10 ether);
        wager.placeBet(0, 10 ether);
        vm.stopPrank();

        vm.warp(wager.bettingCloseTime() + 100 days);
        vm.expectRevert(ParamutuelWager.ResolutionWindowOver.selector);
        vm.prank(bettor2);
        wager.expire();

        vm.prank(proposer);
        wager.closeResolutionWindow();
        vm.prank(bettor2);
        wager.expire();

        assertEq(uint256(wager.state()), uint256(ParamutuelWager.State.Retracted));
    }

    function testCloseBettingAfterTimestampIsNoopWithoutAuthorityFlag() public {
        ParamutuelWager wager = _createBasicWager();
        vm.warp(wager.bettingCloseTime() + 1);

        vm.prank(proposer);
        wager.closeBetting(); // should no-op because already closed by time

        assertFalse(wager.bettingClosedByAuthority(), "authority flag unchanged");
        assertEq(wager.bettingClosedAtByAuthority(), 0, "no authority close timestamp");
    }

    function testOnlyResolutionCloserCanCloseResolutionWindow() public {
        ParamutuelWager wager = _createBasicWager();
        vm.warp(wager.bettingCloseTime() + 1);

        vm.expectRevert(ParamutuelWager.NotResolutionCloser.selector);
        vm.prank(bettor1);
        wager.closeResolutionWindow();
    }

    function testCloseResolutionWindowIdempotent() public {
        ParamutuelWager wager = _createBasicWager();
        vm.warp(wager.bettingCloseTime() + 1);

        vm.prank(proposer);
        wager.closeResolutionWindow();
        assertTrue(wager.resolutionWindowClosedByAuthority());

        vm.prank(proposer);
        wager.closeResolutionWindow(); // idempotent
        assertTrue(wager.resolutionWindowClosedByAuthority());
    }

    function testFiniteWindowsAllowNoAuthorityClosers() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.prank(proposer);
        address wagerAddr = factory.createWager(
            address(token),
            "Time-only finite windows",
            outcomes,
            uint64(block.timestamp + 2 hours),
            2 hours,
            address(0),
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );
        ParamutuelWager wager = ParamutuelWager(wagerAddr);

        assertEq(wager.resolver(), proposer);
        assertEq(wager.bettingCloser(), address(0));
        assertEq(wager.resolutionCloser(), address(0));

        vm.expectRevert(ParamutuelWager.NotBettingCloser.selector);
        vm.prank(proposer);
        wager.closeBetting();

        vm.startPrank(bettor1);
        token.approve(address(wager), 10 ether);
        wager.placeBet(0, 10 ether);
        vm.stopPrank();

        vm.warp(wager.bettingCloseTime() + 1);
        vm.expectRevert(ParamutuelWager.NotResolutionCloser.selector);
        vm.prank(proposer);
        wager.closeResolutionWindow();

        vm.prank(proposer);
        wager.resolve(0);
        assertEq(uint256(wager.state()), uint256(ParamutuelWager.State.Resolved));
    }

    function testNoMaxWindowsWithoutClosersRevert() public {
        string[] memory outcomes = new string[](2);
        outcomes[0] = "YES";
        outcomes[1] = "NO";

        address[] memory extraRecipients = new address[](0);
        uint16[] memory extraBps = new uint16[](0);

        vm.expectRevert(ParamutuelFactory.InvalidLifecycleConfig.selector);
        vm.prank(proposer);
        factory.createWager(
            address(token),
            "No max without closers",
            outcomes,
            0,
            0,
            address(0),
            address(0),
            address(0),
            extraRecipients,
            extraBps
        );

        vm.expectRevert(ParamutuelFactory.InvalidLifecycleConfig.selector);
        vm.prank(proposer);
        factory.createWager(
            address(token),
            "No max betting without betting closer",
            outcomes,
            0,
            2 hours,
            address(0),
            address(0),
            proposer,
            extraRecipients,
            extraBps
        );

        vm.expectRevert(ParamutuelFactory.InvalidLifecycleConfig.selector);
        vm.prank(proposer);
        factory.createWager(
            address(token),
            "No max resolution without resolution closer",
            outcomes,
            uint64(block.timestamp + 2 hours),
            0,
            address(0),
            proposer,
            address(0),
            extraRecipients,
            extraBps
        );
    }
}

