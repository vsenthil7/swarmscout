"""Async Postgres access layer.

Thin repository classes sitting over SQLAlchemy 2.0 asyncio. Agents and the
API talk to repositories; repositories own SQL. No ORM entities — we use
raw ``text()`` with named parameters, because the schema is flat and the
overhead of mapper classes buys nothing here.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agents.common.schemas.envelope import Envelope


@dataclass(frozen=True)
class FindingRow:
    """Materialised view of a ``findings`` row, hydrated for API responses."""

    msg_id: str
    agent: str
    payload_hash: str
    upstream_ids: list[str]
    payload: dict[str, Any]
    model_used: str | None
    created_at: str
    on_chain_tx: str | None
    on_chain_block: int | None


def build_engine(dsn: str) -> AsyncEngine:
    """Build an async SQLAlchemy engine for ``dsn``."""
    return create_async_engine(dsn, pool_pre_ping=True, future=True)


class Database:
    """Entry-point for transactional access to Postgres."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Store the backing reference so repository methods can open sessions."""
        self._engine = engine
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def dispose(self) -> None:
        """Dispose the underlying connection pool."""
        await self._engine.dispose()

    def session(self) -> AsyncSession:
        """Return a new ``AsyncSession``. Caller is responsible for closing it."""
        return self._sessionmaker()


# --------------------------------------------------------------------------- #
# Findings repository                                                         #
# --------------------------------------------------------------------------- #


class FindingsRepository:
    """Read/write access to the ``findings`` table."""

    def __init__(self, db: Database) -> None:
        """Store the backing reference so repository methods can open sessions."""
        self._db = db

    async def insert_envelope(self, env: Envelope) -> None:
        """Persist ``env`` as a ``findings`` row."""
        stmt = text(
            """
            INSERT INTO findings (msg_id, agent, payload_hash, upstream_ids,
                                  payload, model_used, created_at)
            VALUES (:msg_id, :agent, :payload_hash, :upstream_ids,
                    CAST(:payload AS JSONB), :model_used, NOW())
            ON CONFLICT (msg_id) DO NOTHING
            """
        )
        async with self._db.session() as s, s.begin():
            await s.execute(
                stmt,
                {
                    "msg_id": env.msg_id,
                    "agent": env.agent.value,
                    "payload_hash": env.payload_hash,
                    "upstream_ids": env.upstream_ids,
                    "payload": json.dumps(env.payload),
                    "model_used": env.model_used,
                },
            )

    async def record_onchain(self, msg_id: str, tx: str, block: int) -> None:
        """Store the on-chain tx hash and block number for ``msg_id``."""
        stmt = text(
            """
            UPDATE findings
               SET on_chain_tx = :tx, on_chain_block = :block
             WHERE msg_id = :msg_id
            """
        )
        async with self._db.session() as s, s.begin():
            await s.execute(stmt, {"tx": tx, "block": block, "msg_id": msg_id})

    async def get(self, msg_id: str) -> FindingRow | None:
        """Fetch one finding by ``msg_id``."""
        stmt = text(
            """
            SELECT msg_id, agent, payload_hash, upstream_ids, payload,
                   model_used, to_char(created_at AT TIME ZONE 'UTC',
                                       'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS created_at,
                   on_chain_tx, on_chain_block
              FROM findings
             WHERE msg_id = :msg_id
            """
        )
        async with self._db.session() as s:
            row = (await s.execute(stmt, {"msg_id": msg_id})).mappings().first()
        return _finding_from_row(row) if row else None

    async def list_briefs(self, *, limit: int = 50, offset: int = 0) -> list[FindingRow]:
        """List the most recent narrator-produced briefs, newest first."""
        stmt = text(
            """
            SELECT msg_id, agent, payload_hash, upstream_ids, payload,
                   model_used, to_char(created_at AT TIME ZONE 'UTC',
                                       'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS created_at,
                   on_chain_tx, on_chain_block
              FROM findings
             WHERE agent = 'narrator'
             ORDER BY created_at DESC
             LIMIT :limit OFFSET :offset
            """
        )
        async with self._db.session() as s:
            rows = (await s.execute(stmt, {"limit": limit, "offset": offset})).mappings().all()
        return [_finding_from_row(r) for r in rows]

    async def iter_lineage(self, msg_id: str) -> AsyncIterator[FindingRow]:
        """Yield the full upstream lineage for ``msg_id`` in topological order (parents first)."""
        seen: set[str] = set()
        frontier: list[str] = [msg_id]
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            row = await self.get(current)
            if row is None:
                continue
            yield row
            for parent in row.upstream_ids:
                if parent not in seen:
                    frontier.append(parent)


def _finding_from_row(row: Any) -> FindingRow:
    """Hydrate a FindingRow from the raw SQLAlchemy mapping.

    Postgres can return ``payload`` either as a pre-parsed dict or as
    a JSON string depending on driver settings, so we normalise both.
    """
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return FindingRow(
        msg_id=row["msg_id"],
        agent=row["agent"],
        payload_hash=row["payload_hash"],
        upstream_ids=list(row["upstream_ids"] or []),
        payload=payload,
        model_used=row["model_used"],
        created_at=row["created_at"],
        on_chain_tx=row["on_chain_tx"],
        on_chain_block=row["on_chain_block"],
    )


# --------------------------------------------------------------------------- #
# LLM call log                                                                #
# --------------------------------------------------------------------------- #


class LLMCallRepository:
    """Append-only audit log for every LLM call."""

    def __init__(self, db: Database) -> None:
        """Store the backing reference so repository methods can open sessions."""
        self._db = db

    async def log(
        self,
        *,
        agent: str,
        provider: str,
        model: str,
        prompt_hash: str,
        response_hash: str | None,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
        success: bool,
        error_class: str | None = None,
    ) -> None:
        """Insert one row."""
        stmt = text(
            """
            INSERT INTO llm_calls (agent, provider, model, prompt_hash, response_hash,
                                   input_tokens, output_tokens, cost_usd, latency_ms,
                                   success, error_class)
            VALUES (:agent, :provider, :model, :prompt_hash, :response_hash,
                    :input_tokens, :output_tokens, :cost_usd, :latency_ms,
                    :success, :error_class)
            """
        )
        async with self._db.session() as s, s.begin():
            await s.execute(
                stmt,
                {
                    "agent": agent,
                    "provider": provider,
                    "model": model,
                    "prompt_hash": prompt_hash,
                    "response_hash": response_hash,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": cost_usd,
                    "latency_ms": latency_ms,
                    "success": success,
                    "error_class": error_class,
                },
            )

    async def cost_by_provider(self) -> dict[str, float]:
        """Sum cost_usd grouped by provider across all time."""
        stmt = text("SELECT provider, SUM(cost_usd) AS total FROM llm_calls GROUP BY provider")
        async with self._db.session() as s:
            rows = (await s.execute(stmt)).mappings().all()
        return {r["provider"]: float(r["total"] or 0) for r in rows}


# --------------------------------------------------------------------------- #
# Telegram subscriptions                                                      #
# --------------------------------------------------------------------------- #


class SubscriptionRepository:
    """Read/write access to the ``telegram_subscriptions`` table."""

    def __init__(self, db: Database) -> None:
        """Store the backing reference so repository methods can open sessions."""
        self._db = db

    async def subscribe(self, chat_id: int, threshold: str = "moderate") -> None:
        """Add or reactivate a subscription for ``chat_id``."""
        stmt = text(
            """
            INSERT INTO telegram_subscriptions (chat_id, threshold, active)
            VALUES (:chat_id, :threshold, TRUE)
            ON CONFLICT (chat_id) DO UPDATE
               SET active = TRUE, threshold = EXCLUDED.threshold
            """
        )
        async with self._db.session() as s, s.begin():
            await s.execute(stmt, {"chat_id": chat_id, "threshold": threshold})

    async def unsubscribe(self, chat_id: int) -> None:
        """Mark ``chat_id`` inactive; row is retained for analytics."""
        stmt = text("UPDATE telegram_subscriptions SET active = FALSE WHERE chat_id = :chat_id")
        async with self._db.session() as s, s.begin():
            await s.execute(stmt, {"chat_id": chat_id})

    async def set_threshold(self, chat_id: int, threshold: str) -> None:
        """Set the conviction threshold for ``chat_id``."""
        stmt = text(
            """
            UPDATE telegram_subscriptions
               SET threshold = :threshold
             WHERE chat_id = :chat_id
            """
        )
        async with self._db.session() as s, s.begin():
            await s.execute(stmt, {"threshold": threshold, "chat_id": chat_id})

    async def list_active(self) -> list[tuple[int, str]]:
        """Return list of (chat_id, threshold) for active subscribers."""
        stmt = text(
            "SELECT chat_id, threshold FROM telegram_subscriptions WHERE active = TRUE"
        )
        async with self._db.session() as s:
            rows = (await s.execute(stmt)).mappings().all()
        return [(int(r["chat_id"]), str(r["threshold"])) for r in rows]


# --------------------------------------------------------------------------- #
# Agent heartbeats                                                            #
# --------------------------------------------------------------------------- #


class HeartbeatRepository:
    """Latest heartbeat per agent, last-writer-wins."""

    def __init__(self, db: Database) -> None:
        """Store the backing reference so repository methods can open sessions."""
        self._db = db

    async def upsert(
        self,
        *,
        agent: str,
        status: str,
        events_last_min: int,
        current_model: str | None,
        llm_error_rate: float,
    ) -> None:
        """Insert or update the heartbeat row for ``agent``."""
        stmt = text(
            """
            INSERT INTO agent_heartbeats
                (agent, status, events_last_min, current_model, llm_error_rate, last_seen)
            VALUES (:agent, :status, :events, :model, :err, NOW())
            ON CONFLICT (agent) DO UPDATE
               SET status = EXCLUDED.status,
                   events_last_min = EXCLUDED.events_last_min,
                   current_model = EXCLUDED.current_model,
                   llm_error_rate = EXCLUDED.llm_error_rate,
                   last_seen = NOW()
            """
        )
        async with self._db.session() as s, s.begin():
            await s.execute(
                stmt,
                {
                    "agent": agent,
                    "status": status,
                    "events": events_last_min,
                    "model": current_model,
                    "err": llm_error_rate,
                },
            )

    async def all(self) -> list[dict[str, Any]]:
        """Return all heartbeats as dicts for the dashboard."""
        stmt = text(
            """
            SELECT agent, status, events_last_min, current_model, llm_error_rate,
                   to_char(last_seen AT TIME ZONE 'UTC',
                           'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS last_seen
              FROM agent_heartbeats
             ORDER BY agent
            """
        )
        async with self._db.session() as s:
            rows = (await s.execute(stmt)).mappings().all()
        return [dict(r) for r in rows]
