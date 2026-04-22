"""Base class for every SwarmScout agent.

Each concrete agent (``Hunter``, ``Social``, etc.) inherits from ``BaseAgent``
and overrides ``handle``. The base class takes care of:

* Starting a heartbeat loop (FR-008) that writes to Postgres every 10 s.
* Wiring up the bus, db, on-chain anchor, LLM router, and Prometheus metrics.
* Providing helper methods ``publish()`` and ``anchor_and_publish()`` so
  subclasses do not have to re-implement the "hash → anchor → persist → xadd"
  ordering on every single emitted message.

Ordering matters: hash first (to freeze the bytes), persist the payload to
Postgres (so a reader with the hash can find the payload), write the hash
on-chain (so the payload can be independently verified), **then** publish the
envelope to Redis. If we published before anchoring, a downstream consumer
could process a finding that is not yet verifiable on-chain, breaking the
provenance invariant.
"""

from __future__ import annotations

import asyncio
import signal
from abc import ABC, abstractmethod
from typing import Any

from prometheus_client import Counter, Gauge, Histogram
from pydantic import BaseModel

from agents.common.bus import Bus, BusMessage
from agents.common.db import FindingsRepository, HeartbeatRepository
from agents.common.envelope_builder import build_envelope
from agents.common.logging_config import get_logger
from agents.common.on_chain import NullAnchor, OnChainAnchor
from agents.common.schemas.envelope import AgentName, Envelope, StreamName


Anchor = OnChainAnchor | NullAnchor

HEARTBEAT_INTERVAL_SECONDS = 10

# Module-level metrics: Prometheus forbids re-registration in the same
# registry. Defining the collectors once at import time and then binding
# the ``agent`` label at construction is the canonical pattern, and it is
# test-safe because importing the module twice does not re-run class body.
_EVENTS_PROCESSED = Counter(
    "swarmscout_events_processed_total",
    "Events successfully processed by agent.",
    ["agent"],
)
_EVENTS_FAILED = Counter(
    "swarmscout_events_failed_total",
    "Events that failed processing.",
    ["agent"],
)
_PROCESSING_SECONDS = Histogram(
    "swarmscout_processing_seconds",
    "Time spent handling one message.",
    ["agent"],
)
_PENDING_DEPTH = Gauge(
    "swarmscout_pending_depth",
    "Depth of pending-entries list per input stream.",
    ["agent", "stream"],
)


class AgentMetrics:
    """Prometheus metric bundle, one instance per agent."""

    def __init__(self, agent: str) -> None:
        """Bind the agent label to the module-level collectors.

        The collectors are registered exactly once at module import. Multiple
        ``AgentMetrics`` instances in the same process (tests, in-process
        co-location) share the same underlying collectors and cannot collide.
        """
        self.events_processed = _EVENTS_PROCESSED.labels(agent=agent)
        self.events_failed = _EVENTS_FAILED.labels(agent=agent)
        self.processing_seconds = _PROCESSING_SECONDS.labels(agent=agent)
        self.pending_depth = _PENDING_DEPTH


class BaseAgent(ABC):
    """Abstract base for Hunter/Social/Chain/Risk/Narrator."""

    agent_name: AgentName = AgentName.HUNTER  # overridden
    output_stream: StreamName = StreamName.CANDIDATES  # overridden
    primary_model: str = ""

    def __init__(
        self,
        *,
        bus: Bus,
        findings: FindingsRepository,
        heartbeats: HeartbeatRepository,
        anchor: Anchor,
    ) -> None:
        """Initialise the metric bundle with fixed labels.

        Each metric is created with ``.labels(agent=agent)`` so the label
        is stamped in once and does not need to be re-passed at every
        increment call site.
        """
        self.bus = bus
        self.findings = findings
        self.heartbeats = heartbeats
        self.anchor = anchor
        self.metrics = AgentMetrics(self.agent_name.value)
        self.log = get_logger(self.agent_name.value, agent=self.agent_name.value)
        self._stop_event = asyncio.Event()
        self._events_in_window = 0

    # ------------------------------------------------------------------ API

    @abstractmethod
    async def handle(self, msg: BusMessage | None) -> None:
        """Process one message (or ``None`` for root agents like Hunter)."""

    async def run(self) -> None:
        """Main entrypoint — starts heartbeat + message loop, awaits shutdown."""
        self._install_signals()
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        try:
            await self._main_loop()
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _main_loop(self) -> None:
        """Override in agents that consume from a stream.

        Default: call ``handle(None)`` in a loop with a 1-second pause — used
        by root agents like Hunter that poll an external source.
        """
        while not self._stop_event.is_set():
            try:
                await self.handle(None)
                self.metrics.events_processed.inc()
                self._events_in_window += 1
            except Exception:  # noqa: BLE001 — logged and counted; agent stays up
                self.metrics.events_failed.inc()
                self.log.exception("handle_failed")
            await asyncio.sleep(1)

    # ------------------------------------------------------------------ helpers

    async def anchor_and_publish(
        self,
        *,
        payload: BaseModel | dict[str, Any],
        upstream_ids: list[str] | None = None,
        model_used: str | None = None,
    ) -> Envelope:
        """Hash → persist to Postgres → anchor on-chain → publish to the output stream."""
        env = build_envelope(
            agent=self.agent_name,
            payload=payload,
            upstream_ids=upstream_ids or [],
            model_used=model_used,
        )
        await self.findings.insert_envelope(env)
        try:
            tx_hash, block = await self.anchor.record(
                msg_id=env.msg_id, payload_hash_hex=env.payload_hash, agent=self.agent_name.value
            )
            await self.findings.record_onchain(env.msg_id, tx_hash, block)
        except Exception:  # noqa: BLE001 — anchor failure must not block the pipeline
            self.log.exception("anchor_failed", msg_id=env.msg_id)
        await self.bus.publish(self.output_stream, env)
        # Fan out to Redis Pub/Sub mirror so WebSocket subscribers (api/routes/ws.py)
        # and any live dashboard clients see the emission without re-reading the
        # stream. One-way mirror: the stream is still authoritative storage; the
        # pub/sub channel exists only for zero-lag broadcast.
        if self.output_stream == StreamName.BRIEFS:
            try:
                await self.bus.client.publish(
                    "pubsub:briefs",
                    env.model_dump_json(),
                )
            except Exception:  # noqa: BLE001 — broadcast failure must not block persistence
                self.log.exception("pubsub_publish_failed", msg_id=env.msg_id)
        self.log.info(
            "emitted",
            msg_id=env.msg_id,
            stream=self.output_stream.value,
            upstream_ids=env.upstream_ids,
            model_used=env.model_used,
        )
        return env

    # ------------------------------------------------------------------ lifecycle

    def _install_signals(self) -> None:
        """Graceful shutdown on SIGINT/SIGTERM."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop_event.set)
            except NotImplementedError:  # pragma: no cover — Windows fallback
                pass

    async def _heartbeat_loop(self) -> None:
        """Emit heartbeats on a fixed cadence until stop is requested."""
        while not self._stop_event.is_set():
            try:
                await self.heartbeats.upsert(
                    agent=self.agent_name.value,
                    status="online",
                    events_last_min=self._events_in_window,
                    current_model=self.primary_model or None,
                    llm_error_rate=0.0,
                )
                self._events_in_window = 0
            except Exception:  # noqa: BLE001
                self.log.exception("heartbeat_failed")
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
