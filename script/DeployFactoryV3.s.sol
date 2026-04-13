// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import {ParamutuelFactoryV3} from "../src/ParamutuelFactoryV3.sol";

/// @notice Deploy `ParamutuelFactoryV3` (single factory: enumerated + freeform wagers).
/// Run with:
/// forge script script/DeployFactoryV3.s.sol \
///   --rpc-url $RPC_URL_BASE_SEPOLIA \
///   --private-key $PRIVATE_KEY \
///   --broadcast
contract DeployFactoryV3 is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");

        address treasury = vm.envAddress("TREASURY_ADDRESS");
        uint16 protocolFeeBps = uint16(vm.envOr("PROTOCOL_FEE_BPS", uint256(100)));
        uint64 minBettingWindow = uint64(vm.envOr("MIN_BETTING_WINDOW", uint256(3600)));
        uint64 minResolutionWindow = uint64(vm.envOr("MIN_RESOLUTION_WINDOW", uint256(3600)));

        vm.startBroadcast(deployerPrivateKey);
        ParamutuelFactoryV3 factory = new ParamutuelFactoryV3(
            treasury, protocolFeeBps, minBettingWindow, minResolutionWindow
        );
        vm.stopBroadcast();

        console.log("ParamutuelFactoryV3 deployed at:", address(factory));
        console.log("Treasury:", treasury);
        console.log("Protocol fee bps:", protocolFeeBps);
        console.log("Min betting window:", minBettingWindow);
        console.log("Min resolution window:", minResolutionWindow);
    }
}
