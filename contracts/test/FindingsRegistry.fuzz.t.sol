// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title FindingsRegistryFuzz
 * @notice Property-based tests (TC-C20, TC-C21).
 * @dev 1000 runs per property; any non-zero (msgId, payloadHash) must
 *      round-trip, and a repeated msgId must always revert with AlreadyRecorded.
 */

import "forge-std/Test.sol";
import {FindingsRegistry} from "../src/FindingsRegistry.sol";

contract FindingsRegistryFuzz is Test {
    FindingsRegistry internal reg;
    address internal agent = address(0xB0B);

    function setUp() public {
        reg = new FindingsRegistry();
        reg.grantAgent(agent);
    }

    // TC-C20 — any non-zero (msgId, payloadHash) round-trips
    function testFuzz_recordVerifyRoundTrip(
        bytes32 msgId,
        bytes32 payloadHash,
        string calldata agentName
    ) public {
        vm.assume(msgId != bytes32(0));
        vm.assume(payloadHash != bytes32(0));
        vm.assume(bytes(agentName).length > 0 && bytes(agentName).length <= 32);

        vm.prank(agent);
        reg.recordFinding(msgId, payloadHash, agentName);

        (bytes32 h, string memory a, uint256 t) = reg.verifyFinding(msgId);
        assertEq(h, payloadHash);
        assertEq(a, agentName);
        assertEq(t, block.timestamp);
    }

    // TC-C21 — repeated msgId always reverts
    function testFuzz_replayAlwaysReverts(
        bytes32 msgId,
        bytes32 hash1,
        bytes32 hash2
    ) public {
        vm.assume(msgId != bytes32(0));
        vm.assume(hash1 != bytes32(0));
        vm.assume(hash2 != bytes32(0));

        vm.startPrank(agent);
        reg.recordFinding(msgId, hash1, "hunter");
        vm.expectRevert(FindingsRegistry.AlreadyRecorded.selector);
        reg.recordFinding(msgId, hash2, "risk");
        vm.stopPrank();
    }
}
