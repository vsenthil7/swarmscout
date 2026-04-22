"""Narrator agent.

Consumes ``RiskVerdict`` from ``stream:risk`` and produces either:

* An ``AlphaBrief`` on ``stream:briefs``, OR
* A ``HumanReviewRequest`` on ``stream:human_review`` when the Risk verdict
  flagged ``requires_human_review=True`` (FR-086).

The brief is narrated by an LLM from the full lineage (TokenCandidate +
SocialScore + ChainMetrics + RiskVerdict), pulled from Postgres so the
narrator has everything it needs to explain *why* the thesis looks the
way it does. ``model_attribution`` is the list of ``provider/model`` tags
observed anywhere in the upstream chain, plus the narrator's own call.
"""

from __future__ import annotations

import asyncio
import json

from agents.common.base_agent import BaseAgent
from agents.common.bus import BusMessage
from agents.common.context import Context, build_context
from agents.common.envelope_builder import build_envelope, now_iso
from agents.common.llm_router import ChatMessage, RouterExhaustedError
from agents.common.logging_config import configure_logging
from agents.common.schemas.envelope import AgentName, Envelope, StreamName
from agents.common.schemas.payloads import (
    AlphaBrief,
    ConvictionTier,
    DataQuality,
    HumanReviewRequest,
    RiskVerdict,
)

NARRATOR_GROUP = "narrator:primary"
CONSUMER_NAME = "narrator-1"


class NarratorAgent(BaseAgent):
    """Turn RiskVerdict into AlphaBrief / HumanReviewRequest."""

    agent_name = AgentName.NARRATOR
    output_stream = StreamName.BRIEFS

    def __init__(self, *, ctx: Context) -> None:
        """Build the narrator; primary_model comes from settings."""
        super().__init__(
            bus=ctx.bus,
            findings=ctx.findings,
            heartbeats=ctx.heartbeats,
            anchor=ctx.anchor,
        )
        self._ctx = ctx
        self.primary_model = ctx.settings.narrator_primary_model

    async def handle(self, msg: BusMessage | None) -> None:
        """Unused."""
        return None

    async def _main_loop(self) -> None:
        """Consume ``stream:risk`` under the narrator consumer group.

        One RiskVerdict in, one AlphaBrief or HumanReviewRequest out.
        """
        async for msg in self.bus.consume(
            stream=StreamName.RISK, group=NARRATOR_GROUP, consumer=CONSUMER_NAME
        ):
            if self._stop_event.is_set():
                break
            try:
                await self._process(msg.envelope)
                await self.bus.ack(StreamName.RISK, NARRATOR_GROUP, msg.entry_id)
                self.metrics.events_processed.inc()
                self._events_in_window += 1
            except Exception:  # noqa: BLE001
                self.metrics.events_failed.inc()
                self.log.exception("narrator_process_failed", entry_id=msg.entry_id)

    async def _process(self, env: Envelope) -> None:
        """Dispatch a RiskVerdict to either brief narration or human-review emission."""
        verdict = RiskVerdict.model_validate(env.payload)
        if verdict.requires_human_review or verdict.score_0_100 is None:
            review = HumanReviewRequest(
                token_address=verdict.token_address,
                reason="; ".join(verdict.red_flags) or "requires-human-review",
                risk_verdict_msg_id=env.msg_id,
                raised_at=now_iso(),
            )
            review_env = build_envelope(
                agent=self.agent_name,
                payload=review,
                upstream_ids=[env.msg_id],
                model_used=None,
            )
            await self.findings.insert_envelope(review_env)
            try:
                tx, block = await self.anchor.record(
                    msg_id=review_env.msg_id,
                    payload_hash_hex=review_env.payload_hash,
                    agent=self.agent_name.value,
                )
                await self.findings.record_onchain(review_env.msg_id, tx, block)
            except Exception:  # noqa: BLE001
                self.log.exception("anchor_failed_review", msg_id=review_env.msg_id)
            await self.bus.publish(StreamName.HUMAN_REVIEW, review_env)
            return

        brief, model_used = await self._narrate(verdict, env)
        await self.anchor_and_publish(
            payload=brief,
            upstream_ids=[env.msg_id],
            model_used=model_used,
        )

    async def _narrate(
        self, verdict: RiskVerdict, verdict_env: Envelope
    ) -> tuple[AlphaBrief, str | None]:
        """Narrate a brief by pulling the full upstream lineage and prompting the LLM."""
        lineage: list[dict[str, object]] = []
        models: list[str] = []
        async for row in self.findings.iter_lineage(verdict_env.msg_id):
            lineage.append({"agent": row.agent, "payload": row.payload})
            if row.model_used:
                models.append(row.model_used)

        token_name = _extract_token_name(lineage) or "Unknown"
        conviction = _derive_conviction(verdict.score_0_100 or 0)

        system = (
            "You write concise, informative token-launch briefs for experienced crypto "
            "traders. Avoid hype. Lead with the thesis in one sentence. Use caveats "
            "honestly. Output strict JSON with keys: thesis (50-400 words plain prose), "
            "caveats (array of short sentences), sources (array of URLs referenced)."
        )
        user = json.dumps(
            {
                "token_address": verdict.token_address,
                "token_name": token_name,
                "preliminary_score": verdict.score_0_100,
                "red_flags": verdict.red_flags,
                "rationale": verdict.rationale,
                "lineage": lineage,
            }
        )

        try:
            resp = await self._ctx.router.chat(
                agent=self.agent_name.value,
                primary_model=self.primary_model,
                system=system,
                messages=[ChatMessage(role="user", content=user)],
                max_tokens=900,
                temperature=0.3,
            )
            data = _parse_json(resp.content)
            thesis = str(data.get("thesis", "")).strip() or verdict.rationale[:400]
            caveats = [str(x) for x in data.get("caveats", []) or []]
            sources = [str(x) for x in data.get("sources", []) or []]
            this_model = f"{resp.provider}/{resp.model.split('/', 1)[-1]}"
            models.append(this_model)
            quality = DataQuality.OK
        except RouterExhaustedError:
            thesis = verdict.rationale[:400] or "LLM unavailable; heuristic-only brief."
            caveats = ["LLM providers unreachable — brief is heuristic-only."]
            sources = []
            this_model = None
            quality = DataQuality.DEGRADED

        brief = AlphaBrief(
            token_name=token_name,
            token_address=verdict.token_address,
            thesis=thesis[:2000] if thesis else "No thesis available.",
            conviction_tier=conviction,
            caveats=caveats,
            sources=sources,
            model_attribution=sorted(set(models)),
            brief_generated_at=now_iso(),
            confidence_tier=quality,
        )
        return brief, this_model


def _extract_token_name(lineage: list[dict[str, object]]) -> str | None:
    """Pull the token_name out of the TokenCandidate row in lineage."""
    for row in lineage:
        payload = row.get("payload", {})
        if isinstance(payload, dict):
            name = payload.get("token_name")
            if isinstance(name, str) and name:
                return name
    return None


def _derive_conviction(score: int) -> ConvictionTier:
    """Map a 0-100 score onto a conviction tier."""
    if score >= 85:
        return ConvictionTier.HIGH
    if score >= 65:
        return ConvictionTier.MODERATE
    if score >= 40:
        return ConvictionTier.SPECULATIVE
    return ConvictionTier.DEGEN


def _parse_json(text: str) -> dict[str, object]:
    """Tolerant JSON parser that strips ``` fences."""
    t = text.strip()
    if t.startswith("```"):
        newline = t.find("\n")
        if newline != -1:
            t = t[newline + 1 :]
        if t.endswith("```"):
            t = t[:-3]
    try:
        loaded = json.loads(t)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


async def _amain() -> None:
    """Async process entrypoint for the Narrator agent."""
    configure_logging()
    ctx = await build_context()
    agent = NarratorAgent(ctx=ctx)
    try:
        await agent.run()
    finally:
        await ctx.aclose()


def run() -> None:
    """Process entrypoint."""
    asyncio.run(_amain())


if __name__ == "__main__":
    run()
