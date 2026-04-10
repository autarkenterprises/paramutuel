// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {console2} from "forge-std/console2.sol";

import {ParamutuelFactoryV2} from "../src/ParamutuelFactoryV2.sol";
import {ParamutuelWagerV2} from "../src/ParamutuelWagerV2.sol";
import {WagerV2Masks} from "../src/libraries/WagerV2Masks.sol";

/// @notice Logs representative gas costs (run with `forge test --match-contract ParamutuelV2GasReport -vv`).
///         See `docs/ADR-0008-GAS.md` for tables and `script/profile_v2_gas.sh` for full `--gas-report`.
contract ParamutuelV2GasReport is Test {
    ParamutuelFactoryV2 factory;
    MockTok token;

    address treasury = address(0x1000);
    address proposer = address(0x2000);
    address alice = address(0x3000);

    uint256 constant M0 = 1;
    uint256 constant M1 = 2;

    function setUp() public {
        vm.warp(10_000);
        factory = new ParamutuelFactoryV2(treasury, 0, 1 hours, 1 hours);
        token = new MockTok();
        token.mint(proposer, 1e24);
        token.mint(alice, 1e24);
    }

    function _mkWager(ParamutuelWagerV2.PayoffPolicy p) internal returns (ParamutuelWagerV2 w) {
        string[] memory o = new string[](3);
        o[0] = "A";
        o[1] = "B";
        o[2] = "C";
        vm.prank(proposer);
        address wa = factory.createWager(
            address(token),
            "gas",
            o,
            p,
            p == ParamutuelWagerV2.PayoffPolicy.AT_LEAST_K ? uint256(1) : uint256(0),
            uint64(block.timestamp + 1 days),
            1 days,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        w = ParamutuelWagerV2(wa);
    }

    /// forge-config: default.isolate = true
    function test_LOG_GAS_ANY_OF_place_resolve_claim() public {
        ParamutuelWagerV2 w = _mkWager(ParamutuelWagerV2.PayoffPolicy.ANY_OF);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);

        uint256 g0 = gasleft();
        vm.prank(alice);
        w.placeBet(M0, 1 ether);
        console2.log("ANY_OF placeBet (1st distinct mask)", g0 - gasleft());

        vm.prank(alice);
        w.placeBet(M1, 1 ether);
        g0 = gasleft();
        vm.prank(alice);
        w.placeBet(M1, 1 ether); // same mask — no new usedMask push
        console2.log("ANY_OF placeBet (same mask)", g0 - gasleft());

        vm.warp(block.timestamp + 2 days);
        g0 = gasleft();
        vm.prank(proposer);
        w.resolve(M0 | M1);
        console2.log("ANY_OF resolve (2 usedMasks)", g0 - gasleft());

        g0 = gasleft();
        vm.prank(alice);
        w.claim();
        console2.log("ANY_OF claim (2 user masks)", g0 - gasleft());
    }

    /// forge-config: default.isolate = true
    function test_LOG_GAS_WEIGHTED_resolve() public {
        ParamutuelWagerV2 w = _mkWager(ParamutuelWagerV2.PayoffPolicy.WEIGHTED_OVERLAP);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        vm.prank(alice);
        w.placeBet(M0, 1 ether);
        vm.prank(alice);
        w.placeBet(M0 | M1, 1 ether);

        vm.warp(block.timestamp + 2 days);
        uint256 g0 = gasleft();
        vm.prank(proposer);
        w.resolve(M0 | M1);
        console2.log("WEIGHTED_OVERLAP resolve (2 masks)", g0 - gasleft());
    }

    /// forge-config: default.isolate = true
    function test_LOG_GAS_factory_create() public {
        string[] memory o = new string[](3);
        o[0] = "A";
        o[1] = "B";
        o[2] = "C";
        vm.prank(proposer);
        uint256 g0 = gasleft();
        factory.createWager(
            address(token),
            "new",
            o,
            ParamutuelWagerV2.PayoffPolicy.ANY_OF,
            0,
            uint64(block.timestamp + 1 days),
            1 days,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        console2.log("FactoryV2.createWager (empty seed)", g0 - gasleft());
    }

    /// forge-config: default.isolate = true
    function test_LOG_GAS_resolve_scales_with_distinct_masks() public {
        uint256 n = 16;
        string[] memory o = new string[](n);
        for (uint256 i; i < n; i++) {
            o[i] = string.concat("O", vm.toString(i));
        }
        vm.prank(proposer);
        address wa = factory.createWager(
            address(token),
            "scale",
            o,
            ParamutuelWagerV2.PayoffPolicy.ANY_OF,
            0,
            uint64(block.timestamp + 1 days),
            1 days,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        ParamutuelWagerV2 w = ParamutuelWagerV2(wa);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        for (uint256 i; i < n; i++) {
            vm.prank(alice);
            w.placeBet(uint256(1) << i, 1 ether);
        }
        vm.warp(block.timestamp + 2 days);
        uint256 g0 = gasleft();
        vm.prank(proposer);
        w.resolve(WagerV2Masks.fullSet(n));
        console2.log("ANY_OF resolve (16 distinct masks)", g0 - gasleft());
    }
}

contract MockTok {
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
