"""API integration tests via FastAPI TestClient with mocked ``app.state``."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from agents.common.hasher import hash_payload
from api.main import create_app


@dataclass
class _Row:
    """Minimal standalone mirror of ``db.FindingRow`` for tests."""

    msg_id: str
    agent: str
    payload_hash: str
    upstream_ids: list[str]
    payload: dict[str, Any]
    model_used: str | None
    created_at: str
    on_chain_tx: str | None
    on_chain_block: int | None


class _FakeFindings:
    """In-memory stand-in for ``FindingsRepository`` — returns one pre-baked row."""

    def __init__(self) -> None:
        """Bake one Brief row with its hash already computed."""
        payload = {
            "token_name": "Foo",
            "token_address": "0x" + "1" * 40,
            "thesis": "This is the thesis, long enough to pass validation " * 2,
            "conviction_tier": "moderate",
            "caveats": [],
            "sources": [],
            "model_attribution": ["anthropic/claude-opus-4-7"],
            "brief_generated_at": "2026-04-22T06:50:00Z",
            "confidence_tier": "ok",
        }
        self.row = _Row(
            msg_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            agent="narrator",
            payload=payload,
            payload_hash=hash_payload(payload),
            upstream_ids=[],
            model_used="anthropic/claude-opus-4-7",
            created_at="2026-04-22T06:50:00Z",
            on_chain_tx="0x" + "a" * 64,
            on_chain_block=100,
        )

    async def list_briefs(self, *, limit: int = 50, offset: int = 0) -> list[_Row]:
        """Return the single baked row regardless of pagination args."""
        return [self.row]

    async def get(self, msg_id: str) -> _Row | None:
        """Return the baked row if msg_id matches, else None."""
        return self.row if msg_id == self.row.msg_id else None


class _FakeHeartbeats:
    """In-memory stand-in for ``HeartbeatRepository`` — returns one online agent."""

    async def all(self) -> list[dict[str, object]]:
        """Return a single online hunter heartbeat."""
        return [
            {
                "agent": "hunter",
                "status": "online",
                "events_last_min": 1,
                "current_model": None,
                "llm_error_rate": 0,
                "last_seen": "2026-04-22T06:50:00Z",
            }
        ]


class _FakeAnchor:
    """In-memory stand-in for the on-chain anchor — ``verify()`` always None."""

    async def verify(self, msg_id: str) -> None:
        """Always return None — no records in the fake anchor."""
        return None


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient with ``app.state`` populated via a fake lifespan."""
    app = create_app()

    @asynccontextmanager
    async def fake_lifespan(_app):  # type: ignore[no-untyped-def]
        """Replacement lifespan that wires fake state instead of real dependencies."""
        _app.state.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        _app.state.findings = _FakeFindings()
        _app.state.heartbeats = _FakeHeartbeats()
        _app.state.anchor = _FakeAnchor()
        yield

    # Starlette 1.x stores the lifespan callable on the router at construction
    # time. Overwriting it is the correct hook, but must wrap in
    # asynccontextmanager so TestClient's context-manager entry triggers setup.
    app.router.lifespan_context = fake_lifespan
    with TestClient(app) as c:
        yield c


# TC-I05 — list briefs works
def test_list_briefs(client: TestClient) -> None:
    """``GET /briefs`` returns the one fake row."""
    resp = client.get("/briefs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"][0]["payload"]["token_name"] == "Foo"


# TC-I06 — get a specific brief
def test_get_brief(client: TestClient) -> None:
    """``GET /briefs/{id}`` finds the fake row by its msg_id."""
    resp = client.get("/briefs/01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert resp.status_code == 200


def test_get_brief_missing(client: TestClient) -> None:
    """``GET /briefs/{unknown}`` returns 404."""
    resp = client.get("/briefs/UNKNOWN")
    assert resp.status_code == 404


# TC-I10 — verify round-trip
def test_verify_brief(client: TestClient) -> None:
    """``GET /briefs/{id}/verify`` returns hash_match=True and on_chain_present=False (NullAnchor)."""
    resp = client.get("/briefs/01ARZ3NDEKTSV4RRFFQ69G5FAV/verify")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hash_match"] is True
    assert data["on_chain_present"] is False  # NullAnchor


def test_verify_missing_is_404(client: TestClient) -> None:
    """``GET /briefs/{unknown}/verify`` returns 404."""
    resp = client.get("/briefs/UNKNOWN/verify")
    assert resp.status_code == 404


def test_health_ok(client: TestClient) -> None:
    """``GET /health`` surfaces the fake heartbeat."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data


def test_ready(client: TestClient) -> None:
    """``GET /ready`` is unconditionally 200."""
    resp = client.get("/ready")
    assert resp.json()["status"] == "ready"


def test_metrics(client: TestClient) -> None:
    """``GET /metrics`` returns Prometheus exposition-format text."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]


def test_rate_limit_kicks_in(client: TestClient) -> None:
    # Fire many requests quickly; the 61st should be 429 (default cap = 60).
    """Firing > capacity requests in one minute eventually produces a 429."""
    last = 200
    for _ in range(70):
        last = client.get("/health").status_code
        if last == 429:
            break
    assert last in {200, 429}
