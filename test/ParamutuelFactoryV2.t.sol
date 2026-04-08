// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import {ParamutuelFactoryV2} from "../src/ParamutuelFactoryV2.sol";
import {ParamutuelWagerV2} from "../src/ParamutuelWagerV2.sol";

/// @dev Minimal ERC20 for factory create + seed flows.
contract MockERC20FactoryV2 {
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

/// @notice Factory-only validation and lifecycle (ADR-0008 v2). Wager behavior is covered in ParamutuelV2*.t.sol.
contract ParamutuelFactoryV2Test is Test {
    ParamutuelFactoryV2 factory;
    MockERC20FactoryV2 token;

    address treasury = address(0x1000);
    address proposer = address(0x2000);

    uint64 minBettingWindow = 1 hours;
    uint64 minResolutionWindow = 1 hours;

    uint256 constant M0 = 1;
    uint256 constant M1 = 2;
    /// @dev Bit 3 set — invalid when only 3 base options (indices 0..2).
    uint256 constant M_OUT_OF_RANGE = 8;

    function setUp() public {
        vm.warp(1000);
        factory = new ParamutuelFactoryV2(treasury, 0, minBettingWindow, minResolutionWindow);
        token = new MockERC20FactoryV2();
        token.mint(proposer, 1e24);
    }

    function _threeOutcomes() internal pure returns (string[] memory o) {
        o = new string[](3);
        o[0] = "A";
        o[1] = "B";
        o[2] = "C";
    }

    function _futureCloseAndWindow() internal view returns (uint64, uint64) {
        return (uint64(block.timestamp + 2 hours), 2 hours);
    }

    function test_reverts_seedMaskZero_beforeSuccessfulCreate() public {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();
        string[] memory outcomes = _threeOutcomes();
        uint256[] memory masks = new uint256[](1);
        masks[0] = 0;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = 1 ether;

        vm.startPrank(proposer);
        token.approve(address(factory), type(uint256).max);
        vm.expectRevert(ParamutuelFactoryV2.BadSeedConfig.selector);
        factory.createWager(
            address(token),
            "p",
            outcomes,
            ParamutuelWagerV2.PayoffPolicy.ANY_OF,
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

        assertEq(factory.wagersCount(), 0, "no wager on revert");
    }

    function test_reverts_seedMask_bitBeyondNumOptions() public {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();
        string[] memory outcomes = _threeOutcomes();
        uint256[] memory masks = new uint256[](1);
        masks[0] = M_OUT_OF_RANGE;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = 1 ether;

        vm.startPrank(proposer);
        token.approve(address(factory), type(uint256).max);
        vm.expectRevert(ParamutuelFactoryV2.BadSeedConfig.selector);
        factory.createWager(
            address(token),
            "p",
            outcomes,
            ParamutuelWagerV2.PayoffPolicy.ANY_OF,
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

    function test_reverts_seedMask_singleWinner_requiresSingleBit() public {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();
        string[] memory outcomes = _threeOutcomes();
        uint256[] memory masks = new uint256[](1);
        masks[0] = M0 | M1;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = 1 ether;

        vm.startPrank(proposer);
        token.approve(address(factory), type(uint256).max);
        vm.expectRevert(ParamutuelFactoryV2.BadSeedConfig.selector);
        factory.createWager(
            address(token),
            "p",
            outcomes,
            ParamutuelWagerV2.PayoffPolicy.SINGLE_WINNER,
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

    function test_reverts_policyParam_atLeastK_zero() public {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();
        string[] memory outcomes = _threeOutcomes();

        vm.prank(proposer);
        vm.expectRevert(ParamutuelFactoryV2.InvalidPolicyParam.selector);
        factory.createWager(
            address(token),
            "p",
            outcomes,
            ParamutuelWagerV2.PayoffPolicy.AT_LEAST_K,
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
        string[] memory outcomes = _threeOutcomes();

        vm.prank(proposer);
        vm.expectRevert(ParamutuelFactoryV2.InvalidPolicyParam.selector);
        factory.createWager(
            address(token),
            "p",
            outcomes,
            ParamutuelWagerV2.PayoffPolicy.AT_LEAST_K,
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
        string[] memory outcomes = _threeOutcomes();

        vm.prank(proposer);
        vm.expectRevert(ParamutuelFactoryV2.InvalidPolicyParam.selector);
        factory.createWager(
            address(token),
            "p",
            outcomes,
            ParamutuelWagerV2.PayoffPolicy.ANY_OF,
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

    function test_seededCreate_incrementsWagersCount_andMovesTokens() public {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();
        string[] memory outcomes = _threeOutcomes();
        uint256[] memory masks = new uint256[](2);
        masks[0] = M0;
        masks[1] = M1;
        uint256[] memory amounts = new uint256[](2);
        amounts[0] = 10 ether;
        amounts[1] = 20 ether;

        uint256 beforeProposer = token.balanceOf(proposer);

        vm.startPrank(proposer);
        token.approve(address(factory), type(uint256).max);
        address wa = factory.createWager(
            address(token),
            "p",
            outcomes,
            ParamutuelWagerV2.PayoffPolicy.ANY_OF,
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

        assertEq(factory.wagersCount(), 1);
        assertEq(token.balanceOf(proposer), beforeProposer - 30 ether);
        assertEq(token.balanceOf(wa), 30 ether);
        ParamutuelWagerV2 w = ParamutuelWagerV2(wa);
        assertEq(w.ticketPoolTotal(M0), 10 ether);
        assertEq(w.ticketPoolTotal(M1), 20 ether);
    }

    function test_reverts_tooManyOutcomes() public {
        (uint64 close, uint64 resWin) = _futureCloseAndWindow();
        string[] memory outcomes = new string[](65);
        for (uint256 i; i < 65; i++) {
            outcomes[i] = "x";
        }

        vm.prank(proposer);
        vm.expectRevert(ParamutuelFactoryV2.TooManyOutcomes.selector);
        factory.createWager(
            address(token),
            "p",
            outcomes,
            ParamutuelWagerV2.PayoffPolicy.ANY_OF,
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
}
