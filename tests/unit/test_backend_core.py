"""Backend-core tests.

Covers envelope, payload schemas, bus, on-chain adapter, settings,
logging. Tied to TC-U01-13 and TC-U20-34.
"""

from __future__ import annotations

import json

import fakeredis.aioredis
import pytest
import redis.asyncio as aioredis
from pydantic import ValidationError

from agents.common.bus import Bus, BusMessage
from agents.common.envelope_builder import build_envelope, new_msg_id, now_iso
from agents.common.hasher import hash_payload
from agents.common.logging_config import configure_logging, get_logger
from agents.common.on_chain import (
    NullAnchor,
    msg_id_to_bytes32,
    payload_hash_hex_to_bytes32,
)
from agents.common.schemas.envelope import AgentName, Envelope, StreamName
from agents.common.schemas.payloads import (
    AlphaBrief,
    ChainMetrics,
    ConvictionTier,
    DataQuality,
    HumanReviewRequest,
    RiskConfidence,
    RiskVerdict,
    SocialScore,
    TokenCandidate,
)
from agents.common.settings import Settings, get_settings

# --------------------------------------------------------------------------- #
# Envelope (TC-U01-04)                                                        #
# --------------------------------------------------------------------------- #


def _make_payload() -> dict[str, object]:
    """Small payload dict reused across envelope tests."""
    return {"token_address": "0x" + "1" * 40, "score": 42}


def test_envelope_accepts_valid() -> None:
    """A fully-specified Envelope constructs successfully."""
    env = build_envelope(
        agent=AgentName.HUNTER, payload=_make_payload(), model_used="anthropic/claude-opus-4-7"
    )
    assert len(env.msg_id) == 26
    assert env.agent == AgentName.HUNTER
    assert env.payload_hash == hash_payload(env.payload)


def test_envelope_rejects_short_msg_id() -> None:
    """msg_id shorter than 26 chars raises ValidationError."""
    with pytest.raises(ValidationError):
        Envelope(
            msg_id="short",
            agent=AgentName.HUNTER,
            payload_hash="a" * 64,
            payload={},
            created_at=now_iso(),
        )


def test_envelope_rejects_bad_hash() -> None:
    """Non-hex payload_hash raises ValidationError."""
    with pytest.raises(ValidationError):
        Envelope(
            msg_id=new_msg_id(),
            agent=AgentName.HUNTER,
            payload_hash="not-hex",
            payload={},
            created_at=now_iso(),
        )


def test_envelope_rejects_bad_model_used() -> None:
    """model_used without a provider/model slash raises ValidationError."""
    with pytest.raises(ValidationError):
        build_envelope(agent=AgentName.HUNTER, payload={}, model_used="no-slash")


def test_envelope_rejects_invalid_ulid_chars() -> None:
    """Crockford-base32 forbids I and L — msg_id containing them fails."""
    with pytest.raises(ValidationError):
        Envelope(
            msg_id="IILL" + "0" * 22,  # I and L not in Crockford
            agent=AgentName.HUNTER,
            payload_hash="a" * 64,
            payload={},
            created_at=now_iso(),
        )


def test_envelope_rejects_bad_upstream_id() -> None:
    """upstream_ids entries must themselves be 26-char ULIDs."""
    with pytest.raises(ValidationError):
        Envelope(
            msg_id=new_msg_id(),
            agent=AgentName.HUNTER,
            upstream_ids=["short"],
            payload_hash="a" * 64,
            payload={},
            created_at=now_iso(),
        )


def test_envelope_rejects_non_iso_timestamp() -> None:
    """Free-form timestamps are rejected."""
    with pytest.raises(ValidationError):
        Envelope(
            msg_id=new_msg_id(),
            agent=AgentName.HUNTER,
            payload_hash="a" * 64,
            payload={},
            created_at="yesterday",
        )


def test_envelope_accepts_model_none() -> None:
    """model_used=None is valid for non-LLM messages (e.g. Hunter emissions)."""
    env = build_envelope(agent=AgentName.HUNTER, payload={}, model_used=None)
    assert env.model_used is None


# --------------------------------------------------------------------------- #
# Payload schemas                                                             #
# --------------------------------------------------------------------------- #


def test_token_candidate_validates_address() -> None:
    """Non-hex token_address is rejected."""
    with pytest.raises(ValidationError):
        TokenCandidate(
            token_address="not-an-address",
            launch_timestamp=now_iso(),
            creator_address="0x" + "0" * 40,
            token_name="T",
            token_symbol="T",
            initial_liquidity_usd=0,
            source_url="x",
        )


def test_social_score_bounds() -> None:
    """organic_score ∉ [0,100] or sentiment ∉ [-1,1] is rejected."""
    with pytest.raises(ValidationError):
        SocialScore(
            token_address="0x" + "1" * 40,
            organic_score=200,
            mentions_24h=0,
            sentiment=0.0,
        )
    with pytest.raises(ValidationError):
        SocialScore(
            token_address="0x" + "1" * 40,
            organic_score=50,
            mentions_24h=0,
            sentiment=2.0,
        )


def test_chain_metrics_happy() -> None:
    """A valid ChainMetrics constructs with default data_quality=ok."""
    m = ChainMetrics(
        token_address="0x" + "1" * 40,
        holder_count=10,
        top10_concentration_pct=50,
        liquidity_usd=1000,
        buy_sell_velocity_tx_per_min=5,
        whale_entries=0,
        contract_verified=True,
        honeypot_check_passed=True,
        lp_locked=True,
        creator_previous_tokens=0,
    )
    assert m.data_quality == DataQuality.OK


def test_risk_verdict_nullable_score() -> None:
    """score_0_100 may be None when the LLM stack is exhausted (FR-064)."""
    v = RiskVerdict(
        token_address="0x" + "1" * 40,
        score_0_100=None,
        rationale="no llm",
        requires_human_review=True,
    )
    assert v.score_0_100 is None
    assert v.requires_human_review is True


def test_risk_verdict_confidence_enum() -> None:
    """confidence must be one of the RiskConfidence enum values."""
    with pytest.raises(ValidationError):
        RiskVerdict(
            token_address="0x" + "1" * 40,
            score_0_100=50,
            rationale="x",
            confidence="off-the-chart",  # type: ignore[arg-type]
        )


def test_risk_confidence_values() -> None:
    """RiskConfidence is exactly {low, medium, high}."""
    assert {c.value for c in RiskConfidence} == {"low", "medium", "high"}


def test_alpha_brief_thesis_length() -> None:
    """AlphaBrief.thesis below 50 characters is rejected."""
    with pytest.raises(ValidationError):
        AlphaBrief(
            token_name="t",
            token_address="0x" + "1" * 40,
            thesis="short",  # < 50 chars
            conviction_tier=ConvictionTier.DEGEN,
            brief_generated_at=now_iso(),
        )


def test_human_review_request_shape() -> None:
    """HumanReviewRequest constructs with all required fields."""
    r = HumanReviewRequest(
        token_address="0x" + "1" * 40,
        reason="risk requires review",
        risk_verdict_msg_id=new_msg_id(),
        raised_at=now_iso(),
    )
    assert r.reason == "risk requires review"


# --------------------------------------------------------------------------- #
# Bus (TC-U30-34, TC-I04)                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_bus_publish_and_consume(bus: Bus) -> None:
    """XADD then XREADGROUP round-trip recovers the same envelope."""
    env = build_envelope(agent=AgentName.HUNTER, payload={"x": 1})
    await bus.publish(StreamName.CANDIDATES, env)
    received: list[BusMessage] = []
    async for msg in bus.consume(
        stream=StreamName.CANDIDATES, group="test", consumer="c1", block_ms=50, batch=10
    ):
        received.append(msg)
        await bus.ack(StreamName.CANDIDATES, "test", msg.entry_id)
        break
    assert received[0].envelope.msg_id == env.msg_id
    assert await bus.pending_depth(StreamName.CANDIDATES, "test") == 0


@pytest.mark.asyncio
async def test_bus_xlen(bus: Bus) -> None:
    """XLEN reports the stream length after multiple publishes."""
    await bus.publish(StreamName.CANDIDATES, build_envelope(agent=AgentName.HUNTER, payload={}))
    await bus.publish(StreamName.CANDIDATES, build_envelope(agent=AgentName.HUNTER, payload={}))
    assert await bus.stream_length(StreamName.CANDIDATES) == 2


@pytest.mark.asyncio
async def test_bus_ensure_group_idempotent(bus: Bus) -> None:
    """ensure_group() twice does not raise on BUSYGROUP."""
    await bus.ensure_group(StreamName.CANDIDATES, "g1")
    # second call must not raise
    await bus.ensure_group(StreamName.CANDIDATES, "g1")


@pytest.mark.skipif(
    "os.environ.get('REDIS_URL','').find('localhost') < 0",
    reason="Requires real Redis; set REDIS_URL=redis://localhost:6379/0 to enable",
)
@pytest.mark.asyncio
async def test_bus_pel_redelivery_against_real_redis() -> None:
    """Unacked message is redelivered on the next consume (TC-F reliability).

    Runs against real Redis via the docker-compose service (REDIS_URL env var).
    Covers FR-105: crashed consumer's in-flight messages are redelivered after
    visibility timeout via the PEL drain path in Bus.consume.
    """
    import os
    import uuid

    redis_url = os.environ["REDIS_URL"]
    client = aioredis.from_url(redis_url, decode_responses=True)
    try:
        # Use a unique stream+group per run so we don't collide across test invocations.
        stream_name = f"stream:pel_test_{uuid.uuid4().hex[:8]}"
        group = "pel-grp"
        bus = Bus(url=redis_url, client=client)

        env = build_envelope(agent=AgentName.HUNTER, payload={"x": 99})
        await bus.publish(stream_name, env)

        first_id = None
        async for msg in bus.consume(
            stream=stream_name, group=group, consumer="c1", block_ms=50, batch=5
        ):
            first_id = msg.entry_id
            break
        assert first_id is not None

        # Do NOT ack. Next consume must redeliver via PEL drain.
        delivered_again = False
        async for msg in bus.consume(
            stream=stream_name, group=group, consumer="c1", block_ms=50, batch=5
        ):
            if msg.entry_id == first_id:
                delivered_again = True
                await bus.ack(stream_name, group, msg.entry_id)
                break
        assert delivered_again
    finally:
        # Clean up the test stream.
        await client.delete(stream_name)
        await client.aclose()


@pytest.mark.skip(
    reason=(
        "fakeredis PEL drain via XREADGROUP id='0' does not redeliver entries "
        "owned by a consumer across separate generator instances the way real "
        "Redis does. PEL redelivery is covered by an integration test against "
        "real Redis in tests/integration/test_e2e_pipeline.py; production "
        "behaviour is unaffected."
    )
)
@pytest.mark.asyncio
async def test_bus_pel_redelivery(fake_redis: fakeredis.aioredis.FakeRedis, bus: Bus) -> None:
    """Unacked message is redelivered on the next consume (TC-F / reliability)."""
    env = build_envelope(agent=AgentName.HUNTER, payload={"x": 2})
    await bus.publish(StreamName.CANDIDATES, env)
    first_id = None
    async for msg in bus.consume(
        stream=StreamName.CANDIDATES, group="pel", consumer="c1", block_ms=50, batch=5
    ):
        first_id = msg.entry_id
        break
    # Do not ack; next consume call should redeliver via PEL drain.
    assert first_id is not None
    delivered_again = False
    async for msg in bus.consume(
        stream=StreamName.CANDIDATES, group="pel", consumer="c1", block_ms=50, batch=5
    ):
        if msg.entry_id == first_id:
            delivered_again = True
            await bus.ack(StreamName.CANDIDATES, "pel", msg.entry_id)
            break
    assert delivered_again


@pytest.mark.asyncio
async def test_bus_decodes_valid_envelope_field(
    bus: Bus, fake_redis: fakeredis.aioredis.FakeRedis
) -> None:
    # Write a malformed entry directly; consuming should raise.
    """A stream entry missing the ``envelope`` field raises ValueError on consume."""
    await fake_redis.xadd(StreamName.CANDIDATES.value, {"not_envelope": "oops"})
    await bus.ensure_group(StreamName.CANDIDATES, "malformed")
    with pytest.raises(ValueError):
        async for _msg in bus.consume(
            stream=StreamName.CANDIDATES, group="malformed", consumer="c1", block_ms=50
        ):
            pass


# --------------------------------------------------------------------------- #
# On-chain                                                                    #
# --------------------------------------------------------------------------- #


def test_msg_id_to_bytes32_shape() -> None:
    """ULID encodes to 32 bytes with right-zero padding; round-trips."""
    mid = new_msg_id()
    b = msg_id_to_bytes32(mid)
    assert len(b) == 32
    assert b.rstrip(b"\x00").decode("utf-8") == mid


def test_msg_id_to_bytes32_rejects_too_long() -> None:
    """A msg_id longer than 32 bytes raises."""
    with pytest.raises(ValueError):
        msg_id_to_bytes32("X" * 40)


def test_payload_hash_hex_to_bytes32() -> None:
    """64 hex chars decode to 32 raw bytes."""
    assert len(payload_hash_hex_to_bytes32("a" * 64)) == 32


def test_payload_hash_hex_rejects_bad_length() -> None:
    """Fewer than 64 hex chars raises."""
    with pytest.raises(ValueError):
        payload_hash_hex_to_bytes32("abcd")


@pytest.mark.asyncio
async def test_null_anchor_record_and_verify() -> None:
    """NullAnchor returns a deterministic placeholder; verify() is always None."""
    anchor = NullAnchor()
    tx, block = await anchor.record(msg_id="x", payload_hash_hex="a" * 64, agent="hunter")
    assert tx.startswith("0x")
    assert block == 0
    assert await anchor.verify("x") is None


# --------------------------------------------------------------------------- #
# Settings, logging                                                           #
# --------------------------------------------------------------------------- #


def test_settings_defaults() -> None:
    """Settings() constructs without environment overrides."""
    s = Settings()
    assert s.env in {"development", "staging", "production", "ci"}
    assert s.redis_url.startswith("redis://")


def test_settings_cached() -> None:
    """get_settings() is memoised (singleton per process)."""
    assert get_settings() is get_settings()


def test_logging_configures_without_errors() -> None:
    """configure_logging() + get_logger() + .info() does not raise."""
    configure_logging()
    log = get_logger("test", unit="x")
    log.info("ping")  # should not raise


# --------------------------------------------------------------------------- #
# Envelope JSON round-trip                                                    #
# --------------------------------------------------------------------------- #


def test_envelope_round_trips_through_json() -> None:
    """Envelope -> JSON -> Envelope preserves msg_id, payload_hash, and payload."""
    env = build_envelope(agent=AgentName.RISK, payload={"x": [1, 2, 3]})
    dumped = env.model_dump_json()
    reloaded = Envelope.model_validate_json(dumped)
    assert reloaded.msg_id == env.msg_id
    assert reloaded.payload_hash == env.payload_hash
    # Re-hashing the payload must match
    assert hash_payload(reloaded.payload) == env.payload_hash
    # Canonical JSON must be stable
    assert json.loads(dumped)["payload_hash"] == env.payload_hash
