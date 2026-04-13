// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {console2} from "forge-std/console2.sol";

import {ParamutuelFactoryV3} from "../src/ParamutuelFactoryV3.sol";
import {ParamutuelWagerV3} from "../src/ParamutuelWagerV3.sol";
import {WagerV2Masks} from "../src/libraries/WagerV2Masks.sol";

/// @notice Logs representative V3 gas costs (`forge test --match-contract ParamutuelV3GasReport -vv`).
///         Full table: `forge test --match-path 'test/ParamutuelV3*.t.sol' --gas-report` or `script/profile_v3_gas.sh`.
///         Published numbers: `docs/PARAMUTUEL-V3-GAS.md`.
contract ParamutuelV3GasReport is Test {
    ParamutuelFactoryV3 factory;
    MockTokV3 token;

    address treasury = address(0x1000);
    address proposer = address(0x2000);
    address alice = address(0x3000);

    uint256 constant M0 = 1;
    uint256 constant M1 = 2;

    function setUp() public {
        vm.warp(10_000);
        factory = new ParamutuelFactoryV3(treasury, 0, 1 hours, 1 hours);
        token = new MockTokV3();
        token.mint(proposer, 1e24);
        token.mint(alice, 1e24);
    }

    function _mkEnumerated(ParamutuelWagerV3.PayoffPolicy p) internal returns (ParamutuelWagerV3 w) {
        string[] memory o = new string[](3);
        o[0] = "A";
        o[1] = "B";
        o[2] = "C";
        vm.prank(proposer);
        address wa = factory.createEnumeratedWager(
            address(token),
            "gas",
            o,
            p,
            p == ParamutuelWagerV3.PayoffPolicy.AT_LEAST_K ? uint256(1) : uint256(0),
            uint64(block.timestamp + 1 days),
            1 days,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        w = ParamutuelWagerV3(wa);
    }

    function _mkFreeform() internal returns (ParamutuelWagerV3 w) {
        vm.prank(proposer);
        address wa = factory.createFreeformWager(
            address(token),
            "freeform gas",
            uint64(block.timestamp + 1 days),
            1 days,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        w = ParamutuelWagerV3(wa);
    }

    /// forge-config: default.isolate = true
    function test_LOG_GAS_ENUM_ANY_OF_place_resolve_claim() public {
        ParamutuelWagerV3 w = _mkEnumerated(ParamutuelWagerV3.PayoffPolicy.ANY_OF);
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);

        uint256 g0 = gasleft();
        vm.prank(alice);
        w.placeBet(M0, 1 ether);
        console2.log("V3 enum placeBet (1st distinct mask)", g0 - gasleft());

        vm.prank(alice);
        w.placeBet(M1, 1 ether);
        g0 = gasleft();
        vm.prank(alice);
        w.placeBet(M1, 1 ether);
        console2.log("V3 enum placeBet (same mask)", g0 - gasleft());

        vm.warp(block.timestamp + 2 days);
        g0 = gasleft();
        vm.prank(proposer);
        w.resolve(M0 | M1);
        console2.log("V3 enum resolve ANY_OF (2 usedMasks)", g0 - gasleft());

        g0 = gasleft();
        vm.prank(alice);
        w.claim();
        console2.log("V3 enum claim (2 user masks)", g0 - gasleft());
    }

    /// forge-config: default.isolate = true
    function test_LOG_GAS_ENUM_WEIGHTED_resolve() public {
        ParamutuelWagerV3 w = _mkEnumerated(ParamutuelWagerV3.PayoffPolicy.WEIGHTED_OVERLAP);
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
        console2.log("V3 enum WEIGHTED_OVERLAP resolve (2 masks)", g0 - gasleft());
    }

    /// forge-config: default.isolate = true
    function test_LOG_GAS_factory_createEnumerated_noSeed() public {
        string[] memory o = new string[](3);
        o[0] = "A";
        o[1] = "B";
        o[2] = "C";
        vm.prank(proposer);
        uint256 g0 = gasleft();
        factory.createEnumeratedWager(
            address(token),
            "new",
            o,
            ParamutuelWagerV3.PayoffPolicy.ANY_OF,
            0,
            uint64(block.timestamp + 1 days),
            1 days,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        console2.log("FactoryV3.createEnumeratedWager (no seed)", g0 - gasleft());
    }

    /// forge-config: default.isolate = true
    function test_LOG_GAS_factory_createFreeform() public {
        vm.prank(proposer);
        uint256 g0 = gasleft();
        factory.createFreeformWager(
            address(token),
            "ff new",
            uint64(block.timestamp + 1 days),
            1 days,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        console2.log("FactoryV3.createFreeformWager", g0 - gasleft());
    }

    /// forge-config: default.isolate = true
    function test_LOG_GAS_ENUM_resolve_scales_with_distinct_masks() public {
        uint256 n = 16;
        string[] memory o = new string[](n);
        for (uint256 i; i < n; i++) {
            o[i] = string.concat("O", vm.toString(i));
        }
        vm.prank(proposer);
        address wa = factory.createEnumeratedWager(
            address(token),
            "scale",
            o,
            ParamutuelWagerV3.PayoffPolicy.ANY_OF,
            0,
            uint64(block.timestamp + 1 days),
            1 days,
            address(0),
            proposer,
            proposer,
            new address[](0),
            new uint16[](0)
        );
        ParamutuelWagerV3 w = ParamutuelWagerV3(wa);
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
        console2.log("V3 enum resolve ANY_OF (16 distinct masks)", g0 - gasleft());
    }

    /// forge-config: default.isolate = true
    function test_LOG_GAS_FREE_place_resolve_claim() public {
        ParamutuelWagerV3 w = _mkFreeform();
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);

        uint256 g0 = gasleft();
        vm.prank(alice);
        w.placeBet("Paris", 1 ether);
        console2.log("V3 freeform placeBet (1st distinct answer)", g0 - gasleft());

        vm.prank(alice);
        w.placeBet("London", 1 ether);
        g0 = gasleft();
        vm.prank(alice);
        w.placeBet("Paris", 1 ether);
        console2.log("V3 freeform placeBet (same answerId)", g0 - gasleft());

        vm.warp(block.timestamp + 2 days);
        g0 = gasleft();
        vm.prank(proposer);
        w.resolve("Paris");
        console2.log("V3 freeform resolve", g0 - gasleft());

        g0 = gasleft();
        vm.prank(alice);
        w.claim();
        console2.log("V3 freeform claim (winner)", g0 - gasleft());
    }

    /// forge-config: default.isolate = true
    function test_LOG_GAS_FREE_resolve_many_distinct_answers_in_pool() public {
        ParamutuelWagerV3 w = _mkFreeform();
        vm.prank(alice);
        token.approve(address(w), type(uint256).max);
        uint256 n = 16;
        for (uint256 i; i < n; i++) {
            vm.prank(alice);
            w.placeBet(string.concat("a", vm.toString(i)), 1 ether);
        }
        vm.warp(block.timestamp + 2 days);
        uint256 g0 = gasleft();
        vm.prank(proposer);
        w.resolve("a0");
        console2.log("V3 freeform resolve (16 distinct answers in pool)", g0 - gasleft());
    }
}

contract MockTokV3 {
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
