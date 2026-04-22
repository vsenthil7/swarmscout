// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title FindingsRegistryInvariant
 * @notice Handler-driven invariant tests (TC-C30, TC-C31).
 * @dev 256 sequence runs at depth 32. Proves that once a hash is recorded
 *      it never changes, and exists() is monotonic (can only flip false->true).
 */

import "forge-std/Test.sol";
import {FindingsRegistry} from "../src/FindingsRegistry.sol";

/// @dev Handler that randomly calls recordFinding and tracks recorded msgIds.
contract Handler is Test {
    FindingsRegistry internal reg;
    bytes32[] public recordedMsgIds;
    mapping(bytes32 => bytes32) public recordedHash;
    mapping(bytes32 => bool) public isRecorded;

    constructor(FindingsRegistry _reg) {
        reg = _reg;
    }

    function recordFinding(uint256 idx, bytes32 hash) external {
        bytes32 msgId = keccak256(abi.encode(idx));
        if (msgId == bytes32(0) || hash == bytes32(0)) return;
        if (isRecorded[msgId]) {
            try reg.recordFinding(msgId, hash, "test") {
                revert("replay should have reverted");
            } catch {
                return;
            }
        }
        try reg.recordFinding(msgId, hash, "test") {
            recordedMsgIds.push(msgId);
            recordedHash[msgId] = hash;
            isRecorded[msgId] = true;
        } catch {
            return;
        }
    }

    function numRecorded() external view returns (uint256) {
        return recordedMsgIds.length;
    }
}

contract FindingsRegistryInvariant is Test {
    FindingsRegistry internal reg;
    Handler internal handler;

    function setUp() public {
        reg = new FindingsRegistry();
        handler = new Handler(reg);
        reg.grantAgent(address(handler));
        targetContract(address(handler));
    }

    // TC-C30 — every recorded msgId still verifies with its original hash
    function invariant_recordedHashesUnchanged() public view {
        uint256 n = handler.numRecorded();
        for (uint256 i; i < n; ++i) {
            bytes32 msgId = handler.recordedMsgIds(i);
            (bytes32 h,,) = reg.verifyFinding(msgId);
            assertEq(h, handler.recordedHash(msgId));
        }
    }

    // TC-C31 — exists() is monotonic (never flips from true to false)
    function invariant_existsIsMonotonic() public view {
        uint256 n = handler.numRecorded();
        for (uint256 i; i < n; ++i) {
            assertTrue(reg.exists(handler.recordedMsgIds(i)));
        }
    }
}
