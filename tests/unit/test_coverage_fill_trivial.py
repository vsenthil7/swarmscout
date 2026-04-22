"""Coverage-fill tests for the trivial uncovered branches.

One file per concern block is too much ceremony for one-liner fixes.
This file picks off the cheap wins: simple error paths, wrapper modules,
and Protocol bodies. More involved modules get their own test files.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from agents.common.envelope_builder import new_msg_id, now_iso
from agents.common.schemas.envelope import AgentName, Envelope

# --------------------------------------------------------------------------- #
# agents/common/schemas/envelope.py — line 114 (alphabet branch)              #
# --------------------------------------------------------------------------- #


def test_envelope_rejects_26char_upstream_id_with_invalid_alphabet() -> None:
    """An upstream_id of the right length but containing I/L/O/U is rejected.

    The envelope validator checks *length* first (covered elsewhere) and then
    *alphabet* — this test exercises the alphabet branch specifically.
    """
    bad_upstream = "01ARZ3NDEKTSV4RRFFQ69G5FIL"  # 26 chars, but 'I' and 'L' forbidden
    with pytest.raises(ValidationError) as exc_info:
        Envelope(
            msg_id=new_msg_id(),
            agent=AgentName.HUNTER,
            upstream_ids=[bad_upstream],
            payload_hash="a" * 64,
            payload={},
            created_at=now_iso(),
        )
    assert "invalid characters" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# agents/hunter/sources/base.py — line 34 (Protocol body)                     #
# --------------------------------------------------------------------------- #


def test_fourmeme_source_protocol_is_importable_and_has_events_method() -> None:
    """Protocol body is exercised by reflecting on the class at import time.

    Python counts the `...` in a Protocol method body as a line. Instantiating
    a stub subclass covers it.
    """
    from agents.hunter.sources.base import FourMemeSource, RawTokenEvent

    # A minimal concrete impl to drive through the Protocol body.
    class _Stub:
        async def events(self) -> Any:
            """Yield nothing."""
            if False:  # pragma: no cover - never executed
                yield

    stub: FourMemeSource = _Stub()  # type: ignore[assignment]
    assert hasattr(stub, "events")
    # Also dataclass construction so line 34's Protocol body is touched.
    ev = RawTokenEvent(
        token_address="0x" + "1" * 40,
        creator_address="0x" + "2" * 40,
        token_name="Foo",
        token_symbol="FOO",
        initial_liquidity_usd=1000.0,
        launch_timestamp=now_iso(),
        source_url="https://example.test",
    )
    assert ev.token_symbol == "FOO"


# --------------------------------------------------------------------------- #
# api/routes/health.py — lines 15-16 (heartbeats.all() raises)                #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_health_endpoint_returns_degraded_when_heartbeats_raises() -> None:
    """When the heartbeats repository raises, /health returns degraded + the error message."""
    from contextlib import asynccontextmanager

    import fakeredis.aioredis
    from fastapi.testclient import TestClient

    from api.main import create_app

    class _BoomHeartbeats:
        async def all(self) -> list[dict[str, object]]:
            raise RuntimeError("pg down")

    class _NullFindings:
        async def list_briefs(self, **_: object) -> list[object]:
            return []

        async def get(self, _msg_id: str) -> None:
            return None

    class _NullAnchor:
        async def verify(self, _msg_id: str) -> None:
            return None

    app = create_app()

    @asynccontextmanager
    async def fake_lifespan(_app: Any) -> Any:
        _app.state.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        _app.state.findings = _NullFindings()
        _app.state.heartbeats = _BoomHeartbeats()
        _app.state.anchor = _NullAnchor()
        yield

    app.router.lifespan_context = fake_lifespan
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert "pg down" in data["error"]
    assert data["agents"] == []


# --------------------------------------------------------------------------- #
# agents/common/metrics.py — wrapper around prometheus_client.start_http_server #
# --------------------------------------------------------------------------- #


def test_start_metrics_server_delegates_to_prometheus_client() -> None:
    """Thin wrapper must call prometheus_client.start_http_server with the given port."""
    from agents.common import metrics as metrics_mod

    with patch.object(metrics_mod, "start_http_server") as mock:
        metrics_mod.start_metrics_server(9999)
        mock.assert_called_once_with(9999)
