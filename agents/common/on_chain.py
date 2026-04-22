"""On-chain adapter for the FindingsRegistry contract.

The hashes agents produce here must match what ``forge`` sees on BNB Testnet.
Canonical-JSON hashing in ``hasher.py`` guarantees the input; this module
handles the wire-level encoding:

* ``msg_id`` (26-char ULID string) → ``bytes32`` by UTF-8 encoding with
  right-zero padding. Decoding is symmetric.
* ``payload_hash`` (64-hex char string) → ``bytes32`` via ``bytes.fromhex``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from eth_account import Account
from web3 import AsyncWeb3, Web3
from web3.providers.async_rpc import AsyncHTTPProvider

FINDINGS_REGISTRY_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "recordFinding",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "msgId", "type": "bytes32"},
            {"name": "payloadHash", "type": "bytes32"},
            {"name": "agent", "type": "string"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "verifyFinding",
        "stateMutability": "view",
        "inputs": [{"name": "msgId", "type": "bytes32"}],
        "outputs": [
            {"name": "payloadHash", "type": "bytes32"},
            {"name": "agent", "type": "string"},
            {"name": "timestamp", "type": "uint256"},
        ],
    },
    {
        "type": "event",
        "name": "FindingRecorded",
        "anonymous": False,
        "inputs": [
            {"name": "msgId", "type": "bytes32", "indexed": True},
            {"name": "payloadHash", "type": "bytes32", "indexed": False},
            {"name": "agent", "type": "string", "indexed": False},
            {"name": "timestamp", "type": "uint256", "indexed": False},
        ],
    },
]


def msg_id_to_bytes32(msg_id: str) -> bytes:
    """Encode a 26-char ULID as right-zero-padded 32 bytes."""
    raw = msg_id.encode("utf-8")
    if len(raw) > 32:
        raise ValueError(f"msg_id too long to fit in bytes32: {msg_id!r}")
    return raw.ljust(32, b"\x00")


def payload_hash_hex_to_bytes32(payload_hash_hex: str) -> bytes:
    """Decode the 64-hex-char payload hash into 32 raw bytes."""
    if len(payload_hash_hex) != 64:
        raise ValueError(f"payload_hash must be 64 hex chars; got {len(payload_hash_hex)}")
    return bytes.fromhex(payload_hash_hex)


@dataclass(frozen=True)
class OnChainRecord:
    """A record returned from verifyFinding."""

    payload_hash_hex: str
    agent: str
    timestamp: int


class OnChainAnchor:
    """Async wrapper around the FindingsRegistry contract."""

    def __init__(
        self,
        *,
        rpc_url: str,
        contract_address: str,
        private_key: str,
        chain_id: int,
        w3: AsyncWeb3 | None = None,
    ) -> None:
        """Build a Web3 + contract binding; optionally accept a pre-built AsyncWeb3 for tests."""
        self._w3 = w3 or AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self._account = Account.from_key(private_key) if private_key else None
        self._chain_id = chain_id
        self._contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=FINDINGS_REGISTRY_ABI,
        )

    @property
    def address(self) -> str:
        """Return the anchored agent wallet address (checksummed)."""
        if self._account is None:
            raise RuntimeError("OnChainAnchor has no private key configured")
        return cast(str, self._account.address)

    async def record(self, *, msg_id: str, payload_hash_hex: str, agent: str) -> tuple[str, int]:
        """Call ``recordFinding`` and wait for inclusion.

        Returns (tx_hash_hex, block_number).
        """
        if self._account is None:
            raise RuntimeError("OnChainAnchor cannot sign without a private key")

        fn = self._contract.functions.recordFinding(
            msg_id_to_bytes32(msg_id),
            payload_hash_hex_to_bytes32(payload_hash_hex),
            agent,
        )

        nonce = await self._w3.eth.get_transaction_count(self._account.address)
        gas_price = await self._w3.eth.gas_price
        tx = await fn.build_transaction(
            {
                "chainId": self._chain_id,
                "from": self._account.address,
                "nonce": nonce,
                "gasPrice": gas_price,
            }
        )
        signed = self._account.sign_transaction(tx)
        tx_hash = await self._w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = await self._w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex(), int(receipt["blockNumber"])

    async def verify(self, msg_id: str) -> OnChainRecord | None:
        """Read back the record for ``msg_id``; ``None`` if not recorded."""
        result = await self._contract.functions.verifyFinding(msg_id_to_bytes32(msg_id)).call()
        payload_hash_hex = result[0].hex() if isinstance(result[0], bytes) else str(result[0])[2:]
        agent = result[1]
        timestamp = int(result[2])
        if int(payload_hash_hex, 16) == 0 and timestamp == 0:
            return None
        return OnChainRecord(payload_hash_hex=payload_hash_hex, agent=agent, timestamp=timestamp)


class NullAnchor:
    """No-op anchor used in tests and when the wallet is unconfigured.

    Every mutating call returns placeholder values so higher-level code can
    exercise its happy path without network I/O.
    """

    address: str = "0x0000000000000000000000000000000000000000"

    async def record(
        self,
        *,
        msg_id: str,  # noqa: ARG002
        payload_hash_hex: str,  # noqa: ARG002
        agent: str,  # noqa: ARG002
    ) -> tuple[str, int]:
        """Return a deterministic placeholder so callers get predictable shapes."""
        return ("0x" + "0" * 64, 0)

    async def verify(self, msg_id: str) -> OnChainRecord | None:  # noqa: ARG002
        """Always return ``None`` — no records exist in the null anchor."""
        return None
