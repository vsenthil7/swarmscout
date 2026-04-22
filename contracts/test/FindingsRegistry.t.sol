// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title FindingsRegistryTest
 * @notice Forge unit tests covering TC-C01 through TC-C10 (happy path,
 *         reverts, access control) plus five extra boundary tests for
 *         exists(), ownership transfer zero-address, and non-owner revert paths.
 */

import "forge-std/Test.sol";
import {FindingsRegistry} from "../src/FindingsRegistry.sol";

contract FindingsRegistryTest is Test {
    FindingsRegistry internal reg;

    address internal owner = address(0xA11CE);
    address internal agent = address(0xB0B);
    address internal outsider = address(0xDEAD);

    bytes32 internal constant MSG_ID = keccak256("msg-1");
    bytes32 internal constant PAYLOAD_HASH = keccak256("payload-1");

    event FindingRecorded(
        bytes32 indexed msgId,
        bytes32 payloadHash,
        string agent,
        uint256 timestamp
    );

    function setUp() public {
        vm.prank(owner);
        reg = new FindingsRegistry();
        vm.prank(owner);
        reg.grantAgent(agent);
    }

    // TC-C01 — happy path
    function test_recordFinding_happyPath() public {
        vm.prank(agent);
        vm.expectEmit(true, true, true, true);
        emit FindingRecorded(MSG_ID, PAYLOAD_HASH, "hunter", block.timestamp);
        reg.recordFinding(MSG_ID, PAYLOAD_HASH, "hunter");

        (bytes32 h, string memory a, uint256 t) = reg.verifyFinding(MSG_ID);
        assertEq(h, PAYLOAD_HASH);
        assertEq(a, "hunter");
        assertEq(t, block.timestamp);
    }

    // TC-C02 — non-agent is rejected
    function test_recordFinding_revertsForNonAgent() public {
        vm.prank(outsider);
        vm.expectRevert(FindingsRegistry.NotAgent.selector);
        reg.recordFinding(MSG_ID, PAYLOAD_HASH, "hunter");
    }

    // TC-C03 — zero msgId is rejected
    function test_recordFinding_revertsOnZeroMsgId() public {
        vm.prank(agent);
        vm.expectRevert(FindingsRegistry.ZeroMsgId.selector);
        reg.recordFinding(bytes32(0), PAYLOAD_HASH, "hunter");
    }

    // TC-C04 — zero payload hash is rejected
    function test_recordFinding_revertsOnZeroPayloadHash() public {
        vm.prank(agent);
        vm.expectRevert(FindingsRegistry.ZeroPayloadHash.selector);
        reg.recordFinding(MSG_ID, bytes32(0), "hunter");
    }

    // TC-C05 — empty agent string is rejected
    function test_recordFinding_revertsOnEmptyAgent() public {
        vm.prank(agent);
        vm.expectRevert(FindingsRegistry.EmptyAgent.selector);
        reg.recordFinding(MSG_ID, PAYLOAD_HASH, "");
    }

    // TC-C06 — replay of same msgId is rejected
    function test_recordFinding_revertsOnReplay() public {
        vm.startPrank(agent);
        reg.recordFinding(MSG_ID, PAYLOAD_HASH, "hunter");
        vm.expectRevert(FindingsRegistry.AlreadyRecorded.selector);
        reg.recordFinding(MSG_ID, PAYLOAD_HASH, "hunter");
        vm.stopPrank();
    }

    // TC-C07 — verifyFinding on unrecorded msgId returns zeroed struct
    function test_verifyFinding_returnsZeroForMissing() public view {
        (bytes32 h, string memory a, uint256 t) = reg.verifyFinding(keccak256("nope"));
        assertEq(h, bytes32(0));
        assertEq(bytes(a).length, 0);
        assertEq(t, 0);
    }

    // TC-C08 — grantAgent adds, revokeAgent removes
    function test_grantAndRevokeAgent() public {
        address newAgent = address(0xC4FE);
        vm.prank(owner);
        reg.grantAgent(newAgent);
        assertTrue(reg.isAgent(newAgent));

        vm.prank(owner);
        reg.revokeAgent(newAgent);
        assertFalse(reg.isAgent(newAgent));
    }

    // TC-C09 — only owner can grant/revoke
    function test_grantAgent_revertsForNonOwner() public {
        vm.prank(outsider);
        vm.expectRevert(FindingsRegistry.NotOwner.selector);
        reg.grantAgent(address(0x1234));
    }

    // TC-C10 — transferOwnership preserves state
    function test_transferOwnership() public {
        vm.prank(owner);
        reg.transferOwnership(outsider);
        assertEq(reg.owner(), outsider);

        vm.prank(outsider);
        reg.grantAgent(address(0x5678));
        assertTrue(reg.isAgent(address(0x5678)));
    }

    // Extra: exists() mirrors verifyFinding
    function test_exists() public {
        assertFalse(reg.exists(MSG_ID));
        vm.prank(agent);
        reg.recordFinding(MSG_ID, PAYLOAD_HASH, "hunter");
        assertTrue(reg.exists(MSG_ID));
    }

    // Extra: transferOwnership rejects zero address
    function test_transferOwnership_revertsOnZero() public {
        vm.prank(owner);
        vm.expectRevert(FindingsRegistry.ZeroAddress.selector);
        reg.transferOwnership(address(0));
    }

    // Extra: grantAgent rejects zero address
    function test_grantAgent_revertsOnZero() public {
        vm.prank(owner);
        vm.expectRevert(FindingsRegistry.ZeroAddress.selector);
        reg.grantAgent(address(0));
    }

    // Extra: revokeAgent by non-owner reverts
    function test_revokeAgent_revertsForNonOwner() public {
        vm.prank(outsider);
        vm.expectRevert(FindingsRegistry.NotOwner.selector);
        reg.revokeAgent(agent);
    }

    // Extra: transferOwnership by non-owner reverts
    function test_transferOwnership_revertsForNonOwner() public {
        vm.prank(outsider);
        vm.expectRevert(FindingsRegistry.NotOwner.selector);
        reg.transferOwnership(outsider);
    }
}
