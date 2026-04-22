// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "forge-std/Script.sol";
import {FindingsRegistry} from "../src/FindingsRegistry.sol";

/// @notice Deploy FindingsRegistry to BNB Testnet (or any EVM chain via --rpc-url).
/// Usage:
///   forge script contracts/script/Deploy.s.sol --rpc-url bsc_testnet --broadcast --private-key $AGENT_WALLET_PRIVATE_KEY
contract Deploy is Script {
    function run() external returns (FindingsRegistry reg) {
        uint256 pk = vm.envUint("AGENT_WALLET_PRIVATE_KEY");
        vm.startBroadcast(pk);
        reg = new FindingsRegistry();
        vm.stopBroadcast();
        console2.log("FindingsRegistry deployed at", address(reg));
    }
}
