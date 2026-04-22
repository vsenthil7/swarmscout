"""Coverage tests for agents/chain/bscscan.py.

Uses respx to mock the HTTP layer so the rate-limit sleep, query building,
pagination, error handling, and dataclass unpacking are all exercised without
hitting the network.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from agents.chain.bscscan import (
    BscScanClient,
    ContractMeta,
    HolderSnapshot,
)


TOKEN = "0x" + "a" * 40
BASE = "https://api-testnet.bscscan.com/api"


@pytest.fixture()
def client() -> BscScanClient:
    """Construct a client with a test base URL and a high rate limit."""
    http = httpx.AsyncClient(timeout=5.0)
    return BscScanClient(base_url=BASE, api_key="TESTKEY", rate_per_s=100, http=http)


# --------------------------------------------------------------------------- #
# holders                                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@respx.mock
async def test_holders_parses_holder_list_and_computes_top10_concentration(
    client: BscScanClient,
) -> None:
    """Valid holder list: total count + top-10 concentration percent."""
    # 15 holders; top-10 sum is 100+90+...+10 = 550, total 550+80+70+60+50 = 810
    result = [{"TokenHolderQuantity": str(100 - i * 5)} for i in range(15)]
    respx.get(BASE).mock(
        return_value=httpx.Response(200, json={"status": "1", "result": result})
    )
    snap = await client.holders(TOKEN)
    assert isinstance(snap, HolderSnapshot)
    assert snap.total == 15
    assert snap.top10_concentration_pct > 0
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_holders_returns_zero_snapshot_on_empty_result(client: BscScanClient) -> None:
    """Empty result list returns HolderSnapshot(0, 0.0) without crashing."""
    respx.get(BASE).mock(return_value=httpx.Response(200, json={"status": "0", "result": []}))
    snap = await client.holders(TOKEN)
    assert snap.total == 0
    assert snap.top10_concentration_pct == 0.0
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_holders_returns_zero_snapshot_on_non_list_result(client: BscScanClient) -> None:
    """BscScan sometimes returns `result: "Max rate limit reached"` as a string."""
    respx.get(BASE).mock(
        return_value=httpx.Response(200, json={"status": "0", "result": "Max rate limit reached"})
    )
    snap = await client.holders(TOKEN)
    assert snap.total == 0
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_holders_handles_malformed_quantity_values(client: BscScanClient) -> None:
    """Non-numeric TokenHolderQuantity falls through the except branch to zero snapshot."""
    result = [
        {"TokenHolderQuantity": "100"},
        {"TokenHolderQuantity": "not-a-number"},
    ]
    respx.get(BASE).mock(
        return_value=httpx.Response(200, json={"status": "1", "result": result})
    )
    snap = await client.holders(TOKEN)
    # The except branch returns (0, 0.0).
    assert snap.total == 0
    assert snap.top10_concentration_pct == 0.0
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_holders_zero_total_supply_leaves_concentration_zero(
    client: BscScanClient,
) -> None:
    """When summed supply is 0, concentration falls to 0 without DivByZero."""
    result = [{"TokenHolderQuantity": "0"} for _ in range(5)]
    respx.get(BASE).mock(
        return_value=httpx.Response(200, json={"status": "1", "result": result})
    )
    snap = await client.holders(TOKEN)
    assert snap.top10_concentration_pct == 0.0
    await client.aclose()


# --------------------------------------------------------------------------- #
# contract_meta                                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@respx.mock
async def test_contract_meta_verified_with_creator_and_tx_history(
    client: BscScanClient,
) -> None:
    """verified=True when SourceCode present; creator_tx_count derived from tx list length."""
    # Two GET calls: first for getsourcecode, second for txlist.
    route = respx.get(BASE).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "SourceCode": "contract Foo { }",
                            "ContractCreator": "0xABCD",
                        }
                    ]
                },
            ),
            httpx.Response(
                200,
                json={"result": [{"hash": f"0x{i:064x}"} for i in range(73)]},
            ),
        ]
    )
    meta = await client.contract_meta(TOKEN)
    assert isinstance(meta, ContractMeta)
    assert meta.verified is True
    assert meta.creator_address == "0xabcd"  # lowercased
    assert meta.creator_tx_count == 73
    assert route.call_count == 2
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_contract_meta_unverified_when_sourcecode_empty(client: BscScanClient) -> None:
    """Empty SourceCode means verified=False."""
    respx.get(BASE).mock(
        side_effect=[
            httpx.Response(
                200, json={"result": [{"SourceCode": "", "ContractCreator": "0xdead"}]}
            ),
            httpx.Response(200, json={"result": []}),
        ]
    )
    meta = await client.contract_meta(TOKEN)
    assert meta.verified is False
    assert meta.creator_tx_count == 0
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_contract_meta_handles_non_list_verify_result(client: BscScanClient) -> None:
    """Verify-source endpoint returning a string uses the zero-address fallback."""
    respx.get(BASE).mock(
        side_effect=[
            httpx.Response(200, json={"result": "rate limited"}),
            httpx.Response(200, json={"result": []}),
        ]
    )
    meta = await client.contract_meta(TOKEN)
    assert meta.verified is False
    assert meta.creator_address == "0x" + "0" * 40
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_contract_meta_handles_non_list_tx_result(client: BscScanClient) -> None:
    """Tx-list endpoint returning a string becomes creator_tx_count=0."""
    respx.get(BASE).mock(
        side_effect=[
            httpx.Response(
                200,
                json={"result": [{"SourceCode": "contract Foo { }", "ContractCreator": "0x1234"}]},
            ),
            httpx.Response(200, json={"result": "rate limited"}),
        ]
    )
    meta = await client.contract_meta(TOKEN)
    assert meta.verified is True
    assert meta.creator_tx_count == 0
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_contract_meta_first_element_not_a_dict(client: BscScanClient) -> None:
    """If result[0] is not a dict, verified stays False."""
    respx.get(BASE).mock(
        side_effect=[
            httpx.Response(200, json={"result": ["weird-string"]}),
            httpx.Response(200, json={"result": []}),
        ]
    )
    meta = await client.contract_meta(TOKEN)
    assert meta.verified is False
    await client.aclose()


# --------------------------------------------------------------------------- #
# recent_transfers                                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@respx.mock
async def test_recent_transfers_returns_dict_items(client: BscScanClient) -> None:
    """Well-formed tokentx returns list of dict rows."""
    rows = [{"hash": "0xaaa", "value": "1000", "tokenDecimal": "18", "timeStamp": "1713000000"}]
    respx.get(BASE).mock(return_value=httpx.Response(200, json={"result": rows}))
    out = await client.recent_transfers(TOKEN, limit=100)
    assert out == rows
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_recent_transfers_filters_non_dict_entries(client: BscScanClient) -> None:
    """Non-dict entries in the result list are filtered out."""
    respx.get(BASE).mock(
        return_value=httpx.Response(200, json={"result": [{"hash": "ok"}, "string-garbage", 42]})
    )
    out = await client.recent_transfers(TOKEN, limit=50)
    assert len(out) == 1
    assert out[0]["hash"] == "ok"
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_recent_transfers_empty_result(client: BscScanClient) -> None:
    """Empty result returns empty list."""
    respx.get(BASE).mock(return_value=httpx.Response(200, json={"result": []}))
    out = await client.recent_transfers(TOKEN)
    assert out == []
    await client.aclose()


# --------------------------------------------------------------------------- #
# _get low-level plumbing                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@respx.mock
async def test_get_raises_on_http_error(client: BscScanClient) -> None:
    """HTTP 500 is propagated (raise_for_status)."""
    respx.get(BASE).mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await client.holders(TOKEN)
    await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_get_injects_api_key_in_query(client: BscScanClient) -> None:
    """Every request carries apikey=<configured key>."""
    route = respx.get(BASE).mock(return_value=httpx.Response(200, json={"result": []}))
    await client.recent_transfers(TOKEN)
    req = route.calls.last.request
    assert "apikey=TESTKEY" in str(req.url)
    await client.aclose()


def test_client_normalises_rate_below_one() -> None:
    """Rate limits below 1 are coerced upward to 1/s."""
    c = BscScanClient(base_url=BASE, api_key="k", rate_per_s=0)
    # Internal _rate should be clamped to 1.
    assert c._rate == 1
