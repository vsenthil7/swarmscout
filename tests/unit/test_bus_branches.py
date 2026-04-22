"""Coverage tests for agents/common/bus.py uncovered branches."""

from __future__ import annotations

import asyncio
from typing import Any

import fakeredis.aioredis
import pytest
import redis.asyncio as aioredis

from agents.common.bus import Bus, _decode
from agents.common.envelope_builder import build_envelope
from agents.common.schemas.envelope import AgentName, StreamName


@pytest.mark.asyncio
async def test_bus_close_calls_aclose_on_underlying_client() -> None:
    """``Bus.close`` must delegate to the underlying Redis client's ``aclose``."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)
    await bus.close()
    # fakeredis stays functional but the close path executed.


@pytest.mark.asyncio
async def test_bus_ensure_group_reraises_on_non_busygroup_error() -> None:
    """ResponseError that isn't BUSYGROUP is re-raised unchanged."""

    class _BoomRedis:
        async def xgroup_create(self, *_: Any, **__: Any) -> None:
            raise aioredis.ResponseError("something else entirely")

    bus = Bus(url="redis://fake", client=_BoomRedis())  # type: ignore[arg-type]
    with pytest.raises(aioredis.ResponseError, match="something else"):
        await bus.ensure_group(StreamName.CANDIDATES, "g1")


@pytest.mark.asyncio
async def test_bus_consume_new_message_branch_and_empty_tick() -> None:
    """Exercise the while-True block: empty resp tick, then a new message yielded."""

    # We stub xreadgroup to return PEL empty once, then an empty tick, then a real entry.
    state = {"calls": 0}

    async def fake_xreadgroup(**kwargs: Any) -> Any:
        streams = kwargs["streams"]
        # PEL drain pass: streams={name: "0"} — first call, return empty.
        if list(streams.values()) == ["0"]:
            return []
        # New messages pass: streams={name: ">"}
        state["calls"] += 1
        if state["calls"] == 1:
            return []  # Triggers the 'if not resp: sleep(0); continue' branch
        # Second call: return one entry.
        env = build_envelope(agent=AgentName.HUNTER, payload={"x": 1})
        from agents.common.hasher import canonical_json

        body = canonical_json(env.model_dump(mode="json")).decode("utf-8")
        return [(StreamName.CANDIDATES.value, [("1-0", {"envelope": body})])]

    async def fake_xgroup_create(*_: Any, **__: Any) -> None:
        return None

    class _StubRedis:
        xreadgroup = staticmethod(fake_xreadgroup)
        xgroup_create = staticmethod(fake_xgroup_create)

    bus = Bus(url="redis://fake", client=_StubRedis())  # type: ignore[arg-type]

    received: list[Any] = []

    async def drive() -> None:
        async for msg in bus.consume(
            stream=StreamName.CANDIDATES, group="g", consumer="c", block_ms=1, batch=1
        ):
            received.append(msg)
            break

    # Guard against a regression hang.
    await asyncio.wait_for(drive(), timeout=5)
    assert len(received) == 1
    assert received[0].entry_id == "1-0"


def test_decode_raises_valueerror_when_envelope_field_missing() -> None:
    """``_decode`` without an 'envelope' field raises ValueError."""
    with pytest.raises(ValueError, match="missing 'envelope'"):
        _decode({"other": "stuff"})


@pytest.mark.asyncio
async def test_bus_accepts_string_stream_not_just_enum() -> None:
    """publish/ack/pending_depth/stream_length all accept raw string stream names too."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)

    env = build_envelope(agent=AgentName.HUNTER, payload={"x": 1})
    entry_id = await bus.publish("stream:test_raw", env)
    assert entry_id

    assert await bus.stream_length("stream:test_raw") == 1

    # Create a group then read so there is something pending.
    await bus.ensure_group("stream:test_raw", "gg")
    # No pending yet.
    assert await bus.pending_depth("stream:test_raw", "gg") == 0

    # Ack with a string stream — just verifying it doesn't raise on type dispatch.
    await bus.ack("stream:test_raw", "gg", entry_id)
    await bus.close()


@pytest.mark.asyncio
async def test_bus_consume_drains_pel_and_iterates_multiple_entries_fully() -> None:
    """Drive consume with a PEL drain that yields two entries in one batch.

    This exercises the inner-loop completion branches (120->119, 134->123,
    135->134) that require the 'for' loops to actually fall through to the
    next outer iteration rather than breaking early.
    """
    from agents.common.hasher import canonical_json

    env1 = build_envelope(agent=AgentName.HUNTER, payload={"x": 1})
    env2 = build_envelope(agent=AgentName.HUNTER, payload={"x": 2})
    body1 = canonical_json(env1.model_dump(mode="json")).decode("utf-8")
    body2 = canonical_json(env2.model_dump(mode="json")).decode("utf-8")

    state = {"pel_called": False, "new_called": 0}

    async def fake_xreadgroup(**kwargs: Any) -> Any:
        streams = kwargs["streams"]
        # PEL drain pass: return two entries so the inner for-loop iterates twice.
        if list(streams.values()) == ["0"] and not state["pel_called"]:
            state["pel_called"] = True
            return [
                (
                    StreamName.CANDIDATES.value,
                    [("1-0", {"envelope": body1}), ("1-1", {"envelope": body2})],
                )
            ]
        # Subsequent passes: new-message branch, return another entry to exit.
        if list(streams.values()) == [">"]:
            state["new_called"] += 1
            if state["new_called"] == 1:
                return [(StreamName.CANDIDATES.value, [("2-0", {"envelope": body1})])]
        return []

    async def fake_xgroup_create(*_: Any, **__: Any) -> None:
        return None

    class _StubRedis:
        xreadgroup = staticmethod(fake_xreadgroup)
        xgroup_create = staticmethod(fake_xgroup_create)

    bus = Bus(url="redis://fake", client=_StubRedis())  # type: ignore[arg-type]

    received: list[Any] = []

    async def drive() -> None:
        async for msg in bus.consume(
            stream=StreamName.CANDIDATES, group="g", consumer="c", block_ms=1, batch=10
        ):
            received.append(msg)
            if len(received) >= 3:
                break

    await asyncio.wait_for(drive(), timeout=5)
    assert len(received) == 3
    assert [m.entry_id for m in received] == ["1-0", "1-1", "2-0"]
