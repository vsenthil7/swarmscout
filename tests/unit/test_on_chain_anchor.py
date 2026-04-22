"""Coverage tests for agents/common/on_chain.py (OnChainAnchor class)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.common.on_chain import (
    FINDINGS_REGISTRY_ABI,
    OnChainAnchor,
    OnChainRecord,
    msg_id_to_bytes32,
    payload_hash_hex_to_bytes32,
)

# A deterministic hex32 key; it's a well-known Hardhat dev account so static-analysis
# tools recognise it as a test key rather than a secret.
TEST_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_CONTRACT_ADDR = "0x" + "ab" * 20


def _make_fake_w3() -> MagicMock:
    """Build an AsyncWeb3 stand-in with the chain of attributes OnChainAnchor needs."""
    fake_functions = MagicMock()
    fake_record_fn = MagicMock()
    fake_record_fn.build_transaction = AsyncMock(
        return_value={"chainId": 97, "from": "0x0", "nonce": 0, "gasPrice": 1}
    )
    fake_functions.recordFinding = MagicMock(return_value=fake_record_fn)

    fake_verify_fn = MagicMock()
    fake_verify_fn.call = AsyncMock(return_value=(b"\xaa" * 32, "hunter", 123))
    fake_functions.verifyFinding = MagicMock(return_value=fake_verify_fn)

    fake_contract = MagicMock()
    fake_contract.functions = fake_functions

    fake_eth = MagicMock()
    fake_eth.contract = MagicMock(return_value=fake_contract)
    fake_eth.get_transaction_count = AsyncMock(return_value=7)
    fake_eth.gas_price = AsyncMock(return_value=5_000_000_000)
    # Make gas_price an awaitable so `await self._w3.eth.gas_price` resolves.
    # The real AsyncWeb3 exposes gas_price as a property, but OnChainAnchor
    # awaits it, so we need an awaitable.
    fake_eth.gas_price = _awaitable(5_000_000_000)
    fake_eth.send_raw_transaction = AsyncMock(
        return_value=SimpleNamespace(hex=lambda: "0x" + "cd" * 32)
    )
    fake_eth.wait_for_transaction_receipt = AsyncMock(return_value={"blockNumber": 42})

    fake_w3 = MagicMock()
    fake_w3.eth = fake_eth
    return fake_w3


class _Awaitable:
    """Minimal awaitable wrapper that resolves to a fixed value."""

    def __init__(self, value: Any) -> None:
        self._value = value

    def __await__(self):  # type: ignore[no-untyped-def]
        async def _inner() -> Any:
            return self._value

        return _inner().__await__()


def _awaitable(value: Any) -> _Awaitable:
    return _Awaitable(value)


def test_onchain_anchor_address_raises_when_no_private_key() -> None:
    """``.address`` must raise when constructed without a private key."""
    fake_w3 = _make_fake_w3()
    anchor = OnChainAnchor(
        rpc_url="http://rpc",
        contract_address=TEST_CONTRACT_ADDR,
        private_key="",
        chain_id=97,
        w3=fake_w3,
    )
    with pytest.raises(RuntimeError, match="no private key"):
        _ = anchor.address


def test_onchain_anchor_address_returns_checksummed_when_configured() -> None:
    """With a private key the .address property returns the account's checksum address."""
    fake_w3 = _make_fake_w3()
    anchor = OnChainAnchor(
        rpc_url="http://rpc",
        contract_address=TEST_CONTRACT_ADDR,
        private_key=TEST_PRIVATE_KEY,
        chain_id=97,
        w3=fake_w3,
    )
    assert anchor.address.startswith("0x")
    assert len(anchor.address) == 42


@pytest.mark.asyncio
async def test_onchain_anchor_record_returns_tx_hex_and_block() -> None:
    """``record`` builds, signs, sends and waits; returns (tx_hex, block_number)."""
    fake_w3 = _make_fake_w3()
    anchor = OnChainAnchor(
        rpc_url="http://rpc",
        contract_address=TEST_CONTRACT_ADDR,
        private_key=TEST_PRIVATE_KEY,
        chain_id=97,
        w3=fake_w3,
    )

    # Patch sign_transaction on the account to avoid real secp256k1 work.
    signed = SimpleNamespace(rawTransaction=b"\x00" * 4)
    with patch.object(anchor._account, "sign_transaction", return_value=signed):
        tx_hex, block = await anchor.record(
            msg_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            payload_hash_hex="a" * 64,
            agent="hunter",
        )

    assert tx_hex.startswith("0x")
    assert block == 42


@pytest.mark.asyncio
async def test_onchain_anchor_record_raises_when_no_private_key() -> None:
    """``record`` must raise when constructed without a private key."""
    fake_w3 = _make_fake_w3()
    anchor = OnChainAnchor(
        rpc_url="http://rpc",
        contract_address=TEST_CONTRACT_ADDR,
        private_key="",
        chain_id=97,
        w3=fake_w3,
    )
    with pytest.raises(RuntimeError, match="cannot sign"):
        await anchor.record(
            msg_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            payload_hash_hex="a" * 64,
            agent="hunter",
        )


@pytest.mark.asyncio
async def test_onchain_anchor_verify_returns_record_for_present_msg_id() -> None:
    """``verify`` returns an OnChainRecord when the contract has a non-zero entry."""
    fake_w3 = _make_fake_w3()
    anchor = OnChainAnchor(
        rpc_url="http://rpc",
        contract_address=TEST_CONTRACT_ADDR,
        private_key=TEST_PRIVATE_KEY,
        chain_id=97,
        w3=fake_w3,
    )
    rec = await anchor.verify("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert isinstance(rec, OnChainRecord)
    assert rec.agent == "hunter"
    assert rec.timestamp == 123


@pytest.mark.asyncio
async def test_onchain_anchor_verify_returns_none_for_missing_msg_id() -> None:
    """``verify`` returns None when the contract returns an all-zero struct."""
    fake_w3 = _make_fake_w3()
    # Override verifyFinding to return a zero struct.
    fake_w3.eth.contract.return_value.functions.verifyFinding.return_value.call = AsyncMock(
        return_value=(b"\x00" * 32, "", 0)
    )
    anchor = OnChainAnchor(
        rpc_url="http://rpc",
        contract_address=TEST_CONTRACT_ADDR,
        private_key=TEST_PRIVATE_KEY,
        chain_id=97,
        w3=fake_w3,
    )
    rec = await anchor.verify("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert rec is None


@pytest.mark.asyncio
async def test_onchain_anchor_verify_handles_non_bytes_payload_hash() -> None:
    """``verify`` tolerates string-form payload_hash (from JSON-RPC responses)."""
    fake_w3 = _make_fake_w3()
    fake_w3.eth.contract.return_value.functions.verifyFinding.return_value.call = AsyncMock(
        return_value=("0x" + "bb" * 32, "chain", 500)
    )
    anchor = OnChainAnchor(
        rpc_url="http://rpc",
        contract_address=TEST_CONTRACT_ADDR,
        private_key=TEST_PRIVATE_KEY,
        chain_id=97,
        w3=fake_w3,
    )
    rec = await anchor.verify("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert rec is not None
    assert rec.payload_hash_hex == "bb" * 32


def test_onchain_anchor_constructs_with_default_w3_when_not_provided() -> None:
    """When ``w3`` kwarg is None, an AsyncWeb3/AsyncHTTPProvider pair is constructed.

    We intercept both to verify the construction path, since we obviously
    don't want a real RPC connection during tests.
    """
    from agents.common import on_chain as on_chain_mod

    with (
        patch.object(on_chain_mod, "AsyncWeb3") as mock_w3_cls,
        patch.object(on_chain_mod, "AsyncHTTPProvider") as mock_provider,
    ):
        fake_instance = MagicMock()
        fake_eth = MagicMock()
        fake_eth.contract = MagicMock(return_value=MagicMock())
        fake_instance.eth = fake_eth
        mock_w3_cls.return_value = fake_instance

        OnChainAnchor(
            rpc_url="http://rpc",
            contract_address=TEST_CONTRACT_ADDR,
            private_key=TEST_PRIVATE_KEY,
            chain_id=97,
        )

    mock_provider.assert_called_once_with("http://rpc")
    mock_w3_cls.assert_called_once()


def test_abi_shape_sanity() -> None:
    """The ABI list has the expected three entries in the expected order."""
    names = {entry.get("name") for entry in FINDINGS_REGISTRY_ABI}
    assert names == {"recordFinding", "verifyFinding", "FindingRecorded"}


def test_msg_id_padding_is_right_zero() -> None:
    """msg_id_to_bytes32 must right-zero-pad (not left)."""
    result = msg_id_to_bytes32("A")
    assert result == b"A" + b"\x00" * 31


def test_payload_hash_bytes_round_trip() -> None:
    """payload_hash_hex_to_bytes32 exact length + decode check."""
    out = payload_hash_hex_to_bytes32("a" * 64)
    assert out == b"\xaa" * 32
