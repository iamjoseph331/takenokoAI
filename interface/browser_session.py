"""BrowserSession — shared Playwright browser instance for Re.browser and Mo.browser.

Manages the lifecycle of a single browser page. Both the perception submodule
(Re.browser) and the action submodule (Mo.browser) hold a reference to the
same session so they operate on the same page.

Usage:
    session = BrowserSession(headless=True)
    await session.start("https://example.com/tictactoe")
    state = await session.get_dom_snapshot()
    await session.click("#cell-1-2")
    await session.stop()
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

from playwright.async_api import Browser, Page, async_playwright

from interface.logging import ModuleLogger


class BrowserSession:
    """Manages a Playwright browser instance shared by browser submodules."""

    def __init__(
        self,
        *,
        headless: bool = True,
        logger: ModuleLogger | None = None,
    ) -> None:
        self._headless = headless
        self._logger = logger or ModuleLogger("SYS", "browser")
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("BrowserSession not started")
        return self._page

    @property
    def is_running(self) -> bool:
        return self._page is not None

    async def start(self, url: str) -> None:
        """Launch browser and navigate to the given URL."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._page = await self._browser.new_page()
        await self._page.goto(url, wait_until="domcontentloaded")
        self._logger.action(f"Browser started → {url}")

    async def stop(self) -> None:
        """Close browser and clean up."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._browser = None
        self._playwright = None
        self._logger.action("Browser stopped")

    async def navigate(self, url: str) -> None:
        """Navigate the current page to a new URL."""
        await self.page.goto(url, wait_until="domcontentloaded")
        self._logger.action(f"Navigated → {url}")

    async def screenshot(self, *, full_page: bool = False) -> bytes:
        """Capture a PNG screenshot of the page."""
        return await self.page.screenshot(full_page=full_page)

    async def screenshot_base64(self, *, full_page: bool = False) -> str:
        """Capture a screenshot and return as base64-encoded PNG."""
        raw = await self.screenshot(full_page=full_page)
        return base64.b64encode(raw).decode("ascii")

    async def get_dom_snapshot(self) -> dict[str, Any]:
        """Extract a structured snapshot of the page DOM.

        Returns page title, URL, and a serialized view of the body's
        immediate children (tag, id, classes, text content, bounding box).
        """
        result = await self.page.evaluate("""() => {
            function serialize(el, depth) {
                if (depth > 4 || !el) return null;
                const rect = el.getBoundingClientRect();
                const node = {
                    tag: el.tagName.toLowerCase(),
                    id: el.id || null,
                    classes: [...el.classList],
                    text: el.textContent?.trim().slice(0, 200) || null,
                    bbox: {
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height),
                    },
                    children: [],
                };
                for (const child of el.children) {
                    const c = serialize(child, depth + 1);
                    if (c) node.children.push(c);
                }
                return node;
            }
            return {
                title: document.title,
                url: location.href,
                body: serialize(document.body, 0),
            };
        }""")
        return result

    async def click(self, selector: str) -> None:
        """Click an element by CSS selector."""
        await self.page.click(selector)
        self._logger.action(f"Clicked: {selector}")

    async def click_xy(self, x: float, y: float) -> None:
        """Click at specific page coordinates."""
        await self.page.mouse.click(x, y)
        self._logger.action(f"Clicked: ({x}, {y})")

    async def type_text(self, selector: str, text: str) -> None:
        """Type text into an element."""
        await self.page.fill(selector, text)
        self._logger.action(f"Typed into {selector}: {text[:50]}")

    async def press_key(self, key: str) -> None:
        """Press a keyboard key."""
        await self.page.keyboard.press(key)
        self._logger.action(f"Pressed: {key}")

    async def evaluate_js(self, script: str) -> Any:
        """Run arbitrary JavaScript in the page context and return the result."""
        return await self.page.evaluate(script)

    async def wait_for_selector(
        self, selector: str, *, timeout: float = 5000
    ) -> None:
        """Wait for an element matching the selector to appear."""
        await self.page.wait_for_selector(selector, timeout=timeout)

    async def wait_for_stable(self, *, delay: float = 0.3) -> None:
        """Wait briefly for animations/transitions to settle."""
        await asyncio.sleep(delay)
