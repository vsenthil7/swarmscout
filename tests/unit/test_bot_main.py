"""Coverage tests for bot/main.py — delivery loop, dispatch, formatter, entrypoint."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
from aiogram.exceptions import TelegramRetryAfter

from agents.common.bus import Bus, BusMessage
from agents.common.envelope_builder import build_envelope
from agents.common.schemas.envelope import AgentName, StreamName
from bot.main import (
    _dispatch_one,
    _format_brief,
)


class _FakeBot:
    """Minimal Bot stand-in with an AsyncMock send_message + session.close."""

    def __init__(self) -> None:
        self.send_message = AsyncMock()
        self.session = SimpleNamespace(close=AsyncMock())


def _ctx_stub(subs: list[tuple[int, str]] | None = None) -> SimpleNamespace:
    """Build a Context stand-in for bot dispatch."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return SimpleNamespace(
        bus=Bus(url="redis://fake", client=redis),
        redis=redis,
        subscriptions=SimpleNamespace(
            list_active=AsyncMock(return_value=subs or []),
        ),
    )


def _bus_message_with_brief(**brief_fields: Any) -> BusMessage:
    """Build a BusMessage whose envelope carries a brief-shaped payload."""
    payload = {
        "token_name": "FooToken",
        "token_address": "0x" + "a" * 40,
        "conviction_tier": "moderate",
        "thesis": "A detailed thesis about this token.",
        "caveats": ["caveat-one", "caveat-two"],
        **brief_fields,
    }
    env = build_envelope(agent=AgentName.NARRATOR, payload=payload)
    return BusMessage(stream=StreamName.BRIEFS.value, entry_id="1-0", envelope=env)


# --------------------------------------------------------------------------- #
# _format_brief                                                               #
# --------------------------------------------------------------------------- #


def test_format_brief_builds_markdown_with_all_fields() -> None:
    """_format_brief produces a Markdown string with token, conviction, thesis, caveats, footer."""
    body = _format_brief(
        name="FooToken",
        address="0x" + "a" * 40,
        conviction="high",
        thesis="Thesis text here.",
        caveats=["one", "two"],
        msg_id="MSGID",
    )
    assert "*FooToken*" in body
    assert "conviction: *high*" in body
    assert "Thesis text here." in body
    assert "• one" in body
    assert "• two" in body
    assert "testnet.bscscan.com/token/0x" + "a" * 40 in body
    assert "`MSGID`" in body


def test_format_brief_without_caveats_omits_block() -> None:
    """When caveats is empty, no 'Caveats' section is rendered."""
    body = _format_brief(
        name="T", address="0x" + "b" * 40, conviction="degen",
        thesis="x", caveats=[], msg_id="M",
    )
    assert "Caveats" not in body


def test_format_brief_truncates_long_thesis() -> None:
    """Thesis longer than 900 chars is truncated."""
    body = _format_brief(
        name="T", address="0x" + "c" * 40, conviction="high",
        thesis="A" * 2000, caveats=[], msg_id="M",
    )
    # Body must contain at most 900 As in the thesis slice.
    assert body.count("A") <= 900 + 5  # small tolerance for "Caveats" etc (absent here)


def test_format_brief_truncates_caveats_to_five() -> None:
    """Only the first 5 caveats are rendered."""
    body = _format_brief(
        name="T", address="0x" + "c" * 40, conviction="high",
        thesis="x", caveats=[f"cav{i}" for i in range(10)], msg_id="M",
    )
    for i in range(5):
        assert f"cav{i}" in body
    assert "cav5" not in body


# --------------------------------------------------------------------------- #
# _dispatch_one                                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dispatch_one_sends_to_subscriber_above_threshold() -> None:
    """Dispatches to a subscriber whose threshold is <= brief's conviction."""
    ctx = _ctx_stub(subs=[(100, "moderate")])
    bot = _FakeBot()
    msg = _bus_message_with_brief(conviction_tier="high")
    await _dispatch_one(ctx, bot, msg)
    bot.send_message.assert_awaited_once()
    chat_id_arg = bot.send_message.await_args.args[0]
    assert chat_id_arg == 100
    # Redis dedup key populated.
    assert await ctx.redis.sismember("bot:delivered:100", msg.envelope.msg_id)


@pytest.mark.asyncio
async def test_dispatch_one_skips_subscriber_below_threshold() -> None:
    """A 'high'-threshold subscriber does NOT receive a 'degen' brief."""
    ctx = _ctx_stub(subs=[(200, "high")])
    bot = _FakeBot()
    msg = _bus_message_with_brief(conviction_tier="degen")
    await _dispatch_one(ctx, bot, msg)
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_one_skips_already_delivered() -> None:
    """If msg_id is already in the dedup set, don't resend."""
    ctx = _ctx_stub(subs=[(300, "degen")])
    bot = _FakeBot()
    msg = _bus_message_with_brief(conviction_tier="moderate")
    # Pre-seed dedup.
    await ctx.redis.sadd(f"bot:delivered:300", msg.envelope.msg_id)
    await _dispatch_one(ctx, bot, msg)
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_one_swallows_telegram_retry_after() -> None:
    """TelegramRetryAfter triggers a sleep; loop keeps going next subscriber."""
    ctx = _ctx_stub(subs=[(400, "degen"), (401, "degen")])
    bot = _FakeBot()

    # First call raises retry-after, second succeeds.
    call_count = {"n": 0}

    async def side_effect(*a: Any, **kw: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise TelegramRetryAfter(
                method=MagicMock(), message="flood", retry_after=0
            )

    bot.send_message.side_effect = side_effect
    msg = _bus_message_with_brief(conviction_tier="moderate")

    # Patch asyncio.sleep so the test doesn't actually wait.
    with patch("bot.main.asyncio.sleep", new=AsyncMock()):
        await _dispatch_one(ctx, bot, msg)

    assert call_count["n"] == 2  # both subscribers attempted


@pytest.mark.asyncio
async def test_dispatch_one_swallows_arbitrary_send_exception() -> None:
    """A non-Telegram send exception is logged but does not propagate."""
    ctx = _ctx_stub(subs=[(500, "degen")])
    bot = _FakeBot()
    bot.send_message.side_effect = RuntimeError("something broke")
    msg = _bus_message_with_brief(conviction_tier="moderate")
    # Should NOT raise.
    await _dispatch_one(ctx, bot, msg)


# --------------------------------------------------------------------------- #
# _delivery_loop — wired through a stub bus                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_delivery_loop_acks_and_continues_on_failure() -> None:
    """_delivery_loop: on processing exception, log and skip ack; on success, ack."""
    from bot.main import _delivery_loop

    ctx = _ctx_stub(subs=[(600, "degen")])
    bot = _FakeBot()

    msg1 = _bus_message_with_brief(conviction_tier="high")
    msg2 = _bus_message_with_brief(conviction_tier="moderate")

    # Replace bus.consume with an async generator yielding our scripted msgs.
    async def fake_consume(**_: Any):  # type: ignore[no-untyped-def]
        yield msg1
        yield msg2

    ctx.bus.consume = fake_consume  # type: ignore[assignment]
    ctx.bus.ack = AsyncMock()

    # First dispatch succeeds, second raises — via _dispatch_one patched.
    call = {"n": 0}

    async def fake_dispatch(*_a: Any, **_kw: Any) -> None:
        call["n"] += 1
        if call["n"] == 2:
            raise RuntimeError("dispatch boom")

    with patch("bot.main._dispatch_one", new=fake_dispatch):
        await _delivery_loop(ctx, bot)

    # First message was acked, second was not.
    assert ctx.bus.ack.await_count == 1


# --------------------------------------------------------------------------- #
# _amain + run entrypoint                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_amain_wires_dispatcher_and_delivery_loop() -> None:
    """_amain starts the dispatcher + delivery loop, then cleans up on exit."""
    from bot import main as bot_main

    fake_ctx = SimpleNamespace(
        settings=SimpleNamespace(telegram_bot_token="123:abc"),
        bus=Bus(url="redis://fake", client=fakeredis.aioredis.FakeRedis(decode_responses=True)),
        redis=fakeredis.aioredis.FakeRedis(decode_responses=True),
        subscriptions=SimpleNamespace(list_active=AsyncMock(return_value=[])),
        heartbeats=SimpleNamespace(all=AsyncMock(return_value=[])),
        findings=SimpleNamespace(
            list_briefs=AsyncMock(return_value=[]),
            get=AsyncMock(return_value=None),
        ),
        anchor=SimpleNamespace(verify=AsyncMock(return_value=None)),
        aclose=AsyncMock(),
    )

    mock_bot = MagicMock()
    mock_bot.session.close = AsyncMock()

    mock_dp = MagicMock()
    mock_dp.include_router = MagicMock()
    mock_dp.start_polling = AsyncMock()

    async def fake_build_context() -> SimpleNamespace:
        return fake_ctx

    async def fake_delivery_loop(*_a: Any, **_kw: Any) -> None:
        return None

    with patch.object(bot_main, "build_context", new=fake_build_context), \
         patch.object(bot_main, "Bot", return_value=mock_bot), \
         patch.object(bot_main, "Dispatcher", return_value=mock_dp), \
         patch.object(bot_main, "_delivery_loop", new=fake_delivery_loop):
        await bot_main._amain()

    mock_dp.start_polling.assert_awaited_once()
    fake_ctx.aclose.assert_awaited_once()
    mock_bot.session.close.assert_awaited_once()


def test_run_entrypoint_invokes_amain_via_asyncio_run() -> None:
    """run() shims to asyncio.run(_amain())."""
    from bot import main as bot_main

    with patch.object(bot_main.asyncio, "run") as mock_run:
        bot_main.run()
    mock_run.assert_called_once()
