// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import {Script, console} from "forge-std/Script.sol";
import {RalphProposal} from "../src/RalphProposal.sol";

contract DeployScript is Script {
    // Hats Protocol address on Base mainnet
    address constant HATS_PROTOCOL_BASE = 0x3bc1A0Ad72417f2d411118085256fC53CBdDd137;

    function run() public returns (RalphProposal) {
        uint256 deployerPrivateKey = vm.envUint("RALPH_HATS_PRIVATE_KEY");

        vm.startBroadcast(deployerPrivateKey);

        RalphProposal proposal = new RalphProposal(HATS_PROTOCOL_BASE);

        console.log("RalphProposal deployed to:", address(proposal));
        console.log("Hats Protocol:", HATS_PROTOCOL_BASE);

        vm.stopBroadcast();

        return proposal;
    }
}
