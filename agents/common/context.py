"""Process-level wiring — builds the shared dependencies once per agent.

Keeps ``main`` modules in every agent thin: they just pick a subclass of
``BaseAgent`` and hand it a ``Context``.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import redis.asyncio as aioredis

from agents.common.bus import Bus
from agents.common.db import (
    Database,
    FindingsRepository,
    HeartbeatRepository,
    LLMCallRepository,
    SubscriptionRepository,
    build_engine,
)
from agents.common.llm_router import (
    AnthropicProvider,
    DGridProvider,
    GoogleProvider,
    LLMRouter,
    OpenAIProvider,
    TokenBucket,
)
from agents.common.on_chain import NullAnchor, OnChainAnchor
from agents.common.settings import Settings, get_settings


@dataclass
class Context:
    """All the shared dependencies an agent / API / bot needs at runtime."""

    settings: Settings
    bus: Bus
    db: Database
    findings: FindingsRepository
    llm_calls: LLMCallRepository
    subscriptions: SubscriptionRepository
    heartbeats: HeartbeatRepository
    router: LLMRouter
    anchor: OnChainAnchor | NullAnchor
    redis: aioredis.Redis

    async def aclose(self) -> None:
        """Close all pooled resources."""
        await self.bus.close()
        await self.db.dispose()


def _build_anchor(settings: Settings) -> OnChainAnchor | NullAnchor:
    """Instantiate the real anchor when a private key is configured, otherwise a null."""
    if settings.agent_wallet_private_key and settings.findings_registry_address != (
        "0x0000000000000000000000000000000000000000"
    ):
        return OnChainAnchor(
            rpc_url=settings.bnb_testnet_rpc_url,
            contract_address=settings.findings_registry_address,
            private_key=settings.agent_wallet_private_key,
            chain_id=settings.bnb_chain_id,
        )
    return NullAnchor()


def _build_router(
    settings: Settings,
    redis: aioredis.Redis,
    llm_calls: LLMCallRepository,
    http: httpx.AsyncClient | None = None,
) -> LLMRouter:
    """Construct an ``LLMRouter`` from settings — absent keys yield absent providers."""
    dgrid = (
        DGridProvider(settings.dgrid_base_url, settings.dgrid_api_key, http=http)
        if settings.dgrid_api_key
        else None
    )
    anthropic = (
        AnthropicProvider(settings.anthropic_api_key, http=http)
        if settings.anthropic_api_key
        else None
    )
    openai = OpenAIProvider(settings.openai_api_key, http=http) if settings.openai_api_key else None
    google = GoogleProvider(settings.google_api_key, http=http) if settings.google_api_key else None
    bucket = TokenBucket(redis, capacity=60, period_s=60)
    return LLMRouter(
        dgrid=dgrid,
        anthropic=anthropic,
        openai=openai,
        google=google,
        bucket=bucket,
        llm_log=llm_calls,
    )


async def build_context(*, settings: Settings | None = None) -> Context:
    """Build a process-wide ``Context``."""
    s = settings or get_settings()
    redis = aioredis.from_url(s.redis_url, decode_responses=True)
    bus = Bus(s.redis_url, client=redis)
    engine = build_engine(s.postgres_dsn)
    db = Database(engine)
    findings = FindingsRepository(db)
    llm_calls = LLMCallRepository(db)
    subscriptions = SubscriptionRepository(db)
    heartbeats = HeartbeatRepository(db)
    anchor = _build_anchor(s)
    router = _build_router(s, redis, llm_calls)
    return Context(
        settings=s,
        bus=bus,
        db=db,
        findings=findings,
        llm_calls=llm_calls,
        subscriptions=subscriptions,
        heartbeats=heartbeats,
        router=router,
        anchor=anchor,
        redis=redis,
    )
