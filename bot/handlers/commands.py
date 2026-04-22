"""Command handlers for the Telegram bot (FR-161).

Commands:
    /start          — subscribe to alerts
    /stop           — unsubscribe
    /status         — show own threshold + swarm health
    /latest         — show 5 most recent briefs
    /threshold      — set conviction threshold
    /verify <id>    — re-verify a brief id against on-chain
    /help           — list commands

Each handler is a thin orchestration layer — all persistence sits in
the repositories so the handlers are trivially testable.
"""

from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command, CommandObject

from agents.common.context import Context
from agents.common.hasher import hash_payload
from agents.common.schemas.payloads import ConvictionTier

TIER_ORDER = {t.value: i for i, t in enumerate(list(ConvictionTier))}


def build_router(ctx: Context) -> Router:
    """Return an ``aiogram.Router`` bound to ``ctx``."""
    router = Router(name="commands")

    @router.message(Command("start"))
    async def on_start(message: types.Message) -> None:
        """Subscribe the sender; confirm with current threshold."""
        if message.chat is None:
            return
        await ctx.subscriptions.subscribe(message.chat.id, threshold="moderate")
        await message.answer(
            "You are subscribed to SwarmScout. Default threshold: *moderate*.\n"
            "Use /threshold to change, /help for all commands.",
            parse_mode="Markdown",
        )

    @router.message(Command("stop"))
    async def on_stop(message: types.Message) -> None:
        """Unsubscribe the sender."""
        if message.chat is None:
            return
        await ctx.subscriptions.unsubscribe(message.chat.id)
        await message.answer("Unsubscribed. Use /start to re-enable at any time.")

    @router.message(Command("status"))
    async def on_status(message: types.Message) -> None:
        """Show swarm health plus the sender's threshold."""
        hbs = await ctx.heartbeats.all()
        online = sum(1 for h in hbs if h.get("status") == "online")
        lines = [
            f"Swarm: {online}/{len(hbs)} agents online",
        ]
        for h in hbs:
            lines.append(
                f"• {h['agent']}: {h['status']} — {h.get('events_last_min', 0)} evt/min "
                f"(model: {h.get('current_model', 'n/a')})"
            )
        await message.answer("\n".join(lines))

    @router.message(Command("latest"))
    async def on_latest(message: types.Message) -> None:
        """List the 5 most recent briefs."""
        briefs = await ctx.findings.list_briefs(limit=5, offset=0)
        if not briefs:
            await message.answer("No briefs yet.")
            return
        lines: list[str] = []
        for b in briefs:
            p = b.payload
            tier = p.get("conviction_tier", "?")
            name = p.get("token_name", "unknown")
            thesis = str(p.get("thesis", ""))[:200]
            lines.append(f"*{name}* ({tier})\n`{b.msg_id}`\n{thesis}\n")
        await message.answer("\n\n".join(lines), parse_mode="Markdown")

    @router.message(Command("threshold"))
    async def on_threshold(message: types.Message, command: CommandObject) -> None:
        """Set the conviction threshold: degen | speculative | moderate | high."""
        if message.chat is None:
            return
        arg = (command.args or "").strip().lower()
        if arg not in TIER_ORDER:
            await message.answer(
                "Usage: /threshold <degen|speculative|moderate|high>",
            )
            return
        await ctx.subscriptions.set_threshold(message.chat.id, arg)
        await message.answer(f"Threshold set to *{arg}*.", parse_mode="Markdown")

    @router.message(Command("verify"))
    async def on_verify(message: types.Message, command: CommandObject) -> None:
        """Re-verify a brief hash against on-chain."""
        arg = (command.args or "").strip()
        if not arg:
            await message.answer("Usage: /verify <msg_id>")
            return
        row = await ctx.findings.get(arg)
        if row is None:
            await message.answer("Brief not found.")
            return
        local = hash_payload(row.payload)
        hash_match = local == row.payload_hash
        on_chain = await ctx.anchor.verify(row.msg_id)
        on_chain_match = bool(on_chain) and on_chain.payload_hash_hex == row.payload_hash
        await message.answer(
            (
                f"msg_id: `{row.msg_id}`\n"
                f"local hash match: {hash_match}\n"
                f"on-chain match: {on_chain_match}\n"
                f"tx: {row.on_chain_tx or 'n/a'}\n"
                f"block: {row.on_chain_block or 'n/a'}"
            ),
            parse_mode="Markdown",
        )

    @router.message(Command("help"))
    async def on_help(message: types.Message) -> None:
        """List all commands."""
        await message.answer(
            "Commands:\n"
            "/start — subscribe\n"
            "/stop — unsubscribe\n"
            "/status — swarm health\n"
            "/latest — last 5 briefs\n"
            "/threshold — set conviction floor\n"
            "/verify <msg_id> — re-verify a brief\n"
            "/help — this message"
        )

    return router


def passes_threshold(brief_tier: str, user_threshold: str) -> bool:
    """Return True when ``brief_tier`` meets or beats ``user_threshold``."""
    bt = TIER_ORDER.get(brief_tier.lower(), 0)
    ut = TIER_ORDER.get(user_threshold.lower(), 0)
    return bt >= ut
