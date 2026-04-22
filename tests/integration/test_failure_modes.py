"""TC-F01-F04 — failure tests.

Exercises the degrade-not-fail invariant across the four failure modes
that are most likely in production (LLM exhaustion TC-F05 is covered
separately in test_llm_router.py):

* TC-F01 — on-chain anchor failure must not block the envelope chain
* TC-F02 — findings-repo transient insert failure must not crash agents
* TC-F03 — bus publish failure must propagate so callers can retry
* TC-F04 — Risk-agent join window timeout emits a partial verdict
"""

from __future__ import annotations

import asyncio
from typing import Any

import fakeredis.aioredis
import pytest

from agents.common.bus import Bus
from agents.common.envelope_builder import build_envelope, now_iso
from agents.common.on_chain import NullAnchor
from agents.common.schemas.envelope import AgentName, Envelope, StreamName
from agents.common.schemas.payloads import (
    AlphaBrief,
    ConvictionTier,
)


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #


class _FlakyFindings:
    """Findings repo whose ``insert_envelope`` raises the first N times."""

    def __init__(self, raise_times: int = 0) -> None:
        self.raise_times = raise_times
        self.calls = 0
        self.anchored: dict[str, tuple[str, int]] = {}

    async def insert_envelope(self, env: Envelope) -> None:
        """Raise RuntimeError until raise_times is exhausted."""
        self.calls += 1
        if self.calls <= self.raise_times:
            raise RuntimeError("transient db error")

    async def record_onchain(self, msg_id: str, tx: str, block: int) -> None:
        """Record the anchor receipt."""
        self.anchored[msg_id] = (tx, block)


class _FlakyAnchor:
    """Anchor whose ``record`` raises every time — simulates RPC outage."""

    address = "0x0"

    async def record(self, **_: Any) -> tuple[str, int]:
        """Raise to simulate a BNB Testnet outage."""
        raise RuntimeError("rpc timeout")

    async def verify(self, msg_id: str) -> None:  # noqa: ARG002
        """Null verify."""
        return None


class _NopHeartbeat:
    """Heartbeat repo that accepts everything silently."""

    async def upsert(self, **_: Any) -> None:
        """No-op."""
        return None


# --------------------------------------------------------------------------- #
# TC-F01: anchor failure does not block publish                              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_tcf01_anchor_failure_does_not_block_publish() -> None:
    """Base-agent must swallow anchor errors and still publish downstream."""
    from agents.common.base_agent import BaseAgent

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)

    class _E(BaseAgent):
        agent_name = AgentName.NARRATOR
        output_stream = StreamName.BRIEFS

        async def handle(self, _msg: Any) -> None:
            return None

    findings = _FlakyFindings()
    agent = _E(
        bus=bus,
        findings=findings,  # type: ignore[arg-type]
        heartbeats=_NopHeartbeat(),  # type: ignore[arg-type]
        anchor=_FlakyAnchor(),  # type: ignore[arg-type]
    )

    brief = AlphaBrief(
        token_name="X",
        token_address="0x" + "1" * 40,
        thesis="a" * 60,
        conviction_tier=ConvictionTier.DEGEN,
        brief_generated_at=now_iso(),
    )

    try:
        env = await agent.anchor_and_publish(payload=brief)
        assert env.msg_id
        # Stream still got the envelope, even though anchor failed.
        assert await bus.stream_length(StreamName.BRIEFS) == 1
        # No on-chain record was written, which is correct — anchor failed.
        assert findings.anchored == {}
    finally:
        await bus.close()
        await redis.aclose()


# --------------------------------------------------------------------------- #
# TC-F02: findings-repo transient failure                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_tcf02_findings_insert_transient_failure_bubbles_up() -> None:
    """Transient DB error on insert bubbles up — caller (BaseAgent._main_loop) catches and counts.

    We don't want to silently swallow DB writes: losing the Postgres record
    means the ``/verify`` endpoint later cannot retrieve the payload. So
    the exception MUST propagate from ``anchor_and_publish``.
    """
    from agents.common.base_agent import BaseAgent

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)

    class _E(BaseAgent):
        agent_name = AgentName.NARRATOR
        output_stream = StreamName.BRIEFS

        async def handle(self, _msg: Any) -> None:
            return None

    findings = _FlakyFindings(raise_times=1)
    agent = _E(
        bus=bus,
        findings=findings,  # type: ignore[arg-type]
        heartbeats=_NopHeartbeat(),  # type: ignore[arg-type]
        anchor=NullAnchor(),
    )

    brief = AlphaBrief(
        token_name="X",
        token_address="0x" + "1" * 40,
        thesis="a" * 60,
        conviction_tier=ConvictionTier.DEGEN,
        brief_generated_at=now_iso(),
    )

    try:
        with pytest.raises(RuntimeError, match="transient db error"):
            await agent.anchor_and_publish(payload=brief)
    finally:
        await bus.close()
        await redis.aclose()


# --------------------------------------------------------------------------- #
# TC-F03: bus publish failure propagates                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_tcf03_bus_publish_failure_propagates() -> None:
    """If XADD raises, anchor_and_publish should surface it.

    The caller's main loop will count the failure and fall through; it
    must not silently succeed with a half-published envelope.
    """
    from agents.common.base_agent import BaseAgent

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)

    async def _boom(*_a: Any, **_kw: Any) -> str:
        raise RuntimeError("xadd failure")

    # Monkey-patch the bus to simulate Redis refusing writes.
    bus.publish = _boom  # type: ignore[assignment]

    class _E(BaseAgent):
        agent_name = AgentName.NARRATOR
        output_stream = StreamName.BRIEFS

        async def handle(self, _msg: Any) -> None:
            return None

    agent = _E(
        bus=bus,
        findings=_FlakyFindings(),  # type: ignore[arg-type]
        heartbeats=_NopHeartbeat(),  # type: ignore[arg-type]
        anchor=NullAnchor(),
    )

    brief = AlphaBrief(
        token_name="X",
        token_address="0x" + "1" * 40,
        thesis="a" * 60,
        conviction_tier=ConvictionTier.DEGEN,
        brief_generated_at=now_iso(),
    )

    try:
        with pytest.raises(RuntimeError, match="xadd failure"):
            await agent.anchor_and_publish(payload=brief)
    finally:
        # bus.close is on the real bus object — call the underlying redis.
        await redis.aclose()


# --------------------------------------------------------------------------- #
# TC-F04: Risk-agent join timeout                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_tcf04_risk_join_timeout_emits_partial_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    """If only one side of a Risk pair arrives, a partial verdict is emitted after the timeout.

    We short-circuit the 120s window via monkeypatch to keep the test
    fast. The assertion is about *behaviour*, not duration.
    """
    from agents.risk import main as risk_main

    # Shorten the join window to 0.1s for the test.
    monkeypatch.setattr(risk_main, "JOIN_TIMEOUT_S", 0.1)

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)

    captured: list[Envelope] = []

    # Build a RiskAgent with minimal dependencies and hand-drive the pair logic.
    class _CapturingFindings:
        async def insert_envelope(self, env: Envelope) -> None:
            captured.append(env)

        async def record_onchain(self, *_: Any) -> None:
            return None

    class _Ctx:
        class _S:
            risk_primary_model = "anthropic/claude-opus-4-7"

        settings = _S()
        bus = None  # set below
        router = None  # unused — partial-emit path does not call the LLM
        findings = _CapturingFindings()
        heartbeats = _NopHeartbeat()
        anchor = NullAnchor()

    ctx = _Ctx()
    ctx.bus = bus  # type: ignore[attr-defined]

    agent = risk_main.RiskAgent(ctx=ctx)  # type: ignore[arg-type]

    # Seed a single-side social envelope; no chain partner will arrive.
    from agents.common.schemas.payloads import DataQuality, SocialScore

    social = SocialScore(
        token_address="0x" + "1" * 40,
        organic_score=50,
        mentions_24h=10,
        sentiment=0.0,
        data_quality=DataQuality.OK,
    )
    social_env = build_envelope(
        agent=AgentName.SOCIAL, payload=social, upstream_ids=[], model_used=None
    )

    # Inject directly into the pending map so we test the sweeper in isolation.
    async with agent._pending_lock:
        agent._pending[social.token_address] = risk_main.PendingPair(
            envelope=social_env,
            side="social",
            created_at=asyncio.get_event_loop().time() - 10.0,  # force "already expired"
        )

    # Run one iteration of the sweeper (sleep 5s is the loop; we call the body directly).
    expired = []
    now = asyncio.get_event_loop().time()
    async with agent._pending_lock:
        for token, pair in list(agent._pending.items()):
            if now - pair.created_at > risk_main.JOIN_TIMEOUT_S:
                expired.append((token, pair))
                del agent._pending[token]

    try:
        for _, pair in expired:
            await agent._emit_partial(pair)

        assert len(captured) == 1
        verdict = captured[0]
        assert verdict.agent == AgentName.RISK
        assert verdict.payload["requires_human_review"] is True
        assert "missing-chain-input" in verdict.payload["red_flags"]
    finally:
        await bus.close()
        await redis.aclose()
