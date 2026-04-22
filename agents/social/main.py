"""Social agent.

Consumes ``TokenCandidate`` envelopes from ``stream:candidates``, scrapes
X (search) and public Telegram channels for mentions of the token's
``symbol`` and ``name``, computes an organic-vs-botty score, and emits a
``SocialScore`` on ``stream:social``.

The scrapers are Playwright-driven and have a graceful-degradation path:
if either platform blocks us, ``data_quality`` is flipped to ``degraded``
and the empty-arm of the scrape is surfaced in ``red_flags``.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from agents.common.base_agent import BaseAgent
from agents.common.bus import BusMessage
from agents.common.context import Context, build_context
from agents.common.llm_router import ChatMessage, RouterExhaustedError
from agents.common.logging_config import configure_logging
from agents.common.schemas.envelope import AgentName, Envelope, StreamName
from agents.common.schemas.payloads import DataQuality, SocialScore, TokenCandidate
from agents.social.scrapers.telegram_scraper import TelegramScraper
from agents.social.scrapers.x_scraper import XScraper

SOCIAL_GROUP = "social:primary"
CONSUMER_NAME = "social-1"


@dataclass(frozen=True)
class ScrapeBundle:
    """Aggregated scrape output passed to the LLM for scoring."""

    x_mentions: int
    x_samples: list[str]
    x_degraded: bool
    tg_mentions: int
    tg_samples: list[str]
    tg_degraded: bool


class SocialAgent(BaseAgent):
    """Consume candidates; emit SocialScore."""

    agent_name = AgentName.SOCIAL
    output_stream = StreamName.SOCIAL

    def __init__(
        self,
        *,
        ctx: Context,
        x_scraper: XScraper,
        telegram_scraper: TelegramScraper,
    ) -> None:
        """Build a SocialAgent.

        Args:
            ctx: Shared context (bus, db, anchor, router).
            x_scraper: Playwright-driven X search adapter.
            telegram_scraper: Playwright-driven Telegram public-preview adapter.
        """
        super().__init__(
            bus=ctx.bus,
            findings=ctx.findings,
            heartbeats=ctx.heartbeats,
            anchor=ctx.anchor,
        )
        self._ctx = ctx
        self._x = x_scraper
        self._tg = telegram_scraper
        self.primary_model = ctx.settings.social_primary_model

    async def handle(self, msg: BusMessage | None) -> None:
        """Not used — ``_main_loop`` below consumes directly."""
        return None

    async def _main_loop(self) -> None:
        """Consume stream:candidates and emit SocialScore per TokenCandidate."""
        async for msg in self.bus.consume(
            stream=StreamName.CANDIDATES,
            group=SOCIAL_GROUP,
            consumer=CONSUMER_NAME,
        ):
            if self._stop_event.is_set():
                break
            try:
                await self._process(msg.envelope)
                await self.bus.ack(StreamName.CANDIDATES, SOCIAL_GROUP, msg.entry_id)
                self.metrics.events_processed.inc()
                self._events_in_window += 1
            except Exception:  # noqa: BLE001
                self.metrics.events_failed.inc()
                self.log.exception("social_process_failed", entry_id=msg.entry_id)

    async def _process(self, env: Envelope) -> None:
        """Validate the incoming TokenCandidate, scrape + score, publish."""
        candidate = TokenCandidate.model_validate(env.payload)
        bundle = await self._gather(candidate)
        score, model = await self._score(candidate, bundle)
        await self.anchor_and_publish(
            payload=score,
            upstream_ids=[env.msg_id],
            model_used=model,
        )

    async def _gather(self, c: TokenCandidate) -> ScrapeBundle:
        """Run the X and Telegram scrapers in parallel."""
        x_task = asyncio.create_task(self._x.search(query=f"${c.token_symbol} {c.token_name}"))
        tg_task = asyncio.create_task(self._tg.search(query=c.token_symbol))
        x_result = await x_task
        tg_result = await tg_task
        return ScrapeBundle(
            x_mentions=x_result.mention_count,
            x_samples=x_result.sample_snippets[:5],
            x_degraded=x_result.degraded,
            tg_mentions=tg_result.mention_count,
            tg_samples=tg_result.sample_snippets[:5],
            tg_degraded=tg_result.degraded,
        )

    async def _score(
        self,
        c: TokenCandidate,
        bundle: ScrapeBundle,
    ) -> tuple[SocialScore, str | None]:
        """Produce a scored ``SocialScore`` from the scrape bundle.

        Uses the LLM router to classify organic-vs-botty; on router
        exhaustion, produces a degraded zero-score with an explanatory red
        flag.
        """
        quality = (
            DataQuality.DEGRADED if (bundle.x_degraded or bundle.tg_degraded) else DataQuality.OK
        )
        red_flags: list[str] = []
        if bundle.x_degraded:
            red_flags.append("x_scrape_blocked")
        if bundle.tg_degraded:
            red_flags.append("telegram_scrape_blocked")

        try:
            system = (
                "You are a crypto-social classifier. Given sample snippets about a token, "
                "estimate: organic_score (0-100, where 100 = entirely organic human chatter, "
                "0 = entirely bot shilling), sentiment (-1 to 1), influencer_mentions (array of "
                "@handles with more than 10k followers), additional red_flags (array of strings "
                "such as 'copy-paste-shilling', 'bot-networks', 'paid-promotion-disclosure'). "
                "Return strict JSON only; no prose."
            )
            user = json.dumps(
                {
                    "token_name": c.token_name,
                    "token_symbol": c.token_symbol,
                    "x_samples": bundle.x_samples,
                    "tg_samples": bundle.tg_samples,
                    "x_mentions": bundle.x_mentions,
                    "tg_mentions": bundle.tg_mentions,
                }
            )
            resp = await self._ctx.router.chat(
                agent=self.agent_name.value,
                primary_model=self.primary_model,
                system=system,
                messages=[ChatMessage(role="user", content=user)],
                max_tokens=512,
                temperature=0.1,
            )
            try:
                data = json.loads(_strip_fences(resp.content))
            except json.JSONDecodeError:
                data = {}
            organic = int(data.get("organic_score", 0))
            organic = max(0, min(100, organic))
            sentiment = float(data.get("sentiment", 0.0))
            sentiment = max(-1.0, min(1.0, sentiment))
            influencers = [str(x) for x in data.get("influencer_mentions", []) or []]
            for flag in data.get("red_flags", []) or []:
                red_flags.append(str(flag))
            model_used = f"{resp.provider}/{resp.model.split('/', 1)[-1]}"
        except RouterExhaustedError:
            organic = 0
            sentiment = 0.0
            influencers = []
            red_flags.append("social_llm_exhausted")
            quality = DataQuality.DEGRADED
            model_used = None

        score = SocialScore(
            token_address=c.token_address,
            organic_score=organic,
            mentions_24h=bundle.x_mentions + bundle.tg_mentions,
            sentiment=sentiment,
            red_flags=red_flags,
            influencer_mentions=influencers,
            data_quality=quality,
        )
        return score, model_used


def _strip_fences(text: str) -> str:
    """Strip ``` fences from an LLM JSON response, if present."""
    t = text.strip()
    if t.startswith("```"):
        first_newline = t.find("\n")
        if first_newline != -1:
            t = t[first_newline + 1 :]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


async def _amain() -> None:
    """Async process entrypoint for the Social agent.

    Starts both Playwright contexts, runs the agent, tears down cleanly.
    """
    configure_logging()
    ctx = await build_context()
    x = XScraper(ctx.settings)
    tg = TelegramScraper(ctx.settings)
    await x.start()
    await tg.start()
    agent = SocialAgent(ctx=ctx, x_scraper=x, telegram_scraper=tg)
    try:
        await agent.run()
    finally:
        await x.stop()
        await tg.stop()
        await ctx.aclose()


def run() -> None:
    """Process entrypoint."""
    asyncio.run(_amain())


if __name__ == "__main__":
    run()
