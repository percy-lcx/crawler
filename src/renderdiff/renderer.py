"""Headless Chromium rendering via Playwright."""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from typing import Self

from playwright.async_api import async_playwright, Browser, Page, Playwright

from .constants import (
    MOBILE_GOOGLEBOT_UA,
    NAVIGATION_TIMEOUT_MS,
    SETTLE_SECONDS,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
)
from .models import RenderResult


class HeadlessRenderer:
    """Manages a Playwright browser instance for rendering URLs."""

    def __init__(
        self,
        settle_seconds: float = SETTLE_SECONDS,
        screenshot_dir: str | None = None,
    ) -> None:
        self._settle_seconds = settle_seconds
        self._screenshot_dir = screenshot_dir
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> Self:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def render(self, url: str) -> RenderResult:
        """Render a URL and return the rendered DOM with metadata."""
        if not self._browser:
            raise RuntimeError("Renderer not started — use 'async with'")

        console_errors: list[str] = []
        failed_requests: list[str] = []
        start = time.monotonic()

        context = await self._browser.new_context(
            user_agent=MOBILE_GOOGLEBOT_UA,
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        )

        try:
            page = await context.new_page()

            # Block font requests to match Googlebot behavior
            async def _handle_route(route):
                if route.request.resource_type == "font":
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", _handle_route)

            # Capture console errors
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text)
                if msg.type == "error"
                else None,
            )

            # Capture failed network requests
            page.on(
                "requestfailed",
                lambda req: failed_requests.append(
                    f"{req.url} ({req.failure})"
                ),
            )

            try:
                await page.goto(
                    url,
                    wait_until="load",
                    timeout=NAVIGATION_TIMEOUT_MS,
                )
            except Exception as exc:
                elapsed_ms = (time.monotonic() - start) * 1000
                try:
                    rendered_html = await page.content()
                except Exception:
                    rendered_html = ""
                # Still attempt screenshot on partial load
                screenshot_path = None
                if self._screenshot_dir:
                    screenshot_path = await self._take_screenshot(page, url)
                return RenderResult(
                    url=url,
                    rendered_html=rendered_html,
                    rendered_size_bytes=len(rendered_html.encode("utf-8")),
                    console_errors=console_errors,
                    failed_requests=failed_requests,
                    render_time_ms=elapsed_ms,
                    screenshot_path=screenshot_path,
                    error=f"Navigation error: {exc}",
                )

            # Settle time
            await page.wait_for_timeout(self._settle_seconds * 1000)

            rendered_html = await page.content()
            elapsed_ms = (time.monotonic() - start) * 1000

            # Screenshot capture (non-blocking with timeout)
            screenshot_path = None
            if self._screenshot_dir:
                screenshot_path = await self._take_screenshot(page, url)

            return RenderResult(
                url=url,
                rendered_html=rendered_html,
                rendered_size_bytes=len(rendered_html.encode("utf-8")),
                console_errors=console_errors,
                failed_requests=failed_requests,
                render_time_ms=elapsed_ms,
                screenshot_path=screenshot_path,
            )
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            return RenderResult(
                url=url,
                render_time_ms=elapsed_ms,
                error=f"Render error: {exc}",
            )
        finally:
            await context.close()

    async def _take_screenshot(self, page: Page, url: str) -> str | None:
        """Capture a screenshot, trying CDP first then falling back to Playwright."""
        import base64

        slug = hashlib.md5(url.encode()).hexdigest()[:12]
        dir_path = Path(self._screenshot_dir)
        dir_path.mkdir(parents=True, exist_ok=True)
        path = dir_path / f"{slug}.png"

        # Try CDP first (faster, doesn't wait for fonts)
        try:
            cdp = await page.context.new_cdp_session(page)
            try:
                result = await asyncio.wait_for(
                    cdp.send(
                        "Page.captureScreenshot",
                        {
                            "format": "png",
                            "clip": {
                                "x": 0,
                                "y": 0,
                                "width": VIEWPORT_WIDTH,
                                "height": VIEWPORT_HEIGHT,
                                "scale": 1,
                            },
                        },
                    ),
                    timeout=10.0,
                )
                data = base64.b64decode(result["data"])
                path.write_bytes(data)
                return str(path)
            finally:
                await cdp.detach()
        except Exception:
            pass  # Fall through to Playwright fallback

        # Fallback: Playwright's built-in screenshot
        try:
            await page.screenshot(path=str(path), timeout=10000)
            return str(path)
        except Exception:
            return None
