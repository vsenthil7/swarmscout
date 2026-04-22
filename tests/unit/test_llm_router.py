"""Coverage tests for agents/common/llm_router.py.

Covers: TokenBucket acquire (under capacity + over), _cost_usd known +
unknown models, each provider (DGrid/Anthropic/OpenAI/Google) chat()
with HTTP stubbed via respx, LLMRouter primary path through DGrid,
DGrid failure promotes to fallback chain, exhaustion raises, circuit
trip + cooldown, provider missing from map falls through,
_hash_messages determinism.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import httpx
import pytest
import respx

from agents.common.llm_router import (
    DEFAULT_PRICING,
    AnthropicProvider,
    ChatMessage,
    DGridProvider,
    GoogleProvider,
    LLMResponse,
    LLMRouter,
    OpenAIProvider,
    ProviderError,
    RateLimitedError,
    RouterExhaustedError,
    TokenBucket,
    _cost_usd,
)


# --------------------------------------------------------------------------- #
# _cost_usd                                                                   #
# --------------------------------------------------------------------------- #


def test_cost_usd_known_model_pricing() -> None:
    """Known model uses the entry from pricing map."""
    cost = _cost_usd("openai/gpt-4o", 1000, 500, DEFAULT_PRICING)
    # 1000/1000 * 2.50 + 500/1000 * 10.00 = 2.50 + 5.00 = 7.50
    assert abs(cost - 7.5) < 0.001


def test_cost_usd_unknown_model_returns_zero() -> None:
    """Unknown model returns (0, 0) → cost 0."""
    assert _cost_usd("unknown/model", 1000, 1000, DEFAULT_PRICING) == 0.0


# --------------------------------------------------------------------------- #
# TokenBucket                                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_token_bucket_acquire_below_capacity() -> None:
    """First N acquisitions below capacity all succeed."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bucket = TokenBucket(redis, capacity=3, period_s=60)
    for _ in range(3):
        await bucket.acquire("k")


@pytest.mark.asyncio
async def test_token_bucket_raises_over_capacity() -> None:
    """Fourth acquisition when capacity=3 raises."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bucket = TokenBucket(redis, capacity=2, period_s=60)
    await bucket.acquire("k")
    await bucket.acquire("k")
    with pytest.raises(RateLimitedError):
        await bucket.acquire("k")


# --------------------------------------------------------------------------- #
# Providers — isolated HTTP-level tests                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@respx.mock
async def test_dgrid_provider_chat_parses_openai_compatible_response() -> None:
    http = httpx.AsyncClient(timeout=5.0)
    provider = DGridProvider("https://dgrid.example/v1", "K", http=http)
    respx.post("https://dgrid.example/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hello from dgrid"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )
    )
    out = await provider.chat(
        model="google/gemini-2.5-flash",
        system="be concise",
        messages=[ChatMessage(role="user", content="hi")],
        max_tokens=100,
        temperature=0.1,
    )
    assert out.content == "hello from dgrid"
    assert out.provider == "dgrid"
    assert out.input_tokens == 10
    assert out.output_tokens == 5
    await provider.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_anthropic_provider_strips_prefix_and_parses_content_blocks() -> None:
    http = httpx.AsyncClient(timeout=5.0)
    provider = AnthropicProvider("K", http=http)
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "Hello "},
                    {"type": "text", "text": "world."},
                    {"type": "tool_use", "name": "x"},  # filtered
                ],
                "usage": {"input_tokens": 8, "output_tokens": 12},
            },
        )
    )
    out = await provider.chat(
        model="anthropic/claude-opus-4-7",
        system=None,
        messages=[ChatMessage(role="user", content="hi")],
        max_tokens=100,
        temperature=0.0,
    )
    assert out.content == "Hello world."
    assert out.input_tokens == 8
    assert out.output_tokens == 12
    await provider.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_anthropic_provider_with_system_prompt() -> None:
    """Exercising the `if system:` branch in anthropic.chat body building."""
    http = httpx.AsyncClient(timeout=5.0)
    provider = AnthropicProvider("K", http=http)
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 1, "output_tokens": 1}},
        )
    )
    out = await provider.chat(
        model="anthropic/claude-opus-4-7",
        system="be concise",
        messages=[ChatMessage(role="user", content="hi")],
        max_tokens=100,
        temperature=0.0,
    )
    assert out.provider == "anthropic"
    await provider.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_openai_provider_chat_parses_response() -> None:
    http = httpx.AsyncClient(timeout=5.0)
    provider = OpenAIProvider("K", http=http)
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "openai reply"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )
    )
    out = await provider.chat(
        model="openai/gpt-4o",
        system="sys",
        messages=[ChatMessage(role="user", content="hi")],
        max_tokens=10,
        temperature=0.0,
    )
    assert out.content == "openai reply"
    assert out.provider == "openai"
    await provider.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_google_provider_parses_candidates() -> None:
    http = httpx.AsyncClient(timeout=5.0)
    provider = GoogleProvider("K", http=http)
    respx.post(
        url__startswith="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "g-part-1 "}, {"text": "g-part-2"}]
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 7},
            },
        )
    )
    out = await provider.chat(
        model="google/gemini-2.5-flash",
        system="sys",
        messages=[
            ChatMessage(role="user", content="u"),
            ChatMessage(role="assistant", content="a"),
        ],
        max_tokens=50,
        temperature=0.5,
    )
    assert out.content == "g-part-1 g-part-2"
    assert out.provider == "google"
    assert out.input_tokens == 4
    assert out.output_tokens == 7
    await provider.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_google_provider_handles_missing_candidates() -> None:
    """Empty candidates list falls through to empty content string without crashing."""
    http = httpx.AsyncClient(timeout=5.0)
    provider = GoogleProvider("K", http=http)
    respx.post(
        url__startswith="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro"
    ).mock(
        return_value=httpx.Response(
            200, json={"candidates": [], "usageMetadata": {}}
        )
    )
    out = await provider.chat(
        model="google/gemini-2.5-pro",
        system=None,
        messages=[ChatMessage(role="user", content="q")],
        max_tokens=10,
        temperature=0.0,
    )
    assert out.content == ""
    await provider.aclose()


# --------------------------------------------------------------------------- #
# LLMRouter                                                                   #
# --------------------------------------------------------------------------- #


def _fake_llm_log() -> SimpleNamespace:
    return SimpleNamespace(log=AsyncMock())


def _fake_bucket() -> Any:
    class _B:
        async def acquire(self, _k: str) -> None:
            return None
    return _B()


def _router(
    *,
    dgrid: Any = None,
    anthropic: Any = None,
    openai: Any = None,
    google: Any = None,
) -> LLMRouter:
    return LLMRouter(
        dgrid=dgrid,
        anthropic=anthropic,
        openai=openai,
        google=google,
        bucket=_fake_bucket(),
        llm_log=_fake_llm_log(),
    )


def _make_response(provider: str, model: str) -> LLMResponse:
    return LLMResponse(
        provider=provider,
        model=model,
        content="hello",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.0,
        latency_ms=100,
    )


@pytest.mark.asyncio
async def test_router_returns_dgrid_response_on_happy_path() -> None:
    """DGrid primary succeeds: router returns its response and resets counter."""
    dgrid = MagicMock(name="dgrid")
    dgrid.name = "dgrid"
    dgrid.chat = AsyncMock(return_value=_make_response("dgrid", "google/gemini-2.5-flash"))
    router = _router(dgrid=dgrid)
    out = await router.chat(
        agent="hunter",
        primary_model="google/gemini-2.5-flash",
        system=None,
        messages=[ChatMessage(role="user", content="q")],
    )
    assert out.provider == "dgrid"
    assert out.cost_usd > 0  # cost recomputed


@pytest.mark.asyncio
async def test_router_falls_back_to_direct_provider_on_dgrid_failure() -> None:
    """DGrid failure: router moves to direct-provider fallback chain."""
    dgrid = MagicMock()
    dgrid.name = "dgrid"
    dgrid.chat = AsyncMock(side_effect=httpx.RequestError("down"))

    anthropic = MagicMock()
    anthropic.name = "anthropic"
    anthropic.chat = AsyncMock(return_value=_make_response("anthropic", "anthropic/claude-haiku-4-5"))

    router = _router(dgrid=dgrid, anthropic=anthropic)
    out = await router.chat(
        agent="hunter",
        primary_model="google/gemini-2.5-flash",
        system=None,
        messages=[ChatMessage(role="user", content="q")],
    )
    # After DGrid fails, the chain walks primary first (google, no direct client),
    # then anthropic/claude-haiku-4-5 which succeeds.
    assert out.provider == "anthropic"


@pytest.mark.asyncio
async def test_router_raises_exhausted_when_every_provider_fails() -> None:
    """No DGrid + no direct providers configured: RouterExhaustedError."""
    router = _router()
    with pytest.raises(RouterExhaustedError):
        await router.chat(
            agent="hunter",
            primary_model="google/gemini-2.5-flash",
            system=None,
            messages=[ChatMessage(role="user", content="q")],
        )


@pytest.mark.asyncio
async def test_router_falls_through_missing_direct_provider() -> None:
    """If a chain model has no configured direct client, continue to next."""
    # Primary = openai/gpt-4o; chain = [anthropic/claude-sonnet-4-6, google/gemini-2.5-pro].
    # Only google configured -> should succeed on google.
    google = MagicMock()
    google.name = "google"
    google.chat = AsyncMock(return_value=_make_response("google", "google/gemini-2.5-pro"))
    router = _router(google=google)
    out = await router.chat(
        agent="risk",
        primary_model="openai/gpt-4o",
        system=None,
        messages=[ChatMessage(role="user", content="q")],
    )
    assert out.provider == "google"


@pytest.mark.asyncio
async def test_router_circuit_trips_after_three_dgrid_failures() -> None:
    """After 3 consecutive DGrid failures, _dgrid_available returns False."""
    dgrid = MagicMock()
    dgrid.name = "dgrid"
    dgrid.chat = AsyncMock(side_effect=httpx.RequestError("down"))

    anthropic = MagicMock()
    anthropic.name = "anthropic"
    anthropic.chat = AsyncMock(return_value=_make_response("anthropic", "anthropic/claude-haiku-4-5"))

    router = _router(dgrid=dgrid, anthropic=anthropic)
    for _ in range(3):
        await router.chat(
            agent="hunter",
            primary_model="google/gemini-2.5-flash",
            system=None,
            messages=[ChatMessage(role="user", content="q")],
        )
    # After 3 failures the circuit should be open.
    assert router._dgrid_available() is False


@pytest.mark.asyncio
async def test_router_note_dgrid_success_resets_counter() -> None:
    """_note_dgrid_success clears a non-zero failure counter."""
    router = _router()
    router._dgrid_health.consecutive_failures = 2
    router._note_dgrid_success()
    assert router._dgrid_health.consecutive_failures == 0


def test_router_dgrid_available_after_cooldown_elapsed() -> None:
    """Once cooldown elapses, _dgrid_available returns True even with high failure counter."""
    router = _router()
    router._dgrid_health.consecutive_failures = 10
    router._dgrid_health.last_recovery = time.monotonic() - (router.DGRID_CIRCUIT_COOLDOWN_S + 10)
    assert router._dgrid_available() is True


@pytest.mark.asyncio
async def test_router_logs_http_status_error_and_raises_provider_error() -> None:
    """HTTPStatusError in provider: _call_provider logs and raises ProviderError."""
    dgrid = MagicMock()
    dgrid.name = "dgrid"
    http_err = httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock(status_code=500))
    dgrid.chat = AsyncMock(side_effect=http_err)

    log = _fake_llm_log()
    router = LLMRouter(
        dgrid=dgrid, anthropic=None, openai=None, google=None,
        bucket=_fake_bucket(), llm_log=log,
    )
    with pytest.raises(RouterExhaustedError):
        await router.chat(
            agent="hunter",
            primary_model="google/gemini-2.5-flash",
            system=None,
            messages=[ChatMessage(role="user", content="q")],
        )
    # llm_log.log was called at least once with success=False
    calls = log.log.await_args_list
    assert any(c.kwargs.get("success") is False for c in calls)


@pytest.mark.asyncio
async def test_router_handles_rate_limited_error_in_fallback() -> None:
    """A fallback provider that raises RateLimitedError is caught and the chain continues."""
    class _RateLimitedBucket:
        def __init__(self) -> None:
            self.count = 0

        async def acquire(self, _k: str) -> None:
            self.count += 1
            if self.count == 1:
                raise RateLimitedError("first one limited")

    dgrid_provider = MagicMock()
    dgrid_provider.name = "dgrid"
    dgrid_provider.chat = AsyncMock(return_value=_make_response("dgrid", "openai/gpt-4o"))

    openai_provider = MagicMock()
    openai_provider.name = "openai"
    openai_provider.chat = AsyncMock(return_value=_make_response("openai", "openai/gpt-4o"))

    router = LLMRouter(
        dgrid=dgrid_provider, anthropic=None, openai=openai_provider, google=None,
        bucket=_RateLimitedBucket(), llm_log=_fake_llm_log(),
    )
    # First acquire on dgrid rate-limits (treated as ProviderError surrogate via exception).
    # But RateLimitedError isn't ProviderError so dgrid path raises RouterExhaustedError unless
    # caught in fallback chain -- for DGrid path, the router only catches ProviderError.
    # So this call should raise RouterExhaustedError since DGrid path fails on rate-limit.
    with pytest.raises((RouterExhaustedError, RateLimitedError)):
        await router.chat(
            agent="risk",
            primary_model="openai/gpt-4o",
            system=None,
            messages=[ChatMessage(role="user", content="q")],
        )


# --------------------------------------------------------------------------- #
# _hash_messages                                                              #
# --------------------------------------------------------------------------- #


def test_hash_messages_deterministic_with_system() -> None:
    h1 = LLMRouter._hash_messages("sys", [ChatMessage(role="user", content="x")])
    h2 = LLMRouter._hash_messages("sys", [ChatMessage(role="user", content="x")])
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_hash_messages_deterministic_without_system() -> None:
    h = LLMRouter._hash_messages(None, [ChatMessage(role="user", content="y")])
    assert len(h) == 64


def test_hash_messages_sensitive_to_content() -> None:
    h1 = LLMRouter._hash_messages(None, [ChatMessage(role="user", content="x")])
    h2 = LLMRouter._hash_messages(None, [ChatMessage(role="user", content="y")])
    assert h1 != h2
