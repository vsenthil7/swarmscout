"""Hunter agent entrypoint.

Picks a source at runtime based on ``FOURMEME_SOURCE`` (``polling`` or
``rpc_log``), then for every raw event produces a ``TokenCandidate``
envelope on ``stream:candidates``.

Hunter is a *root* agent — it has no upstream. Its ``upstream_ids`` list is
always empty.
"""

from __future__ import annotations

import asyncio

from agents.common.base_agent import BaseAgent
from agents.common.bus import BusMessage
from agents.common.context import Context, build_context
from agents.common.logging_config import configure_logging
from agents.common.schemas.envelope import AgentName, StreamName
from agents.common.schemas.payloads import TokenCandidate
from agents.hunter.sources.base import FourMemeSource, RawTokenEvent
from agents.hunter.sources.polling import FourMemePollingSource
from agents.hunter.sources.rpc_log import (
    FOURMEME_FACTORY_ADDRESS,
    TOKEN_CREATED_TOPIC,
    FourMemeRPCLogSource,
)


class HunterAgent(BaseAgent):
    """Root agent — turns raw Four.meme events into ``TokenCandidate`` envelopes."""

    agent_name = AgentName.HUNTER
    output_stream = StreamName.CANDIDATES

    def __init__(self, *, ctx: Context, source: FourMemeSource) -> None:
        """Initialise HunterAgent with its Context and chosen source adapter."""
        super().__init__(
            bus=ctx.bus,
            findings=ctx.findings,
            heartbeats=ctx.heartbeats,
            anchor=ctx.anchor,
        )
        self.primary_model = ctx.settings.hunter_primary_model
        self._source = source
        self._ctx = ctx

    async def handle(self, msg: BusMessage | None) -> None:
        """Root agents do not consume from a bus stream — ``_main_loop`` overrides this."""
        return None

    async def _main_loop(self) -> None:
        """Iterate source events and emit ``TokenCandidate`` envelopes."""
        async for raw in self._source.events():
            if self._stop_event.is_set():
                break
            candidate = self._to_candidate(raw)
            await self.anchor_and_publish(payload=candidate, model_used=None)
            self.metrics.events_processed.inc()
            self._events_in_window += 1

    @staticmethod
    def _to_candidate(raw: RawTokenEvent) -> TokenCandidate:
        """Map a raw source event onto the ``TokenCandidate`` schema."""
        return TokenCandidate(
            token_address=raw.token_address,
            launch_timestamp=raw.launch_timestamp or _now_iso(),
            creator_address=raw.creator_address,
            token_name=raw.token_name or "unknown",
            token_symbol=raw.token_symbol or "?",
            initial_liquidity_usd=raw.initial_liquidity_usd,
            source_url=raw.source_url or "https://four.meme",
        )


def _now_iso() -> str:
    """ISO-8601 UTC for cases where the source didn't supply a timestamp."""
    from datetime import UTC, datetime

    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_source(ctx: Context) -> FourMemeSource:
    """Instantiate the source selected by settings."""
    mode = ctx.settings.fourmeme_source.lower().strip()
    if mode == "rpc_log":
        return FourMemeRPCLogSource(
            rpc_url=ctx.settings.bnb_testnet_rpc_url,
            factory_address=FOURMEME_FACTORY_ADDRESS,
            topic=TOKEN_CREATED_TOPIC,
            redis=ctx.redis,
        )
    return FourMemePollingSource(
        url=ctx.settings.fourmeme_poll_url,
        interval_seconds=ctx.settings.fourmeme_poll_interval_seconds,
        redis=ctx.redis,
    )


async def _amain() -> None:
    """Async entrypoint — built so it can be awaited by tests."""
    configure_logging()
    ctx = await build_context()
    source = _build_source(ctx)
    agent = HunterAgent(ctx=ctx, source=source)
    try:
        await agent.run()
    finally:
        await ctx.aclose()


def run() -> None:
    """Process entrypoint for ``python -m agents.hunter.main``."""
    asyncio.run(_amain())


if __name__ == "__main__":
    run()
