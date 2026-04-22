"""WebSocket endpoint streaming live briefs to the dashboard.

Subscribes to ``pubsub:briefs`` — the agents publish new briefs there *in
addition* to ``stream:briefs`` — so every connected client gets a push
without needing XREAD. On disconnect we clean up the pubsub client cleanly.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agents.common.logging_config import get_logger

log = get_logger("api.ws")

router = APIRouter(tags=["ws"])


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    """Stream brief events to the client until they disconnect."""
    await websocket.accept()
    redis = websocket.app.state.redis
    pubsub = redis.pubsub()
    await pubsub.subscribe("pubsub:briefs")
    try:
        await websocket.send_text(json.dumps({"type": "hello"}))
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg is None:
                await asyncio.sleep(0)
                continue
            data = msg.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            await websocket.send_text(str(data))
    except WebSocketDisconnect:
        log.info("ws_client_disconnected")
    except Exception:
        log.exception("ws_error")
    finally:
        await pubsub.unsubscribe("pubsub:briefs")
        await pubsub.aclose()
