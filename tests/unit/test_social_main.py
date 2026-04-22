"""Coverage tests for agents/social/main.py.

Covers: handle noop, _main_loop ack + error paths, _process validation+publish,
_gather parallel scrape, _score LLM-success+JSON-decode-error+router-exhaustion
+clamping, _strip_fences, _amain/run.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest

from agents.common.bus import Bus, BusMessage
from agents.common.envelope_builder import build_envelope
from agents.common.llm_router import RouterExhaustedError
from agents.common.on_chain import NullAnchor
from agents.common.schemas.envelope import AgentName, StreamName
from agents.common.schemas.payloads import DataQuality, TokenCandidate
from agents.social.main import (
    ScrapeBundle,
    SocialAgent,
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


@dataclass
class _FakeScrapeResult:
    mention_count: int
    sample_snippets: list[str]
    degraded: bool


class _FakeXScraper:
    def __init__(
        self, mentions: int = 25, samples: list[str] | None = None, degraded: bool = False
    ) -> None:
        self.mentions = mentions
        self.samples = samples or ["@a: great new token", "@b: bullish"]
        self.degraded = degraded
        self.started = False
        self.stopped = False

    async def search(self, query: str) -> _FakeScrapeResult:
        return _FakeScrapeResult(
            mention_count=self.mentions, sample_snippets=self.samples, degraded=self.degraded
        )

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class _FakeTelegramScraper(_FakeXScraper):
    pass


def _ctx_stub(router: Any | None = None) -> SimpleNamespace:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)
    return SimpleNamespace(
        settings=SimpleNamespace(social_primary_model="openai/gpt-4o"),
        bus=bus,
        findings=_NullFindings(),
        heartbeats=_StubHeartbeats(),
        anchor=NullAnchor(),
        redis=redis,
        router=router or SimpleNamespace(chat=AsyncMock()),
    )


def _candidate_env(addr: str = "0x" + "a" * 40) -> Any:
    c = TokenCandidate(
        token_address=addr,
        launch_timestamp="2026-04-22T10:00:00Z",
        creator_address="0x" + "b" * 40,
        token_name="FooToken",
        token_symbol="FOO",
        initial_liquidity_usd=2500.0,
        source_url="https://four.meme/foo",
    )
    return build_envelope(agent=AgentName.HUNTER, payload=c)


# --------------------------------------------------------------------------- #
# _strip_fences                                                               #
# --------------------------------------------------------------------------- #


def test_strip_fences_with_json_tag() -> None:
    assert _strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_fences_no_fences_noop() -> None:
    assert _strip_fences('{"a": 1}') == '{"a": 1}'


def test_strip_fences_bare_fences() -> None:
    assert _strip_fences('```\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_fences_no_trailing_newline() -> None:
    """Confirm the no-newline branch runs without error."""
    assert isinstance(_strip_fences("```"), str)


# --------------------------------------------------------------------------- #
# handle() no-op                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_handle_returns_none() -> None:
    ctx = _ctx_stub()
    agent = SocialAgent(ctx=ctx, x_scraper=_FakeXScraper(), telegram_scraper=_FakeTelegramScraper())
    assert await agent.handle(None) is None


# --------------------------------------------------------------------------- #
# _gather                                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_gather_combines_both_scrapers() -> None:
    ctx = _ctx_stub()
    x = _FakeXScraper(mentions=10, samples=[f"x{i}" for i in range(7)], degraded=False)
    tg = _FakeTelegramScraper(mentions=5, samples=[f"t{i}" for i in range(3)], degraded=True)
    agent = SocialAgent(ctx=ctx, x_scraper=x, telegram_scraper=tg)
    c = TokenCandidate.model_validate(_candidate_env().payload)
    bundle = await agent._gather(c)
    assert bundle.x_mentions == 10
    # Samples are capped at 5.
    assert len(bundle.x_samples) == 5
    assert bundle.tg_mentions == 5
    assert len(bundle.tg_samples) == 3
    assert bundle.x_degraded is False
    assert bundle.tg_degraded is True


# --------------------------------------------------------------------------- #
# _score                                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_score_happy_path_parses_llm_json() -> None:
    ctx = _ctx_stub()
    ctx.router.chat = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps(
                {
                    "organic_score": 72,
                    "sentiment": 0.45,
                    "influencer_mentions": ["@alpha", "@beta"],
                    "red_flags": ["minor-concern"],
                }
            ),
            provider="openai",
            model="openai/gpt-4o",
        )
    )
    agent = SocialAgent(ctx=ctx, x_scraper=_FakeXScraper(), telegram_scraper=_FakeTelegramScraper())
    c = TokenCandidate.model_validate(_candidate_env().payload)
    bundle = ScrapeBundle(
        x_mentions=20, x_samples=["a", "b"], x_degraded=False,
        tg_mentions=5, tg_samples=["t1"], tg_degraded=False,
    )
    score, model = await agent._score(c, bundle)
    assert score.organic_score == 72
    assert score.sentiment == 0.45
    assert "minor-concern" in score.red_flags
    assert score.influencer_mentions == ["@alpha", "@beta"]
    assert model == "openai/gpt-4o"
    assert score.data_quality == DataQuality.OK


@pytest.mark.asyncio
async def test_score_clamps_values_out_of_range() -> None:
    """organic_score clamped 0..100, sentiment clamped -1..1."""
    ctx = _ctx_stub()
    ctx.router.chat = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps(
                {"organic_score": 250, "sentiment": 5.0, "influencer_mentions": [], "red_flags": []}
            ),
            provider="openai",
            model="openai/gpt-4o",
        )
    )
    agent = SocialAgent(ctx=ctx, x_scraper=_FakeXScraper(), telegram_scraper=_FakeTelegramScraper())
    c = TokenCandidate.model_validate(_candidate_env().payload)
    bundle = ScrapeBundle(0, [], False, 0, [], False)
    score, _ = await agent._score(c, bundle)
    assert score.organic_score == 100  # clamped
    assert score.sentiment == 1.0  # clamped


@pytest.mark.asyncio
async def test_score_sets_degraded_when_scrapers_degraded() -> None:
    """If either scraper was degraded, data_quality is flipped + red_flags populated."""
    ctx = _ctx_stub()
    ctx.router.chat = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps(
                {"organic_score": 50, "sentiment": 0, "influencer_mentions": [], "red_flags": []}
            ),
            provider="anthropic",
            model="anthropic/claude-sonnet",
        )
    )
    agent = SocialAgent(ctx=ctx, x_scraper=_FakeXScraper(), telegram_scraper=_FakeTelegramScraper())
    c = TokenCandidate.model_validate(_candidate_env().payload)
    bundle = ScrapeBundle(0, [], True, 0, [], True)  # both degraded
    score, _ = await agent._score(c, bundle)
    assert score.data_quality == DataQuality.DEGRADED
    assert "x_scrape_blocked" in score.red_flags
    assert "telegram_scrape_blocked" in score.red_flags


@pytest.mark.asyncio
async def test_score_falls_back_on_json_decode_error() -> None:
    """Non-JSON LLM response leaves organic=0 / sentiment=0 defaults."""
    ctx = _ctx_stub()
    ctx.router.chat = AsyncMock(
        return_value=SimpleNamespace(
            content="not valid json at all",
            provider="google",
            model="google/gemini-2.5-pro",
        )
    )
    agent = SocialAgent(ctx=ctx, x_scraper=_FakeXScraper(), telegram_scraper=_FakeTelegramScraper())
    c = TokenCandidate.model_validate(_candidate_env().payload)
    bundle = ScrapeBundle(0, [], False, 0, [], False)
    score, model = await agent._score(c, bundle)
    assert score.organic_score == 0
    assert model == "google/gemini-2.5-pro"


@pytest.mark.asyncio
async def test_score_handles_router_exhausted() -> None:
    """RouterExhaustedError produces a degraded score with 'social_llm_exhausted' flag."""
    ctx = _ctx_stub()
    ctx.router.chat = AsyncMock(side_effect=RouterExhaustedError("all down"))
    agent = SocialAgent(ctx=ctx, x_scraper=_FakeXScraper(), telegram_scraper=_FakeTelegramScraper())
    c = TokenCandidate.model_validate(_candidate_env().payload)
    bundle = ScrapeBundle(0, [], False, 0, [], False)
    score, model = await agent._score(c, bundle)
    assert model is None
    assert "social_llm_exhausted" in score.red_flags
    assert score.data_quality == DataQuality.DEGRADED


# --------------------------------------------------------------------------- #
# _process                                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_process_validates_and_publishes() -> None:
    """_process validates, gathers, scores, anchors+publishes."""
    ctx = _ctx_stub()
    ctx.router.chat = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps(
                {"organic_score": 60, "sentiment": 0.3, "influencer_mentions": [], "red_flags": []}
            ),
            provider="openai",
            model="openai/gpt-4o",
        )
    )
    agent = SocialAgent(ctx=ctx, x_scraper=_FakeXScraper(), telegram_scraper=_FakeTelegramScraper())
    env = _candidate_env()

    with patch.object(agent, "anchor_and_publish", new=AsyncMock()) as emit:
        await agent._process(env)
    emit.assert_awaited_once()


# --------------------------------------------------------------------------- #
# _main_loop                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_main_loop_acks_on_success() -> None:
    ctx = _ctx_stub()
    agent = SocialAgent(ctx=ctx, x_scraper=_FakeXScraper(), telegram_scraper=_FakeTelegramScraper())
    env = _candidate_env()
    msg = BusMessage(stream=StreamName.CANDIDATES.value, entry_id="1-0", envelope=env)

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
    ctx = _ctx_stub()
    agent = SocialAgent(ctx=ctx, x_scraper=_FakeXScraper(), telegram_scraper=_FakeTelegramScraper())
    env = _candidate_env()
    msg = BusMessage(stream=StreamName.CANDIDATES.value, entry_id="1-0", envelope=env)

    async def fake_consume(**_: Any):  # type: ignore[no-untyped-def]
        yield msg

    ctx.bus.consume = fake_consume  # type: ignore[assignment]
    ctx.bus.ack = AsyncMock()

    with patch.object(agent, "_process", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await asyncio.wait_for(agent._main_loop(), timeout=3)

    ctx.bus.ack.assert_not_awaited()


@pytest.mark.asyncio
async def test_main_loop_exits_when_stop_event_set() -> None:
    ctx = _ctx_stub()
    agent = SocialAgent(ctx=ctx, x_scraper=_FakeXScraper(), telegram_scraper=_FakeTelegramScraper())
    agent._stop_event.set()

    env = _candidate_env()
    msg = BusMessage(stream=StreamName.CANDIDATES.value, entry_id="1-0", envelope=env)

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
async def test_amain_wires_scrapers_and_tears_down() -> None:
    from agents.social import main as social_main

    fake_ctx = SimpleNamespace(
        settings=SimpleNamespace(social_primary_model="m"),
        bus=Bus(url="redis://fake", client=fakeredis.aioredis.FakeRedis(decode_responses=True)),
        findings=_NullFindings(),
        heartbeats=_StubHeartbeats(),
        anchor=NullAnchor(),
        redis=fakeredis.aioredis.FakeRedis(decode_responses=True),
        router=SimpleNamespace(chat=AsyncMock()),
        aclose=AsyncMock(),
    )
    fake_x = _FakeXScraper()
    fake_tg = _FakeTelegramScraper()

    async def fake_build_context() -> SimpleNamespace:
        return fake_ctx

    with patch.object(social_main, "build_context", new=fake_build_context), \
         patch.object(social_main, "XScraper", return_value=fake_x), \
         patch.object(social_main, "TelegramScraper", return_value=fake_tg), \
         patch.object(SocialAgent, "run", new=AsyncMock()):
        await social_main._amain()

    assert fake_x.started and fake_x.stopped
    assert fake_tg.started and fake_tg.stopped
    fake_ctx.aclose.assert_awaited_once()


def test_run_entrypoint_invokes_amain_via_asyncio_run() -> None:
    from agents.social import main as social_main
    with patch.object(social_main.asyncio, "run") as mock_run:
        social_main.run()
    mock_run.assert_called_once()
