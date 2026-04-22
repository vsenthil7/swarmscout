"""Coverage tests for api/main.py — lifespan context + run() entrypoint."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_lifespan_wires_state_and_tears_down() -> None:
    """The real _lifespan must: build context, attach to app.state, yield, and aclose on exit."""
    from api import main as api_main

    fake_ctx = SimpleNamespace(
        redis=object(),
        findings=object(),
        heartbeats=object(),
        anchor=object(),
        aclose=AsyncMock(),
    )
    app = SimpleNamespace(state=SimpleNamespace())

    with patch.object(api_main, "build_context", new=AsyncMock(return_value=fake_ctx)):
        async with api_main._lifespan(app):  # type: ignore[arg-type]
            # During the yield the state must be fully wired.
            assert app.state.ctx is fake_ctx
            assert app.state.redis is fake_ctx.redis
            assert app.state.findings is fake_ctx.findings
            assert app.state.heartbeats is fake_ctx.heartbeats
            assert app.state.anchor is fake_ctx.anchor

    # On exit the context's aclose() must have been awaited exactly once.
    fake_ctx.aclose.assert_awaited_once()


def test_run_entrypoint_invokes_uvicorn_with_expected_args() -> None:
    """``run()`` must hand the app string + settings-sourced reload flag to uvicorn."""
    from api import main as api_main

    fake_settings = SimpleNamespace(env="development", api_rate_limit_per_minute=60)

    with patch.object(api_main, "get_settings", return_value=fake_settings), \
         patch.object(api_main, "uvicorn") as mock_uvicorn:
        api_main.run()

    mock_uvicorn.run.assert_called_once()
    args, kwargs = mock_uvicorn.run.call_args
    assert args[0] == "api.main:app"
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 8000
    assert kwargs["reload"] is True  # because env == development


def test_run_entrypoint_reload_false_when_env_not_development() -> None:
    """Reload must be False when env is anything other than 'development'."""
    from api import main as api_main

    fake_settings = SimpleNamespace(env="production", api_rate_limit_per_minute=60)

    with patch.object(api_main, "get_settings", return_value=fake_settings), \
         patch.object(api_main, "uvicorn") as mock_uvicorn:
        api_main.run()

    _, kwargs = mock_uvicorn.run.call_args
    assert kwargs["reload"] is False


def test_rate_limit_middleware_allows_first_and_blocks_overflow() -> None:
    """Middleware increments Redis, sets EXPIRE on first hit, 429s on overflow."""
    from contextlib import asynccontextmanager

    import fakeredis.aioredis
    from fastapi.testclient import TestClient

    from api.main import create_app

    app = create_app()

    @asynccontextmanager
    async def fake_lifespan(_app: Any) -> Any:
        _app.state.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        _app.state.findings = SimpleNamespace(
            list_briefs=AsyncMock(return_value=[]),
            get=AsyncMock(return_value=None),
        )
        _app.state.heartbeats = SimpleNamespace(all=AsyncMock(return_value=[]))
        _app.state.anchor = SimpleNamespace(verify=AsyncMock(return_value=None))
        yield

    app.router.lifespan_context = fake_lifespan
    with TestClient(app) as client:
        # Fire > capacity (60) requests — eventually 429.
        last = 200
        for _ in range(70):
            last = client.get("/ready").status_code
            if last == 429:
                break
        assert last == 429
