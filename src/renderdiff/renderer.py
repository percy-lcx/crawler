"""Headless Chromium rendering via Playwright."""

from __future__ import annotations

import time
from typing import Self

from playwright.async_api import async_playwright, Browser, Playwright

from .constants import (
    DEFAULT_TIMEOUT_MS,
    FONT_EXTENSIONS,
    MOBILE_GOOGLEBOT_UA,
    SETTLE_SECONDS,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
)
from .models import RenderResult


class HeadlessRenderer:
    """Manages a Playwright browser instance for rendering URLs."""

    def __init__(self, settle_seconds: float = SETTLE_SECONDS) -> None:
        self._settle_seconds = settle_seconds
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

            # Block font requests
            await page.route(
                _font_pattern(),
                lambda route: route.abort(),
            )

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
                    wait_until="networkidle",
                    timeout=DEFAULT_TIMEOUT_MS,
                )
            except Exception as exc:
                elapsed_ms = (time.monotonic() - start) * 1000
                # Still try to capture whatever loaded
                try:
                    rendered_html = await page.content()
                except Exception:
                    rendered_html = ""
                return RenderResult(
                    url=url,
                    rendered_html=rendered_html,
                    rendered_size_bytes=len(rendered_html.encode("utf-8")),
                    console_errors=console_errors,
                    failed_requests=failed_requests,
                    render_time_ms=elapsed_ms,
                    error=f"Navigation error: {exc}",
                )

            # Settle time
            await page.wait_for_timeout(self._settle_seconds * 1000)

            rendered_html = await page.content()
            elapsed_ms = (time.monotonic() - start) * 1000

            return RenderResult(
                url=url,
                rendered_html=rendered_html,
                rendered_size_bytes=len(rendered_html.encode("utf-8")),
                console_errors=console_errors,
                failed_requests=failed_requests,
                render_time_ms=elapsed_ms,
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


def _font_pattern() -> str:
    exts = "|".join(FONT_EXTENSIONS)
    return f"**/*.{{{exts}}}"
