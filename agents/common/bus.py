"""Redis Streams bus abstraction.

Every inter-agent message flows through this module. It:

* Publishes envelopes with ``MAXLEN ~ 100000`` approximate trimming (FR-102).
* Reads from consumer groups with at-least-once semantics (FR-104).
* Handles redelivery via the Pending Entries List (FR-105).
* Exposes ``pending_depth`` for backpressure monitoring (FR-106).

Wire format: each stream entry has a single ``envelope`` field whose value
is the canonical JSON string of the envelope. Keeping one field rather than
splatting envelope keys into the stream simplifies XADD / XREADGROUP and
makes schema changes free.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis

from agents.common.hasher import canonical_json
from agents.common.schemas.envelope import Envelope, StreamName

DEFAULT_MAXLEN = 100_000
DEFAULT_BLOCK_MS = 5_000
DEFAULT_BATCH = 16
DEFAULT_VISIBILITY_SECONDS = 60


@dataclass(frozen=True)
class BusMessage:
    """A single entry read from a stream, with the raw Redis id preserved."""

    stream: str
    entry_id: str
    envelope: Envelope


class Bus:
    """Async wrapper around Redis Streams."""

    def __init__(self, url: str, *, client: aioredis.Redis | None = None) -> None:
        """Wrap or build a Redis async client.

        Args:
            url: Redis URL (used when ``client`` is not provided).
            client: Pre-built redis.asyncio.Redis — used in tests with
                fakeredis so no real connection pool is opened.
        """
        self._client: aioredis.Redis = client or aioredis.from_url(url, decode_responses=True)

    @property
    def client(self) -> aioredis.Redis:
        """Expose underlying Redis client for advanced callers (rate limits, pub/sub)."""
        return self._client

    async def close(self) -> None:
        """Close the underlying connection pool."""
        await self._client.aclose()

    async def publish(
        self,
        stream: StreamName | str,
        envelope: Envelope,
        *,
        maxlen: int = DEFAULT_MAXLEN,
    ) -> str:
        """Publish ``envelope`` onto ``stream``, return the assigned stream id."""
        name = stream.value if isinstance(stream, StreamName) else stream
        body = canonical_json(envelope.model_dump(mode="json")).decode("utf-8")
        entry_id: str = await self._client.xadd(
            name,
            {"envelope": body},
            maxlen=maxlen,
            approximate=True,
        )
        return entry_id

    async def ensure_group(self, stream: StreamName | str, group: str) -> None:
        """Create a consumer group on ``stream`` if it does not exist."""
        name = stream.value if isinstance(stream, StreamName) else stream
        try:
            await self._client.xgroup_create(name, group, id="0", mkstream=True)
        except aioredis.ResponseError as err:  # pragma: no branch
            if "BUSYGROUP" not in str(err):
                raise

    async def consume(
        self,
        *,
        stream: StreamName | str,
        group: str,
        consumer: str,
        block_ms: int = DEFAULT_BLOCK_MS,
        batch: int = DEFAULT_BATCH,
    ) -> AsyncIterator[BusMessage]:
        """Asynchronously iterate messages delivered to ``consumer`` within ``group``.

        On every iteration, first the Pending Entries List is drained (to
        guarantee redelivery of any messages the previous process crashed on
        mid-handle), then new messages are read. The caller must call
        :meth:`ack` after successful processing.
        """
        name = stream.value if isinstance(stream, StreamName) else stream
        await self.ensure_group(name, group)

        # Drain PEL first so crashed work is retried before we consume new entries.
        pending = await self._client.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={name: "0"},
            count=batch,
        )
        for _stream, entries in pending:
            for entry_id, fields in entries:
                yield BusMessage(stream=name, entry_id=entry_id, envelope=_decode(fields))

        while True:
            resp = await self._client.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={name: ">"},
                count=batch,
                block=block_ms,
            )
            if not resp:
                await asyncio.sleep(0)
                continue
            for _stream, entries in resp:
                for entry_id, fields in entries:
                    yield BusMessage(stream=name, entry_id=entry_id, envelope=_decode(fields))

    async def ack(self, stream: StreamName | str, group: str, entry_id: str) -> None:
        """Acknowledge an entry, removing it from the consumer group's PEL."""
        name = stream.value if isinstance(stream, StreamName) else stream
        await self._client.xack(name, group, entry_id)

    async def pending_depth(self, stream: StreamName | str, group: str) -> int:
        """Return the number of pending (unacknowledged) messages for ``group``."""
        name = stream.value if isinstance(stream, StreamName) else stream
        summary: dict[str, Any] = await self._client.xpending(name, group)
        return int(summary.get("pending", 0))

    async def stream_length(self, stream: StreamName | str) -> int:
        """Return ``XLEN`` for ``stream``."""
        name = stream.value if isinstance(stream, StreamName) else stream
        return int(await self._client.xlen(name))


def _decode(fields: dict[str, str]) -> Envelope:
    """Decode the single-field envelope payload out of a Redis stream entry."""
    raw = fields.get("envelope")
    if raw is None:
        raise ValueError("stream entry missing 'envelope' field")
    return Envelope.model_validate(json.loads(raw))
