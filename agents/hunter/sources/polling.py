"""REST polling source for Four.meme new-token feed.

Polls a JSON endpoint every ``interval`` seconds, tracks the last-seen token
address in Redis, and yields every new event since then. Reused as the
default until on-chain logs prove more reliable.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import redis.asyncio as aioredis

from agents.common.logging_config import get_logger
from agents.hunter.sources.base import RawTokenEvent

log = get_logger("hunter.sources.polling")


LAST_SEEN_KEY = "hunter:last_seen_token"


class FourMemePollingSource:
    """Poll the Four.meme REST feed and emit new-token events."""

    def __init__(
        self,
        *,
        url: str,
        interval_seconds: int,
        redis: aioredis.Redis,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        """Build a polling source with URL, interval, Redis cursor store, and HTTP client."""
        self._url = url
        self._interval = interval_seconds
        self._redis = redis
        self._http = http or httpx.AsyncClient(timeout=20.0)

    async def events(self) -> AsyncIterator[RawTokenEvent]:
        """Yield events indefinitely; stops when caller stops iterating."""
        while True:
            batch = await self._fetch_batch()
            for raw in batch:
                yield raw
            await asyncio.sleep(self._interval)

    async def _fetch_batch(self) -> list[RawTokenEvent]:
        """Fetch one page and dedupe against the last-seen cursor."""
        try:
            resp = await self._http.get(self._url)
            resp.raise_for_status()
        except httpx.HTTPError as err:
            log.warning("polling_http_error", err=str(err))
            return []
        data = resp.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            log.warning("polling_unexpected_shape", sample=str(items)[:200])
            return []
        last_seen = await self._redis.get(LAST_SEEN_KEY)
        out: list[RawTokenEvent] = []
        newest: str | None = None
        for item in items:
            event = self._map_item(item)
            if event is None:
                continue
            if newest is None:
                newest = event.token_address
            if last_seen is not None and event.token_address == last_seen:
                break
            out.append(event)
        if newest is not None:
            await self._redis.set(LAST_SEEN_KEY, newest)
        # Reverse so oldest-first downstream.
        return list(reversed(out))

    @staticmethod
    def _map_item(item: Any) -> RawTokenEvent | None:
        """Defensively map a raw JSON item into a ``RawTokenEvent``."""
        if not isinstance(item, dict):
            return None
        try:
            return RawTokenEvent(
                token_address=str(item["address"]).lower(),
                creator_address=str(item["creator"]).lower(),
                token_name=str(item["name"]),
                token_symbol=str(item["symbol"]),
                initial_liquidity_usd=float(item.get("liquidityUsd", 0) or 0),
                launch_timestamp=str(item.get("launchedAt", "")),
                source_url=str(item.get("url", "")),
            )
        except (KeyError, ValueError, TypeError) as err:
            log.warning("polling_map_error", err=str(err), item=str(item)[:200])
            return None
