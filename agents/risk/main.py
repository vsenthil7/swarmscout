"""Risk agent.

Consumes ``SocialScore`` (stream:social) and ``ChainMetrics``
(stream:chain) and emits a ``RiskVerdict`` on ``stream:risk``. Pairs are
joined by ``token_address`` with a 120-second timeout (FR-061):

* If both sides arrive within 120s, we run heuristics and ask the LLM to
  write a rationale.
* If only one side arrives, a partial verdict is emitted with
  ``missing_inputs`` noting which side is absent.
* If all three LLM providers are unreachable (``RouterExhaustedError``)
  we still emit a ``RiskVerdict`` but with ``score_0_100=None``,
  ``confidence=None``, and ``requires_human_review=True`` (FR-064,
  TC-F05).
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Literal

from agents.common.base_agent import BaseAgent
from agents.common.bus import BusMessage
from agents.common.context import Context, build_context
from agents.common.llm_router import ChatMessage, RouterExhaustedError
from agents.common.logging_config import configure_logging
from agents.common.schemas.envelope import AgentName, Envelope, StreamName
from agents.common.schemas.payloads import (
    ChainMetrics,
    RiskConfidence,
    RiskVerdict,
    SocialScore,
)
from agents.risk.heuristics import Finding, aggregate_score, run_heuristics

SOCIAL_GROUP = "risk:social"
CHAIN_GROUP = "risk:chain"
CONSUMER_NAME = "risk-1"

JOIN_TIMEOUT_S = 120.0


@dataclass
class PendingPair:
    """One half of a join, waiting for its partner."""

    envelope: Envelope
    side: Literal["social", "chain"]
    created_at: float


class RiskAgent(BaseAgent):
    """Join social + chain per token_address, emit RiskVerdict."""

    agent_name = AgentName.RISK
    output_stream = StreamName.RISK

    def __init__(self, *, ctx: Context) -> None:
        """Initialise the Risk agent with an empty pending-pair buffer."""
        super().__init__(
            bus=ctx.bus,
            findings=ctx.findings,
            heartbeats=ctx.heartbeats,
            anchor=ctx.anchor,
        )
        self._ctx = ctx
        self.primary_model = ctx.settings.risk_primary_model
        self._pending: dict[str, PendingPair] = {}
        self._pending_lock = asyncio.Lock()

    async def handle(self, msg: BusMessage | None) -> None:
        """Unused — see ``_main_loop``."""
        return None

    async def _main_loop(self) -> None:
        """Run both consumers and a timeout sweeper in parallel."""
        tasks = [
            asyncio.create_task(self._consume(StreamName.SOCIAL, SOCIAL_GROUP, "social")),
            asyncio.create_task(self._consume(StreamName.CHAIN, CHAIN_GROUP, "chain")),
            asyncio.create_task(self._sweep_timeouts()),
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                t.cancel()

    async def _consume(
        self,
        stream: StreamName,
        group: str,
        side: Literal["social", "chain"],
    ) -> None:
        """Generic consumer loop shared by the social and chain streams.

        ``side`` parameterises the callback so the join logic treats the
        two streams symmetrically.
        """
        async for msg in self.bus.consume(stream=stream, group=group, consumer=CONSUMER_NAME):
            if self._stop_event.is_set():
                break
            try:
                await self._on_message(msg.envelope, side)
                await self.bus.ack(stream, group, msg.entry_id)
                self.metrics.events_processed.inc()
                self._events_in_window += 1
            except Exception:  # noqa: BLE001
                self.metrics.events_failed.inc()
                self.log.exception("risk_on_message_failed", side=side, entry_id=msg.entry_id)

    async def _on_message(self, env: Envelope, side: Literal["social", "chain"]) -> None:
        """Store one side of the pair in the pending buffer; emit verdict if partner present.

        Guarded by ``self._pending_lock`` because two parallel tasks (one
        per stream) are both mutating the buffer. Duplicate same-side
        messages overwrite the earlier envelope (newest wins).
        """
        token_addr = env.payload.get("token_address", "")
        async with self._pending_lock:
            partner = self._pending.pop(token_addr, None)
            if partner is None:
                self._pending[token_addr] = PendingPair(
                    envelope=env, side=side, created_at=time.monotonic()
                )
                return
            if partner.side == side:
                # Duplicate side — overwrite with the newer envelope.
                self._pending[token_addr] = PendingPair(
                    envelope=env, side=side, created_at=time.monotonic()
                )
                return

        social_env, chain_env = (
            (env, partner.envelope) if side == "social" else (partner.envelope, env)
        )
        await self._emit_verdict(social_env=social_env, chain_env=chain_env)

    async def _sweep_timeouts(self) -> None:
        """Every 5 s, evict partial-pair entries that have exceeded ``JOIN_TIMEOUT_S``."""
        while not self._stop_event.is_set():
            await asyncio.sleep(5)
            now = time.monotonic()
            expired: list[tuple[str, PendingPair]] = []
            async with self._pending_lock:
                for token, pair in list(self._pending.items()):
                    if now - pair.created_at > JOIN_TIMEOUT_S:
                        expired.append((token, pair))
                        del self._pending[token]
            for _, pair in expired:
                try:
                    await self._emit_partial(pair)
                except Exception:  # noqa: BLE001
                    self.log.exception("risk_partial_emit_failed", token=pair.envelope.payload.get("token_address"))

    async def _emit_verdict(self, *, social_env: Envelope, chain_env: Envelope) -> None:
        """Compute heuristics, ask LLM for rationale, publish RiskVerdict on stream:risk."""
        social = SocialScore.model_validate(social_env.payload)
        chain = ChainMetrics.model_validate(chain_env.payload)
        findings = run_heuristics(social, chain)
        score = aggregate_score(findings)
        rationale, model_used, confidence = await self._ask_llm(social, chain, findings, score)

        verdict = RiskVerdict(
            token_address=social.token_address,
            score_0_100=None if model_used is None else score,
            red_flags=[f.tag for f in findings],
            rationale=rationale,
            missing_inputs=[],
            confidence=confidence,
            requires_human_review=model_used is None,
        )
        await self.anchor_and_publish(
            payload=verdict,
            upstream_ids=[social_env.msg_id, chain_env.msg_id],
            model_used=model_used,
        )

    async def _emit_partial(self, pair: PendingPair) -> None:
        """Emit a degraded RiskVerdict when the join window expired without a partner."""
        missing = "chain" if pair.side == "social" else "social"
        verdict = RiskVerdict(
            token_address=pair.envelope.payload.get("token_address", "0x" + "0" * 40),
            score_0_100=None,
            red_flags=[f"missing-{missing}-input"],
            rationale=f"{missing.title()} data did not arrive within {JOIN_TIMEOUT_S:.0f}s.",
            missing_inputs=[missing],
            confidence=RiskConfidence.LOW,
            requires_human_review=True,
        )
        await self.anchor_and_publish(
            payload=verdict,
            upstream_ids=[pair.envelope.msg_id],
            model_used=None,
        )

    async def _ask_llm(
        self,
        s: SocialScore,
        c: ChainMetrics,
        findings: list[Finding],
        score: int,
    ) -> tuple[str, str | None, RiskConfidence | None]:
        """Produce (rationale, model_used, confidence), or a degraded triplet on exhaustion."""
        system = (
            "You write concise risk rationales for memecoin launches. Input: social metrics, "
            "chain metrics, triggered heuristics, and a preliminary score. Output strict JSON "
            "with keys: rationale (<=400 words plain prose), confidence (low|medium|high)."
        )
        user = json.dumps(
            {
                "social": s.model_dump(mode="json"),
                "chain": c.model_dump(mode="json"),
                "findings": [{"tag": f.tag, "weight": f.weight, "reason": f.reason} for f in findings],
                "preliminary_score": score,
            }
        )
        try:
            resp = await self._ctx.router.chat(
                agent=self.agent_name.value,
                primary_model=self.primary_model,
                system=system,
                messages=[ChatMessage(role="user", content=user)],
                max_tokens=700,
                temperature=0.2,
            )
        except RouterExhaustedError:
            return (
                "LLM providers unreachable. Verdict is heuristic-only and not narrative.",
                None,
                None,
            )
        try:
            data = json.loads(_strip_fences(resp.content))
            rationale = str(data.get("rationale", "")).strip() or "No rationale produced."
            conf_raw = str(data.get("confidence", "medium")).lower()
            if conf_raw not in {c.value for c in RiskConfidence}:
                conf_raw = "medium"
            return rationale, f"{resp.provider}/{resp.model.split('/', 1)[-1]}", RiskConfidence(conf_raw)
        except json.JSONDecodeError:
            return resp.content[:400], f"{resp.provider}/{resp.model.split('/', 1)[-1]}", RiskConfidence.LOW


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
    """Async process entrypoint for the Risk agent."""
    configure_logging()
    ctx = await build_context()
    agent = RiskAgent(ctx=ctx)
    try:
        await agent.run()
    finally:
        await ctx.aclose()


def run() -> None:
    """Process entrypoint."""
    asyncio.run(_amain())


if __name__ == "__main__":
    run()
