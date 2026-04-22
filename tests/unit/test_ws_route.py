"""Coverage tests for api/routes/ws.py — the live brief WebSocket endpoint.

Drives the route via FastAPI TestClient.websocket_connect() against a fake
pubsub. Exercises: hello frame, data frame (bytes + str), None tick, normal
disconnect, and the broad Exception branch.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

import fakeredis.aioredis
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.main import create_app


class _NullFindings:
    async def list_briefs(self, **_: object) -> list[object]:
        return []

    async def get(self, _msg_id: str) -> None:
        return None


class _NullHeartbeats:
    async def all(self) -> list[dict[str, object]]:
        return []


class _NullAnchor:
    async def verify(self, _msg_id: str) -> None:
        return None


class _FakePubSub:
    """Minimal pubsub client that hands out scripted messages then ``None``."""

    def __init__(self, scripted: list[Any] | None = None) -> None:
        self._scripted: list[Any] = list(scripted or [])
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed.append(channel)

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed.append(channel)

    async def get_message(self, *, ignore_subscribe_messages: bool = True, timeout: float = 1.0) -> Any:
        # ignore the kwargs, they are for real redis.
        _ = (ignore_subscribe_messages, timeout)
        if self._scripted:
            return self._scripted.pop(0)
        # Simulate exhaustion by sleeping and returning None, letting the
        # outer loop advance so a disconnect can be detected.
        await asyncio.sleep(0)
        return None

    async def aclose(self) -> None:
        self.closed = True


class _FakeRedisWithPubSub:
    """Wraps a real fakeredis but overrides ``.pubsub()`` to return our fake."""

    def __init__(self, pubsub: _FakePubSub, backing: fakeredis.aioredis.FakeRedis) -> None:
        self._pubsub = pubsub
        self._backing = backing

    def pubsub(self) -> _FakePubSub:
        return self._pubsub

    # Rate-limit middleware still runs; proxy through to backing redis.
    async def incr(self, key: str) -> int:
        return await self._backing.incr(key)

    async def expire(self, key: str, seconds: int) -> int:
        return await self._backing.expire(key, seconds)


def _client_with(pubsub: _FakePubSub) -> TestClient:
    """Build a TestClient whose app.state.redis exposes our fake pubsub."""
    app = create_app()
    backing = fakeredis.aioredis.FakeRedis(decode_responses=True)
    redis = _FakeRedisWithPubSub(pubsub, backing)

    @asynccontextmanager
    async def fake_lifespan(_app: Any) -> Any:
        _app.state.redis = redis
        _app.state.findings = _NullFindings()
        _app.state.heartbeats = _NullHeartbeats()
        _app.state.anchor = _NullAnchor()
        yield

    app.router.lifespan_context = fake_lifespan
    return TestClient(app)


def test_ws_hello_frame_and_bytes_message_and_normal_disconnect() -> None:
    """A subscribed client receives the hello frame then a decoded bytes payload."""
    pubsub = _FakePubSub(
        scripted=[
            {"type": "message", "data": b"hello-world"},  # bytes branch
        ]
    )
    with _client_with(pubsub) as client, client.websocket_connect("/ws/events") as ws:
        hello = ws.receive_text()
        assert json.loads(hello) == {"type": "hello"}
        frame = ws.receive_text()
        assert frame == "hello-world"
            # Client disconnects normally by exiting the `with` block.
    assert "pubsub:briefs" in pubsub.subscribed
    assert "pubsub:briefs" in pubsub.unsubscribed
    assert pubsub.closed is True


def test_ws_handles_websocket_disconnect_explicitly() -> None:
    """Client disconnecting mid-stream raises WebSocketDisconnect; the handler logs and exits cleanly."""

    class _DisconnectingWS:
        """WebSocket stand-in whose send_text raises WebSocketDisconnect after the hello frame."""

        def __init__(self, pubsub: _FakePubSub) -> None:
            self.sent: list[str] = []

            class _App:
                class state:
                    redis = _FakeRedisWithPubSub(
                        pubsub, fakeredis.aioredis.FakeRedis(decode_responses=True)
                    )

            self.app = _App()

        async def accept(self) -> None:
            return None

        async def send_text(self, data: str) -> None:
            self.sent.append(data)
            # First send is the hello frame; second is a real payload -> client has gone.
            if len(self.sent) >= 2:
                raise WebSocketDisconnect(code=1000)

    from api.routes.ws import ws_events

    pubsub = _FakePubSub(
        scripted=[
            {"type": "message", "data": b"first-brief"},
            {"type": "message", "data": b"second-brief"},
        ]
    )
    ws = _DisconnectingWS(pubsub)

    asyncio.run(ws_events(ws))  # type: ignore[arg-type]

    # Hello frame delivered, then client disconnected during the first payload send.
    assert len(ws.sent) == 2
    assert "pubsub:briefs" in pubsub.unsubscribed
    assert pubsub.closed is True


def test_ws_string_payload_passes_through() -> None:
    """A pubsub message whose ``data`` is already a str is forwarded verbatim."""
    pubsub = _FakePubSub(
        scripted=[
            {"type": "message", "data": "already-a-string"},  # str branch
        ]
    )
    with _client_with(pubsub) as client, client.websocket_connect("/ws/events") as ws:
        _ = ws.receive_text()  # hello
        frame = ws.receive_text()
        assert frame == "already-a-string"


def test_ws_none_tick_skips_without_sending() -> None:
    """When ``get_message`` returns None the loop continues without pushing."""
    pubsub = _FakePubSub(scripted=[None, {"type": "message", "data": "after-tick"}])
    with _client_with(pubsub) as client, client.websocket_connect("/ws/events") as ws:
        _ = ws.receive_text()  # hello
        frame = ws.receive_text()
        assert frame == "after-tick"


def test_ws_handles_unexpected_exception_in_pubsub_loop() -> None:
    class _BoomPubSub(_FakePubSub):
        async def get_message(self, *, ignore_subscribe_messages: bool = True, timeout: float = 1.0) -> Any:
            raise RuntimeError("boom")

    class _FakeWS:
        """Smallest WebSocket stand-in that satisfies the handler's usage."""

        def __init__(self, pubsub: _FakePubSub) -> None:
            self.sent: list[str] = []

            class _App:
                class state:
                    redis = _FakeRedisWithPubSub(
                        pubsub, fakeredis.aioredis.FakeRedis(decode_responses=True)
                    )

            self.app = _App()

        async def accept(self) -> None:
            return None

        async def send_text(self, data: str) -> None:
            self.sent.append(data)

    from api.routes.ws import ws_events

    pubsub = _BoomPubSub()
    ws = _FakeWS(pubsub)

    async def run() -> None:
        # Handler must complete (not raise out) even when get_message blows up.
        await ws_events(ws)  # type: ignore[arg-type]

    asyncio.run(run())

    # hello frame was sent, then the loop blew up, the broad except caught it,
    # and the finally block unsubscribed and closed pubsub.
    assert ws.sent and json.loads(ws.sent[0]) == {"type": "hello"}
    assert "pubsub:briefs" in pubsub.unsubscribed
    assert pubsub.closed is True
