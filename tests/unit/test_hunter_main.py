"""Coverage tests for agents/hunter/main.py.

Covers HunterAgent construction, handle()→None root behaviour, _main_loop
iterating a source and emitting candidates, _to_candidate mapping with and
without optional timestamp/name/symbol/url, _build_source branching
(polling vs rpc_log), and the run()/_amain entrypoint wiring.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from agents.common.bus import Bus
from agents.common.on_chain import NullAnchor
from agents.common.schemas.envelope import StreamName
from agents.hunter.main import (
    HunterAgent,
    _build_source,
    _now_iso,
)
from agents.hunter.sources.base import RawTokenEvent


class _StubHeartbeats:
    async def upsert(self, **_: Any) -> None:
        return None


class _NullFindings:
    async def insert_envelope(self, _env: Any) -> None:
        return None

    async def record_onchain(self, *_: Any) -> None:
        return None


def _ctx_stub(**overrides: Any) -> SimpleNamespace:
    """Build a minimal Context stand-in with all attrs HunterAgent needs."""
    settings = SimpleNamespace(
        hunter_primary_model="google/gemini-2.5-flash",
        fourmeme_source="polling",
        fourmeme_poll_url="https://four.meme/api/new",
        fourmeme_poll_interval_seconds=2,
        bnb_testnet_rpc_url="https://data-seed-prebsc-1-s1.binance.org:8545/",
    )
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)
    ctx = SimpleNamespace(
        settings=settings,
        bus=bus,
        findings=_NullFindings(),
        heartbeats=_StubHeartbeats(),
        anchor=NullAnchor(),
        redis=redis,
    )
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


class _StaticSource:
    """Source that yields a fixed list of events then stops iteration."""

    def __init__(self, events: list[RawTokenEvent]) -> None:
        self._events = events

    async def events(self):  # type: ignore[no-untyped-def]
        for ev in self._events:
            yield ev


@pytest.mark.asyncio
async def test_handle_returns_none_for_root_agent() -> None:
    """Hunter is a root agent — handle() ignores its argument and returns None."""
    ctx = _ctx_stub()
    source = _StaticSource([])
    agent = HunterAgent(ctx=ctx, source=source)
    assert await agent.handle(None) is None


@pytest.mark.asyncio
async def test_main_loop_emits_candidates_for_each_event() -> None:
    """_main_loop iterates the source and calls anchor_and_publish once per event."""
    ctx = _ctx_stub()
    events = [
        RawTokenEvent(
            token_address="0x" + "a" * 40,
            creator_address="0x" + "b" * 40,
            token_name="Tok1",
            token_symbol="T1",
            initial_liquidity_usd=1500.0,
            launch_timestamp="2026-04-22T10:00:00Z",
            source_url="https://four.meme/t1",
        ),
        RawTokenEvent(
            token_address="0x" + "c" * 40,
            creator_address="0x" + "d" * 40,
            token_name="",
            token_symbol="",
            initial_liquidity_usd=0.0,
            launch_timestamp="",
            source_url="",
        ),
    ]
    source = _StaticSource(events)
    agent = HunterAgent(ctx=ctx, source=source)

    with patch.object(agent, "anchor_and_publish", new=AsyncMock()) as anchor_mock:
        await asyncio.wait_for(agent._main_loop(), timeout=3)

    assert anchor_mock.await_count == 2
    # _events_in_window should increment once per successful emit.
    assert agent._events_in_window == 2
    await ctx.bus.close()


@pytest.mark.asyncio
async def test_main_loop_stops_on_stop_event() -> None:
    """When _stop_event is set between yields, the loop breaks without emitting more."""
    ctx = _ctx_stub()

    class _InfiniteSource:
        async def events(self):  # type: ignore[no-untyped-def]
            counter = 0
            while True:
                counter += 1
                yield RawTokenEvent(
                    token_address="0x" + f"{counter:040x}"[:40],
                    creator_address="0x" + "f" * 40,
                    token_name=f"T{counter}",
                    token_symbol="T",
                    initial_liquidity_usd=0.0,
                    launch_timestamp="2026-04-22T10:00:00Z",
                    source_url="",
                )

    source = _InfiniteSource()
    agent = HunterAgent(ctx=ctx, source=source)

    emit_count = {"n": 0}

    async def emit_then_stop(payload: Any, model_used: Any = None) -> Any:
        emit_count["n"] += 1
        if emit_count["n"] >= 3:
            agent._stop_event.set()
        return None

    with patch.object(agent, "anchor_and_publish", new=emit_then_stop):
        await asyncio.wait_for(agent._main_loop(), timeout=3)

    # Loop processed at least 3 events, then stopped cleanly.
    assert emit_count["n"] >= 3
    await ctx.bus.close()


def test_to_candidate_passes_values_through_when_all_fields_present() -> None:
    """_to_candidate uses every supplied field verbatim."""
    raw = RawTokenEvent(
        token_address="0x" + "a" * 40,
        creator_address="0x" + "b" * 40,
        token_name="FooToken",
        token_symbol="FOO",
        initial_liquidity_usd=12_345.67,
        launch_timestamp="2026-04-22T11:00:00Z",
        source_url="https://four.meme/foo",
    )
    c = HunterAgent._to_candidate(raw)
    assert c.token_address == "0x" + "a" * 40
    assert c.creator_address == "0x" + "b" * 40
    assert c.token_name == "FooToken"
    assert c.token_symbol == "FOO"
    assert c.initial_liquidity_usd == 12_345.67
    assert c.launch_timestamp == "2026-04-22T11:00:00Z"
    assert c.source_url == "https://four.meme/foo"


def test_to_candidate_substitutes_defaults_for_missing_fields() -> None:
    """Empty name/symbol/url/timestamp must be replaced with sane defaults."""
    raw = RawTokenEvent(
        token_address="0x" + "c" * 40,
        creator_address="0x" + "d" * 40,
        token_name="",
        token_symbol="",
        initial_liquidity_usd=0.0,
        launch_timestamp="",
        source_url="",
    )
    c = HunterAgent._to_candidate(raw)
    assert c.token_name == "unknown"
    assert c.token_symbol == "?"
    assert c.source_url == "https://four.meme"
    # _now_iso is substituted; must match ISO-8601 Z suffix.
    assert c.launch_timestamp.endswith("Z")
    assert "T" in c.launch_timestamp


def test_now_iso_returns_utc_iso8601_z_suffix() -> None:
    """_now_iso always produces an ISO-8601 timestamp with Z terminator."""
    s = _now_iso()
    assert s.endswith("Z")
    assert "T" in s
    assert len(s) == 20  # YYYY-MM-DDTHH:MM:SSZ


def test_build_source_selects_polling_by_default() -> None:
    """fourmeme_source == 'polling' (the default) yields a FourMemePollingSource."""
    from agents.hunter.sources.polling import FourMemePollingSource

    ctx = _ctx_stub()
    src = _build_source(ctx)
    assert isinstance(src, FourMemePollingSource)


def test_build_source_selects_rpc_log_when_configured() -> None:
    """fourmeme_source == 'rpc_log' yields a FourMemeRPCLogSource."""
    from agents.hunter.sources.rpc_log import FourMemeRPCLogSource

    ctx = _ctx_stub()
    ctx.settings.fourmeme_source = "rpc_log"
    src = _build_source(ctx)
    assert isinstance(src, FourMemeRPCLogSource)


def test_build_source_is_case_and_whitespace_insensitive() -> None:
    """'RPC_LOG ' with case and surrounding whitespace still picks rpc_log."""
    from agents.hunter.sources.rpc_log import FourMemeRPCLogSource

    ctx = _ctx_stub()
    ctx.settings.fourmeme_source = "  RPC_LOG  "
    src = _build_source(ctx)
    assert isinstance(src, FourMemeRPCLogSource)


@pytest.mark.asyncio
async def test_amain_drives_agent_run_and_closes_context() -> None:
    """_amain builds a context, constructs HunterAgent, runs, and closes on exit."""
    from agents.hunter import main as hunter_main

    fake_ctx = SimpleNamespace(
        settings=SimpleNamespace(
            hunter_primary_model="m",
            fourmeme_source="polling",
            fourmeme_poll_url="https://four.meme/api/new",
            fourmeme_poll_interval_seconds=1,
            bnb_testnet_rpc_url="rpc",
        ),
        bus=Bus(url="redis://fake", client=fakeredis.aioredis.FakeRedis(decode_responses=True)),
        findings=_NullFindings(),
        heartbeats=_StubHeartbeats(),
        anchor=NullAnchor(),
        redis=fakeredis.aioredis.FakeRedis(decode_responses=True),
        aclose=AsyncMock(),
    )

    run_mock = AsyncMock()

    async def fake_build_context() -> SimpleNamespace:
        return fake_ctx

    with patch.object(hunter_main, "build_context", new=fake_build_context), \
         patch.object(HunterAgent, "run", new=run_mock):
        await hunter_main._amain()

    run_mock.assert_awaited_once()
    fake_ctx.aclose.assert_awaited_once()


def test_run_entrypoint_invokes_amain_via_asyncio_run() -> None:
    """run() is the sync shim — it must hand off to asyncio.run(_amain())."""
    from agents.hunter import main as hunter_main

    with patch.object(hunter_main.asyncio, "run") as mock_run:
        hunter_main.run()
    mock_run.assert_called_once()
