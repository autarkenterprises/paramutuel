// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import {ParamutuelFactory} from "../src/ParamutuelFactory.sol";

/// @notice Simple deployment script for ParamutuelFactory.
/// Run with:
/// forge script script/DeployFactory.s.sol \
///   --rpc-url $RPC_URL_SEPOLIA \
///   --private-key $PRIVATE_KEY \
///   --broadcast
contract DeployFactory is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");

        // Configure these as desired for your deployment
        address treasury = vm.envAddress("TREASURY_ADDRESS");
        uint16 protocolFeeBps = uint16(vm.envOr("PROTOCOL_FEE_BPS", uint256(200))); // default 2%
        uint64 minBettingWindow = uint64(vm.envOr("MIN_BETTING_WINDOW", uint256(3600))); // 1 hour
        uint64 minResolutionWindow = uint64(vm.envOr("MIN_RESOLUTION_WINDOW", uint256(3600))); // 1 hour

        vm.startBroadcast(deployerPrivateKey);
        ParamutuelFactory factory = new ParamutuelFactory(
            treasury,
            protocolFeeBps,
            minBettingWindow,
            minResolutionWindow
        );
        vm.stopBroadcast();

        console.log("ParamutuelFactory deployed at:", address(factory));
        console.log("Treasury:", treasury);
        console.log("Protocol fee bps:", protocolFeeBps);
        console.log("Min betting window:", minBettingWindow);
        console.log("Min resolution window:", minResolutionWindow);
    }
}

