// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import {ParamutuelFactoryFreeform} from "../src/ParamutuelFactoryFreeform.sol";

/// @notice Deploy `ParamutuelFactoryFreeform` (ADR-0009 freeform text-answer wagers).
/// Run with:
/// forge script script/DeployFactoryFreeform.s.sol \
///   --rpc-url $RPC_URL \
///   --private-key $PRIVATE_KEY \
///   --broadcast
contract DeployFactoryFreeform is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");

        address treasury = vm.envAddress("TREASURY_ADDRESS");
        uint16 protocolFeeBps = uint16(vm.envOr("PROTOCOL_FEE_BPS", uint256(100)));
        uint64 minBettingWindow = uint64(vm.envOr("MIN_BETTING_WINDOW", uint256(3600)));
        uint64 minResolutionWindow = uint64(vm.envOr("MIN_RESOLUTION_WINDOW", uint256(3600)));

        vm.startBroadcast(deployerPrivateKey);
        ParamutuelFactoryFreeform factory = new ParamutuelFactoryFreeform(
            treasury, protocolFeeBps, minBettingWindow, minResolutionWindow
        );
        vm.stopBroadcast();

        console.log("ParamutuelFactoryFreeform deployed at:", address(factory));
        console.log("Treasury:", treasury);
        console.log("Protocol fee bps:", protocolFeeBps);
        console.log("Min betting window:", minBettingWindow);
        console.log("Min resolution window:", minResolutionWindow);
    }
}
