// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import {ParamutuelFactoryV3} from "../src/ParamutuelFactoryV3.sol";
import {ParamutuelWagerV3} from "../src/ParamutuelWagerV3.sol";

contract MockERC20FactoryV3 {
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
}

/// @notice Factory-only validation for ADR-0010 V3. Ports the
///         pre-migration `ParamutuelFactoryV2.t.sol` coverage (seed mask
///         sanity, policyParam bounds, MAX_OUTCOMES cap, seed token flow)
///         onto the unified V3 factory. Wager execution semantics are covered
///         in `ParamutuelV3Enumerated.t.sol` / `ParamutuelV3Freeform.t.sol`.
contract ParamutuelFactoryV3Test is Test {
    ParamutuelFactoryV3 factory;
    MockERC20FactoryV3 token;

    address treasury = address(0x1000);
    address proposer = address(0x2000);

    uint64 minBettingWindow = 1 hours;
    uint64 minResolutionWindow = 1 hours;

    uint256 constant M0 = 1;
    uint256 constant M1 = 2;
    /// @dev Bit 3 set — invalid when only 3 base outcomes (indices 0..2).
    uint256 constant M_OUT_OF_RANGE = 8;

    function setUp() public {
        vm.warp(1000);
        factory = new ParamutuelFactoryV3(treasury, 0, minBettingWindow, minResolutionWindow);
        token = new MockERC20FactoryV3();
        token.mint(proposer, 1e24);
    }

    function _threeOutcomes() internal pure returns (string[] memory o) {
        o = new string[](3);
        o[0] = "A";
        o[1] = "B";
        o[2] = "C";
    }

    function _nSameOutcomes(uint256 n) internal pure returns (string[] memory o) {
        o = new string[](n);
        for (uint256 i; i < n; i++) {
            o[i] = "x";
        }
    }

    function _futureCloseAndWindow() internal view returns (uint64, uint64) {
        return (uint64(block.timestamp + 2 hours), 2 hours);
    }

    // ---- Seed mask validation --------------------------------------------

    /// @dev Helper wraps the 14-argument seeded factory call so that
    ///      individual revert tests stay under `via_ir`'s Yul stack ceiling.
    function _expectSeedRevert(ParamutuelWagerV3.PayoffPolicy policy, uint256[] memory masks, uint256[] memory amounts)
        internal
    {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();
        vm.startPrank(proposer);
        token.approve(address(factory), type(uint256).max);
        vm.expectRevert(ParamutuelFactoryV3.BadSeedConfig.selector);
        factory.createEnumeratedWager(
            address(token),
            "p",
            _threeOutcomes(),
            policy,
            0,
            close,
            resWin,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0),
            masks,
            amounts
        );
        vm.stopPrank();
    }

    function test_reverts_seedMaskZero_beforeSuccessfulCreate() public {
        uint256[] memory masks = new uint256[](1);
        masks[0] = 0;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = 1 ether;
        _expectSeedRevert(ParamutuelWagerV3.PayoffPolicy.ANY_OF, masks, amounts);
        assertEq(factory.wagersCount(), 0, "no wager recorded on revert");
    }

    function test_reverts_seedMask_bitBeyondNumOptions() public {
        uint256[] memory masks = new uint256[](1);
        masks[0] = M_OUT_OF_RANGE;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = 1 ether;
        _expectSeedRevert(ParamutuelWagerV3.PayoffPolicy.ANY_OF, masks, amounts);
    }

    function test_reverts_seedMask_singleWinner_requiresSingleBit() public {
        uint256[] memory masks = new uint256[](1);
        masks[0] = M0 | M1;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = 1 ether;
        _expectSeedRevert(ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, masks, amounts);
    }

    // ---- Policy parameter sanity ------------------------------------------

    function test_reverts_policyParam_atLeastK_zero() public {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();

        vm.prank(proposer);
        vm.expectRevert(ParamutuelFactoryV3.InvalidPolicyParam.selector);
        factory.createEnumeratedWager(
            address(token),
            "p",
            _threeOutcomes(),
            ParamutuelWagerV3.PayoffPolicy.AT_LEAST_K,
            0,
            close,
            resWin,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
    }

    function test_reverts_policyParam_atLeastK_exceedsOutcomes() public {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();

        vm.prank(proposer);
        vm.expectRevert(ParamutuelFactoryV3.InvalidPolicyParam.selector);
        factory.createEnumeratedWager(
            address(token),
            "p",
            _threeOutcomes(),
            ParamutuelWagerV3.PayoffPolicy.AT_LEAST_K,
            4,
            close,
            resWin,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
    }

    function test_reverts_policyParam_nonZeroForAnyOf() public {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();

        vm.prank(proposer);
        vm.expectRevert(ParamutuelFactoryV3.InvalidPolicyParam.selector);
        factory.createEnumeratedWager(
            address(token),
            "p",
            _threeOutcomes(),
            ParamutuelWagerV3.PayoffPolicy.ANY_OF,
            1,
            close,
            resWin,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
    }

    // ---- Seeded create: token flow + accounting --------------------------

    /// @dev Helper isolates the 14-argument seeded factory call into its own
    ///      stack frame to keep the calling test below `via_ir`'s Yul stack
    ///      limit.
    function _createSeededAnyOfThreeOutcomes(uint256[] memory masks, uint256[] memory amounts)
        internal
        returns (address wa)
    {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();
        vm.startPrank(proposer);
        token.approve(address(factory), type(uint256).max);
        wa = factory.createEnumeratedWager(
            address(token),
            "p",
            _threeOutcomes(),
            ParamutuelWagerV3.PayoffPolicy.ANY_OF,
            0,
            close,
            resWin,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0),
            masks,
            amounts
        );
        vm.stopPrank();
    }

    function test_seededCreate_incrementsWagersCount_andMovesTokens() public {
        uint256[] memory masks = new uint256[](2);
        masks[0] = M0;
        masks[1] = M1;
        uint256[] memory amounts = new uint256[](2);
        amounts[0] = 10 ether;
        amounts[1] = 20 ether;

        uint256 beforeProposer = token.balanceOf(proposer);
        address wa = _createSeededAnyOfThreeOutcomes(masks, amounts);

        assertEq(factory.wagersCount(), 1);
        assertEq(token.balanceOf(proposer), beforeProposer - 30 ether);
        assertEq(token.balanceOf(wa), 30 ether);
        ParamutuelWagerV3 w = ParamutuelWagerV3(wa);
        // V3 exposes global stake-by-mask via the `ticketPoolByMask` public
        // mapping (renamed from V2's `ticketPoolTotal` getter).
        assertEq(w.ticketPoolByMask(M0), 10 ether);
        assertEq(w.ticketPoolByMask(M1), 20 ether);
    }

    // ---- Outcome cap -------------------------------------------------------

    function test_v3_factory_MAX_OUTCOMES_is_255() public view {
        assertEq(factory.MAX_OUTCOMES(), 255);
    }

    /// @notice V3 lifts the old V2 64-outcome cap — 65-outcome creates now succeed.
    function test_v3_create_succeeds_with_65_outcomes() public {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();
        string[] memory outcomes = _nSameOutcomes(65);

        vm.startPrank(proposer);
        token.approve(address(factory), type(uint256).max);
        uint256 before = factory.wagersCount();
        factory.createEnumeratedWager(
            address(token),
            "p",
            outcomes,
            ParamutuelWagerV3.PayoffPolicy.ANY_OF,
            0,
            close,
            resWin,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        vm.stopPrank();
        assertEq(factory.wagersCount(), before + 1);
    }

    function test_v3_reverts_when_outcomes_length_exceeds_MAX_OUTCOMES() public {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();
        string[] memory outcomes = _nSameOutcomes(256);

        vm.prank(proposer);
        vm.expectRevert(ParamutuelFactoryV3.TooManyOutcomes.selector);
        factory.createEnumeratedWager(
            address(token),
            "p",
            outcomes,
            ParamutuelWagerV3.PayoffPolicy.ANY_OF,
            0,
            close,
            resWin,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
    }

    // ---- Lifecycle config --------------------------------------------------

    /// @notice When both `bettingCloseTime == 0` AND no `bettingCloser` address
    ///         is provided, the wager has no way to progress past Open — the
    ///         factory must reject the config.
    function test_reverts_when_bettingClose_zero_and_noBettingCloser() public {
        vm.prank(proposer);
        vm.expectRevert(ParamutuelFactoryV3.InvalidLifecycleConfig.selector);
        factory.createEnumeratedWager(
            address(token),
            "p",
            _threeOutcomes(),
            ParamutuelWagerV3.PayoffPolicy.ANY_OF,
            0,
            uint64(0),
            2 hours,
            address(0),
            address(0),
            proposer,
            new address[](0),
            new uint16[](0)
        );
    }

    function test_reverts_when_resolutionWindow_zero_and_noResolutionCloser() public {
        (uint64 close,) = _futureCloseAndWindow();
        vm.prank(proposer);
        vm.expectRevert(ParamutuelFactoryV3.InvalidLifecycleConfig.selector);
        factory.createEnumeratedWager(
            address(token),
            "p",
            _threeOutcomes(),
            ParamutuelWagerV3.PayoffPolicy.ANY_OF,
            0,
            close,
            uint64(0),
            address(0),
            proposer,
            address(0),
            new address[](0),
            new uint16[](0)
        );
    }

    function test_freeform_createFactory_emitsFreeformEvent_andRecordsWager() public {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();
        vm.prank(proposer);
        address wa = factory.createFreeformWager(
            address(token),
            "ff",
            close,
            resWin,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        assertEq(factory.wagersCount(), 1);
        assertEq(factory.wagers(0), wa);
        ParamutuelWagerV3 w = ParamutuelWagerV3(wa);
        assertEq(uint256(w.MODE()), uint256(ParamutuelWagerV3.WagerMode.Freeform));
        assertEq(w.maxDistinctAnswers(), 1024);
    }
}
