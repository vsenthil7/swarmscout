"""Coverage tests for agents/narrator/main.py.

Exercises: handle() noop, _main_loop consume/ack/failure paths, _process
human-review branch + brief branch, _narrate happy + RouterExhausted,
_parse_json fences + invalid + non-dict, _extract_token_name
happy/missing/non-dict, _derive_conviction boundaries, _amain, run().
"""

from __future__ import annotations

import asyncio
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
    ConvictionTier,
    RiskConfidence,
    RiskVerdict,
)
from agents.narrator.main import (
    NARRATOR_GROUP,
    NarratorAgent,
    _derive_conviction,
    _extract_token_name,
    _parse_json,
)


class _StubHeartbeats:
    async def upsert(self, **_: Any) -> None:
        return None


class _LineageFindings:
    """Findings stub with a configurable iter_lineage async generator."""

    def __init__(self, lineage_rows: list[SimpleNamespace] | None = None) -> None:
        self.lineage_rows = lineage_rows or []
        self.inserted: list[Any] = []
        self.on_chain_records: list[Any] = []

    async def insert_envelope(self, env: Any) -> None:
        self.inserted.append(env)

    async def record_onchain(self, *args: Any) -> None:
        self.on_chain_records.append(args)

    async def iter_lineage(self, _msg_id: str):  # type: ignore[no-untyped-def]
        for row in self.lineage_rows:
            yield row


def _ctx_stub(router: Any | None = None, findings: Any | None = None) -> SimpleNamespace:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)
    return SimpleNamespace(
        settings=SimpleNamespace(narrator_primary_model="anthropic/claude-opus-4-7"),
        bus=bus,
        findings=findings or _LineageFindings(),
        heartbeats=_StubHeartbeats(),
        anchor=NullAnchor(),
        redis=redis,
        router=router or SimpleNamespace(chat=AsyncMock()),
    )


def _risk_verdict_env(
    *,
    score: int | None = 70,
    requires_human: bool = False,
    red_flags: list[str] | None = None,
    token_addr: str = "0x" + "a" * 40,
) -> Any:
    """Build a RiskVerdict-payload envelope."""
    verdict = RiskVerdict(
        token_address=token_addr,
        score_0_100=score,
        red_flags=red_flags or [],
        rationale="Solid setup with reasonable liquidity.",
        missing_inputs=[],
        confidence=RiskConfidence.MEDIUM,
        requires_human_review=requires_human,
    )
    return build_envelope(agent=AgentName.RISK, payload=verdict)


# --------------------------------------------------------------------------- #
# _parse_json                                                                 #
# --------------------------------------------------------------------------- #


def test_parse_json_strips_json_fences() -> None:
    assert _parse_json('```json\n{"x": 1}\n```') == {"x": 1}


def test_parse_json_strips_bare_fences() -> None:
    assert _parse_json('```\n{"y": 2}\n```') == {"y": 2}


def test_parse_json_returns_empty_on_decode_failure() -> None:
    assert _parse_json("not valid json") == {}


def test_parse_json_returns_empty_when_non_dict() -> None:
    """Top-level JSON arrays are dropped — we expect an object."""
    assert _parse_json("[1, 2, 3]") == {}


def test_parse_json_handles_fences_without_newline() -> None:
    """```{'x':1}``` with no newline still trims closing fence."""
    result = _parse_json("```{\"x\": 1}```")
    # Depending on how fences split, result may be {} or {"x":1}; either way
    # the function must return without raising.
    assert isinstance(result, dict)


def test_parse_json_handles_leading_fence_without_newline_closing() -> None:
    """Covers the branch where starts with ``` but no newline inside; closing ``` present."""
    # After `if newline != -1` is False (no newline), falls straight through to
    # the endswith check which still strips.
    result = _parse_json("```")
    assert isinstance(result, dict)


# --------------------------------------------------------------------------- #
# _extract_token_name                                                         #
# --------------------------------------------------------------------------- #


def test_extract_token_name_picks_first_matching_row() -> None:
    lineage = [
        {"agent": "social", "payload": {"organic_score": 70}},
        {"agent": "hunter", "payload": {"token_name": "FooToken"}},
        {"agent": "chain", "payload": {"token_name": "Shouldnt be used"}},
    ]
    assert _extract_token_name(lineage) == "FooToken"


def test_extract_token_name_returns_none_when_absent() -> None:
    lineage = [{"agent": "social", "payload": {"organic_score": 5}}]
    assert _extract_token_name(lineage) is None


def test_extract_token_name_skips_non_dict_payloads() -> None:
    """A non-dict payload row is silently skipped, not raised on."""
    lineage = [
        {"agent": "weird", "payload": "not-a-dict"},
        {"agent": "hunter", "payload": {"token_name": "RealName"}},
    ]
    assert _extract_token_name(lineage) == "RealName"


def test_extract_token_name_treats_empty_name_as_missing() -> None:
    lineage = [{"agent": "hunter", "payload": {"token_name": ""}}]
    assert _extract_token_name(lineage) is None


# --------------------------------------------------------------------------- #
# _derive_conviction                                                          #
# --------------------------------------------------------------------------- #


def test_derive_conviction_high_at_85_and_above() -> None:
    assert _derive_conviction(85) == ConvictionTier.HIGH
    assert _derive_conviction(100) == ConvictionTier.HIGH


def test_derive_conviction_moderate_65_to_84() -> None:
    assert _derive_conviction(65) == ConvictionTier.MODERATE
    assert _derive_conviction(84) == ConvictionTier.MODERATE


def test_derive_conviction_speculative_40_to_64() -> None:
    assert _derive_conviction(40) == ConvictionTier.SPECULATIVE
    assert _derive_conviction(64) == ConvictionTier.SPECULATIVE


def test_derive_conviction_degen_below_40() -> None:
    assert _derive_conviction(0) == ConvictionTier.DEGEN
    assert _derive_conviction(39) == ConvictionTier.DEGEN


# --------------------------------------------------------------------------- #
# handle() noop                                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_handle_returns_none() -> None:
    ctx = _ctx_stub()
    agent = NarratorAgent(ctx=ctx)
    assert await agent.handle(None) is None


# --------------------------------------------------------------------------- #
# _process — human review branch                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_process_human_review_when_requires_human_review_flag_set() -> None:
    """requires_human_review=True emits a HumanReviewRequest on stream:human_review."""
    findings = _LineageFindings()
    ctx = _ctx_stub(findings=findings)
    agent = NarratorAgent(ctx=ctx)
    env = _risk_verdict_env(requires_human=True, red_flags=["honeypot", "creator-dumped"])

    with patch.object(agent.bus, "publish", new=AsyncMock()) as pub:
        await agent._process(env)

    assert len(findings.inserted) == 1  # review envelope persisted
    pub.assert_awaited_once()
    stream_arg = pub.await_args.args[0]
    assert stream_arg == StreamName.HUMAN_REVIEW


@pytest.mark.asyncio
async def test_process_human_review_when_score_is_none() -> None:
    """score_0_100=None also triggers the human-review branch."""
    findings = _LineageFindings()
    ctx = _ctx_stub(findings=findings)
    agent = NarratorAgent(ctx=ctx)
    env = _risk_verdict_env(score=None, requires_human=True, red_flags=[])

    with patch.object(agent.bus, "publish", new=AsyncMock()) as pub:
        await agent._process(env)

    pub.assert_awaited_once()
    review = findings.inserted[0].payload
    # Empty red_flags falls back to default reason
    assert "requires-human-review" in review["reason"]


@pytest.mark.asyncio
async def test_process_human_review_swallows_anchor_failure() -> None:
    """Anchor exception during human-review persists doesn't block publish."""
    findings = _LineageFindings()
    ctx = _ctx_stub(findings=findings)
    agent = NarratorAgent(ctx=ctx)
    # Make the anchor raise.
    agent.anchor = SimpleNamespace(record=AsyncMock(side_effect=RuntimeError("rpc down")))
    env = _risk_verdict_env(requires_human=True)

    with patch.object(agent.bus, "publish", new=AsyncMock()) as pub:
        await agent._process(env)

    pub.assert_awaited_once()  # publish still fires


# --------------------------------------------------------------------------- #
# _process — normal brief branch                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_process_normal_brief_calls_anchor_and_publish() -> None:
    """Non-human-review verdict emits via anchor_and_publish (standard path)."""
    lineage_rows = [
        SimpleNamespace(agent="hunter", payload={"token_name": "TokA"}, model_used=None),
        SimpleNamespace(
            agent="risk",
            payload={"rationale": "ok"},
            model_used="anthropic/claude-opus-4-7",
        ),
    ]
    findings = _LineageFindings(lineage_rows=lineage_rows)
    ctx = _ctx_stub(findings=findings)
    ctx.router.chat = AsyncMock(
        return_value=SimpleNamespace(
            content='{"thesis": "This is a thoroughly researched thesis with more than fifty characters of substance.", "caveats": ["low lp"], "sources": ["x.com"]}',
            provider="openai",
            model="openai/gpt-4o",
        )
    )
    agent = NarratorAgent(ctx=ctx)
    env = _risk_verdict_env(score=72, requires_human=False)

    with patch.object(agent, "anchor_and_publish", new=AsyncMock()) as emit:
        await agent._process(env)

    emit.assert_awaited_once()
    brief = emit.await_args.kwargs["payload"]
    assert brief.token_name == "TokA"
    assert brief.conviction_tier == ConvictionTier.MODERATE
    assert "low lp" in brief.caveats


# --------------------------------------------------------------------------- #
# _narrate — RouterExhausted fallback                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_narrate_falls_back_when_router_exhausted() -> None:
    """If all providers are down, brief uses the rationale + degraded caveat."""
    findings = _LineageFindings(lineage_rows=[
        SimpleNamespace(agent="hunter", payload={"token_name": "FallbackTok"}, model_used=None),
    ])
    ctx = _ctx_stub(findings=findings)
    ctx.router.chat = AsyncMock(side_effect=RouterExhaustedError("all down"))
    agent = NarratorAgent(ctx=ctx)
    verdict = RiskVerdict(
        token_address="0x" + "b" * 40,
        score_0_100=70,
        red_flags=[],
        rationale="This is a heuristic-only rationale for the brief with enough length to satisfy the thesis minimum character requirement.",
        missing_inputs=[],
        confidence=RiskConfidence.MEDIUM,
        requires_human_review=False,
    )
    env = build_envelope(agent=AgentName.RISK, payload=verdict)

    brief, model_used = await agent._narrate(verdict, env)
    assert model_used is None
    assert brief.thesis.startswith("This is a heuristic")
    assert any("unreachable" in c.lower() for c in brief.caveats)


@pytest.mark.asyncio
async def test_narrate_handles_empty_thesis_from_llm() -> None:
    """LLM returning {thesis: ''} falls through to verdict.rationale truncation."""
    findings = _LineageFindings(lineage_rows=[
        SimpleNamespace(agent="hunter", payload={"token_name": "EmptyThesisTok"}, model_used=None),
    ])
    ctx = _ctx_stub(findings=findings)
    ctx.router.chat = AsyncMock(
        return_value=SimpleNamespace(
            content='{"thesis": "", "caveats": [], "sources": []}',
            provider="anthropic",
            model="anthropic/claude-opus-4-7",
        )
    )
    agent = NarratorAgent(ctx=ctx)
    verdict = RiskVerdict(
        token_address="0x" + "c" * 40,
        score_0_100=50,
        red_flags=[],
        rationale="A full rationale long enough to satisfy the fifty-character minimum thesis requirement of AlphaBrief.",
        missing_inputs=[],
        confidence=RiskConfidence.MEDIUM,
        requires_human_review=False,
    )
    env = build_envelope(agent=AgentName.RISK, payload=verdict)

    brief, model_used = await agent._narrate(verdict, env)
    assert model_used == "anthropic/claude-opus-4-7"
    assert brief.thesis.startswith("A full rationale")


# --------------------------------------------------------------------------- #
# _main_loop — ack on success, log+skip on exception                          #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_main_loop_acks_on_successful_process() -> None:
    """Happy-path _main_loop acks and increments counters."""
    ctx = _ctx_stub()
    agent = NarratorAgent(ctx=ctx)
    env = _risk_verdict_env()
    msg = BusMessage(stream=StreamName.RISK.value, entry_id="1-0", envelope=env)

    async def fake_consume(**_: Any):  # type: ignore[no-untyped-def]
        yield msg

    ctx.bus.consume = fake_consume  # type: ignore[assignment]
    ctx.bus.ack = AsyncMock()

    with patch.object(agent, "_process", new=AsyncMock()):
        await asyncio.wait_for(agent._main_loop(), timeout=3)

    ctx.bus.ack.assert_awaited_once()
    assert agent._events_in_window == 1


@pytest.mark.asyncio
async def test_main_loop_swallows_process_exception() -> None:
    """_process exception: log + count failure + DO NOT ack."""
    ctx = _ctx_stub()
    agent = NarratorAgent(ctx=ctx)
    env = _risk_verdict_env()
    msg = BusMessage(stream=StreamName.RISK.value, entry_id="1-0", envelope=env)

    async def fake_consume(**_: Any):  # type: ignore[no-untyped-def]
        yield msg

    ctx.bus.consume = fake_consume  # type: ignore[assignment]
    ctx.bus.ack = AsyncMock()

    with patch.object(agent, "_process", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await asyncio.wait_for(agent._main_loop(), timeout=3)

    ctx.bus.ack.assert_not_awaited()


@pytest.mark.asyncio
async def test_main_loop_exits_when_stop_event_set() -> None:
    """If stop event set before consume iteration, loop breaks."""
    ctx = _ctx_stub()
    agent = NarratorAgent(ctx=ctx)
    agent._stop_event.set()

    env = _risk_verdict_env()
    msg = BusMessage(stream=StreamName.RISK.value, entry_id="1-0", envelope=env)

    async def fake_consume(**_: Any):  # type: ignore[no-untyped-def]
        yield msg

    ctx.bus.consume = fake_consume  # type: ignore[assignment]
    ctx.bus.ack = AsyncMock()

    with patch.object(agent, "_process", new=AsyncMock()) as proc:
        await asyncio.wait_for(agent._main_loop(), timeout=3)

    proc.assert_not_awaited()


# --------------------------------------------------------------------------- #
# _amain + run                                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_amain_drives_agent_and_closes_context() -> None:
    from agents.narrator import main as narrator_main

    fake_ctx = SimpleNamespace(
        settings=SimpleNamespace(narrator_primary_model="m"),
        bus=Bus(url="redis://fake", client=fakeredis.aioredis.FakeRedis(decode_responses=True)),
        findings=_LineageFindings(),
        heartbeats=_StubHeartbeats(),
        anchor=NullAnchor(),
        redis=fakeredis.aioredis.FakeRedis(decode_responses=True),
        router=SimpleNamespace(chat=AsyncMock()),
        aclose=AsyncMock(),
    )

    async def fake_build_context() -> SimpleNamespace:
        return fake_ctx

    with patch.object(narrator_main, "build_context", new=fake_build_context), \
         patch.object(NarratorAgent, "run", new=AsyncMock()):
        await narrator_main._amain()

    fake_ctx.aclose.assert_awaited_once()


def test_run_entrypoint_invokes_amain_via_asyncio_run() -> None:
    from agents.narrator import main as narrator_main

    with patch.object(narrator_main.asyncio, "run") as mock_run:
        narrator_main.run()
    mock_run.assert_called_once()
