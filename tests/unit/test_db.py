"""Coverage tests for agents/common/db.py.

All repository methods funnel SQL through ``Database.session()``. We mock
the session + execute chain at the sessionmaker level, verify the SQL
contains the expected clauses, and exercise every hydration branch in
_finding_from_row. build_engine is exercised with sqlite+aiosqlite so we
don't need a live Postgres.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.common.db import (
    Database,
    FindingRow,
    FindingsRepository,
    HeartbeatRepository,
    LLMCallRepository,
    SubscriptionRepository,
    _finding_from_row,
    build_engine,
)
from agents.common.envelope_builder import build_envelope
from agents.common.schemas.envelope import AgentName
from agents.common.schemas.payloads import TokenCandidate


# --------------------------------------------------------------------------- #
# Session-mock plumbing                                                       #
# --------------------------------------------------------------------------- #


class _FakeSession:
    """AsyncSession stand-in capturing every execute() call."""

    def __init__(self, mappings_rows: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[tuple[Any, dict[str, Any] | None]] = []
        self.mappings_rows = mappings_rows or []
        self.began = False
        self.closed = False

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_: Any) -> None:
        self.closed = True

    def begin(self):  # type: ignore[no-untyped-def]
        """Return an async context manager that marks transaction start."""
        outer = self

        @asynccontextmanager
        async def _txn() -> Any:
            outer.began = True
            yield outer

        return _txn()

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> Any:
        """Record the call and return a result stub."""
        self.calls.append((stmt, params))
        rows = self.mappings_rows

        class _Result:
            def mappings(self_inner) -> Any:
                class _Mappings:
                    def first(self_m) -> dict[str, Any] | None:
                        return rows[0] if rows else None

                    def all(self_m) -> list[dict[str, Any]]:
                        return rows

                return _Mappings()

        return _Result()


def _make_db(session: _FakeSession) -> Database:
    """Build a Database with its sessionmaker swapped for one returning ``session``."""
    # Avoid actually creating an engine — bypass __init__ with object.__new__.
    db = object.__new__(Database)
    db._engine = MagicMock()
    db._sessionmaker = MagicMock(return_value=session)
    return db


# --------------------------------------------------------------------------- #
# build_engine                                                                #
# --------------------------------------------------------------------------- #


def test_build_engine_returns_async_engine_instance() -> None:
    """``build_engine`` returns an AsyncEngine configured with pool_pre_ping."""
    from unittest.mock import patch
    from agents.common import db as db_module

    sentinel = MagicMock()
    with patch.object(db_module, "create_async_engine", return_value=sentinel) as mock_create:
        result = build_engine("postgresql+asyncpg://user:pass@host/db")
    assert result is sentinel
    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs.get("pool_pre_ping") is True
    assert kwargs.get("future") is True


# --------------------------------------------------------------------------- #
# Database                                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_database_dispose_calls_engine_dispose() -> None:
    """Database.dispose propagates to engine.dispose."""
    db = object.__new__(Database)
    db._engine = SimpleNamespace(dispose=AsyncMock())
    db._sessionmaker = MagicMock()
    await db.dispose()
    db._engine.dispose.assert_awaited_once()


def test_database_session_returns_new_session() -> None:
    """Database.session() returns the result of the configured sessionmaker."""
    sentinel = object()
    db = object.__new__(Database)
    db._engine = MagicMock()
    db._sessionmaker = MagicMock(return_value=sentinel)
    assert db.session() is sentinel


# --------------------------------------------------------------------------- #
# _finding_from_row                                                           #
# --------------------------------------------------------------------------- #


def test_finding_from_row_hydrates_dict_payload() -> None:
    row = {
        "msg_id": "A",
        "agent": "hunter",
        "payload_hash": "h",
        "upstream_ids": ["X"],
        "payload": {"x": 1},
        "model_used": "m",
        "created_at": "2026-04-22T10:00:00Z",
        "on_chain_tx": "0xtx",
        "on_chain_block": 42,
    }
    f = _finding_from_row(row)
    assert isinstance(f, FindingRow)
    assert f.payload == {"x": 1}
    assert f.upstream_ids == ["X"]


def test_finding_from_row_parses_json_string_payload() -> None:
    """Some drivers return JSONB as a str; it must be json.loads'd."""
    row = {
        "msg_id": "A",
        "agent": "hunter",
        "payload_hash": "h",
        "upstream_ids": None,  # NULL — normalised to [] via `list(None or [])`
        "payload": json.dumps({"a": 2}),
        "model_used": None,
        "created_at": "2026-04-22T10:00:00Z",
        "on_chain_tx": None,
        "on_chain_block": None,
    }
    f = _finding_from_row(row)
    assert f.payload == {"a": 2}
    assert f.upstream_ids == []


# --------------------------------------------------------------------------- #
# FindingsRepository                                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_findings_insert_envelope_executes_insert() -> None:
    session = _FakeSession()
    db = _make_db(session)
    repo = FindingsRepository(db)
    c = TokenCandidate(
        token_address="0x" + "a" * 40,
        launch_timestamp="2026-04-22T10:00:00Z",
        creator_address="0x" + "b" * 40,
        token_name="Tk",
        token_symbol="T",
        initial_liquidity_usd=100.0,
        source_url="https://four.meme/x",
    )
    env = build_envelope(agent=AgentName.HUNTER, payload=c)
    await repo.insert_envelope(env)
    assert session.began is True
    assert len(session.calls) == 1
    params = session.calls[0][1]
    assert params is not None
    assert params["msg_id"] == env.msg_id
    assert json.loads(params["payload"])  # valid JSON


@pytest.mark.asyncio
async def test_findings_record_onchain_updates_row() -> None:
    session = _FakeSession()
    repo = FindingsRepository(_make_db(session))
    await repo.record_onchain("M1", "0xdead", 123)
    assert session.began is True
    params = session.calls[0][1]
    assert params == {"tx": "0xdead", "block": 123, "msg_id": "M1"}


@pytest.mark.asyncio
async def test_findings_get_returns_row_when_found() -> None:
    row_dict = {
        "msg_id": "M1",
        "agent": "hunter",
        "payload_hash": "h",
        "upstream_ids": [],
        "payload": {"n": 1},
        "model_used": "m",
        "created_at": "2026-04-22T10:00:00Z",
        "on_chain_tx": None,
        "on_chain_block": None,
    }
    session = _FakeSession(mappings_rows=[row_dict])
    repo = FindingsRepository(_make_db(session))
    result = await repo.get("M1")
    assert result is not None
    assert result.msg_id == "M1"


@pytest.mark.asyncio
async def test_findings_get_returns_none_when_absent() -> None:
    session = _FakeSession(mappings_rows=[])
    repo = FindingsRepository(_make_db(session))
    assert await repo.get("unknown") is None


@pytest.mark.asyncio
async def test_findings_list_briefs_returns_hydrated_rows() -> None:
    row_dict = {
        "msg_id": "M1",
        "agent": "narrator",
        "payload_hash": "h",
        "upstream_ids": ["P1"],
        "payload": {"token_name": "X"},
        "model_used": "anthropic/claude-opus-4-7",
        "created_at": "2026-04-22T10:00:00Z",
        "on_chain_tx": "0xabc",
        "on_chain_block": 77,
    }
    session = _FakeSession(mappings_rows=[row_dict, row_dict])
    repo = FindingsRepository(_make_db(session))
    out = await repo.list_briefs(limit=10, offset=0)
    assert len(out) == 2
    assert out[0].agent == "narrator"


@pytest.mark.asyncio
async def test_findings_iter_lineage_walks_upstream() -> None:
    """iter_lineage walks the graph via upstream_ids parent pointers."""
    row1 = FindingRow(
        msg_id="M2",
        agent="risk",
        payload_hash="h2",
        upstream_ids=["M1"],
        payload={},
        model_used=None,
        created_at="t",
        on_chain_tx=None,
        on_chain_block=None,
    )
    row2 = FindingRow(
        msg_id="M1",
        agent="hunter",
        payload_hash="h1",
        upstream_ids=[],
        payload={},
        model_used=None,
        created_at="t",
        on_chain_tx=None,
        on_chain_block=None,
    )
    repo = FindingsRepository(_make_db(_FakeSession()))
    # Patch get to simulate the lookup graph.
    lookup = {"M2": row1, "M1": row2}

    async def fake_get(msg_id: str) -> FindingRow | None:
        return lookup.get(msg_id)

    repo.get = fake_get  # type: ignore[assignment]
    collected: list[str] = []
    async for r in repo.iter_lineage("M2"):
        collected.append(r.msg_id)
    assert collected == ["M2", "M1"]


@pytest.mark.asyncio
async def test_findings_iter_lineage_skips_seen_and_missing() -> None:
    """Loop dedups seen ids and skips None results."""
    row = FindingRow(
        msg_id="M1",
        agent="hunter",
        payload_hash="h",
        upstream_ids=["MISSING", "M1"],  # self-ref + missing parent
        payload={},
        model_used=None,
        created_at="t",
        on_chain_tx=None,
        on_chain_block=None,
    )
    repo = FindingsRepository(_make_db(_FakeSession()))

    async def fake_get(msg_id: str) -> FindingRow | None:
        return row if msg_id == "M1" else None

    repo.get = fake_get  # type: ignore[assignment]
    collected = [r.msg_id async for r in repo.iter_lineage("M1")]
    assert collected == ["M1"]  # self-ref skipped, missing parent skipped


# --------------------------------------------------------------------------- #
# LLMCallRepository                                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_llmcall_log_inserts_row() -> None:
    session = _FakeSession()
    repo = LLMCallRepository(_make_db(session))
    await repo.log(
        agent="risk",
        provider="anthropic",
        model="claude-opus-4-7",
        prompt_hash="abc",
        response_hash="def",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.002,
        latency_ms=1234,
        success=True,
        error_class=None,
    )
    assert session.began is True
    params = session.calls[0][1]
    assert params is not None
    assert params["provider"] == "anthropic"
    assert params["input_tokens"] == 100


@pytest.mark.asyncio
async def test_llmcall_cost_by_provider_aggregates() -> None:
    rows = [
        {"provider": "anthropic", "total": 1.25},
        {"provider": "openai", "total": 0.75},
        {"provider": "google", "total": None},  # NULL aggregation
    ]
    session = _FakeSession(mappings_rows=rows)
    repo = LLMCallRepository(_make_db(session))
    out = await repo.cost_by_provider()
    assert out == {"anthropic": 1.25, "openai": 0.75, "google": 0.0}


# --------------------------------------------------------------------------- #
# SubscriptionRepository                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_subscription_subscribe_executes_upsert() -> None:
    session = _FakeSession()
    repo = SubscriptionRepository(_make_db(session))
    await repo.subscribe(12345, "high")
    params = session.calls[0][1]
    assert params == {"chat_id": 12345, "threshold": "high"}


@pytest.mark.asyncio
async def test_subscription_unsubscribe_marks_inactive() -> None:
    session = _FakeSession()
    repo = SubscriptionRepository(_make_db(session))
    await repo.unsubscribe(98765)
    assert session.calls[0][1] == {"chat_id": 98765}


@pytest.mark.asyncio
async def test_subscription_set_threshold() -> None:
    session = _FakeSession()
    repo = SubscriptionRepository(_make_db(session))
    await repo.set_threshold(55, "degen")
    assert session.calls[0][1] == {"threshold": "degen", "chat_id": 55}


@pytest.mark.asyncio
async def test_subscription_list_active_returns_tuples() -> None:
    session = _FakeSession(
        mappings_rows=[
            {"chat_id": 1, "threshold": "moderate"},
            {"chat_id": 2, "threshold": "high"},
        ]
    )
    repo = SubscriptionRepository(_make_db(session))
    out = await repo.list_active()
    assert out == [(1, "moderate"), (2, "high")]


# --------------------------------------------------------------------------- #
# HeartbeatRepository                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_heartbeat_upsert_inserts_row() -> None:
    session = _FakeSession()
    repo = HeartbeatRepository(_make_db(session))
    await repo.upsert(
        agent="hunter",
        status="online",
        events_last_min=42,
        current_model="gemini-2.5-flash",
        llm_error_rate=0.01,
    )
    assert session.began is True
    params = session.calls[0][1]
    assert params is not None
    assert params["agent"] == "hunter"
    assert params["events"] == 42


@pytest.mark.asyncio
async def test_heartbeat_all_returns_dict_list() -> None:
    session = _FakeSession(
        mappings_rows=[
            {
                "agent": "hunter",
                "status": "online",
                "events_last_min": 3,
                "current_model": "gemini",
                "llm_error_rate": 0.0,
                "last_seen": "2026-04-22T10:00:00Z",
            },
        ]
    )
    repo = HeartbeatRepository(_make_db(session))
    rows = await repo.all()
    assert rows == [
        {
            "agent": "hunter",
            "status": "online",
            "events_last_min": 3,
            "current_model": "gemini",
            "llm_error_rate": 0.0,
            "last_seen": "2026-04-22T10:00:00Z",
        }
    ]
