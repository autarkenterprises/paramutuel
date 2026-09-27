// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import {ParamutuelFactoryV3} from "../src/ParamutuelFactoryV3.sol";
import {ParamutuelWagerV3} from "../src/ParamutuelWagerV3.sol";

/// @dev Standard ERC-20 mock with two failure toggles so the wager's
///      `require(ok, "TRANSFER_FROM")` / `require(ok, "TRANSFER")` guards can be
///      exercised: when a toggle is set the token returns `false` *without*
///      moving balances (the legacy "false instead of revert" ERC-20 style).
contract MockERC20V3Life {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    bool public failTransfer;
    bool public failTransferFrom;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function setFailTransfer(bool v) external {
        failTransfer = v;
    }

    function setFailTransferFrom(bool v) external {
        failTransferFrom = v;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        if (failTransfer) return false;
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        if (failTransferFrom) return false;
        uint256 a = allowance[from][msg.sender];
        require(a >= amount, "ALLOWANCE");
        allowance[from][msg.sender] = a - amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

/// @dev Hostile collateral: on `transfer` out of the wager it re-enters
///      `claim()` once. Used to prove the `nonReentrant` guard on `claim` holds
///      (the re-entrant call must revert with "REENTRANCY", which bubbles up and
///      reverts the outer claim, so no double payout is possible).
contract ReentrantTokenV3 {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    address public target;
    bool private _armed;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function arm(address wager) external {
        target = wager;
        _armed = true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        if (_armed && msg.sender == target) {
            _armed = false;
            ParamutuelWagerV3(target).claim();
        }
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

/// @notice ADR-0019 test-parity restoration. Commit `b2a2f28` deleted the V1
///         suite (`test/Paramutuel.t.sol`) that pinned the lifecycle, access-
///         control, fee-cap and token-failure behaviour V3 inherited, without
///         porting it. This file restores that coverage against the V3 ABI and
///         adds the V3-only guards (factory-only seeder, distinct-ticket cap,
///         constructor defence-in-depth). Goal: every custom error and string
///         `require` in `src/` is asserted by at least one test here or in the
///         sibling V3 suites.
///
///         Time model used throughout: `setUp` warps to t=1000; the default
///         wager closes betting at `T0 + 2h` and has a 2h resolution window, so
///         the resolution window is `[close, close + 2h]` inclusive and
///         `expire()` becomes legal at `close + 2h + 1`.
contract ParamutuelV3LifecycleTest is Test {
    ParamutuelFactoryV3 factory;
    MockERC20V3Life token;

    address treasury = address(0x1000);
    address proposer = address(0x2000);
    address alice = address(0x3000);
    address bob = address(0x4000);
    address resolverAddr = address(0x7000);
    address bCloser = address(0x8000);
    address rCloser = address(0x9000);
    address stranger = address(0xDEAD);

    uint64 constant MIN_BET_WIN = 1 hours;
    uint64 constant MIN_RES_WIN = 1 hours;
    uint64 constant RES_WIN = 2 hours;
    uint64 closeAt;

    uint256 constant M0 = 1;
    uint256 constant M1 = 2;

    function setUp() public {
        vm.warp(1000);
        closeAt = uint64(block.timestamp + 2 hours);
        factory = new ParamutuelFactoryV3(treasury, 0, MIN_BET_WIN, MIN_RES_WIN);
        token = new MockERC20V3Life();
        token.mint(proposer, 1e24);
        token.mint(alice, 1e24);
        token.mint(bob, 1e24);
    }

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    function _two() internal pure returns (string[] memory o) {
        o = new string[](2);
        o[0] = "YES";
        o[1] = "NO";
    }

    function _n(uint256 n) internal pure returns (string[] memory o) {
        o = new string[](n);
        for (uint256 i; i < n; i++) o[i] = "x";
    }

    /// @dev Fully-parameterised enumerated create through `factory` as `proposer`.
    function _enum(
        uint64 close,
        uint64 resWin,
        address resolver,
        address bc,
        address rc,
        ParamutuelWagerV3.PayoffPolicy policy,
        string[] memory outcomes
    ) internal returns (ParamutuelWagerV3) {
        vm.prank(proposer);
        return ParamutuelWagerV3(
            factory.createEnumeratedWager(
                address(token),
                "q",
                outcomes,
                policy,
                0,
                close,
                resWin,
                resolver,
                bc,
                rc,
                new address[](0),
                new uint16[](0)
            )
        );
    }

    /// @dev Default enumerated wager: SINGLE_WINNER YES/NO, timed windows,
    ///      delegated resolver and both closers set to distinct addresses.
    function _default() internal returns (ParamutuelWagerV3) {
        return _enum(closeAt, RES_WIN, resolverAddr, bCloser, rCloser, ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, _two());
    }

    function _free(uint64 close, uint64 resWin, address bc, address rc) internal returns (ParamutuelWagerV3) {
        vm.prank(proposer);
        return ParamutuelWagerV3(
            factory.createFreeformWager(
                address(token), "q", close, resWin, resolverAddr, bc, rc, new address[](0), new uint16[](0)
            )
        );
    }

    function _bet(ParamutuelWagerV3 w, address who, uint256 mask, uint256 amt) internal {
        vm.startPrank(who);
        token.approve(address(w), type(uint256).max);
        w.placeBet(mask, amt);
        vm.stopPrank();
    }

    function _betFree(ParamutuelWagerV3 w, address who, string memory ans, uint256 amt) internal {
        vm.startPrank(who);
        token.approve(address(w), type(uint256).max);
        w.placeBet(ans, amt);
        vm.stopPrank();
    }

    /// @dev Direct wager construction with every knob exposed, for the
    ///      constructor's defence-in-depth checks the factory never lets through.
    function _direct(
        ParamutuelWagerV3.WagerMode mode,
        string[] memory outcomes,
        ParamutuelWagerV3.PayoffPolicy policy,
        uint256 policyParam,
        address[] memory feeR,
        uint16[] memory feeB,
        uint256 maxDistinct
    ) internal returns (ParamutuelWagerV3) {
        return new ParamutuelWagerV3(
            mode,
            address(this),
            proposer,
            proposer,
            proposer,
            proposer,
            address(token),
            "direct",
            outcomes,
            policy,
            policyParam,
            closeAt,
            RES_WIN,
            closeAt + RES_WIN,
            feeR,
            feeB,
            maxDistinct
        );
    }

    // ------------------------------------------------------------------
    // Factory constructor + creation validation
    // ------------------------------------------------------------------

    function test_factoryConstructor_rejectsZeroTreasury() public {
        vm.expectRevert(bytes("TREASURY"));
        new ParamutuelFactoryV3(address(0), 0, 0, 0);
    }

    function test_factoryConstructor_rejectsFeeAboveCap_allowsFullCap() public {
        vm.expectRevert(bytes("FEE"));
        new ParamutuelFactoryV3(treasury, 10_001, 0, 0);
        ParamutuelFactoryV3 f = new ParamutuelFactoryV3(treasury, 10_000, 0, 0);
        assertEq(f.protocolFeeBps(), 10_000);
    }

    function test_create_rejectsFewerThanTwoOutcomes() public {
        string[] memory one = new string[](1);
        one[0] = "only";
        vm.expectRevert(ParamutuelFactoryV3.BadOutcomes.selector);
        _enum(closeAt, RES_WIN, address(0), address(0), address(0), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, one);
    }

    function test_create_rejectsWindowsShorterThanFactoryMinimum_bothModes() public {
        uint64 tooSoon = uint64(block.timestamp + MIN_BET_WIN - 1);
        vm.expectRevert(ParamutuelFactoryV3.WindowTooShort.selector);
        _enum(tooSoon, RES_WIN, address(0), address(0), address(0), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, _two());
        vm.expectRevert(ParamutuelFactoryV3.WindowTooShort.selector);
        _enum(closeAt, MIN_RES_WIN - 1, address(0), address(0), address(0), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, _two());
        vm.expectRevert(ParamutuelFactoryV3.WindowTooShort.selector);
        _free(tooSoon, RES_WIN, address(0), address(0));
        vm.expectRevert(ParamutuelFactoryV3.WindowTooShort.selector);
        _free(closeAt, MIN_RES_WIN - 1, address(0), address(0));
        // Exactly at the minimum is allowed.
        _enum(
            uint64(block.timestamp + MIN_BET_WIN),
            MIN_RES_WIN,
            address(0),
            address(0),
            address(0),
            ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER,
            _two()
        );
    }

    function test_createFreeform_rejectsUncloseableLifecycle() public {
        vm.expectRevert(ParamutuelFactoryV3.InvalidLifecycleConfig.selector);
        _free(0, RES_WIN, address(0), address(0));
        vm.expectRevert(ParamutuelFactoryV3.InvalidLifecycleConfig.selector);
        _free(closeAt, 0, address(0), address(0));
    }

    /// @dev Four ways to produce a bad fee config: array length mismatch, zero
    ///      recipient, zero bps entry, and a total (protocol + extras) over 100%.
    ///      Checked on both creation paths.
    function test_create_rejectsBadFeeConfig_bothModes() public {
        factory = new ParamutuelFactoryV3(treasury, 100, MIN_BET_WIN, MIN_RES_WIN);
        address[] memory r1 = new address[](1);
        uint16[] memory b0 = new uint16[](0);
        uint16[] memory b1 = new uint16[](1);

        // length mismatch
        r1[0] = alice;
        _expectEnumFeeRevert(r1, b0);
        _expectFreeFeeRevert(r1, b0);
        // zero recipient
        r1[0] = address(0);
        b1[0] = 50;
        _expectEnumFeeRevert(r1, b1);
        _expectFreeFeeRevert(r1, b1);
        // zero bps
        r1[0] = alice;
        b1[0] = 0;
        _expectEnumFeeRevert(r1, b1);
        _expectFreeFeeRevert(r1, b1);
        // protocol 100 + extra 9901 = 10001 > cap
        b1[0] = 9_901;
        _expectEnumFeeRevert(r1, b1);
        _expectFreeFeeRevert(r1, b1);
    }

    function _expectEnumFeeRevert(address[] memory r, uint16[] memory b) internal {
        vm.prank(proposer);
        vm.expectRevert(ParamutuelFactoryV3.BadFeeConfig.selector);
        factory.createEnumeratedWager(
            address(token), "q", _two(), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, closeAt, RES_WIN,
            address(0), address(0), address(0), r, b
        );
    }

    function _expectFreeFeeRevert(address[] memory r, uint16[] memory b) internal {
        vm.prank(proposer);
        vm.expectRevert(ParamutuelFactoryV3.BadFeeConfig.selector);
        factory.createFreeformWager(address(token), "q", closeAt, RES_WIN, address(0), address(0), address(0), r, b);
    }

    /// @dev Protocol slot is prepended only when `protocolFeeBps > 0`; extras
    ///      follow in declared order; the cached total matches the sum.
    function test_create_feeConfigComposition() public {
        factory = new ParamutuelFactoryV3(treasury, 100, MIN_BET_WIN, MIN_RES_WIN);
        address[] memory r = new address[](1);
        uint16[] memory b = new uint16[](1);
        r[0] = alice;
        b[0] = 250;
        vm.prank(proposer);
        ParamutuelWagerV3 w = ParamutuelWagerV3(
            factory.createEnumeratedWager(
                address(token), "q", _two(), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, closeAt, RES_WIN,
                address(0), address(0), address(0), r, b
            )
        );
        assertEq(w.feeRecipients(0), treasury);
        assertEq(w.feeBps(0), 100);
        assertEq(w.feeRecipients(1), alice);
        assertEq(w.feeBps(1), 250);
        assertEq(w.totalFeeBps(), 350);

        // Zero protocol fee: no treasury slot at all.
        factory = new ParamutuelFactoryV3(treasury, 0, MIN_BET_WIN, MIN_RES_WIN);
        vm.prank(proposer);
        w = ParamutuelWagerV3(
            factory.createEnumeratedWager(
                address(token), "q", _two(), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, closeAt, RES_WIN,
                address(0), address(0), address(0), r, b
            )
        );
        assertEq(w.feeRecipients(0), alice);
        assertEq(w.totalFeeBps(), 250);
        vm.expectRevert();
        w.feeRecipients(1);
    }

    /// @dev Resolver defaults to proposer on `address(0)`; closers do NOT default
    ///      (since `bc8e4a8` `address(0)` disables the role — ADR-0019 finding 4).
    ///      `resolutionDeadline` is `close + window`, or 0 if either is unbounded.
    function test_create_roleDefaultsAndDeadline() public {
        ParamutuelWagerV3 w =
            _enum(closeAt, RES_WIN, address(0), address(0), address(0), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, _two());
        assertEq(w.proposer(), proposer);
        assertEq(w.resolver(), proposer);
        assertEq(w.bettingCloser(), address(0));
        assertEq(w.resolutionCloser(), address(0));
        assertEq(w.resolutionDeadline(), closeAt + RES_WIN);
        assertEq(w.factory(), address(factory));
        assertEq(factory.wagers(0), address(w));

        ParamutuelWagerV3 w2 = _default();
        assertEq(w2.resolver(), resolverAddr);
        assertEq(w2.bettingCloser(), bCloser);
        assertEq(w2.resolutionCloser(), rCloser);

        ParamutuelWagerV3 w3 =
            _enum(0, RES_WIN, address(0), bCloser, address(0), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, _two());
        assertEq(w3.resolutionDeadline(), 0);
        ParamutuelWagerV3 w4 = _free(closeAt, 0, address(0), rCloser);
        assertEq(w4.resolutionDeadline(), 0);
        assertEq(factory.wagersCount(), 4);
    }

    function test_create_seedConfigRejectsZeroAmountAndLengthMismatch() public {
        uint256[] memory masks = new uint256[](1);
        uint256[] memory amts = new uint256[](1);
        masks[0] = M0;
        amts[0] = 0;
        vm.startPrank(proposer);
        token.approve(address(factory), type(uint256).max);
        vm.expectRevert(ParamutuelFactoryV3.BadSeedConfig.selector);
        factory.createEnumeratedWager(
            address(token), "q", _two(), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, closeAt, RES_WIN,
            address(0), address(0), address(0), new address[](0), new uint16[](0), masks, amts
        );
        vm.expectRevert(ParamutuelFactoryV3.BadSeedConfig.selector);
        factory.createEnumeratedWager(
            address(token), "q", _two(), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, closeAt, RES_WIN,
            address(0), address(0), address(0), new address[](0), new uint16[](0), masks, new uint256[](0)
        );
        vm.stopPrank();
    }

    function test_create_seedTransferFromFalse_reverts() public {
        uint256[] memory masks = new uint256[](1);
        uint256[] memory amts = new uint256[](1);
        masks[0] = M0;
        amts[0] = 5;
        token.setFailTransferFrom(true);
        vm.prank(proposer);
        vm.expectRevert(bytes("TRANSFER_FROM"));
        factory.createEnumeratedWager(
            address(token), "q", _two(), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, closeAt, RES_WIN,
            address(0), address(0), address(0), new address[](0), new uint16[](0), masks, amts
        );
    }

    // ------------------------------------------------------------------
    // Wager constructor defence-in-depth (unreachable through the factory)
    // ------------------------------------------------------------------

    function test_wagerConstructor_feeConfigChecks() public {
        address[] memory r = new address[](1);
        r[0] = alice;
        vm.expectRevert(ParamutuelWagerV3.FeeConfigMismatch.selector);
        _direct(ParamutuelWagerV3.WagerMode.Enumerated, _two(), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, r, new uint16[](0), 0);
        uint16[] memory b = new uint16[](1);
        b[0] = 10_001;
        vm.expectRevert(ParamutuelWagerV3.FeeTooHigh.selector);
        _direct(ParamutuelWagerV3.WagerMode.Enumerated, _two(), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, r, b, 0);
    }

    function test_wagerConstructor_enumeratedShapeChecks() public {
        string[] memory one = new string[](1);
        vm.expectRevert(bytes("OUTCOMES_MIN"));
        _direct(ParamutuelWagerV3.WagerMode.Enumerated, one, ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, new address[](0), new uint16[](0), 0);
        vm.expectRevert(bytes("OUTCOMES_MAX"));
        _direct(ParamutuelWagerV3.WagerMode.Enumerated, _n(257), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, new address[](0), new uint16[](0), 0);
        vm.expectRevert(ParamutuelWagerV3.InvalidPolicyParam.selector);
        _direct(ParamutuelWagerV3.WagerMode.Enumerated, _two(), ParamutuelWagerV3.PayoffPolicy.AT_LEAST_K, 0, new address[](0), new uint16[](0), 0);
        vm.expectRevert(ParamutuelWagerV3.InvalidPolicyParam.selector);
        _direct(ParamutuelWagerV3.WagerMode.Enumerated, _two(), ParamutuelWagerV3.PayoffPolicy.AT_LEAST_K, 3, new address[](0), new uint16[](0), 0);
        vm.expectRevert(ParamutuelWagerV3.InvalidPolicyParam.selector);
        _direct(ParamutuelWagerV3.WagerMode.Enumerated, _two(), ParamutuelWagerV3.PayoffPolicy.ANY_OF, 1, new address[](0), new uint16[](0), 0);
        // 256 outcomes is the wager's own ceiling (factory caps tighter at 255).
        ParamutuelWagerV3 w = _direct(
            ParamutuelWagerV3.WagerMode.Enumerated, _n(256), ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0, new address[](0), new uint16[](0), 0
        );
        assertEq(w.numOptions(), 256);
        assertEq(w.maxDistinctAnswers(), 0);
    }

    function test_wagerConstructor_freeformShapeChecks() public {
        vm.expectRevert(ParamutuelWagerV3.InvalidOutcome.selector);
        _direct(ParamutuelWagerV3.WagerMode.Freeform, _two(), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, new address[](0), new uint16[](0), 8);
        string[] memory none;
        vm.expectRevert(ParamutuelWagerV3.InvalidDistinctCap.selector);
        _direct(ParamutuelWagerV3.WagerMode.Freeform, none, ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, new address[](0), new uint16[](0), 0);
        vm.expectRevert(ParamutuelWagerV3.InvalidDistinctCap.selector);
        _direct(ParamutuelWagerV3.WagerMode.Freeform, none, ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, new address[](0), new uint16[](0), 1025);
        vm.expectRevert(ParamutuelWagerV3.InvalidPolicyParam.selector);
        _direct(ParamutuelWagerV3.WagerMode.Freeform, none, ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 1, new address[](0), new uint16[](0), 8);
        ParamutuelWagerV3 w = _direct(
            ParamutuelWagerV3.WagerMode.Freeform, none, ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, new address[](0), new uint16[](0), 1024
        );
        assertEq(w.numOptions(), 0);
        assertEq(w.maxDistinctAnswers(), 1024);
    }

    // ------------------------------------------------------------------
    // Factory-only seeder
    // ------------------------------------------------------------------

    function test_seeder_onlyFactory_onlyEnumerated_nonEmpty_onlyOpen() public {
        ParamutuelWagerV3 w = _default();
        uint256[] memory masks = new uint256[](1);
        uint256[] memory amts = new uint256[](1);
        masks[0] = M0;
        amts[0] = 1;

        vm.prank(stranger);
        vm.expectRevert(ParamutuelWagerV3.NotFactory.selector);
        w.seedInitialBetsFromFactory(stranger, masks, amts);

        vm.prank(address(factory));
        vm.expectRevert(ParamutuelWagerV3.ArrayLengthMismatch.selector);
        w.seedInitialBetsFromFactory(stranger, new uint256[](0), new uint256[](0));

        ParamutuelWagerV3 f = _free(closeAt, RES_WIN, address(0), address(0));
        vm.prank(address(factory));
        vm.expectRevert(ParamutuelWagerV3.WrongMode.selector);
        f.seedInitialBetsFromFactory(stranger, masks, amts);

        // After finalisation the seeder refuses (`NotOpen`) even for the factory.
        _bet(w, alice, M0, 10);
        vm.warp(closeAt);
        vm.prank(resolverAddr);
        w.resolve(M0);
        vm.prank(address(factory));
        vm.expectRevert(ParamutuelWagerV3.NotOpen.selector);
        w.seedInitialBetsFromFactory(stranger, masks, amts);
    }

    // ------------------------------------------------------------------
    // Betting
    // ------------------------------------------------------------------

    function test_placeBet_zeroAmountReverts_allEntryPoints() public {
        ParamutuelWagerV3 w = _default();
        vm.startPrank(alice);
        token.approve(address(w), type(uint256).max);
        vm.expectRevert(bytes("AMOUNT"));
        w.placeBet(M0, 0);
        uint256[] memory masks = new uint256[](2);
        uint256[] memory amts = new uint256[](2);
        masks[0] = M0;
        masks[1] = M1;
        amts[0] = 1;
        amts[1] = 0;
        vm.expectRevert(bytes("AMOUNT"));
        w.placeBets(masks, amts);
        vm.expectRevert(ParamutuelWagerV3.ArrayLengthMismatch.selector);
        w.placeBets(new uint256[](0), new uint256[](0));
        vm.stopPrank();

        ParamutuelWagerV3 f = _free(closeAt, RES_WIN, address(0), address(0));
        vm.startPrank(alice);
        token.approve(address(f), type(uint256).max);
        vm.expectRevert(bytes("AMOUNT"));
        f.placeBet("a", 0);
        vm.stopPrank();
    }

    function test_placeBet_transferFromFalse_revertsAndRecordsNothing() public {
        ParamutuelWagerV3 w = _default();
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        token.setFailTransferFrom(true);
        vm.startPrank(alice);
        vm.expectRevert(bytes("TRANSFER_FROM"));
        w.placeBet(M0, 5);
        uint256[] memory masks = new uint256[](1);
        uint256[] memory amts = new uint256[](1);
        masks[0] = M0;
        amts[0] = 5;
        vm.expectRevert(bytes("TRANSFER_FROM"));
        w.placeBets(masks, amts);
        vm.stopPrank();
        assertEq(w.totalPot(), 0);

        ParamutuelWagerV3 f = _free(closeAt, RES_WIN, address(0), address(0));
        vm.startPrank(alice);
        token.approve(address(f), type(uint256).max);
        vm.expectRevert(bytes("TRANSFER_FROM"));
        f.placeBet("a", 5);
        vm.stopPrank();
    }

    /// @dev Betting is open strictly before `bettingCloseTime` and closed at it.
    function test_placeBet_closesExactlyAtBettingCloseTime_bothModes() public {
        ParamutuelWagerV3 w = _default();
        ParamutuelWagerV3 f = _free(closeAt, RES_WIN, address(0), address(0));
        vm.warp(closeAt - 1);
        _bet(w, alice, M0, 1);
        _betFree(f, alice, "a", 1);
        vm.warp(closeAt);
        vm.startPrank(alice);
        vm.expectRevert(ParamutuelWagerV3.BettingClosed.selector);
        w.placeBet(M0, 1);
        uint256[] memory masks = new uint256[](1);
        uint256[] memory amts = new uint256[](1);
        masks[0] = M0;
        amts[0] = 1;
        vm.expectRevert(ParamutuelWagerV3.BettingClosed.selector);
        w.placeBets(masks, amts);
        vm.expectRevert(ParamutuelWagerV3.BettingClosed.selector);
        f.placeBet("a", 1);
        vm.stopPrank();
    }

    function test_placeBet_afterFinalisation_revertsNotOpen() public {
        ParamutuelWagerV3 w = _default();
        _bet(w, alice, M0, 1);
        vm.warp(closeAt);
        vm.prank(resolverAddr);
        w.retract();
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV3.NotOpen.selector);
        w.placeBet(M0, 1);
    }

    /// @dev `MAX_DISTINCT_TICKETS = 1024` bounds `_usedMasks`. With ANY_OF over
    ///      11 options there are 2047 legal masks, so the cap is reachable.
    ///      Re-betting an already-used mask must still work after the cap.
    function test_enumerated_distinctTicketCap() public {
        ParamutuelWagerV3 w =
            _enum(closeAt, RES_WIN, resolverAddr, address(0), address(0), ParamutuelWagerV3.PayoffPolicy.ANY_OF, _n(11));
        uint256[] memory masks = new uint256[](1024);
        uint256[] memory amts = new uint256[](1024);
        for (uint256 i; i < 1024; i++) {
            masks[i] = i + 1;
            amts[i] = 1;
        }
        vm.startPrank(alice);
        token.approve(address(w), type(uint256).max);
        w.placeBets(masks, amts);
        assertEq(w.usedMasksCount(), 1024);
        vm.expectRevert(ParamutuelWagerV3.TooManyDistinctTickets.selector);
        w.placeBet(1025, 1);
        w.placeBet(1, 7);
        vm.stopPrank();
        assertEq(w.ticketPoolByMask(1), 8);
    }

    /// @notice ADR-0019 finding 3 — pins the freeform answer-space exhaustion
    ///         boundary as an executable fact. A single address filling
    ///         `maxDistinctAnswers` with 1-wei bets locks every other bettor out of
    ///         *new* answers (including, potentially, the correct one). Cost is
    ///         1024 wei of stake plus gas. Mitigation is Proposed for the next
    ///         wager revision; if this test starts failing, the mitigation shipped
    ///         and this test should be inverted to assert the defence.
    function test_freeform_answerSpaceExhaustion_griefingBoundary() public {
        ParamutuelWagerV3 f = _free(closeAt, RES_WIN, address(0), address(0));
        vm.startPrank(bob);
        token.approve(address(f), type(uint256).max);
        for (uint256 i; i < 1024; i++) {
            f.placeBet(vm.toString(i), 1);
        }
        vm.stopPrank();
        assertEq(f.usedAnswerIdsCount(), f.maxDistinctAnswers());
        assertEq(f.totalPot(), 1024);

        vm.startPrank(alice);
        token.approve(address(f), type(uint256).max);
        vm.expectRevert(ParamutuelWagerV3.TooManyDistinctAnswers.selector);
        f.placeBet("the real answer", 1e18);
        // Existing (attacker-chosen) answers remain bettable.
        f.placeBet("0", 1e18);
        vm.stopPrank();
    }

    // ------------------------------------------------------------------
    // Authority closers (ADR-0005)
    // ------------------------------------------------------------------

    function test_closeBetting_onlyCloser_stopsBets_idempotent() public {
        ParamutuelWagerV3 w = _default();
        vm.prank(stranger);
        vm.expectRevert(ParamutuelWagerV3.NotBettingCloser.selector);
        w.closeBetting();
        vm.prank(proposer);
        vm.expectRevert(ParamutuelWagerV3.NotBettingCloser.selector);
        w.closeBetting();

        vm.warp(2000);
        vm.prank(bCloser);
        w.closeBetting();
        assertTrue(w.bettingClosedByAuthority());
        assertEq(w.bettingClosedAtByAuthority(), 2000);

        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV3.BettingClosed.selector);
        w.placeBet(M0, 1);

        // Second call is a silent no-op: the anchor timestamp does not move.
        vm.warp(3000);
        vm.prank(bCloser);
        w.closeBetting();
        assertEq(w.bettingClosedAtByAuthority(), 2000);
    }

    /// @dev Once the timed close has fired, `closeBetting` is a no-op and must
    ///      NOT set the authority flag (which would re-anchor the window).
    function test_closeBetting_afterTimedClose_isNoop() public {
        ParamutuelWagerV3 w = _default();
        vm.warp(closeAt + 10);
        vm.prank(bCloser);
        w.closeBetting();
        assertFalse(w.bettingClosedByAuthority());
        assertEq(w.bettingClosedAtByAuthority(), 0);
    }

    /// @dev `address(0)` disables the closer role: no real account can call it.
    function test_zeroAddressCloser_disablesRole() public {
        ParamutuelWagerV3 w =
            _enum(closeAt, RES_WIN, resolverAddr, address(0), address(0), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, _two());
        vm.prank(proposer);
        vm.expectRevert(ParamutuelWagerV3.NotBettingCloser.selector);
        w.closeBetting();
        vm.warp(closeAt);
        vm.prank(proposer);
        vm.expectRevert(ParamutuelWagerV3.NotResolutionCloser.selector);
        w.closeResolutionWindow();
    }

    function test_closeResolutionWindow_onlyCloser_requiresBettingClosed_idempotent_enablesEarlyExpire() public {
        ParamutuelWagerV3 w = _default();
        _bet(w, alice, M0, 10);

        vm.prank(rCloser);
        vm.expectRevert(ParamutuelWagerV3.BettingNotClosed.selector);
        w.closeResolutionWindow();

        vm.warp(closeAt);
        vm.prank(stranger);
        vm.expectRevert(ParamutuelWagerV3.NotResolutionCloser.selector);
        w.closeResolutionWindow();

        // Window is still open, so expire is not yet legal.
        vm.expectRevert(ParamutuelWagerV3.ResolutionWindowOver.selector);
        w.expire();

        vm.prank(rCloser);
        w.closeResolutionWindow();
        assertTrue(w.resolutionWindowClosedByAuthority());
        vm.prank(rCloser);
        w.closeResolutionWindow(); // idempotent

        // Resolver is now locked out; anyone may expire before the deadline.
        vm.startPrank(resolverAddr);
        vm.expectRevert(ParamutuelWagerV3.ResolutionWindowOver.selector);
        w.resolve(M0);
        vm.expectRevert(ParamutuelWagerV3.ResolutionWindowOver.selector);
        w.retract();
        vm.stopPrank();
        vm.prank(stranger);
        w.expire();
        assertEq(uint256(w.state()), uint256(ParamutuelWagerV3.State.Retracted));
    }

    /// @dev No-max betting (`bettingCloseTime == 0`) + finite resolution window:
    ///      the window is anchored at the authority close, not at any timestamp
    ///      known at creation.
    function test_noMaxBetting_resolutionWindowAnchoredAtAuthorityClose() public {
        ParamutuelWagerV3 w =
            _enum(0, RES_WIN, resolverAddr, bCloser, address(0), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, _two());
        _bet(w, alice, M0, 10);
        vm.warp(1_000_000); // arbitrarily far in the future — still open
        _bet(w, bob, M1, 10);
        vm.prank(resolverAddr);
        vm.expectRevert(ParamutuelWagerV3.BettingNotClosed.selector);
        w.resolve(M0);
        vm.expectRevert(ParamutuelWagerV3.BettingNotClosed.selector);
        w.expire();

        vm.prank(bCloser);
        w.closeBetting();
        uint256 anchor = block.timestamp;

        vm.warp(anchor + RES_WIN);
        vm.expectRevert(ParamutuelWagerV3.ResolutionWindowOver.selector);
        w.expire();
        vm.warp(anchor + RES_WIN + 1);
        vm.prank(resolverAddr);
        vm.expectRevert(ParamutuelWagerV3.ResolutionWindowOver.selector);
        w.resolve(M0);
        w.expire();
    }

    /// @dev ADR-0019 finding 6: an early authority close pulls the effective
    ///      resolution deadline *earlier* than the immutable `resolutionDeadline`.
    function test_earlyAuthorityClose_shortensEffectiveResolutionDeadline() public {
        ParamutuelWagerV3 w = _default();
        _bet(w, alice, M0, 10);
        uint256 early = closeAt - 1 hours;
        vm.warp(early);
        vm.prank(bCloser);
        w.closeBetting();

        vm.warp(early + RES_WIN + 1);
        assertLt(block.timestamp, w.resolutionDeadline());
        vm.prank(resolverAddr);
        vm.expectRevert(ParamutuelWagerV3.ResolutionWindowOver.selector);
        w.resolve(M0);
        w.expire();
    }

    /// @dev No-max resolution (`resolutionWindow == 0`): expire is impossible
    ///      until the resolution closer acts; the resolver may act indefinitely.
    function test_noMaxResolution_expireRequiresResolutionCloser() public {
        ParamutuelWagerV3 w =
            _enum(closeAt, 0, resolverAddr, address(0), rCloser, ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, _two());
        ParamutuelWagerV3 w2 =
            _enum(closeAt, 0, resolverAddr, address(0), rCloser, ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, _two());
        _bet(w, alice, M0, 10);
        _bet(w2, alice, M0, 10);
        vm.warp(uint256(closeAt) + 365 days);
        vm.expectRevert(ParamutuelWagerV3.ResolutionWindowOver.selector);
        w.expire();
        vm.prank(rCloser);
        w.closeResolutionWindow();
        w.expire();

        // A second wager: the resolver may still act a year after betting closed.
        vm.prank(resolverAddr);
        w2.resolve(M0);
        assertEq(uint256(w2.state()), uint256(ParamutuelWagerV3.State.Resolved));
    }

    // ------------------------------------------------------------------
    // Resolve / retract / expire guards
    // ------------------------------------------------------------------

    function test_finalisers_requireBettingClosed_bothModes() public {
        ParamutuelWagerV3 w = _default();
        _bet(w, alice, M0, 10);
        vm.startPrank(resolverAddr);
        vm.expectRevert(ParamutuelWagerV3.BettingNotClosed.selector);
        w.resolve(M0);
        vm.expectRevert(ParamutuelWagerV3.BettingNotClosed.selector);
        w.retract();
        vm.stopPrank();
        vm.expectRevert(ParamutuelWagerV3.BettingNotClosed.selector);
        w.expire();

        ParamutuelWagerV3 f = _free(closeAt, RES_WIN, address(0), address(0));
        _betFree(f, alice, "a", 10);
        vm.prank(resolverAddr);
        vm.expectRevert(ParamutuelWagerV3.BettingNotClosed.selector);
        f.resolve("a");
    }

    /// @dev Window is inclusive at `close + window`; expire legal only strictly after.
    function test_resolutionWindowBoundaries_bothModes() public {
        ParamutuelWagerV3 w = _default();
        ParamutuelWagerV3 w2 = _default();
        ParamutuelWagerV3 f = _free(closeAt, RES_WIN, address(0), address(0));
        _bet(w, alice, M0, 10);
        _bet(w2, alice, M0, 10);
        _betFree(f, alice, "a", 10);

        vm.warp(closeAt + RES_WIN);
        vm.expectRevert(ParamutuelWagerV3.ResolutionWindowOver.selector);
        w.expire();
        vm.prank(resolverAddr);
        w.resolve(M0); // last legal second

        vm.warp(closeAt + RES_WIN + 1);
        vm.startPrank(resolverAddr);
        vm.expectRevert(ParamutuelWagerV3.ResolutionWindowOver.selector);
        w2.resolve(M0);
        vm.expectRevert(ParamutuelWagerV3.ResolutionWindowOver.selector);
        w2.retract();
        vm.expectRevert(ParamutuelWagerV3.ResolutionWindowOver.selector);
        f.resolve("a");
        vm.stopPrank();
        w2.expire();
        f.expire();
    }

    function test_onlyResolver_canResolveOrRetract() public {
        ParamutuelWagerV3 w = _default();
        _bet(w, alice, M0, 10);
        vm.warp(closeAt);
        // Proposer is NOT the resolver here (delegated resolution, ADR-0001).
        vm.startPrank(proposer);
        vm.expectRevert(ParamutuelWagerV3.NotResolver.selector);
        w.resolve(M0);
        vm.expectRevert(ParamutuelWagerV3.NotResolver.selector);
        w.retract();
        vm.stopPrank();
        vm.prank(resolverAddr);
        w.resolve(M0);
    }

    function test_alreadyFinalized_forEveryFinaliserPair() public {
        ParamutuelWagerV3 w = _default();
        ParamutuelWagerV3 f = _free(closeAt, RES_WIN, address(0), address(0));
        _bet(w, alice, M0, 10);
        _betFree(f, alice, "a", 10);
        vm.warp(closeAt);
        vm.startPrank(resolverAddr);
        w.resolve(M0);
        vm.expectRevert(ParamutuelWagerV3.AlreadyFinalized.selector);
        w.resolve(M0);
        vm.expectRevert(ParamutuelWagerV3.AlreadyFinalized.selector);
        w.retract();
        vm.stopPrank();
        vm.warp(closeAt + RES_WIN + 1);
        vm.expectRevert(ParamutuelWagerV3.AlreadyFinalized.selector);
        w.expire();

        f.expire();
        vm.expectRevert(ParamutuelWagerV3.AlreadyFinalized.selector);
        f.expire();
        // The window is over, but the AlreadyFinalized guard is checked first.
        vm.prank(resolverAddr);
        vm.expectRevert(ParamutuelWagerV3.AlreadyFinalized.selector);
        f.resolve("a");
    }

    // ------------------------------------------------------------------
    // Claims
    // ------------------------------------------------------------------

    function test_claim_whileOpen_revertsNotOpen() public {
        ParamutuelWagerV3 w = _default();
        _bet(w, alice, M0, 10);
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV3.NotOpen.selector);
        w.claim();
    }

    function test_claim_nonBettorAndEmptyWager_nothingToClaim() public {
        ParamutuelWagerV3 w = _default();
        ParamutuelWagerV3 empty = _default();
        _bet(w, alice, M0, 10);
        vm.warp(closeAt);
        vm.prank(resolverAddr);
        w.retract();
        vm.prank(stranger);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();

        // A wager with zero bets can still be expired (no stuck state) and
        // nobody can claim anything from it.
        vm.warp(closeAt + RES_WIN + 1);
        empty.expire();
        assertTrue(empty.feesCharged());
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        empty.claim();
    }

    function test_claim_transferFalse_revertsAndCanRetry() public {
        ParamutuelWagerV3 w = _default();
        _bet(w, alice, M0, 10);
        vm.warp(closeAt);
        vm.prank(resolverAddr);
        w.resolve(M0);
        token.setFailTransfer(true);
        vm.prank(alice);
        vm.expectRevert(bytes("TRANSFER"));
        w.claim();
        // The revert rolled back `hasClaimed`, so the claim is retryable.
        assertFalse(w.hasClaimed(alice));
        token.setFailTransfer(false);
        vm.prank(alice);
        assertEq(w.claim(), 10);
    }

    function test_claim_reentrancyBlocked() public {
        ReentrantTokenV3 evil = new ReentrantTokenV3();
        evil.mint(alice, 100);
        vm.prank(proposer);
        ParamutuelWagerV3 w = ParamutuelWagerV3(
            factory.createEnumeratedWager(
                address(evil), "q", _two(), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, closeAt, RES_WIN,
                resolverAddr, address(0), address(0), new address[](0), new uint16[](0)
            )
        );
        vm.startPrank(alice);
        evil.approve(address(w), type(uint256).max);
        w.placeBet(M0, 100);
        vm.stopPrank();
        vm.warp(closeAt);
        vm.prank(resolverAddr);
        w.resolve(M0);
        evil.arm(address(w));
        vm.prank(alice);
        vm.expectRevert(bytes("REENTRANCY"));
        w.claim();
        assertEq(evil.balanceOf(address(w)), 100);
    }

    // ------------------------------------------------------------------
    // Fees
    // ------------------------------------------------------------------

    /// @dev Three-way fee split: slices are floor(fees * bps_i / totalBps) with
    ///      the last recipient absorbing rounding. Fees are charged once and the
    ///      balances sum to exactly `floor(totalPot * totalBps / 10000)`.
    function test_feeSplit_lastRecipientTakesRemainder_withdrawOnce() public {
        factory = new ParamutuelFactoryV3(treasury, 100, MIN_BET_WIN, MIN_RES_WIN);
        address[] memory r = new address[](2);
        uint16[] memory b = new uint16[](2);
        r[0] = alice;
        r[1] = bob;
        b[0] = 33;
        b[1] = 67;
        vm.prank(proposer);
        ParamutuelWagerV3 w = ParamutuelWagerV3(
            factory.createEnumeratedWager(
                address(token), "q", _two(), ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, closeAt, RES_WIN,
                resolverAddr, address(0), address(0), r, b
            )
        );
        _bet(w, alice, M0, 10_007);
        _bet(w, bob, M1, 3);
        vm.warp(closeAt);

        vm.prank(treasury);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector); // nothing accrued yet
        w.withdrawFees();

        vm.prank(resolverAddr);
        w.resolve(M0);
        uint256 pot = w.totalPot();
        assertEq(pot, 10_010);
        uint256 fees = (pot * 200) / 10_000; // floor(200.2) = 200
        uint256 s0 = (fees * 100) / 200; // treasury 100
        uint256 s1 = (fees * 33) / 200; // alice 33
        assertEq(w.feeBalances(treasury), s0);
        assertEq(w.feeBalances(alice), s1);
        assertEq(w.feeBalances(bob), fees - s0 - s1);

        vm.prank(treasury);
        assertEq(w.withdrawFees(), s0);
        vm.prank(treasury);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.withdrawFees();

        vm.prank(alice);
        assertEq(w.claim(), 10_010 - fees);
        vm.prank(alice);
        w.withdrawFees();
        vm.prank(bob);
        w.withdrawFees();
        assertEq(token.balanceOf(address(w)), 0);
    }

    function test_withdrawFees_transferFalse_reverts() public {
        factory = new ParamutuelFactoryV3(treasury, 500, MIN_BET_WIN, MIN_RES_WIN);
        ParamutuelWagerV3 w = _default();
        _bet(w, alice, M0, 1000);
        vm.warp(closeAt);
        vm.prank(resolverAddr);
        w.retract();
        token.setFailTransfer(true);
        vm.prank(treasury);
        vm.expectRevert(bytes("TRANSFER"));
        w.withdrawFees();
        assertEq(w.feeBalances(treasury), 50);
    }

    /// @dev 100% fee cap: winners get nothing (claim reverts NothingToClaim in
    ///      resolved state; pays 0 in retracted state) and the entire pot goes
    ///      to fee recipients. The wager is exactly drained either way.
    function test_fullFee_resolveAndRetract_paysOnlyFeeRecipients() public {
        factory = new ParamutuelFactoryV3(treasury, 10_000, MIN_BET_WIN, MIN_RES_WIN);
        ParamutuelWagerV3 w = _default();
        _bet(w, alice, M0, 500);
        _bet(w, bob, M1, 500);
        vm.warp(closeAt);
        vm.prank(resolverAddr);
        w.resolve(M0);
        vm.prank(alice);
        vm.expectRevert(ParamutuelWagerV3.NothingToClaim.selector);
        w.claim();
        vm.prank(treasury);
        assertEq(w.withdrawFees(), 1000);
        assertEq(token.balanceOf(address(w)), 0);

        vm.warp(1000);
        ParamutuelWagerV3 w2 = _default();
        _bet(w2, alice, M0, 500);
        vm.warp(closeAt);
        vm.prank(resolverAddr);
        w2.retract();
        vm.prank(alice);
        assertEq(w2.claim(), 0);
        vm.prank(treasury);
        assertEq(w2.withdrawFees(), 500);
        assertEq(token.balanceOf(address(w2)), 0);
    }

    /// @dev Refund rounding must never overpay: after every bettor claims and
    ///      every fee recipient withdraws, the wager balance is >= 0 (i.e. no
    ///      transfer ran out of funds) and the residual dust is < bettor count.
    function test_retractRounding_neverOverpays() public {
        factory = new ParamutuelFactoryV3(treasury, 333, MIN_BET_WIN, MIN_RES_WIN);
        ParamutuelWagerV3 w = _default();
        _bet(w, alice, M0, 7);
        _bet(w, bob, M1, 13);
        _bet(w, proposer, M0, 101);
        vm.warp(closeAt + RES_WIN + 1);
        w.expire();
        vm.prank(alice);
        w.claim();
        vm.prank(bob);
        w.claim();
        vm.prank(proposer);
        w.claim();
        vm.prank(treasury);
        w.withdrawFees();
        assertLt(token.balanceOf(address(w)), 3);
    }

    // ------------------------------------------------------------------
    // Views and mode dispatch
    // ------------------------------------------------------------------

    function test_views_outcomesAndMaskEnumeration() public {
        ParamutuelWagerV3 w =
            _enum(closeAt, RES_WIN, resolverAddr, address(0), address(0), ParamutuelWagerV3.PayoffPolicy.ANY_OF, _two());
        ParamutuelWagerV3 f = _free(closeAt, RES_WIN, address(0), address(0));
        assertEq(w.outcomesCount(), 2);
        assertEq(w.outcomeText(1), "NO");
        vm.expectRevert(ParamutuelWagerV3.InvalidOutcome.selector);
        w.outcomeText(2);
        _bet(w, alice, 3, 5);
        _bet(w, alice, M1, 5);
        _bet(w, alice, 3, 5); // repeat does not duplicate enumeration entries
        assertEq(w.usedMasksCount(), 2);
        assertEq(w.usedMaskAt(0), 3);
        assertEq(w.userMasksCount(alice), 2);
        assertEq(w.userMaskAt(alice, 1), M1);
        assertEq(w.userTotalBet(alice), 15);
        assertEq(w.betsByMask(alice, 3), 10);

        vm.expectRevert(ParamutuelWagerV3.WrongMode.selector);
        w.usedAnswerIdsCount();
        vm.expectRevert(ParamutuelWagerV3.WrongMode.selector);
        w.usedAnswerId(0);
        vm.warp(closeAt);
        vm.prank(resolverAddr);
        vm.expectRevert(ParamutuelWagerV3.WrongMode.selector);
        w.resolve("a");

        vm.expectRevert(ParamutuelWagerV3.WrongMode.selector);
        f.usedMasksCount();
        vm.expectRevert(ParamutuelWagerV3.WrongMode.selector);
        f.userMasksCount(alice);
        vm.expectRevert(ParamutuelWagerV3.WrongMode.selector);
        f.placeBets(new uint256[](1), new uint256[](1));
        assertEq(f.outcomesCount(), 0);
        vm.expectRevert(ParamutuelWagerV3.InvalidOutcome.selector);
        f.outcomeText(0);
    }
}
