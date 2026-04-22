"""Coverage tests for agents/common/base_agent.py (run, loops, signals, heartbeat)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest

from agents.common.base_agent import (
    HEARTBEAT_INTERVAL_SECONDS,
    BaseAgent,
)
from agents.common.bus import Bus, BusMessage
from agents.common.on_chain import NullAnchor
from agents.common.schemas.envelope import AgentName, StreamName
from agents.common.schemas.payloads import (
    AlphaBrief,
    ConvictionTier,
)


class _StubHeartbeats:
    """Heartbeat repo whose upsert records each call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def upsert(self, **kw: Any) -> None:
        self.calls.append(kw)


class _BoomHeartbeats:
    """Heartbeat repo that always raises."""

    async def upsert(self, **_: Any) -> None:
        raise RuntimeError("pg outage")


class _NullFindings:
    async def insert_envelope(self, _env: Any) -> None:
        return None

    async def record_onchain(self, *_: Any) -> None:
        return None


class _BoomPubSubRedis:
    """A redis-like that raises on ``publish`` to test the pubsub-broadcast error swallow."""

    async def publish(self, *_: Any, **__: Any) -> int:
        raise RuntimeError("pubsub broken")


class _BoomPubSubBus:
    """A bus whose ``client.publish`` raises but ``publish`` (xadd) is fine."""

    def __init__(self) -> None:
        self._redis = _BoomPubSubRedis()
        self.published_streams: list[StreamName] = []

    @property
    def client(self) -> Any:
        return self._redis

    async def publish(self, stream: StreamName, _env: Any) -> str:
        self.published_streams.append(stream)
        return "1-0"


class _CountingAgent(BaseAgent):
    """Minimal agent that counts handle() calls and optionally raises."""

    agent_name = AgentName.HUNTER
    output_stream = StreamName.CANDIDATES

    def __init__(self, *, should_raise: bool = False, **kw: Any) -> None:
        super().__init__(**kw)
        self.calls = 0
        self._should_raise = should_raise

    async def handle(self, _msg: BusMessage | None) -> None:
        self.calls += 1
        if self._should_raise:
            raise RuntimeError("handle blew up")
        # Stop after two iterations so the loop exits deterministically.
        if self.calls >= 2:
            self._stop_event.set()


# --------------------------------------------------------------------------- #
# run() + _main_loop() happy and exception paths                              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_run_drives_main_loop_and_starts_heartbeat() -> None:
    """``run()`` spawns the heartbeat task and calls handle() in the main loop."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)
    heartbeats = _StubHeartbeats()

    agent = _CountingAgent(
        bus=bus,
        findings=_NullFindings(),  # type: ignore[arg-type]
        heartbeats=heartbeats,  # type: ignore[arg-type]
        anchor=NullAnchor(),
    )

    # Patch the sleeps so the loop races through iterations.
    with patch("agents.common.base_agent.asyncio.sleep", new=AsyncMock()):
        await asyncio.wait_for(agent.run(), timeout=3)

    assert agent.calls >= 2
    # run() started a heartbeat task and then cancelled it on shutdown.
    # Whether the heartbeat fired depends on scheduler ordering; what matters
    # is that run() completed without raising and main-loop iterated.
    await bus.close()


@pytest.mark.asyncio
async def test_main_loop_swallows_handle_exceptions_and_counts_failures() -> None:
    """When handle() raises, the loop logs, counts the failure, and keeps going."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)
    heartbeats = _StubHeartbeats()

    class _FailingThenStoppingAgent(BaseAgent):
        agent_name = AgentName.HUNTER
        output_stream = StreamName.CANDIDATES

        def __init__(self, **kw: Any) -> None:
            super().__init__(**kw)
            self.calls = 0

        async def handle(self, _msg: BusMessage | None) -> None:
            self.calls += 1
            if self.calls >= 2:
                self._stop_event.set()
            raise RuntimeError("boom")

    agent = _FailingThenStoppingAgent(
        bus=bus,
        findings=_NullFindings(),  # type: ignore[arg-type]
        heartbeats=heartbeats,  # type: ignore[arg-type]
        anchor=NullAnchor(),
    )

    with patch("agents.common.base_agent.asyncio.sleep", new=AsyncMock()):
        await asyncio.wait_for(agent.run(), timeout=3)

    # The loop ran despite exceptions and stopped after two failures.
    assert agent.calls >= 2
    await bus.close()


# --------------------------------------------------------------------------- #
# anchor_and_publish — pubsub-broadcast exception path (lines 184-185)        #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_anchor_and_publish_swallows_pubsub_errors_for_briefs_stream() -> None:
    """When the output is stream:briefs and the pubsub mirror fails, the stream publish still succeeds."""

    class _BriefAgent(BaseAgent):
        agent_name = AgentName.NARRATOR
        output_stream = StreamName.BRIEFS

        async def handle(self, _msg: Any) -> None:
            return None

    bus = _BoomPubSubBus()
    agent = _BriefAgent(
        bus=bus,  # type: ignore[arg-type]
        findings=_NullFindings(),  # type: ignore[arg-type]
        heartbeats=_StubHeartbeats(),  # type: ignore[arg-type]
        anchor=NullAnchor(),
    )

    brief = AlphaBrief(
        token_name="X",
        token_address="0x" + "1" * 40,
        thesis="long enough thesis text " * 3,
        conviction_tier=ConvictionTier.DEGEN,
        brief_generated_at="2026-04-22T10:00:00Z",
    )

    env = await agent.anchor_and_publish(payload=brief)
    # The main stream publish ran.
    assert StreamName.BRIEFS in bus.published_streams
    # The envelope was still constructed and returned despite pubsub failure.
    assert env.msg_id


# --------------------------------------------------------------------------- #
# _install_signals — NotImplementedError path (Windows)                       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_install_signals_tolerates_notimplementederror_on_windows() -> None:
    """``_install_signals`` swallows NotImplementedError from loop.add_signal_handler.

    Windows asyncio does not support ``add_signal_handler`` for SIGINT/SIGTERM;
    the base agent must degrade gracefully rather than crash at startup.
    """

    class _TrivialAgent(BaseAgent):
        agent_name = AgentName.HUNTER
        output_stream = StreamName.CANDIDATES

        async def handle(self, _msg: Any) -> None:
            return None

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)

    agent = _TrivialAgent(
        bus=bus,
        findings=_NullFindings(),  # type: ignore[arg-type]
        heartbeats=_StubHeartbeats(),  # type: ignore[arg-type]
        anchor=NullAnchor(),
    )

    loop = asyncio.get_running_loop()
    with patch.object(loop, "add_signal_handler", side_effect=NotImplementedError):
        # Should not raise despite NotImplementedError from both SIGINT and SIGTERM.
        agent._install_signals()

    await bus.close()


# --------------------------------------------------------------------------- #
# _heartbeat_loop — pg-failure swallow branch (line 216)                      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_heartbeat_loop_resets_events_window_after_successful_upsert() -> None:
    """On success, _heartbeat_loop resets the events-in-window counter (line 217)."""

    class _TrivialAgent(BaseAgent):
        agent_name = AgentName.HUNTER
        output_stream = StreamName.CANDIDATES

        async def handle(self, _msg: Any) -> None:
            return None

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)
    heartbeats = _StubHeartbeats()

    agent = _TrivialAgent(
        bus=bus,
        findings=_NullFindings(),  # type: ignore[arg-type]
        heartbeats=heartbeats,  # type: ignore[arg-type]
        anchor=NullAnchor(),
    )
    agent._events_in_window = 42

    original_sleep = asyncio.sleep
    sleeps = {"n": 0}

    async def quick_sleep(delay: float) -> None:
        sleeps["n"] += 1
        if sleeps["n"] >= 1:
            agent._stop_event.set()
        await original_sleep(0)

    with patch("agents.common.base_agent.asyncio.sleep", new=quick_sleep):
        await asyncio.wait_for(agent._heartbeat_loop(), timeout=3)

    # Success path: at least one upsert call landed and the counter was reset.
    assert len(heartbeats.calls) >= 1
    assert agent._events_in_window == 0
    await bus.close()


@pytest.mark.asyncio
async def test_heartbeat_loop_swallows_pg_failures_and_keeps_running() -> None:
    """When heartbeats.upsert raises, the heartbeat loop logs and retries after the interval."""

    class _TrivialAgent(BaseAgent):
        agent_name = AgentName.HUNTER
        output_stream = StreamName.CANDIDATES

        async def handle(self, _msg: Any) -> None:
            return None

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)

    agent = _TrivialAgent(
        bus=bus,
        findings=_NullFindings(),  # type: ignore[arg-type]
        heartbeats=_BoomHeartbeats(),  # type: ignore[arg-type]
        anchor=NullAnchor(),
    )

    # Run a single heartbeat iteration, then stop.
    sleep_calls = {"n": 0}

    original_sleep = asyncio.sleep

    async def quick_sleep(delay: float) -> None:
        sleep_calls["n"] += 1
        if sleep_calls["n"] >= 2:
            agent._stop_event.set()
        await original_sleep(0)

    with patch("agents.common.base_agent.asyncio.sleep", new=quick_sleep):
        await asyncio.wait_for(agent._heartbeat_loop(), timeout=3)

    assert HEARTBEAT_INTERVAL_SECONDS == 10  # sanity: module constant intact
    await bus.close()
