"""Agent-specific unit tests — hunter, chain, narrator, social helpers."""

from __future__ import annotations

import pytest

from agents.chain.main import _velocity_tx_per_min, _whale_count
from agents.hunter.sources.polling import FourMemePollingSource
from agents.hunter.sources.rpc_log import FourMemeRPCLogSource
from agents.narrator.main import _derive_conviction, _extract_token_name, _parse_json
from agents.social.main import _strip_fences
from agents.common.schemas.payloads import ConvictionTier


# --------------------------------------------------------------------------- #
# Hunter polling source TC-U50-53                                             #
# --------------------------------------------------------------------------- #


class _FakeResp:
    """Stand-in for ``httpx.Response`` used by the polling-source tests."""
    def __init__(self, body: object, status: int = 200) -> None:
        """Hold the body and status; no side effects."""
        self._body = body
        self.status_code = status

    def raise_for_status(self) -> None:
        """Raise an httpx.HTTPStatusError if the baked status is >=400."""
        if self.status_code >= 400:
            from httpx import HTTPStatusError, Request, Response

            raise HTTPStatusError(
                "boom",
                request=Request("GET", "x"),
                response=Response(self.status_code),
            )

    def json(self) -> object:
        """Return the baked body verbatim."""
        return self._body


class _FakeHTTP:
    """Stand-in for an ``httpx.AsyncClient`` that always returns a pre-baked body."""
    def __init__(self, body: object, status: int = 200) -> None:
        """Hold the body and status; no side effects."""
        self._body = body
        self._status = status

    async def get(self, url: str, **_: object) -> _FakeResp:
        """Ignore URL and return the fake response."""
        return _FakeResp(self._body, self._status)


def test_polling_map_item_happy() -> None:
    """A well-formed item maps cleanly to a RawTokenEvent."""
    item = {
        "address": "0xabc",
        "creator": "0xcre",
        "name": "Foo",
        "symbol": "FOO",
        "liquidityUsd": 1000,
        "launchedAt": "2026-04-22T00:00:00Z",
        "url": "https://four.meme/foo",
    }
    mapped = FourMemePollingSource._map_item(item)
    assert mapped is not None
    assert mapped.token_address == "0xabc"


def test_polling_map_item_rejects_non_dict() -> None:
    """Non-dict inputs return None rather than raising."""
    assert FourMemePollingSource._map_item("not-a-dict") is None


def test_polling_map_item_tolerates_missing_fields() -> None:
    """Missing required keys return None rather than raising."""
    assert FourMemePollingSource._map_item({}) is None


@pytest.mark.asyncio
async def test_polling_fetch_batch_dedupes(fake_redis) -> None:  # type: ignore[no-untyped-def]
    """Second poll with unchanged cursor yields an empty batch (dedup works)."""
    items = [
        {
            "address": "0x1",
            "creator": "0x0",
            "name": "n",
            "symbol": "s",
            "liquidityUsd": 0,
            "launchedAt": "",
            "url": "",
        },
        {
            "address": "0x2",
            "creator": "0x0",
            "name": "n",
            "symbol": "s",
            "liquidityUsd": 0,
            "launchedAt": "",
            "url": "",
        },
    ]
    src = FourMemePollingSource(
        url="http://x", interval_seconds=1, redis=fake_redis, http=_FakeHTTP({"items": items})
    )
    batch1 = await src._fetch_batch()
    assert len(batch1) == 2
    # Re-poll: should return zero because cursor has moved.
    batch2 = await src._fetch_batch()
    assert batch2 == []


def test_rpc_log_decode_malformed_returns_none() -> None:
    """Short topic list decodes to None, never to a garbage event."""
    assert FourMemeRPCLogSource._decode({"topics": []}) is None


# --------------------------------------------------------------------------- #
# Chain helpers TC-U70-72                                                     #
# --------------------------------------------------------------------------- #


def test_velocity_empty_returns_zero() -> None:
    """Empty transfer list -> 0 tx/min (no division by zero)."""
    assert _velocity_tx_per_min([]) == 0.0


def test_velocity_basic() -> None:
    """60 s span with 2 transfers -> 2 tx/min."""
    transfers = [
        {"timeStamp": "1000"},
        {"timeStamp": "940"},  # 60s span, 2 tx -> 2/min
    ]
    assert _velocity_tx_per_min(transfers) == 2.0


def test_velocity_bad_timestamps_returns_zero() -> None:
    """Non-numeric timestamps -> 0 tx/min rather than raising."""
    assert _velocity_tx_per_min([{"timeStamp": "x"}, {"timeStamp": "y"}]) == 0.0


def test_whale_count_detects_high_transfers() -> None:
    """A transfer above $1k threshold counts as a whale entry."""
    transfers = [
        {"value": str(10**22), "tokenDecimal": "18"},
        {"value": "1", "tokenDecimal": "18"},
    ]
    assert _whale_count(transfers, threshold_usd=1000) >= 1


def test_whale_count_tolerates_bad_data() -> None:
    """Malformed value / decimal fields do not raise; return 0."""
    assert _whale_count([{"value": "x", "tokenDecimal": "y"}], threshold_usd=100) == 0


# --------------------------------------------------------------------------- #
# Narrator helpers TC-U90-92                                                  #
# --------------------------------------------------------------------------- #


def test_derive_conviction_boundaries() -> None:
    """All four tiers map from representative scores (10/50/70/90)."""
    assert _derive_conviction(90) == ConvictionTier.HIGH
    assert _derive_conviction(70) == ConvictionTier.MODERATE
    assert _derive_conviction(50) == ConvictionTier.SPECULATIVE
    assert _derive_conviction(10) == ConvictionTier.DEGEN


def test_extract_token_name_found() -> None:
    """Token name is pulled from the TokenCandidate row in lineage."""
    lineage = [{"agent": "hunter", "payload": {"token_name": "Foo"}}]
    assert _extract_token_name(lineage) == "Foo"


def test_extract_token_name_missing() -> None:
    """When no lineage row has a token_name, return None."""
    assert _extract_token_name([{"agent": "risk", "payload": {}}]) is None


def test_parse_json_fenced() -> None:
    """```json fenced content parses after stripping."""
    assert _parse_json('```json\n{"a":1}\n```') == {"a": 1}


def test_parse_json_plain() -> None:
    """Unfenced JSON parses directly."""
    assert _parse_json('{"x":2}') == {"x": 2}


def test_parse_json_invalid_returns_empty() -> None:
    """Malformed JSON returns {} rather than raising."""
    assert _parse_json("not-json") == {}


def test_parse_json_non_dict_returns_empty() -> None:
    """A JSON array returns {} — the parser is dict-only by contract."""
    assert _parse_json("[1,2,3]") == {}


# --------------------------------------------------------------------------- #
# Social helper TC-U60-63                                                     #
# --------------------------------------------------------------------------- #


def test_strip_fences_removes_backticks() -> None:
    """```json wrapped content is unwrapped to its inner JSON."""
    assert _strip_fences("```json\n{\"a\":1}\n```") == '{"a":1}'


def test_strip_fences_plain_passthrough() -> None:
    """Text without fences is returned unchanged."""
    assert _strip_fences('{"b":2}') == '{"b":2}'
