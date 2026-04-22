// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title FindingsRegistry
 * @notice Append-only registry that records a payload hash per agent finding.
 *
 * Design goals:
 * - Immutability: once a finding is recorded, it cannot be mutated or deleted.
 * - Traceability: emit an event on every write so off-chain indexers reconstruct
 *   the swarm's full history from logs alone.
 * - Permissioning: only whitelisted agent EOAs may write; the owner manages
 *   the whitelist. This prevents spam and makes the registry's content
 *   attributable to the deploying team.
 * - Gas minimalism: one slot per recorded finding (payloadHash + packed
 *   agent+timestamp).
 *
 * Storage:
 *   mapping(bytes32 msgId => Finding) findings
 *
 * msgId is the bytes32-encoded ULID string (UTF-8, right-zero-padded).
 * payloadHash is SHA-256 of the canonical JSON of the agent's payload.
 */
contract FindingsRegistry {
    // ---------------------------------------------------------------- types

    struct Finding {
        bytes32 payloadHash;
        uint64 timestamp;
        string agent;
    }

    // ---------------------------------------------------------------- state

    address public owner;
    mapping(address => bool) public isAgent;
    mapping(bytes32 => Finding) private _findings;

    // ---------------------------------------------------------------- events

    event FindingRecorded(
        bytes32 indexed msgId,
        bytes32 payloadHash,
        string agent,
        uint256 timestamp
    );

    event AgentGranted(address indexed agent);
    event AgentRevoked(address indexed agent);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    // ---------------------------------------------------------------- errors

    error NotOwner();
    error NotAgent();
    error ZeroAddress();
    error ZeroMsgId();
    error ZeroPayloadHash();
    error EmptyAgent();
    error AlreadyRecorded();

    // ---------------------------------------------------------------- modifiers

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyAgent() {
        if (!isAgent[msg.sender]) revert NotAgent();
        _;
    }

    // ---------------------------------------------------------------- ctor

    constructor() {
        owner = msg.sender;
        isAgent[msg.sender] = true;
        emit OwnershipTransferred(address(0), msg.sender);
        emit AgentGranted(msg.sender);
    }

    // ---------------------------------------------------------------- admin

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function grantAgent(address agent) external onlyOwner {
        if (agent == address(0)) revert ZeroAddress();
        isAgent[agent] = true;
        emit AgentGranted(agent);
    }

    function revokeAgent(address agent) external onlyOwner {
        isAgent[agent] = false;
        emit AgentRevoked(agent);
    }

    // ---------------------------------------------------------------- writes

    /**
     * @notice Record a finding.
     * @param msgId Unique id of the finding (ULID right-zero-padded to bytes32).
     * @param payloadHash SHA-256 of the canonical JSON of the agent's payload.
     * @param agent Short identifier, e.g. "hunter" / "social" / "chain" / "risk" / "narrator".
     */
    function recordFinding(
        bytes32 msgId,
        bytes32 payloadHash,
        string calldata agent
    ) external onlyAgent {
        if (msgId == bytes32(0)) revert ZeroMsgId();
        if (payloadHash == bytes32(0)) revert ZeroPayloadHash();
        if (bytes(agent).length == 0) revert EmptyAgent();
        if (_findings[msgId].payloadHash != bytes32(0)) revert AlreadyRecorded();

        _findings[msgId] = Finding({
            payloadHash: payloadHash,
            timestamp: uint64(block.timestamp),
            agent: agent
        });

        emit FindingRecorded(msgId, payloadHash, agent, block.timestamp);
    }

    // ---------------------------------------------------------------- reads

    /**
     * @notice Look up a finding by msgId.
     * @return payloadHash SHA-256 of the payload (zero if never recorded).
     * @return agent Short agent identifier (empty string if never recorded).
     * @return timestamp When the finding was recorded (zero if never recorded).
     */
    function verifyFinding(bytes32 msgId)
        external
        view
        returns (bytes32 payloadHash, string memory agent, uint256 timestamp)
    {
        Finding storage f = _findings[msgId];
        return (f.payloadHash, f.agent, uint256(f.timestamp));
    }

    function exists(bytes32 msgId) external view returns (bool) {
        return _findings[msgId].payloadHash != bytes32(0);
    }
}
