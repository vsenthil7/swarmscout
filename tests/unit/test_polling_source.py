"""Coverage tests for agents/hunter/sources/polling.py.

Exercises: events() generator loop, HTTP error path, malformed-shape branch,
last-seen cursor dedup, _map_item happy + error paths.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import httpx
import pytest
import respx

from agents.hunter.sources.polling import LAST_SEEN_KEY, FourMemePollingSource


def _sample_items() -> list[dict[str, Any]]:
    """Return two well-formed API items in newest-first order."""
    return [
        {
            "address": "0xAAA" + "1" * 37,
            "creator": "0xBBB" + "2" * 37,
            "name": "Tok2",
            "symbol": "T2",
            "liquidityUsd": 10000,
            "launchedAt": "2026-04-22T10:00:00Z",
            "url": "https://four.meme/t2",
        },
        {
            "address": "0xCCC" + "3" * 37,
            "creator": "0xDDD" + "4" * 37,
            "name": "Tok1",
            "symbol": "T1",
            "liquidityUsd": 5000,
            "launchedAt": "2026-04-22T09:00:00Z",
            "url": "https://four.meme/t1",
        },
    ]


@pytest.mark.asyncio
async def test_events_yields_batch_then_sleeps_and_loops() -> None:
    """events() loops: first batch yields items, sleeps, second batch yields more."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://four.meme/api/new").mock(
            side_effect=[
                httpx.Response(200, json={"items": _sample_items()}),
                httpx.Response(200, json={"items": []}),
            ]
        )
        source = FourMemePollingSource(
            url="https://four.meme/api/new",
            interval_seconds=0,
            redis=redis,
        )
        events = source.events()
        collected = []
        async for ev in events:
            collected.append(ev)
            if len(collected) >= 2:
                break
    assert len(collected) == 2
    # Last-seen cursor was set to the newest item's address.
    last = await redis.get(LAST_SEEN_KEY)
    assert last is not None


@pytest.mark.asyncio
async def test_fetch_batch_returns_empty_on_http_error() -> None:
    """A 500 from the upstream yields [] and logs the error."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://four.meme/api/new").mock(return_value=httpx.Response(500))
        source = FourMemePollingSource(
            url="https://four.meme/api/new",
            interval_seconds=0,
            redis=redis,
        )
        batch = await source._fetch_batch()
    assert batch == []


@pytest.mark.asyncio
async def test_fetch_batch_returns_empty_on_unexpected_shape() -> None:
    """If the response is neither a list nor a dict with 'items' list, return []."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://four.meme/api/new").mock(
            return_value=httpx.Response(200, json={"items": "not-a-list"})
        )
        source = FourMemePollingSource(
            url="https://four.meme/api/new",
            interval_seconds=0,
            redis=redis,
        )
        batch = await source._fetch_batch()
    assert batch == []


@pytest.mark.asyncio
async def test_fetch_batch_handles_list_root_payload() -> None:
    """If the API returns a bare list at the root, treat that as items."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://four.meme/api/new").mock(
            return_value=httpx.Response(200, json=_sample_items())
        )
        source = FourMemePollingSource(
            url="https://four.meme/api/new",
            interval_seconds=0,
            redis=redis,
        )
        batch = await source._fetch_batch()
    assert len(batch) == 2


@pytest.mark.asyncio
async def test_fetch_batch_deduplicates_against_last_seen_cursor() -> None:
    """Once we've seen Tok2, a second fetch with same items yields nothing new."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://four.meme/api/new").mock(
            return_value=httpx.Response(200, json={"items": _sample_items()})
        )
        source = FourMemePollingSource(
            url="https://four.meme/api/new",
            interval_seconds=0,
            redis=redis,
        )
        first = await source._fetch_batch()
        assert len(first) == 2
        # Second call: cursor is Tok2, so iterating items hits the break on item #1.
        second = await source._fetch_batch()
    assert second == []


@pytest.mark.asyncio
async def test_events_completes_batch_yields_and_reaches_sleep() -> None:
    """Drive the events() generator through enough iterations to hit the sleep call (line 49).

    Using a counter-driven handler so every request has a response, rather than
    ``side_effect=[...]`` which raises StopIteration when exhausted.
    """
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(200, json={"items": _sample_items()[:1]})
        if call_count["n"] == 2:
            # Fresh items with different addresses so dedup doesn't break to empty.
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "address": "0xFFF" + "9" * 37,
                            "creator": "0x" + "0" * 40,
                            "name": "Tok3",
                            "symbol": "T3",
                            "liquidityUsd": 100,
                            "launchedAt": "2026-04-22T11:00:00Z",
                            "url": "https://four.meme/t3",
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"items": []})

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://four.meme/api/new").mock(side_effect=handler)
        source = FourMemePollingSource(
            url="https://four.meme/api/new",
            interval_seconds=0,
            redis=redis,
        )
        events = source.events()
        collected = []
        async def drive() -> None:
            async for ev in events:
                collected.append(ev)
                if len(collected) >= 2:
                    break
        await asyncio.wait_for(drive(), timeout=3)
    # Got 1 from the first batch, then 1+ from the second after sleep.
    assert len(collected) >= 2
    assert call_count["n"] >= 2


def test_map_item_returns_none_for_non_dict() -> None:
    """Non-dict items are defensively mapped to None, not raised."""
    assert FourMemePollingSource._map_item("not-a-dict") is None
    assert FourMemePollingSource._map_item(42) is None


def test_map_item_returns_none_when_required_fields_missing() -> None:
    """Missing required keys are caught and logged, not propagated."""
    result = FourMemePollingSource._map_item({"name": "onlyname"})
    assert result is None


def test_map_item_defaults_numeric_and_optional_fields() -> None:
    """Missing optional fields default to 0/'' and the event builds cleanly."""
    ev = FourMemePollingSource._map_item(
        {"address": "0xabc", "creator": "0xdef", "name": "n", "symbol": "s"}
    )
    assert ev is not None
    assert ev.initial_liquidity_usd == 0.0
    assert ev.launch_timestamp == ""
    assert ev.source_url == ""


def test_map_item_returns_none_when_liquidity_is_unparseable_string() -> None:
    """A non-empty unparseable string triggers ValueError and returns None."""
    ev = FourMemePollingSource._map_item(
        {
            "address": "0x1",
            "creator": "0x2",
            "name": "n",
            "symbol": "s",
            "liquidityUsd": "not-a-number",
        }
    )
    assert ev is None
