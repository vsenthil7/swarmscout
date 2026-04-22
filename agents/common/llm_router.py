"""LLM router with DGrid primary and direct-provider fallback chains.

Every LLM call in SwarmScout flows through this module. Responsibilities:

* Route to the DGrid AI Gateway first (FR-140) — OpenAI-compatible API.
* On repeated DGrid 5xx (>=3 consecutive), fall back to direct-provider APIs
  in the per-agent fallback chain (FR-141).
* Per-provider Redis-backed token buckets for rate limiting (FR-142).
* Log every attempt to the ``llm_calls`` table (FR-143).
* Exhaustion of all providers is reported as ``RouterExhaustedError`` — the
  caller decides whether to degrade (e.g. Risk agent sets ``requires_human_review``).

The router never decides business behaviour on exhaustion — that is the
agent's responsibility and keeps the router focused on transport.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
import redis.asyncio as aioredis
from tenacity import retry, stop_after_attempt, wait_exponential

from agents.common.db import LLMCallRepository
from agents.common.logging_config import get_logger

log = get_logger("llm_router")


# --------------------------------------------------------------------------- #
# Exceptions                                                                  #
# --------------------------------------------------------------------------- #


class LLMError(Exception):
    """Base exception for LLM router errors."""


class RateLimitedError(LLMError):
    """Raised when the Redis token bucket refused the call."""


class ProviderError(LLMError):
    """Raised when a single provider call failed."""


class RouterExhaustedError(LLMError):
    """Raised after every model in the fallback chain has failed."""


# --------------------------------------------------------------------------- #
# Data carriers                                                               #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ChatMessage:
    """One turn of a chat conversation."""

    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class LLMResponse:
    """Result of a successful call."""

    provider: str
    model: str
    content: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int


# Approximate prices per 1K tokens (USD). Values drift — we keep them
# conservative and configurable via the ``pricing`` constructor argument.
DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "anthropic/claude-opus-4-7": (15.00, 75.00),
    "anthropic/claude-sonnet-4-6": (3.00, 15.00),
    "anthropic/claude-haiku-4-5": (0.80, 4.00),
    "openai/gpt-4o": (2.50, 10.00),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "google/gemini-2.5-pro": (1.25, 5.00),
    "google/gemini-2.5-flash": (0.075, 0.30),
}


def _cost_usd(
    model: str, input_tokens: int, output_tokens: int, pricing: dict[str, tuple[float, float]]
) -> float:
    """Approximate dollar cost for this call."""
    price_in, price_out = pricing.get(model, (0.0, 0.0))
    return (input_tokens / 1000.0) * price_in + (output_tokens / 1000.0) * price_out


# --------------------------------------------------------------------------- #
# Rate limit                                                                  #
# --------------------------------------------------------------------------- #


class TokenBucket:
    """Fixed-window token bucket backed by Redis INCR + EXPIRE.

    Simpler than a sliding-window leaky bucket but good enough for the
    per-minute scales we hit here; the window resets every ``period_s``.
    """

    def __init__(self, redis: aioredis.Redis, *, capacity: int, period_s: int) -> None:
        """Store pricing / circuit / provider references on the router instance."""
        self._redis = redis
        self._capacity = capacity
        self._period_s = period_s

    async def acquire(self, key: str) -> None:
        """Consume one token for ``key`` or raise ``RateLimitedError``."""
        count = await self._redis.incr(f"rl:{key}")
        if count == 1:
            await self._redis.expire(f"rl:{key}", self._period_s)
        if count > self._capacity:
            raise RateLimitedError(f"rate-limited for {key} (>{self._capacity}/{self._period_s}s)")


# --------------------------------------------------------------------------- #
# Provider clients                                                            #
# --------------------------------------------------------------------------- #


class ProviderClient(Protocol):
    """Protocol every concrete provider implements."""

    name: str

    async def chat(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Issue a chat request and return a normalised response."""
        ...


class _HTTPProvider:
    """Base HTTP client with retries and simple response parsing."""

    name: str = "base"

    def __init__(self, base_url: str, api_key: str, http: httpx.AsyncClient | None = None) -> None:
        """Store pricing / circuit / provider references on the router instance."""
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._http = http or httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.5, max=4))
    async def _post(
        self, path: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> httpx.Response:
        """POST helper shared by every _HTTPProvider.

        Retries on transient failures with exponential backoff (tenacity)
        before giving up to the caller. The retry policy is deliberately
        short: 3 attempts, 0.5-4 s, because the router itself will fall
        over to another provider if this one fails.
        """
        resp = await self._http.post(f"{self._base}{path}", json=payload, headers=headers)
        resp.raise_for_status()
        return resp


class DGridProvider(_HTTPProvider):
    """DGrid AI Gateway (OpenAI-compatible wire format)."""

    name = "dgrid"

    async def chat(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Call DGrid /chat/completions."""
        start = time.perf_counter()
        body: dict[str, Any] = {
            "model": model,
            "messages": (
                ([{"role": "system", "content": system}] if system else [])
                + [{"role": m.role, "content": m.content} for m in messages]
            ),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        resp = await self._post("/chat/completions", body, headers)
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        latency_ms = int((time.perf_counter() - start) * 1000)
        return LLMResponse(
            provider="dgrid",
            model=model,
            content=content,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            cost_usd=0.0,
            latency_ms=latency_ms,
        )


class AnthropicProvider(_HTTPProvider):
    """Direct Anthropic Messages API."""

    name = "anthropic"

    def __init__(self, api_key: str, http: httpx.AsyncClient | None = None) -> None:
        """Store pricing / circuit / provider references on the router instance."""
        super().__init__("https://api.anthropic.com/v1", api_key, http)

    async def chat(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Call POST /messages; strip the ``anthropic/`` prefix from model."""
        raw_model = model.split("/", 1)[-1]
        start = time.perf_counter()
        body: dict[str, Any] = {
            "model": raw_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            body["system"] = system
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        resp = await self._post("/messages", body, headers)
        data = resp.json()
        parts = data.get("content", [])
        content = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        usage = data.get("usage", {})
        latency_ms = int((time.perf_counter() - start) * 1000)
        return LLMResponse(
            provider="anthropic",
            model=model,
            content=content,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cost_usd=0.0,
            latency_ms=latency_ms,
        )


class OpenAIProvider(_HTTPProvider):
    """Direct OpenAI /v1/chat/completions."""

    name = "openai"

    def __init__(self, api_key: str, http: httpx.AsyncClient | None = None) -> None:
        """Store pricing / circuit / provider references on the router instance."""
        super().__init__("https://api.openai.com/v1", api_key, http)

    async def chat(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Call POST /chat/completions."""
        raw_model = model.split("/", 1)[-1]
        start = time.perf_counter()
        body: dict[str, Any] = {
            "model": raw_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": (
                ([{"role": "system", "content": system}] if system else [])
                + [{"role": m.role, "content": m.content} for m in messages]
            ),
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        resp = await self._post("/chat/completions", body, headers)
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        latency_ms = int((time.perf_counter() - start) * 1000)
        return LLMResponse(
            provider="openai",
            model=model,
            content=content,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            cost_usd=0.0,
            latency_ms=latency_ms,
        )


class GoogleProvider(_HTTPProvider):
    """Direct Google Generative Language API."""

    name = "google"

    def __init__(self, api_key: str, http: httpx.AsyncClient | None = None) -> None:
        """Store pricing / circuit / provider references on the router instance."""
        super().__init__("https://generativelanguage.googleapis.com/v1beta", api_key, http)

    async def chat(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[ChatMessage],
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Call Gemini's generateContent endpoint."""
        raw_model = model.split("/", 1)[-1]
        start = time.perf_counter()
        contents: list[dict[str, Any]] = []
        if system:
            contents.append({"role": "user", "parts": [{"text": f"System: {system}"}]})
        for m in messages:
            contents.append(
                {"role": "user" if m.role == "user" else "model", "parts": [{"text": m.content}]}
            )
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        resp = await self._post(
            f"/models/{raw_model}:generateContent?key={self._api_key}",
            body,
            {"Content-Type": "application/json"},
        )
        data = resp.json()
        candidate = (data.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        content = "".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata", {})
        latency_ms = int((time.perf_counter() - start) * 1000)
        return LLMResponse(
            provider="google",
            model=model,
            content=content,
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
            cost_usd=0.0,
            latency_ms=latency_ms,
        )


# --------------------------------------------------------------------------- #
# Fallback chain configuration                                                #
# --------------------------------------------------------------------------- #


DEFAULT_FALLBACK_CHAINS: dict[str, list[str]] = {
    # Keyed by primary model; value is the ordered direct-provider fallback list.
    "google/gemini-2.5-flash": ["anthropic/claude-haiku-4-5", "openai/gpt-4o-mini"],
    "openai/gpt-4o": ["anthropic/claude-sonnet-4-6", "google/gemini-2.5-pro"],
    "anthropic/claude-sonnet-4-6": ["openai/gpt-4o", "google/gemini-2.5-pro"],
    "anthropic/claude-opus-4-7": ["openai/gpt-4o", "google/gemini-2.5-pro"],
}


# --------------------------------------------------------------------------- #
# Router                                                                      #
# --------------------------------------------------------------------------- #


@dataclass
class _DGridHealth:
    """Rolling count of consecutive 5xx from DGrid."""

    consecutive_failures: int = 0
    last_recovery: float = field(default_factory=time.monotonic)


class LLMRouter:
    """Route chat calls across DGrid + direct providers with fallback."""

    DGRID_CIRCUIT_TRIP_THRESHOLD = 3
    DGRID_CIRCUIT_COOLDOWN_S = 60

    def __init__(
        self,
        *,
        dgrid: DGridProvider | None,
        anthropic: AnthropicProvider | None,
        openai: OpenAIProvider | None,
        google: GoogleProvider | None,
        bucket: TokenBucket,
        llm_log: LLMCallRepository,
        pricing: dict[str, tuple[float, float]] | None = None,
        fallback_chains: dict[str, list[str]] | None = None,
    ) -> None:
        """Store pricing / circuit / provider references on the router instance."""
        self._dgrid = dgrid
        self._providers: dict[str, ProviderClient] = {}
        if anthropic is not None:
            self._providers["anthropic"] = anthropic
        if openai is not None:
            self._providers["openai"] = openai
        if google is not None:
            self._providers["google"] = google
        self._bucket = bucket
        self._log = llm_log
        self._pricing = pricing or DEFAULT_PRICING
        self._chains = fallback_chains or DEFAULT_FALLBACK_CHAINS
        self._dgrid_health = _DGridHealth()
        self._dgrid_lock = asyncio.Lock()

    async def chat(
        self,
        *,
        agent: str,
        primary_model: str,
        system: str | None,
        messages: list[ChatMessage],
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Execute a chat call and return the response.

        Raises:
            RouterExhaustedError: Every candidate model failed.
        """
        chain = [primary_model, *self._chains.get(primary_model, [])]
        prompt_hash = self._hash_messages(system, messages)
        last_error: Exception | None = None

        # First pass: DGrid on the primary model (if DGrid is configured and healthy).
        if self._dgrid is not None and self._dgrid_available():
            try:
                resp = await self._call_provider(
                    provider=self._dgrid,
                    agent=agent,
                    model=primary_model,
                    system=system,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    prompt_hash=prompt_hash,
                )
                self._note_dgrid_success()
                return resp
            except ProviderError as err:
                self._note_dgrid_failure()
                last_error = err
                log.warning("dgrid_failed", model=primary_model, err=str(err))

        # Direct-provider fallback chain.
        for model in chain:
            provider_name = model.split("/", 1)[0]
            provider = self._providers.get(provider_name)
            if provider is None:
                last_error = ProviderError(f"no direct client configured for {provider_name!r}")
                continue
            try:
                return await self._call_provider(
                    provider=provider,
                    agent=agent,
                    model=model,
                    system=system,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    prompt_hash=prompt_hash,
                )
            except (ProviderError, RateLimitedError) as err:
                last_error = err
                log.warning("provider_failed", provider=provider_name, model=model, err=str(err))

        raise RouterExhaustedError(
            f"all providers failed for {primary_model!r}: {last_error}"
        ) from last_error

    async def _call_provider(
        self,
        *,
        provider: ProviderClient,
        agent: str,
        model: str,
        system: str | None,
        messages: list[ChatMessage],
        max_tokens: int,
        temperature: float,
        prompt_hash: str,
    ) -> LLMResponse:
        """Invoke one provider with rate-limiting and audit logging."""
        await self._bucket.acquire(f"{provider.name}:{agent}")
        start = time.perf_counter()
        try:
            resp = await provider.chat(
                model=model,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except httpx.HTTPStatusError as err:
            latency_ms = int((time.perf_counter() - start) * 1000)
            await self._log.log(
                agent=agent,
                provider=provider.name,
                model=model,
                prompt_hash=prompt_hash,
                response_hash=None,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=latency_ms,
                success=False,
                error_class=type(err).__name__,
            )
            raise ProviderError(str(err)) from err
        except httpx.RequestError as err:
            latency_ms = int((time.perf_counter() - start) * 1000)
            await self._log.log(
                agent=agent,
                provider=provider.name,
                model=model,
                prompt_hash=prompt_hash,
                response_hash=None,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=latency_ms,
                success=False,
                error_class=type(err).__name__,
            )
            raise ProviderError(str(err)) from err

        cost = _cost_usd(model, resp.input_tokens, resp.output_tokens, self._pricing)
        resp = LLMResponse(
            provider=resp.provider,
            model=resp.model,
            content=resp.content,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_usd=cost,
            latency_ms=resp.latency_ms,
        )
        await self._log.log(
            agent=agent,
            provider=resp.provider,
            model=resp.model,
            prompt_hash=prompt_hash,
            response_hash=hashlib.sha256(resp.content.encode("utf-8")).hexdigest(),
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_usd=cost,
            latency_ms=resp.latency_ms,
            success=True,
        )
        return resp

    def _dgrid_available(self) -> bool:
        """Return True unless the DGrid circuit is tripped."""
        if self._dgrid_health.consecutive_failures < self.DGRID_CIRCUIT_TRIP_THRESHOLD:
            return True
        elapsed = time.monotonic() - self._dgrid_health.last_recovery
        return elapsed > self.DGRID_CIRCUIT_COOLDOWN_S

    def _note_dgrid_failure(self) -> None:
        """Increment the DGrid consecutive-failure counter.

        When the threshold is hit, stamp the cooldown start so the circuit
        stays open for ``DGRID_CIRCUIT_COOLDOWN_S`` seconds.
        """
        self._dgrid_health.consecutive_failures += 1
        if self._dgrid_health.consecutive_failures == self.DGRID_CIRCUIT_TRIP_THRESHOLD:
            self._dgrid_health.last_recovery = time.monotonic()
            log.warning("dgrid_circuit_open")

    def _note_dgrid_success(self) -> None:
        """Reset the DGrid failure counter to zero.

        Called on every successful DGrid response — returns the circuit
        to its closed / healthy state.
        """
        if self._dgrid_health.consecutive_failures > 0:
            log.info("dgrid_circuit_closed")
        self._dgrid_health.consecutive_failures = 0

    @staticmethod
    def _hash_messages(system: str | None, messages: list[ChatMessage]) -> str:
        """Deterministic hash of the prompt for audit logging."""
        hasher = hashlib.sha256()
        if system:
            hasher.update(b"system\x00")
            hasher.update(system.encode("utf-8"))
            hasher.update(b"\x00")
        for m in messages:
            hasher.update(m.role.encode("utf-8"))
            hasher.update(b"\x00")
            hasher.update(m.content.encode("utf-8"))
            hasher.update(b"\x00")
        return hasher.hexdigest()
