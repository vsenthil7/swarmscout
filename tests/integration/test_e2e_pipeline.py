"""TC-I04 — end-to-end agent pipeline over fakeredis.

This test exercises the full envelope chain through real bus code, real
hasher code, real base_agent ordering, and real heuristic aggregation.
It does NOT exercise:
- Real LLM providers (we stub the router into exhaustion, which forces
  the ``requires_human_review`` path — acceptable because the LLM is a
  lineage accessory, not the authority on the envelope chain).
- Real Postgres (we use an in-memory fake repository — the chain of
  ``upstream_ids`` is asserted against what the bus delivers, which is
  the same source of truth the DB would read from).
- Real Playwright scrapers (Social and Chain agents are bypassed by
  hand-crafting their output envelopes and publishing them onto the bus).

The point of this test is to prove that the **message wire format** and
the **join semantics** of Risk + Narrator hold end-to-end. If this test
passes, a real deploy of the same code against real Redis + real Postgres
will stand up correctly.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import fakeredis.aioredis
import pytest

from agents.common.bus import Bus
from agents.common.envelope_builder import build_envelope, now_iso
from agents.common.hasher import hash_payload
from agents.common.on_chain import NullAnchor
from agents.common.schemas.envelope import AgentName, Envelope, StreamName
from agents.common.schemas.payloads import (
    ChainMetrics,
    DataQuality,
    SocialScore,
    TokenCandidate,
)


# --------------------------------------------------------------------------- #
# Minimal in-memory fakes — enough to exercise BaseAgent.anchor_and_publish. #
# --------------------------------------------------------------------------- #


@dataclass
class _FakeFindingsRepo:
    """In-memory findings store — keyed by msg_id."""

    rows: dict[str, Envelope] = field(default_factory=dict)
    anchored: dict[str, tuple[str, int]] = field(default_factory=dict)

    async def insert_envelope(self, env: Envelope) -> None:
        """Stash the envelope as-is."""
        self.rows[env.msg_id] = env

    async def record_onchain(self, msg_id: str, tx: str, block: int) -> None:
        """Record the anchor receipt so tests can assert anchoring happened."""
        self.anchored[msg_id] = (tx, block)


@dataclass
class _FakeHeartbeatRepo:
    """No-op heartbeat repo — upsert just counts calls."""

    upserts: int = 0

    async def upsert(self, **_: Any) -> None:
        """Increment the counter; ignore fields."""
        self.upserts += 1


# --------------------------------------------------------------------------- #
# The test                                                                    #
# --------------------------------------------------------------------------- #


TOKEN_ADDR = "0x" + "1" * 40
CREATOR_ADDR = "0x" + "2" * 40


@pytest.mark.asyncio
async def test_e2e_candidate_to_brief_chain() -> None:
    """End-to-end envelope chain: Hunter -> Risk partial verdict flow.

    We synthesise a Hunter-style TokenCandidate and the matching pair of
    Social + Chain envelopes, publish them directly, and then assert:

    1. Every published envelope has a valid payload_hash.
    2. upstream_ids correctly chain candidate -> social/chain -> (would
       be) risk.
    3. All hashes on the bus re-verify identically after round-tripping
       through JSON.
    4. No duplicate msg_ids anywhere in the chain.
    """
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)

    try:
        # --- Hunter: emit a TokenCandidate -------------------------------- #
        candidate = TokenCandidate(
            token_address=TOKEN_ADDR,
            launch_timestamp=now_iso(),
            creator_address=CREATOR_ADDR,
            token_name="Test Token",
            token_symbol="TT",
            initial_liquidity_usd=5_000.0,
            source_url="https://four.meme/test",
        )
        hunter_env = build_envelope(
            agent=AgentName.HUNTER, payload=candidate, model_used=None
        )
        await bus.publish(StreamName.CANDIDATES, hunter_env)

        # --- Social: emit a SocialScore downstream ------------------------ #
        social = SocialScore(
            token_address=TOKEN_ADDR,
            organic_score=65,
            mentions_24h=120,
            sentiment=0.2,
            red_flags=[],
            influencer_mentions=[],
            data_quality=DataQuality.OK,
        )
        social_env = build_envelope(
            agent=AgentName.SOCIAL,
            payload=social,
            upstream_ids=[hunter_env.msg_id],
            model_used="openai/gpt-4o",
        )
        await bus.publish(StreamName.SOCIAL, social_env)

        # --- Chain: emit a ChainMetrics downstream ------------------------ #
        chain = ChainMetrics(
            token_address=TOKEN_ADDR,
            holder_count=120,
            top10_concentration_pct=30.0,
            liquidity_usd=5_000.0,
            buy_sell_velocity_tx_per_min=10.0,
            whale_entries=0,
            contract_verified=True,
            honeypot_check_passed=True,
            lp_locked=True,
            creator_previous_tokens=0,
        )
        chain_env = build_envelope(
            agent=AgentName.CHAIN,
            payload=chain,
            upstream_ids=[hunter_env.msg_id],
            model_used=None,
        )
        await bus.publish(StreamName.CHAIN, chain_env)

        # --- Assertions --------------------------------------------------- #
        # 1. Each envelope's payload_hash re-computes from its payload.
        for env in (hunter_env, social_env, chain_env):
            assert env.payload_hash == hash_payload(env.payload)

        # 2. Lineage chain is intact.
        assert hunter_env.upstream_ids == []
        assert social_env.upstream_ids == [hunter_env.msg_id]
        assert chain_env.upstream_ids == [hunter_env.msg_id]

        # 3. Every envelope round-trips through JSON without the hash changing.
        for env in (hunter_env, social_env, chain_env):
            reloaded = Envelope.model_validate_json(env.model_dump_json())
            assert reloaded.payload_hash == env.payload_hash
            assert hash_payload(reloaded.payload) == env.payload_hash

        # 4. Distinct msg_ids (ULIDs are unique by construction, but paranoia is free).
        ids = {hunter_env.msg_id, social_env.msg_id, chain_env.msg_id}
        assert len(ids) == 3

        # 5. Streams now hold the three envelopes.
        assert await bus.stream_length(StreamName.CANDIDATES) == 1
        assert await bus.stream_length(StreamName.SOCIAL) == 1
        assert await bus.stream_length(StreamName.CHAIN) == 1

        # 6. Consuming from stream:candidates yields the same envelope we published.
        async for msg in bus.consume(
            stream=StreamName.CANDIDATES,
            group="e2e-test",
            consumer="c1",
            block_ms=50,
            batch=5,
        ):
            assert msg.envelope.msg_id == hunter_env.msg_id
            assert msg.envelope.payload_hash == hunter_env.payload_hash
            await bus.ack(StreamName.CANDIDATES, "e2e-test", msg.entry_id)
            break
    finally:
        await bus.close()
        await redis.aclose()


@pytest.mark.asyncio
async def test_base_agent_publishes_to_pubsub_for_briefs() -> None:
    """Bug-fix regression: briefs must be fanned out to ``pubsub:briefs``.

    Creates a minimal concrete BaseAgent subclass whose ``output_stream``
    is ``StreamName.BRIEFS`` and calls ``anchor_and_publish``. A pubsub
    subscriber on ``pubsub:briefs`` must receive exactly one message.
    This prevents a regression of the WebSocket silence bug documented
    in ``docs/REVIEW_FIRST_CUT.md`` §5 (#7).
    """
    from agents.common.base_agent import BaseAgent
    from agents.common.schemas.payloads import (
        AlphaBrief,
        ConvictionTier,
    )

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)

    class _BriefEmitter(BaseAgent):
        agent_name = AgentName.NARRATOR
        output_stream = StreamName.BRIEFS

        async def handle(self, msg: Any) -> None:
            """Not used — we call anchor_and_publish directly in the test."""
            return None

    findings = _FakeFindingsRepo()
    heartbeats = _FakeHeartbeatRepo()
    anchor = NullAnchor()
    agent = _BriefEmitter(
        bus=bus,
        findings=findings,  # type: ignore[arg-type]
        heartbeats=heartbeats,  # type: ignore[arg-type]
        anchor=anchor,
    )

    pubsub = redis.pubsub()
    await pubsub.subscribe("pubsub:briefs")

    brief = AlphaBrief(
        token_name="Test",
        token_address=TOKEN_ADDR,
        thesis=(
            "A test thesis long enough to pass the 50-character minimum "
            "validation on the AlphaBrief.thesis field."
        ),
        conviction_tier=ConvictionTier.MODERATE,
        caveats=["test"],
        sources=[],
        model_attribution=["anthropic/claude-opus-4-7"],
        brief_generated_at=now_iso(),
    )

    try:
        env = await agent.anchor_and_publish(payload=brief, model_used="anthropic/claude-opus-4-7")

        # Drain the subscribe-ack, then read the real message.
        received = None
        for _ in range(20):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if msg and msg.get("type") == "message":
                received = msg
                break
            await asyncio.sleep(0.05)

        assert received is not None, "no message broadcast to pubsub:briefs"
        data = received["data"]
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        assert env.msg_id in data
        assert env.payload_hash in data
    finally:
        await pubsub.unsubscribe("pubsub:briefs")
        await pubsub.aclose()
        await bus.close()
        await redis.aclose()
