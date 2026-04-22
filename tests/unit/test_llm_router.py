"""LLM router tests — TC-U20-28 and TC-F05."""

from __future__ import annotations

from dataclasses import dataclass

import fakeredis.aioredis
import pytest

from agents.common.llm_router import (
    ChatMessage,
    LLMResponse,
    LLMRouter,
    ProviderError,
    RateLimitedError,
    RouterExhaustedError,
    TokenBucket,
)


class _FakeLLMCallRepo:
    """In-memory audit log fake that records every ``log()`` call."""

    def __init__(self) -> None:
        """Start with an empty call log."""
        self.calls: list[dict[str, object]] = []

    async def log(self, **kw: object) -> None:  # type: ignore[no-untyped-def]
        """Capture the call kwargs verbatim so test assertions can inspect them."""
        self.calls.append(kw)


@dataclass
class _FakeProvider:
    """A fake provider that either returns a response or raises."""

    name: str
    response_text: str = "ok"
    raise_times: int = 0
    _calls: int = 0

    async def chat(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Return a canned success response, or raise ProviderError up to ``raise_times``."""
        self._calls += 1
        if self._calls <= self.raise_times:
            raise ProviderError(f"{self.name} simulated failure")
        return LLMResponse(
            provider=self.name,
            model=model,
            content=self.response_text,
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.0,
            latency_ms=1,
        )


@pytest.fixture
def audit() -> _FakeLLMCallRepo:
    """Fresh in-memory audit log per test."""
    return _FakeLLMCallRepo()


@pytest.fixture
async def bucket(fake_redis: fakeredis.aioredis.FakeRedis) -> TokenBucket:
    """TokenBucket capacity 10/minute bound to fakeredis."""
    return TokenBucket(fake_redis, capacity=10, period_s=60)


# TC-U20 — DGrid primary happy path
@pytest.mark.asyncio
async def test_router_uses_dgrid_first(audit: _FakeLLMCallRepo, bucket: TokenBucket) -> None:
    """Happy path: DGrid is primary and its response is returned."""
    dgrid = _FakeProvider(name="dgrid", response_text="dgrid-hello")
    router = LLMRouter(
        dgrid=dgrid,  # type: ignore[arg-type]
        anthropic=None,
        openai=None,
        google=None,
        bucket=bucket,
        llm_log=audit,  # type: ignore[arg-type]
    )
    resp = await router.chat(
        agent="risk",
        primary_model="anthropic/claude-opus-4-7",
        system=None,
        messages=[ChatMessage(role="user", content="hi")],
    )
    assert resp.provider == "dgrid"
    assert resp.content == "dgrid-hello"
    assert audit.calls[0]["success"] is True


# TC-U21 — DGrid fails once, direct provider picks up
@pytest.mark.asyncio
async def test_router_falls_back_on_dgrid_failure(
    audit: _FakeLLMCallRepo, bucket: TokenBucket
) -> None:
    """DGrid failure falls through to Anthropic on the first call."""
    dgrid = _FakeProvider(name="dgrid", raise_times=1)
    anthropic = _FakeProvider(name="anthropic", response_text="claude")
    router = LLMRouter(
        dgrid=dgrid,  # type: ignore[arg-type]
        anthropic=anthropic,  # type: ignore[arg-type]
        openai=None,
        google=None,
        bucket=bucket,
        llm_log=audit,  # type: ignore[arg-type]
    )
    resp = await router.chat(
        agent="risk",
        primary_model="anthropic/claude-opus-4-7",
        system=None,
        messages=[ChatMessage(role="user", content="hi")],
    )
    assert resp.provider == "anthropic"


# TC-U22 — DGrid circuit breaker trips after 3 failures
@pytest.mark.asyncio
async def test_router_circuit_breaker_trips(
    audit: _FakeLLMCallRepo, bucket: TokenBucket
) -> None:
    """After 3 consecutive DGrid failures, _dgrid_available flips to False."""
    dgrid = _FakeProvider(name="dgrid", raise_times=99)
    anthropic = _FakeProvider(name="anthropic", response_text="claude")
    router = LLMRouter(
        dgrid=dgrid,  # type: ignore[arg-type]
        anthropic=anthropic,  # type: ignore[arg-type]
        openai=None,
        google=None,
        bucket=bucket,
        llm_log=audit,  # type: ignore[arg-type]
    )
    # Drive enough calls to trip the breaker.
    for _ in range(5):
        await router.chat(
            agent="risk",
            primary_model="anthropic/claude-opus-4-7",
            system=None,
            messages=[ChatMessage(role="user", content="go")],
        )
    assert not router._dgrid_available()


# TC-U23 — rate limiter blocks on overflow
@pytest.mark.asyncio
async def test_rate_limiter_blocks_over_capacity(
    audit: _FakeLLMCallRepo, fake_redis: fakeredis.aioredis.FakeRedis
) -> None:
    """Router surfaces RouterExhaustedError when every provider is rate-limited."""
    tiny = TokenBucket(fake_redis, capacity=1, period_s=60)
    anthropic = _FakeProvider(name="anthropic")
    router = LLMRouter(
        dgrid=None,
        anthropic=anthropic,  # type: ignore[arg-type]
        openai=None,
        google=None,
        bucket=tiny,
        llm_log=audit,  # type: ignore[arg-type]
    )
    await router.chat(
        agent="risk",
        primary_model="anthropic/claude-opus-4-7",
        system=None,
        messages=[ChatMessage(role="user", content="hi")],
    )
    with pytest.raises(RouterExhaustedError):
        await router.chat(
            agent="risk",
            primary_model="anthropic/claude-opus-4-7",
            system=None,
            messages=[ChatMessage(role="user", content="hi")],
        )


# TC-U24 — token bucket raises on overflow
@pytest.mark.asyncio
async def test_token_bucket_raises_over_capacity(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    """Direct TokenBucket.acquire raises RateLimitedError past capacity."""
    b = TokenBucket(fake_redis, capacity=1, period_s=60)
    await b.acquire("provider:agent")
    with pytest.raises(RateLimitedError):
        await b.acquire("provider:agent")


# TC-F05 — every provider fails -> RouterExhaustedError
@pytest.mark.asyncio
async def test_router_exhausted(audit: _FakeLLMCallRepo, bucket: TokenBucket) -> None:
    """TC-F05: every configured provider failing raises RouterExhaustedError."""
    dgrid = _FakeProvider(name="dgrid", raise_times=99)
    anthropic = _FakeProvider(name="anthropic", raise_times=99)
    openai = _FakeProvider(name="openai", raise_times=99)
    google = _FakeProvider(name="google", raise_times=99)
    router = LLMRouter(
        dgrid=dgrid,  # type: ignore[arg-type]
        anthropic=anthropic,  # type: ignore[arg-type]
        openai=openai,  # type: ignore[arg-type]
        google=google,  # type: ignore[arg-type]
        bucket=bucket,
        llm_log=audit,  # type: ignore[arg-type]
    )
    with pytest.raises(RouterExhaustedError):
        await router.chat(
            agent="risk",
            primary_model="anthropic/claude-opus-4-7",
            system=None,
            messages=[ChatMessage(role="user", content="hi")],
        )


# TC-U25 — prompt hash is deterministic
def test_prompt_hash_deterministic() -> None:
    """Same (system, messages) hashes identically; different system differs."""
    a = LLMRouter._hash_messages("sys", [ChatMessage(role="user", content="x")])
    b = LLMRouter._hash_messages("sys", [ChatMessage(role="user", content="x")])
    assert a == b
    c = LLMRouter._hash_messages("sys2", [ChatMessage(role="user", content="x")])
    assert a != c


# TC-U26 — success closes circuit
@pytest.mark.asyncio
async def test_circuit_resets_on_success(audit: _FakeLLMCallRepo, bucket: TokenBucket) -> None:
    """After DGrid recovers, consecutive_failures returns to 0."""
    dgrid = _FakeProvider(name="dgrid", raise_times=2)
    anthropic = _FakeProvider(name="anthropic", response_text="x")
    router = LLMRouter(
        dgrid=dgrid,  # type: ignore[arg-type]
        anthropic=anthropic,  # type: ignore[arg-type]
        openai=None,
        google=None,
        bucket=bucket,
        llm_log=audit,  # type: ignore[arg-type]
    )
    for _ in range(4):
        await router.chat(
            agent="risk",
            primary_model="anthropic/claude-opus-4-7",
            system=None,
            messages=[ChatMessage(role="user", content="go")],
        )
    assert router._dgrid_health.consecutive_failures == 0


# TC-U27 — provider-less router raises exhaustion immediately
@pytest.mark.asyncio
async def test_router_no_providers(audit: _FakeLLMCallRepo, bucket: TokenBucket) -> None:
    """Router with no providers at all raises RouterExhaustedError."""
    router = LLMRouter(
        dgrid=None,
        anthropic=None,
        openai=None,
        google=None,
        bucket=bucket,
        llm_log=audit,  # type: ignore[arg-type]
    )
    with pytest.raises(RouterExhaustedError):
        await router.chat(
            agent="x",
            primary_model="anthropic/claude-opus-4-7",
            system=None,
            messages=[ChatMessage(role="user", content="go")],
        )


# TC-U28 — cost is computed from pricing table
@pytest.mark.asyncio
async def test_cost_computed(audit: _FakeLLMCallRepo, bucket: TokenBucket) -> None:
    """cost_usd is computed from the pricing table and surfaced on LLMResponse."""
    dgrid = _FakeProvider(name="dgrid")
    router = LLMRouter(
        dgrid=dgrid,  # type: ignore[arg-type]
        anthropic=None,
        openai=None,
        google=None,
        bucket=bucket,
        llm_log=audit,  # type: ignore[arg-type]
    )
    resp = await router.chat(
        agent="risk",
        primary_model="anthropic/claude-opus-4-7",
        system=None,
        messages=[ChatMessage(role="user", content="hi")],
    )
    assert resp.cost_usd > 0
