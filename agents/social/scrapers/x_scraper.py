"""X (Twitter) scraper.

A minimal, resilient scraper — the goal is *never* to break the pipeline
if X blocks us: on any failure we return an empty result with
``degraded=True`` so the Social agent can surface the gap rather than
swallowing it.

For the hackathon this is intentionally plain Playwright; the adapter
pattern means we can swap in a more aggressive stealth stack later without
touching the Social agent itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from playwright.async_api import Browser, BrowserContext, async_playwright

from agents.common.logging_config import get_logger
from agents.common.settings import Settings

log = get_logger("scraper.x")


@dataclass
class ScrapeResult:
    """Unified scrape output."""

    mention_count: int = 0
    sample_snippets: list[str] = field(default_factory=list)
    degraded: bool = False


class XScraper:
    """Search X for token mentions via public search URL."""

    def __init__(self, settings: Settings) -> None:
        """Hold Playwright handles; the real browser opens in ``start()``."""
        self._settings = settings
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def start(self) -> None:
        """Launch Chromium with a persistent profile."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._settings.playwright_headless
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
        )

    async def stop(self) -> None:
        """Tear down the browser."""
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    async def search(self, *, query: str) -> ScrapeResult:
        """Return a ``ScrapeResult`` for ``query``; degraded on any failure."""
        if self._context is None:
            return ScrapeResult(degraded=True)
        page = await self._context.new_page()
        url = f"https://x.com/search?q={query}&src=typed_query&f=live"
        try:
            await page.goto(url, timeout=15_000)
            await page.wait_for_timeout(3_000)
            articles = await page.locator("article").all()
            snippets: list[str] = []
            for a in articles[:20]:
                try:
                    text = await a.inner_text(timeout=1_500)
                except Exception:
                    continue
                if text.strip():
                    snippets.append(text.strip()[:280])
            if not snippets:
                return ScrapeResult(degraded=True)
            return ScrapeResult(mention_count=len(snippets), sample_snippets=snippets)
        except Exception as err:
            log.warning("x_scrape_failed", query=query, err=str(err))
            return ScrapeResult(degraded=True)
        finally:
            await page.close()
