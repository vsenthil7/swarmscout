"""Coverage tests for agents/risk/main.py.

Covers: handle() noop, _main_loop task orchestration, _consume happy +
exception paths, _on_message first-half buffering + same-side dup
overwrite + both-sides-emit, _sweep_timeouts eviction, _emit_verdict
happy path, _emit_partial, _ask_llm JSON success + JSON parse fail +
RouterExhaustedError, _strip_fences, _amain + run.
"""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from agents.common.bus import Bus, BusMessage
from agents.common.envelope_builder import build_envelope
from agents.common.llm_router import RouterExhaustedError
from agents.common.on_chain import NullAnchor
from agents.common.schemas.envelope import AgentName, StreamName
from agents.common.schemas.payloads import (
    ChainMetrics,
    RiskConfidence,
    SocialScore,
)
from agents.risk.heuristics import Finding
from agents.risk.main import (
    CHAIN_GROUP,
    JOIN_TIMEOUT_S,
    SOCIAL_GROUP,
    PendingPair,
    RiskAgent,
    _strip_fences,
)


class _StubHeartbeats:
    async def upsert(self, **_: Any) -> None:
        return None


class _NullFindings:
    async def insert_envelope(self, _env: Any) -> None:
        return None

    async def record_onchain(self, *_: Any) -> None:
        return None


def _ctx_stub(router: Any | None = None) -> SimpleNamespace:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)
    return SimpleNamespace(
        settings=SimpleNamespace(risk_primary_model="anthropic/claude-opus-4-7"),
        bus=bus,
        findings=_NullFindings(),
        heartbeats=_StubHeartbeats(),
        anchor=NullAnchor(),
        redis=redis,
        router=router or SimpleNamespace(chat=AsyncMock()),
    )


def _social_env(addr: str = "0x" + "a" * 40) -> Any:
    """Build a SocialScore-payload envelope."""
    s = SocialScore(
        token_address=addr,
        organic_score=60,
        mentions_24h=42,
        sentiment=0.3,
        red_flags=[],
        influencer_mentions=[],
    )
    return build_envelope(agent=AgentName.SOCIAL, payload=s)


def _chain_env(addr: str = "0x" + "a" * 40) -> Any:
    """Build a ChainMetrics-payload envelope."""
    c = ChainMetrics(
        token_address=addr,
        holder_count=500,
        top10_concentration_pct=30.0,
        liquidity_usd=25_000.0,
        buy_sell_velocity_tx_per_min=12.0,
        whale_entries=3,
        contract_verified=True,
        honeypot_check_passed=True,
        lp_locked=True,
        creator_previous_tokens=0,
    )
    return build_envelope(agent=AgentName.CHAIN, payload=c)


# --------------------------------------------------------------------------- #
# _strip_fences                                                               #
# --------------------------------------------------------------------------- #


def test_strip_fences_removes_markdown_code_block() -> None:
    """Strips leading ```json and trailing ```."""
    assert _strip_fences('```json\n{"x": 1}\n```') == '{"x": 1}'


def test_strip_fences_removes_bare_fences() -> None:
    """Strips ``` without a language tag."""
    assert _strip_fences('```\n{"x": 1}\n```') == '{"x": 1}'


def test_strip_fences_noop_when_no_fences() -> None:
    """Plain JSON is unchanged."""
    assert _strip_fences('{"x": 1}') == '{"x": 1}'


def test_strip_fences_preserves_content_when_newline_missing() -> None:
    """If there's no newline after ```, return trimmed original."""
    # "```{x}```" — no newline, so first-newline branch is skipped.
    s = "```{x}```"
    result = _strip_fences(s)
    # The code takes the `first_newline == -1` branch, then strips trailing ```
    assert result.endswith("}")


# --------------------------------------------------------------------------- #
# handle() is a no-op for root-of-branch agents                               #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_handle_returns_none() -> None:
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    assert await agent.handle(None) is None


# --------------------------------------------------------------------------- #
# _on_message — buffer + overwrite + emit-when-partner-arrives                #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_on_message_buffers_first_side() -> None:
    """First side of a pair is stored in the pending buffer; no verdict yet."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    with patch.object(agent, "_emit_verdict", new=AsyncMock()) as emit:
        await agent._on_message(_social_env(), "social")
    emit.assert_not_awaited()
    assert len(agent._pending) == 1


@pytest.mark.asyncio
async def test_on_message_overwrites_same_side_duplicate() -> None:
    """Receiving the same side twice overwrites the pending entry (newest wins)."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    env1 = _social_env()
    env2 = _social_env()
    with patch.object(agent, "_emit_verdict", new=AsyncMock()) as emit:
        await agent._on_message(env1, "social")
        await agent._on_message(env2, "social")
    emit.assert_not_awaited()
    assert len(agent._pending) == 1


@pytest.mark.asyncio
async def test_on_message_emits_verdict_when_both_sides_arrive() -> None:
    """Receiving social then chain (same token_address) triggers _emit_verdict."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    addr = "0x" + "a" * 40
    with patch.object(agent, "_emit_verdict", new=AsyncMock()) as emit:
        await agent._on_message(_social_env(addr), "social")
        await agent._on_message(_chain_env(addr), "chain")
    emit.assert_awaited_once()
    # Pending buffer is now empty.
    assert len(agent._pending) == 0


@pytest.mark.asyncio
async def test_on_message_emits_verdict_when_chain_arrives_first() -> None:
    """Reverse order: chain first, social second — same behaviour."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    addr = "0x" + "a" * 40
    with patch.object(agent, "_emit_verdict", new=AsyncMock()) as emit:
        await agent._on_message(_chain_env(addr), "chain")
        await agent._on_message(_social_env(addr), "social")
    emit.assert_awaited_once()
    # Inspect the call — social_env should be the first kw, chain_env second.
    kw = emit.await_args.kwargs
    assert kw["social_env"].agent == AgentName.SOCIAL
    assert kw["chain_env"].agent == AgentName.CHAIN


# --------------------------------------------------------------------------- #
# _sweep_timeouts                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_sweep_timeouts_evicts_stale_and_emits_partial() -> None:
    """Entries older than JOIN_TIMEOUT_S are removed and _emit_partial is awaited."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    env = _social_env()
    stale_pair = PendingPair(
        envelope=env, side="social",
        created_at=time.monotonic() - JOIN_TIMEOUT_S - 10,
    )
    agent._pending[env.payload["token_address"]] = stale_pair

    emit_partial_mock = AsyncMock()
    # Stop the loop after one iteration.
    sleep_calls = {"n": 0}
    original_sleep = asyncio.sleep

    async def stop_after_first(delay: float) -> None:
        sleep_calls["n"] += 1
        if sleep_calls["n"] >= 1:
            agent._stop_event.set()
        await original_sleep(0)

    with patch.object(agent, "_emit_partial", new=emit_partial_mock), \
         patch("agents.risk.main.asyncio.sleep", new=stop_after_first):
        await asyncio.wait_for(agent._sweep_timeouts(), timeout=3)

    emit_partial_mock.assert_awaited_once()
    assert len(agent._pending) == 0


@pytest.mark.asyncio
async def test_sweep_timeouts_swallows_emit_partial_exception() -> None:
    """If _emit_partial raises, the sweeper logs and keeps running."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    env = _social_env()
    agent._pending[env.payload["token_address"]] = PendingPair(
        envelope=env, side="social",
        created_at=time.monotonic() - JOIN_TIMEOUT_S - 10,
    )

    sleep_calls = {"n": 0}
    original_sleep = asyncio.sleep

    async def stop_after_first(delay: float) -> None:
        sleep_calls["n"] += 1
        if sleep_calls["n"] >= 1:
            agent._stop_event.set()
        await original_sleep(0)

    with patch.object(agent, "_emit_partial", new=AsyncMock(side_effect=RuntimeError("x"))), \
         patch("agents.risk.main.asyncio.sleep", new=stop_after_first):
        # Must NOT raise.
        await asyncio.wait_for(agent._sweep_timeouts(), timeout=3)


# --------------------------------------------------------------------------- #
# _emit_verdict + _emit_partial                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_emit_verdict_builds_risk_verdict_and_publishes() -> None:
    """_emit_verdict runs heuristics, asks LLM, anchors + publishes."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)

    with patch.object(agent, "_ask_llm", new=AsyncMock(
            return_value=("rationale text", "anthropic/claude-opus-4-7", RiskConfidence.MEDIUM))), \
         patch.object(agent, "anchor_and_publish", new=AsyncMock()) as anchor:
        await agent._emit_verdict(social_env=_social_env(), chain_env=_chain_env())
    anchor.assert_awaited_once()


@pytest.mark.asyncio
async def test_emit_verdict_marks_human_review_when_llm_exhausted() -> None:
    """When _ask_llm returns (_, None, None), verdict flags requires_human_review."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)

    with patch.object(agent, "_ask_llm", new=AsyncMock(return_value=("fallback note", None, None))), \
         patch.object(agent, "anchor_and_publish", new=AsyncMock()) as anchor:
        await agent._emit_verdict(social_env=_social_env(), chain_env=_chain_env())

    published_verdict = anchor.await_args.kwargs["payload"]
    assert published_verdict.requires_human_review is True
    assert published_verdict.score_0_100 is None


@pytest.mark.asyncio
async def test_emit_partial_when_only_social_arrived() -> None:
    """_emit_partial emits missing='chain' when only social is buffered."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    pair = PendingPair(envelope=_social_env(), side="social", created_at=0.0)

    with patch.object(agent, "anchor_and_publish", new=AsyncMock()) as anchor:
        await agent._emit_partial(pair)

    verdict = anchor.await_args.kwargs["payload"]
    assert verdict.missing_inputs == ["chain"]
    assert verdict.requires_human_review is True


@pytest.mark.asyncio
async def test_emit_partial_when_only_chain_arrived() -> None:
    """_emit_partial emits missing='social' when only chain is buffered."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    pair = PendingPair(envelope=_chain_env(), side="chain", created_at=0.0)

    with patch.object(agent, "anchor_and_publish", new=AsyncMock()) as anchor:
        await agent._emit_partial(pair)

    verdict = anchor.await_args.kwargs["payload"]
    assert verdict.missing_inputs == ["social"]


# --------------------------------------------------------------------------- #
# _ask_llm                                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ask_llm_parses_happy_path_json() -> None:
    """When the LLM returns valid JSON with rationale+confidence, both are extracted."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    response_payload = {"rationale": "Solid setup.", "confidence": "high"}
    ctx.router.chat = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps(response_payload),
            provider="anthropic",
            model="anthropic/claude-opus-4-7",
        )
    )
    result = await agent._ask_llm(
        SocialScore.model_validate(_social_env().payload),
        ChainMetrics.model_validate(_chain_env().payload),
        [Finding(tag="low-lp", weight=10, reason="LP small")],
        42,
    )
    rationale, model_used, confidence = result
    assert rationale == "Solid setup."
    assert model_used == "anthropic/claude-opus-4-7"
    assert confidence == RiskConfidence.HIGH


@pytest.mark.asyncio
async def test_ask_llm_defaults_unknown_confidence_to_medium() -> None:
    """If confidence is not in the enum, default to 'medium'."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    ctx.router.chat = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps({"rationale": "ok", "confidence": "maybe"}),
            provider="openai",
            model="openai/gpt-4o",
        )
    )
    _rationale, _model, confidence = await agent._ask_llm(
        SocialScore.model_validate(_social_env().payload),
        ChainMetrics.model_validate(_chain_env().payload),
        [],
        50,
    )
    assert confidence == RiskConfidence.MEDIUM


@pytest.mark.asyncio
async def test_ask_llm_handles_empty_rationale() -> None:
    """Empty rationale falls back to the 'No rationale produced.' default."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    ctx.router.chat = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps({"rationale": "   ", "confidence": "low"}),
            provider="openai",
            model="openai/gpt-4o",
        )
    )
    rationale, _model, _conf = await agent._ask_llm(
        SocialScore.model_validate(_social_env().payload),
        ChainMetrics.model_validate(_chain_env().payload),
        [],
        50,
    )
    assert rationale == "No rationale produced."


@pytest.mark.asyncio
async def test_ask_llm_falls_back_on_json_parse_failure() -> None:
    """Unparseable LLM response becomes a LOW-confidence rationale of the first 400 chars."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    ctx.router.chat = AsyncMock(
        return_value=SimpleNamespace(
            content="not valid json at all",
            provider="google",
            model="google/gemini-2.5-pro",
        )
    )
    rationale, model_used, confidence = await agent._ask_llm(
        SocialScore.model_validate(_social_env().payload),
        ChainMetrics.model_validate(_chain_env().payload),
        [],
        50,
    )
    assert rationale.startswith("not valid json")
    assert model_used == "google/gemini-2.5-pro"
    assert confidence == RiskConfidence.LOW


@pytest.mark.asyncio
async def test_ask_llm_returns_degraded_triplet_on_router_exhaustion() -> None:
    """RouterExhaustedError yields (message, None, None) — signalling needs_human_review."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    ctx.router.chat = AsyncMock(side_effect=RouterExhaustedError("all providers down"))
    rationale, model_used, confidence = await agent._ask_llm(
        SocialScore.model_validate(_social_env().payload),
        ChainMetrics.model_validate(_chain_env().payload),
        [],
        50,
    )
    assert model_used is None
    assert confidence is None
    assert "unreachable" in rationale.lower()


# --------------------------------------------------------------------------- #
# _consume                                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_consume_processes_acks_and_increments_counters() -> None:
    """_consume: on success, ack + events_processed + events_in_window."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)

    env = _social_env()
    msg = BusMessage(stream=StreamName.SOCIAL.value, entry_id="1-0", envelope=env)

    async def fake_consume(**_: Any):  # type: ignore[no-untyped-def]
        yield msg

    ctx.bus.consume = fake_consume  # type: ignore[assignment]
    ctx.bus.ack = AsyncMock()

    with patch.object(agent, "_on_message", new=AsyncMock()):
        await asyncio.wait_for(
            agent._consume(StreamName.SOCIAL, SOCIAL_GROUP, "social"), timeout=3
        )

    ctx.bus.ack.assert_awaited_once()
    assert agent._events_in_window == 1


@pytest.mark.asyncio
async def test_consume_swallows_on_message_exception() -> None:
    """If _on_message raises, log + count failure, do NOT ack."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)

    env = _social_env()
    msg = BusMessage(stream=StreamName.SOCIAL.value, entry_id="1-0", envelope=env)

    async def fake_consume(**_: Any):  # type: ignore[no-untyped-def]
        yield msg

    ctx.bus.consume = fake_consume  # type: ignore[assignment]
    ctx.bus.ack = AsyncMock()

    with patch.object(agent, "_on_message", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await asyncio.wait_for(
            agent._consume(StreamName.SOCIAL, SOCIAL_GROUP, "social"), timeout=3
        )

    ctx.bus.ack.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_exits_when_stop_event_set() -> None:
    """If _stop_event is already set, consume breaks on first iteration."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)
    agent._stop_event.set()

    env = _social_env()
    msg = BusMessage(stream=StreamName.SOCIAL.value, entry_id="1-0", envelope=env)

    async def fake_consume(**_: Any):  # type: ignore[no-untyped-def]
        yield msg

    ctx.bus.consume = fake_consume  # type: ignore[assignment]
    ctx.bus.ack = AsyncMock()

    with patch.object(agent, "_on_message", new=AsyncMock()) as on_msg:
        await asyncio.wait_for(
            agent._consume(StreamName.SOCIAL, SOCIAL_GROUP, "social"), timeout=3
        )

    on_msg.assert_not_awaited()


# --------------------------------------------------------------------------- #
# _main_loop                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_main_loop_gathers_consumers_and_sweeper_then_cleans_up() -> None:
    """_main_loop gathers three tasks; when they finish, tasks are cancelled."""
    ctx = _ctx_stub()
    agent = RiskAgent(ctx=ctx)

    async def instant_return(*_: Any, **_kw: Any) -> None:
        return None

    with patch.object(agent, "_consume", new=instant_return), \
         patch.object(agent, "_sweep_timeouts", new=instant_return):
        await asyncio.wait_for(agent._main_loop(), timeout=3)


# --------------------------------------------------------------------------- #
# _amain + run                                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_amain_drives_agent_and_closes_context() -> None:
    """_amain builds context, runs RiskAgent, aclose on exit."""
    from agents.risk import main as risk_main

    fake_ctx = SimpleNamespace(
        settings=SimpleNamespace(risk_primary_model="m"),
        bus=Bus(url="redis://fake", client=fakeredis.aioredis.FakeRedis(decode_responses=True)),
        findings=_NullFindings(),
        heartbeats=_StubHeartbeats(),
        anchor=NullAnchor(),
        redis=fakeredis.aioredis.FakeRedis(decode_responses=True),
        router=SimpleNamespace(chat=AsyncMock()),
        aclose=AsyncMock(),
    )

    async def fake_build_context() -> SimpleNamespace:
        return fake_ctx

    with patch.object(risk_main, "build_context", new=fake_build_context), \
         patch.object(RiskAgent, "run", new=AsyncMock()):
        await risk_main._amain()

    fake_ctx.aclose.assert_awaited_once()


def test_run_entrypoint_invokes_amain_via_asyncio_run() -> None:
    """run() shims to asyncio.run(_amain())."""
    from agents.risk import main as risk_main

    with patch.object(risk_main.asyncio, "run") as mock_run:
        risk_main.run()
    mock_run.assert_called_once()
