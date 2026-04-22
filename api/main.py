"""FastAPI application factory and runtime entrypoint.

The API is consciously thin: it is a read-only projection over the findings
table plus a WebSocket tail of Redis Pub/Sub. Writes happen only inside the
agents. This keeps the attack surface minimal — an attacker compromising the
API cannot fabricate findings.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from agents.common.context import build_context
from agents.common.logging_config import configure_logging, get_logger
from agents.common.settings import get_settings
from api.routes import briefs, health, ws

log = get_logger("api")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate-limit by client IP (FR-203).

    Uses the Redis backend already in process state so limits survive process
    restarts. Window is one minute; capacity is ``api_rate_limit_per_minute``.
    """

    def __init__(self, app: FastAPI, *, capacity: int) -> None:
        """Install the middleware with the per-minute capacity."""
        super().__init__(app)
        self._capacity = capacity

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        """Increment the per-IP counter in Redis; reject with 429 on overflow.

        The counter window is one minute (EXPIRE is set on first INCR).
        Capacity is taken from settings so it can be tuned without a deploy.
        """
        redis = request.app.state.redis
        ip = request.client.host if request.client else "unknown"
        key = f"api_rl:{ip}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        if count > self._capacity:
            return Response(content='{"detail":"rate limit exceeded"}', status_code=429,
                            media_type="application/json")
        return await call_next(request)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the ``Context`` on startup and tear it down on shutdown."""
    ctx = await build_context()
    app.state.ctx = ctx
    app.state.redis = ctx.redis
    app.state.findings = ctx.findings
    app.state.heartbeats = ctx.heartbeats
    app.state.anchor = ctx.anchor
    log.info("api_started")
    try:
        yield
    finally:
        await ctx.aclose()
        log.info("api_stopped")


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    configure_logging()
    settings = get_settings()
    app = FastAPI(
        title="SwarmScout Public API",
        version="0.1.0",
        description=(
            "Read-only API over the SwarmScout findings database. Every brief is "
            "hash-anchored on BNB Testnet; clients can independently verify via "
            "the /briefs/{id}/verify endpoint."
        ),
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.public_dashboard_url, "http://localhost:3000"],
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    app.add_middleware(RateLimitMiddleware, capacity=settings.api_rate_limit_per_minute)

    app.include_router(briefs.router)
    app.include_router(health.router)
    app.include_router(ws.router)

    @app.get("/metrics")
    async def metrics() -> Response:
        """Prometheus scrape endpoint.

        Emits metrics from the default process-wide registry so that counters
        registered by imported modules (``AgentMetrics``, middleware timings,
        etc.) are included. A fresh ``CollectorRegistry`` would return the
        empty set.
        """
        return Response(
            content=generate_latest(REGISTRY),
            media_type=CONTENT_TYPE_LATEST,
        )

    return app


app = create_app()


def run() -> None:
    """Process entrypoint for ``python -m api.main``."""
    settings = get_settings()
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",  # noqa: S104 — containerised, externally fronted by nginx
        port=8000,
        log_config=None,
        reload=settings.env == "development",
    )


if __name__ == "__main__":
    run()
