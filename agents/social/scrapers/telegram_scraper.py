"""Telegram public-channel scraper.

Hits ``https://t.me/s/<channel>`` preview pages — no authentication, no
rate-limit friction. We iterate a curated list of memecoin-flavoured public
channels and count string matches. Quick, cheap, no-auth.
"""

from __future__ import annotations

from playwright.async_api import Browser, BrowserContext, async_playwright

from agents.common.logging_config import get_logger
from agents.common.settings import Settings
from agents.social.scrapers.x_scraper import ScrapeResult

log = get_logger("scraper.telegram")

DEFAULT_CHANNELS: tuple[str, ...] = (
    "MemeCoinsDaily",
    "binancesignals",
    "cryptocom",
    "CryptoWhalePumps",
    "DegenNews",
)


class TelegramScraper:
    """Scrape ``t.me/s/<channel>`` for token-symbol mentions."""

    def __init__(self, settings: Settings, channels: tuple[str, ...] = DEFAULT_CHANNELS) -> None:
        """Build a TelegramScraper with the list of channels to probe."""
        self._settings = settings
        self._channels = channels
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def start(self) -> None:
        """Launch Chromium."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._settings.playwright_headless
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
        )

    async def stop(self) -> None:
        """Tear down."""
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    async def search(self, *, query: str) -> ScrapeResult:
        """Search all channels for ``query`` and aggregate."""
        if self._context is None:
            return ScrapeResult(degraded=True)
        total = 0
        samples: list[str] = []
        any_success = False
        for ch in self._channels:
            page = await self._context.new_page()
            try:
                await page.goto(f"https://t.me/s/{ch}", timeout=10_000)
                await page.wait_for_timeout(1_500)
                messages = await page.locator(".tgme_widget_message_text").all()
                for m in messages[-40:]:
                    try:
                        text = await m.inner_text(timeout=1_000)
                    except Exception:
                        continue
                    if query.lower() in text.lower():
                        total += 1
                        if len(samples) < 5:
                            samples.append(text.strip()[:280])
                any_success = True
            except Exception as err:
                log.warning("telegram_channel_failed", channel=ch, err=str(err))
            finally:
                await page.close()
        if not any_success:
            return ScrapeResult(degraded=True)
        return ScrapeResult(mention_count=total, sample_snippets=samples)
