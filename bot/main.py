"""Telegram bot entrypoint.

Runs two concurrent loops:

1. ``aiogram`` dispatcher for inbound commands.
2. ``_delivery_loop`` that consumes ``stream:briefs`` and pushes each new
   brief to every active subscriber whose threshold it meets.

Dedup is via a Redis SET ``bot:delivered:<chat_id>`` holding msg_ids already
sent; this is robust across restarts.

Rate-limited outbound: on Telegram 429 the loop sleeps for the retry-after
window before continuing.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from agents.common.bus import BusMessage
from agents.common.context import Context, build_context
from agents.common.logging_config import configure_logging, get_logger
from agents.common.schemas.envelope import StreamName
from bot.handlers.commands import build_router, passes_threshold

log = get_logger("bot")

DELIVERY_GROUP = "bot:delivery"
CONSUMER_NAME = "bot-1"


async def _delivery_loop(ctx: Context, bot: Bot) -> None:
    """Consume briefs and forward to each active subscriber."""
    async for msg in ctx.bus.consume(
        stream=StreamName.BRIEFS, group=DELIVERY_GROUP, consumer=CONSUMER_NAME
    ):
        try:
            await _dispatch_one(ctx, bot, msg)
            await ctx.bus.ack(StreamName.BRIEFS, DELIVERY_GROUP, msg.entry_id)
        except Exception:  # noqa: BLE001
            log.exception("bot_delivery_failed", entry_id=msg.entry_id)


async def _dispatch_one(ctx: Context, bot: Bot, msg: BusMessage) -> None:
    """Filter + dedup + send one brief to every subscriber that wants it."""
    brief = msg.envelope.payload
    conviction = str(brief.get("conviction_tier", "degen"))
    token_name = str(brief.get("token_name", "unknown"))
    token_addr = str(brief.get("token_address", ""))
    thesis = str(brief.get("thesis", ""))
    caveats = brief.get("caveats") or []
    msg_id = msg.envelope.msg_id

    subscribers = await ctx.subscriptions.list_active()
    for chat_id, threshold in subscribers:
        if not passes_threshold(conviction, threshold):
            continue
        dedup_key = f"bot:delivered:{chat_id}"
        already = await ctx.redis.sismember(dedup_key, msg_id)
        if already:
            continue
        body = _format_brief(token_name, token_addr, conviction, thesis, caveats, msg_id)
        try:
            await bot.send_message(chat_id, body)
            await ctx.redis.sadd(dedup_key, msg_id)
            await ctx.redis.expire(dedup_key, 7 * 24 * 3600)
        except TelegramRetryAfter as err:
            log.warning("telegram_rate_limited", seconds=err.retry_after)
            await asyncio.sleep(err.retry_after + 1)
        except Exception:  # noqa: BLE001
            log.exception("bot_send_failed", chat_id=chat_id, msg_id=msg_id)


def _format_brief(
    name: str,
    address: str,
    conviction: str,
    thesis: str,
    caveats: list[str],
    msg_id: str,
) -> str:
    """Format a brief for Telegram (Markdown)."""
    head = f"*{name}* — conviction: *{conviction}*"
    body = thesis[:900]
    caveat_block = ""
    if caveats:
        caveat_block = "\n\n*Caveats*:\n" + "\n".join(f"• {c}" for c in caveats[:5])
    link = f"https://testnet.bscscan.com/token/{address}"
    footer = f"\n\n[BscScan]({link}) · `{msg_id}`"
    return f"{head}\n\n{body}{caveat_block}{footer}"


async def _amain() -> None:
    """Async process entrypoint for the Telegram bot.

    Runs the aiogram dispatcher and the brief-delivery loop concurrently,
    tearing both down on SIGINT.
    """
    configure_logging()
    ctx = await build_context()
    bot = Bot(
        token=ctx.settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()
    dp.include_router(build_router(ctx))

    delivery_task = asyncio.create_task(_delivery_loop(ctx, bot))
    try:
        await dp.start_polling(bot)
    finally:
        delivery_task.cancel()
        with suppress(asyncio.CancelledError):
            await delivery_task
        await bot.session.close()
        await ctx.aclose()


def run() -> None:
    """Process entrypoint."""
    asyncio.run(_amain())


if __name__ == "__main__":
    run()
