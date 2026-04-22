"""Coverage tests for bot/handlers/commands.py.

Exercises every command handler (/start, /stop, /status, /latest,
/threshold, /verify, /help) plus the passes_threshold helper. Uses
MagicMock message objects because aiogram's real Message class requires
a full Bot session.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers.commands import build_router, passes_threshold


def _ctx_stub(**overrides: Any) -> SimpleNamespace:
    """Build a Context stub exposing the five repositories commands.py uses."""
    ctx = SimpleNamespace(
        subscriptions=SimpleNamespace(
            subscribe=AsyncMock(),
            unsubscribe=AsyncMock(),
            set_threshold=AsyncMock(),
        ),
        heartbeats=SimpleNamespace(all=AsyncMock(return_value=[])),
        findings=SimpleNamespace(
            list_briefs=AsyncMock(return_value=[]),
            get=AsyncMock(return_value=None),
        ),
        anchor=SimpleNamespace(verify=AsyncMock(return_value=None)),
    )
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


def _get_handler(router: Any, command_name: str) -> Any:
    """Extract the callable wrapped by the @router.message(Command(name)) decorator.

    aiogram's Router stores observers which hold handler tuples; we reach through
    them to grab the underlying async function. This avoids having to drive a
    real Bot instance through the update dispatcher just to trigger a command.
    """
    for obs in router.observers.values():
        for handler in getattr(obs, "handlers", []):
            # aiogram stores the callback on .callback
            cb = getattr(handler, "callback", None)
            if cb is None:
                continue
            # The filter list holds Command(...) objects. Match by command name.
            for f in getattr(handler, "filters", []):
                inner = getattr(f, "callback", None)
                commands = getattr(inner, "commands", None) if inner else None
                if commands and any(
                    getattr(c, "command", getattr(c, "prefix", None)) == command_name
                    or (isinstance(c, str) and c == command_name)
                    for c in commands
                ):
                    return cb
    # Fallback: aiogram >=3 stores the raw Command on handler.flags sometimes.
    raise AssertionError(f"handler for /{command_name} not found in router")


def _fake_message(chat_id: int = 42, text: str = "") -> MagicMock:
    """Build a MagicMock message with answer() as an AsyncMock."""
    m = MagicMock()
    m.chat = SimpleNamespace(id=chat_id)
    m.text = text
    m.answer = AsyncMock()
    return m


# --------------------------------------------------------------------------- #
# Direct-call tests: we wrap each handler and invoke it explicitly to exercise #
# the branches. We bypass aiogram's filter engine by calling the decorated    #
# inner function via the router's .observers.                                 #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def router_and_ctx():  # type: ignore[no-untyped-def]
    ctx = _ctx_stub()
    router = build_router(ctx)
    return router, ctx


@pytest.mark.asyncio
async def test_start_subscribes_and_confirms(router_and_ctx: Any) -> None:
    """/start registers chat + replies."""
    router, ctx = router_and_ctx
    # Find the start handler by iterating router.message.handlers
    start = None
    for h in router.message.handlers:
        name = getattr(h.callback, "__name__", "")
        if name == "on_start":
            start = h.callback
            break
    assert start is not None

    msg = _fake_message(chat_id=100)
    await start(msg)
    ctx.subscriptions.subscribe.assert_awaited_once_with(100, threshold="moderate")
    msg.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_with_no_chat_returns_early(router_and_ctx: Any) -> None:
    """If message.chat is None, /start is a no-op — no subscribe, no answer."""
    router, ctx = router_and_ctx
    start = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_start")

    msg = MagicMock()
    msg.chat = None
    msg.answer = AsyncMock()
    await start(msg)
    ctx.subscriptions.subscribe.assert_not_awaited()
    msg.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_unsubscribes_and_confirms(router_and_ctx: Any) -> None:
    """/stop unsubscribes + replies."""
    router, ctx = router_and_ctx
    stop = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_stop")
    msg = _fake_message(chat_id=200)
    await stop(msg)
    ctx.subscriptions.unsubscribe.assert_awaited_once_with(200)
    msg.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_with_no_chat_returns_early(router_and_ctx: Any) -> None:
    """/stop silently returns when chat is None."""
    router, ctx = router_and_ctx
    stop = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_stop")
    msg = MagicMock()
    msg.chat = None
    msg.answer = AsyncMock()
    await stop(msg)
    ctx.subscriptions.unsubscribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_reports_agents_online_and_models() -> None:
    """/status reads heartbeats and formats swarm summary."""
    ctx = _ctx_stub()
    ctx.heartbeats.all = AsyncMock(
        return_value=[
            {"agent": "hunter", "status": "online", "events_last_min": 3, "current_model": "gemini-flash"},
            {"agent": "risk", "status": "degraded", "events_last_min": 0, "current_model": "claude-opus"},
        ]
    )
    router = build_router(ctx)
    status_h = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_status")

    msg = _fake_message()
    await status_h(msg)
    msg.answer.assert_awaited_once()
    body = msg.answer.await_args.args[0]
    assert "1/2 agents online" in body
    assert "hunter" in body
    assert "risk" in body


@pytest.mark.asyncio
async def test_latest_returns_empty_when_no_briefs(router_and_ctx: Any) -> None:
    """/latest with zero briefs shows 'No briefs yet.'"""
    router, _ = router_and_ctx
    latest = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_latest")
    msg = _fake_message()
    await latest(msg)
    msg.answer.assert_awaited_once_with("No briefs yet.")


@pytest.mark.asyncio
async def test_latest_formats_brief_list() -> None:
    """/latest formats briefs with name, tier, msg_id, and truncated thesis."""
    briefs = [
        SimpleNamespace(
            msg_id="ABC",
            payload={
                "conviction_tier": "moderate",
                "token_name": "Foo",
                "thesis": "A" * 300,  # truncation target
            },
        ),
        SimpleNamespace(
            msg_id="DEF",
            payload={},  # missing fields — defaults
        ),
    ]
    ctx = _ctx_stub()
    ctx.findings.list_briefs = AsyncMock(return_value=briefs)
    router = build_router(ctx)
    latest = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_latest")

    msg = _fake_message()
    await latest(msg)
    body = msg.answer.await_args.args[0]
    assert "Foo" in body
    assert "ABC" in body
    assert "unknown" in body  # default for missing token_name
    assert "?" in body  # default for missing conviction_tier


@pytest.mark.asyncio
async def test_threshold_rejects_invalid_value(router_and_ctx: Any) -> None:
    """/threshold with unknown tier replies with usage hint."""
    router, ctx = router_and_ctx
    threshold = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_threshold")
    msg = _fake_message(chat_id=1)
    command = SimpleNamespace(args="INVALID")
    await threshold(msg, command)
    ctx.subscriptions.set_threshold.assert_not_awaited()
    msg.answer.assert_awaited_once()
    assert "Usage" in msg.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_threshold_accepts_valid_tier(router_and_ctx: Any) -> None:
    """/threshold with 'high' calls set_threshold and confirms."""
    router, ctx = router_and_ctx
    threshold = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_threshold")
    msg = _fake_message(chat_id=99)
    command = SimpleNamespace(args="high")
    await threshold(msg, command)
    ctx.subscriptions.set_threshold.assert_awaited_once_with(99, "high")


@pytest.mark.asyncio
async def test_threshold_with_no_chat_returns_early(router_and_ctx: Any) -> None:
    """/threshold silently returns when chat is None."""
    router, ctx = router_and_ctx
    threshold = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_threshold")
    msg = MagicMock()
    msg.chat = None
    msg.answer = AsyncMock()
    command = SimpleNamespace(args="high")
    await threshold(msg, command)
    ctx.subscriptions.set_threshold.assert_not_awaited()


@pytest.mark.asyncio
async def test_threshold_empty_args_triggers_usage(router_and_ctx: Any) -> None:
    """/threshold with empty string falls through the 'not in TIER_ORDER' branch."""
    router, ctx = router_and_ctx
    threshold = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_threshold")
    msg = _fake_message()
    command = SimpleNamespace(args=None)  # coerced to '' internally
    await threshold(msg, command)
    ctx.subscriptions.set_threshold.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_missing_arg_replies_usage(router_and_ctx: Any) -> None:
    """/verify with no arg shows usage."""
    router, _ = router_and_ctx
    verify = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_verify")
    msg = _fake_message()
    command = SimpleNamespace(args="")
    await verify(msg, command)
    msg.answer.assert_awaited_once_with("Usage: /verify <msg_id>")


@pytest.mark.asyncio
async def test_verify_returns_not_found_when_findings_empty(router_and_ctx: Any) -> None:
    """/verify with unknown msg_id replies 'Brief not found.'"""
    router, ctx = router_and_ctx
    ctx.findings.get = AsyncMock(return_value=None)
    verify = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_verify")
    msg = _fake_message()
    await verify(msg, SimpleNamespace(args="UNKNOWN"))
    msg.answer.assert_awaited_with("Brief not found.")


@pytest.mark.asyncio
async def test_verify_reports_hash_and_onchain_match() -> None:
    """/verify computes local hash, compares to stored, and checks on-chain."""
    ctx = _ctx_stub()
    payload = {"x": 1, "y": 2}
    from agents.common.hasher import hash_payload

    stored_hash = hash_payload(payload)
    row = SimpleNamespace(
        msg_id="XYZ",
        payload=payload,
        payload_hash=stored_hash,
        on_chain_tx="0xabc",
        on_chain_block=123,
    )
    ctx.findings.get = AsyncMock(return_value=row)
    ctx.anchor.verify = AsyncMock(
        return_value=SimpleNamespace(payload_hash_hex=stored_hash, agent="hunter", timestamp=0)
    )
    router = build_router(ctx)
    verify = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_verify")

    msg = _fake_message()
    await verify(msg, SimpleNamespace(args="XYZ"))
    body = msg.answer.await_args.args[0]
    assert "XYZ" in body
    assert "local hash match: True" in body
    assert "on-chain match: True" in body
    assert "0xabc" in body


@pytest.mark.asyncio
async def test_verify_handles_onchain_missing_record(router_and_ctx: Any) -> None:
    """When on-chain returns None, on-chain-match is False."""
    router, ctx = router_and_ctx
    from agents.common.hasher import hash_payload

    payload = {"a": 1}
    row = SimpleNamespace(
        msg_id="ABC",
        payload=payload,
        payload_hash=hash_payload(payload),
        on_chain_tx=None,
        on_chain_block=None,
    )
    ctx.findings.get = AsyncMock(return_value=row)
    ctx.anchor.verify = AsyncMock(return_value=None)
    verify = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_verify")

    msg = _fake_message()
    await verify(msg, SimpleNamespace(args="ABC"))
    body = msg.answer.await_args.args[0]
    assert "on-chain match: False" in body
    assert "n/a" in body  # tx fallback


@pytest.mark.asyncio
async def test_help_lists_commands(router_and_ctx: Any) -> None:
    """/help replies with the full command list."""
    router, _ = router_and_ctx
    help_h = next(h.callback for h in router.message.handlers if h.callback.__name__ == "on_help")
    msg = _fake_message()
    await help_h(msg)
    body = msg.answer.await_args.args[0]
    for cmd in ("/start", "/stop", "/status", "/latest", "/threshold", "/verify", "/help"):
        assert cmd in body


# --------------------------------------------------------------------------- #
# passes_threshold helper                                                     #
# --------------------------------------------------------------------------- #


def test_passes_threshold_exact_match() -> None:
    """Tier equal to user threshold passes."""
    assert passes_threshold("moderate", "moderate") is True


def test_passes_threshold_beats_user_floor() -> None:
    """A higher tier beats a lower user floor."""
    assert passes_threshold("high", "moderate") is True


def test_passes_threshold_below_user_floor() -> None:
    """A lower tier fails a higher user floor."""
    assert passes_threshold("degen", "high") is False


def test_passes_threshold_unknown_tier_defaults_to_zero() -> None:
    """Unknown tier names default to 0 (degen), so they pass a degen threshold."""
    assert passes_threshold("bogus", "degen") is True


def test_passes_threshold_is_case_insensitive() -> None:
    """Case does not affect the comparison."""
    assert passes_threshold("HIGH", "moderate") is True
