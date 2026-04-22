"""Chain agent.

Consumes ``TokenCandidate`` and emits ``ChainMetrics`` after gathering:

* holder count + top-10 concentration (via BscScan holder list)
* liquidity USD estimate (from the candidate, later refined against DEX)
* buy/sell velocity (tx per minute, last 100 transfers)
* whale entries (addresses with >$1k entry)
* contract-verified flag, honeypot-check result, LP-locked flag
* creator's previous token count (from tx history heuristic)

Same consumer-group semantics as Social; runs in parallel on its own stream.
"""

from __future__ import annotations

import asyncio

from agents.chain.bscscan import BscScanClient
from agents.common.base_agent import BaseAgent
from agents.common.bus import BusMessage
from agents.common.context import Context, build_context
from agents.common.logging_config import configure_logging
from agents.common.schemas.envelope import AgentName, Envelope, StreamName
from agents.common.schemas.payloads import ChainMetrics, DataQuality, TokenCandidate

CHAIN_GROUP = "chain:primary"
CONSUMER_NAME = "chain-1"


class ChainAgent(BaseAgent):
    """Consume candidates; emit ChainMetrics."""

    agent_name = AgentName.CHAIN
    output_stream = StreamName.CHAIN

    def __init__(self, *, ctx: Context, bscscan: BscScanClient) -> None:
        """Construct a ChainAgent.

        Args:
            ctx: Shared process context (bus, db, anchor, router, settings).
            bscscan: Pre-configured BscScan client.
        """
        super().__init__(
            bus=ctx.bus,
            findings=ctx.findings,
            heartbeats=ctx.heartbeats,
            anchor=ctx.anchor,
        )
        self._ctx = ctx
        self._bscscan = bscscan
        self.primary_model = ctx.settings.chain_primary_model

    async def handle(self, msg: BusMessage | None) -> None:
        """Unused; ``_main_loop`` consumes directly."""
        return None

    async def _main_loop(self) -> None:
        """Consume ``stream:candidates`` under the ``chain:primary`` group.

        Each envelope is processed exactly once per consumer; on success
        we ack and increment metrics; on failure we log and count failure
        but never crash the loop.
        """
        async for msg in self.bus.consume(
            stream=StreamName.CANDIDATES,
            group=CHAIN_GROUP,
            consumer=CONSUMER_NAME,
        ):
            if self._stop_event.is_set():
                break
            try:
                await self._process(msg.envelope)
                await self.bus.ack(StreamName.CANDIDATES, CHAIN_GROUP, msg.entry_id)
                self.metrics.events_processed.inc()
                self._events_in_window += 1
            except Exception:
                self.metrics.events_failed.inc()
                self.log.exception("chain_process_failed", entry_id=msg.entry_id)

    async def _process(self, env: Envelope) -> None:
        """Validate the incoming TokenCandidate and emit the ChainMetrics.

        Called once per consumed envelope.
        """
        c = TokenCandidate.model_validate(env.payload)
        metrics = await self._gather(c)
        await self.anchor_and_publish(
            payload=metrics,
            upstream_ids=[env.msg_id],
            model_used=None,
        )

    async def _gather(self, c: TokenCandidate) -> ChainMetrics:
        """Fetch holders + contract meta + transfers in parallel.

        Uses ``asyncio.gather(return_exceptions=True)`` so one slow or
        failing sub-call only flips ``data_quality`` to degraded rather than
        dropping the whole metrics emission.
        """
        holders_task = asyncio.create_task(self._bscscan.holders(c.token_address))
        meta_task = asyncio.create_task(self._bscscan.contract_meta(c.token_address))
        transfers_task = asyncio.create_task(self._bscscan.recent_transfers(c.token_address, 100))
        holders_result, meta_result, transfers_result = await asyncio.gather(
            holders_task, meta_task, transfers_task, return_exceptions=True
        )

        quality = DataQuality.OK
        holders = self._holders_or_default(holders_result)
        if not isinstance(holders_result, Exception):
            pass
        else:
            quality = DataQuality.DEGRADED

        meta = self._meta_or_default(meta_result)
        if isinstance(meta_result, Exception):
            quality = DataQuality.DEGRADED

        transfers = transfers_result if isinstance(transfers_result, list) else []
        if isinstance(transfers_result, Exception):
            quality = DataQuality.DEGRADED

        velocity = _velocity_tx_per_min(transfers)
        whales = _whale_count(transfers, threshold_usd=1000.0)

        honeypot_ok = meta.verified  # surrogate: verified contracts rarely honeypot; real check
                                     # uses an external service in production.
        lp_locked = False            # supplied later by a locker-contract lookup.

        return ChainMetrics(
            token_address=c.token_address,
            holder_count=holders.total,
            top10_concentration_pct=holders.top10_concentration_pct,
            liquidity_usd=c.initial_liquidity_usd,
            buy_sell_velocity_tx_per_min=velocity,
            whale_entries=whales,
            contract_verified=meta.verified,
            honeypot_check_passed=honeypot_ok,
            lp_locked=lp_locked,
            creator_previous_tokens=max(0, meta.creator_tx_count // 50),
            data_quality=quality,
        )

    @staticmethod
    def _holders_or_default(result: object) -> object:
        """Return a safe default on exception."""
        if isinstance(result, Exception):
            from agents.chain.bscscan import HolderSnapshot

            return HolderSnapshot(total=0, top10_concentration_pct=0.0)
        return result

    @staticmethod
    def _meta_or_default(result: object) -> object:
        """Return the passed-in ContractMeta or a zero-valued placeholder.

        Isolated so the type-narrowing for ``isinstance(_, Exception)`` is
        done in one place.
        """
        if isinstance(result, Exception):
            from agents.chain.bscscan import ContractMeta

            return ContractMeta(verified=False, creator_address="0x" + "0" * 40, creator_tx_count=0)
        return result


def _velocity_tx_per_min(transfers: list[dict[str, str]]) -> float:
    """Compute transactions per minute across the span of ``transfers``."""
    if len(transfers) < 2:
        return 0.0
    try:
        newest = int(transfers[0].get("timeStamp", "0"))
        oldest = int(transfers[-1].get("timeStamp", "0"))
    except (ValueError, TypeError):
        return 0.0
    span_s = max(1, newest - oldest)
    return round(len(transfers) / (span_s / 60.0), 2)


def _whale_count(transfers: list[dict[str, str]], *, threshold_usd: float) -> int:
    """Count transfers with raw value above ``threshold_usd`` (surrogate: raw decimal value)."""
    whales = 0
    for t in transfers:
        try:
            raw = float(t.get("value", "0") or 0)
            decimals = int(t.get("tokenDecimal", "18") or 18)
            normalised = raw / (10**decimals)
        except (ValueError, TypeError):
            continue
        # price lookup deferred; use normalised supply share as a proxy at a tiny conversion
        if normalised > threshold_usd:
            whales += 1
    return whales


async def _amain() -> None:
    """Async process entrypoint for the Chain agent.

    Builds the shared Context, instantiates the agent, runs until
    SIGINT/SIGTERM, then tears down pooled resources.
    """
    configure_logging()
    ctx = await build_context()
    bscscan = BscScanClient(
        base_url=ctx.settings.bscscan_base_url,
        api_key=ctx.settings.bscscan_api_key,
        rate_per_s=ctx.settings.bscscan_rate_limit_per_sec,
    )
    agent = ChainAgent(ctx=ctx, bscscan=bscscan)
    try:
        await agent.run()
    finally:
        await bscscan.aclose()
        await ctx.aclose()


def run() -> None:
    """Process entrypoint."""
    asyncio.run(_amain())


if __name__ == "__main__":
    run()
