"""Google indexation checker via site: search."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Self
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from playwright.async_api import Browser, Page, Playwright, async_playwright
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .constants import (
    DEFAULT_INDEX_CONCURRENCY,
    DEFAULT_INDEX_DELAY_S,
    GENERIC_BROWSER_UA,
    GOOGLE_SEARCH_URL,
    INDEX_NAVIGATION_TIMEOUT_MS,
    INDEX_SETTLE_SECONDS,
)
from .models import IndexReport, IndexResult, IndexStatus

_VIEWPORT_WIDTH = 1280
_VIEWPORT_HEIGHT = 800


class GoogleIndexChecker:
    """Checks URL indexation via Google site: searches using Playwright."""

    def __init__(
        self,
        delay: float = DEFAULT_INDEX_DELAY_S,
        screenshot_dir: str | None = None,
        cookies_file: str | None = None,
    ) -> None:
        self._delay = delay
        self._screenshot_dir = screenshot_dir
        self._cookies_file = Path(cookies_file) if cookies_file else None
        self._cookies_lock = asyncio.Lock()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> Self:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            args=["--disable-blink-features=AutomationControlled"],
        )

        # If cookies file specified but doesn't exist, launch headed browser
        # for the user to solve the CAPTCHA manually.
        if self._cookies_file and not self._cookies_file.exists():
            await self._warm_up_cookies()

        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _warm_up_cookies(self) -> None:
        """Launch a headed browser for the user to solve Google CAPTCHA."""
        console = Console()
        console.print(
            "[bold yellow]Launching browser for CAPTCHA solving. "
            "Please solve the CAPTCHA, then the tool will continue.[/bold yellow]"
        )

        headed_browser = await self._playwright.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await headed_browser.new_context(
            user_agent=GENERIC_BROWSER_UA,
            viewport={"width": _VIEWPORT_WIDTH, "height": _VIEWPORT_HEIGHT},
            locale="en-US",
        )
        page = await context.new_page()
        await page.goto(
            f"{GOOGLE_SEARCH_URL}?q=test&hl=en&gl=us",
            wait_until="load",
            timeout=INDEX_NAVIGATION_TIMEOUT_MS,
        )

        # Poll until the CAPTCHA is solved (up to 5 minutes)
        max_wait = 300
        elapsed = 0
        interval = 2
        while elapsed < max_wait:
            await page.wait_for_timeout(interval * 1000)
            elapsed += interval
            html = await page.content()
            status, _, _ = _parse_serp(html)
            if status != IndexStatus.BLOCKED:
                break
        else:
            await context.close()
            await headed_browser.close()
            raise RuntimeError(
                "CAPTCHA was not solved within 5 minutes. Please try again."
            )

        self._cookies_file.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(self._cookies_file))
        console.print("[bold green]Cookies saved. Continuing with checks.[/bold green]")
        await context.close()
        await headed_browser.close()

    async def check_url(self, url: str) -> IndexResult:
        """Perform a site:{url} Google search and determine indexation status."""
        if not self._browser:
            raise RuntimeError("Checker not started — use 'async with'")

        query = f"site:{url}"
        search_url = f"{GOOGLE_SEARCH_URL}?q={quote_plus(query)}&hl=en&gl=us"
        start = time.monotonic()

        context_kwargs: dict = {
            "user_agent": GENERIC_BROWSER_UA,
            "viewport": {"width": _VIEWPORT_WIDTH, "height": _VIEWPORT_HEIGHT},
            "locale": "en-US",
        }
        if self._cookies_file and self._cookies_file.exists():
            context_kwargs["storage_state"] = str(self._cookies_file)

        context = await self._browser.new_context(**context_kwargs)

        try:
            page = await context.new_page()

            try:
                await page.goto(
                    search_url,
                    wait_until="load",
                    timeout=INDEX_NAVIGATION_TIMEOUT_MS,
                )
            except Exception as exc:
                elapsed = (time.monotonic() - start) * 1000
                screenshot_path = await self._take_screenshot(page, url)
                return IndexResult(
                    url=url,
                    status=IndexStatus.ERROR,
                    query=query,
                    check_time_ms=elapsed,
                    screenshot_path=screenshot_path,
                    error=f"Navigation error: {exc}",
                )

            await page.wait_for_timeout(INDEX_SETTLE_SECONDS * 1000)

            # Dismiss Google cookie consent if present
            try:
                consent_btn = page.locator("#L2AGLb")
                if await consent_btn.is_visible(timeout=1000):
                    await consent_btn.click()
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # Take screenshot of the SERP before parsing
            screenshot_path = await self._take_screenshot(page, url)

            html = await page.content()
            elapsed = (time.monotonic() - start) * 1000

            status, result_count, top_url = _parse_serp(html)

            # Persist fresh cookies to keep the session alive
            if self._cookies_file:
                async with self._cookies_lock:
                    try:
                        await context.storage_state(path=str(self._cookies_file))
                    except Exception:
                        pass

            return IndexResult(
                url=url,
                status=status,
                timestamp=datetime.now(timezone.utc).isoformat(),
                query=query,
                result_count=result_count,
                top_result_url=top_url,
                check_time_ms=elapsed,
                screenshot_path=screenshot_path,
            )

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            return IndexResult(
                url=url,
                status=IndexStatus.ERROR,
                query=query,
                check_time_ms=elapsed,
                error=f"Check error: {exc}",
            )
        finally:
            await context.close()

    async def _take_screenshot(self, page: Page, url: str) -> str | None:
        """Capture a screenshot of the SERP page."""
        if not self._screenshot_dir:
            return None

        slug = hashlib.md5(url.encode()).hexdigest()[:12]
        dir_path = Path(self._screenshot_dir)
        dir_path.mkdir(parents=True, exist_ok=True)
        path = dir_path / f"{slug}.png"

        # Try CDP first (faster)
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
                                "width": _VIEWPORT_WIDTH,
                                "height": _VIEWPORT_HEIGHT,
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
            pass

        # Fallback: Playwright screenshot
        try:
            await page.screenshot(path=str(path), timeout=10000)
            return str(path)
        except Exception:
            return None


def _parse_serp(html: str) -> tuple[IndexStatus, str, str | None]:
    """Parse Google SERP HTML to determine indexation status.

    Returns (status, result_count_text, first_result_url).
    """
    soup = BeautifulSoup(html, "lxml")
    body_text = soup.get_text().lower()

    # Check for CAPTCHA / bot detection
    if soup.find("form", id="captcha-form") or soup.find("div", id="recaptcha"):
        return (IndexStatus.BLOCKED, "", None)
    if "unusual traffic" in body_text:
        return (IndexStatus.BLOCKED, "", None)

    # Check for "did not match any documents"
    if "did not match any documents" in body_text:
        return (IndexStatus.NOT_INDEXED, "0", None)
    if "no results found" in body_text:
        return (IndexStatus.NOT_INDEXED, "0", None)

    # Look for search result divs
    result_divs = soup.select("div.g")
    if result_divs:
        first_link = result_divs[0].find("a", href=True)
        first_url = first_link["href"] if first_link else None
        stats = soup.find("div", id="result-stats")
        count_text = stats.get_text().strip() if stats else ""
        return (IndexStatus.INDEXED, count_text, first_url)

    # Fallback: check result-stats without div.g
    stats = soup.find("div", id="result-stats")
    if stats and stats.get_text().strip():
        return (IndexStatus.INDEXED, stats.get_text().strip(), None)

    # No clear signal — treat as blocked/unknown
    return (IndexStatus.BLOCKED, "", None)


async def check_indexation(
    urls: list[str],
    delay: float = DEFAULT_INDEX_DELAY_S,
    concurrency: int = DEFAULT_INDEX_CONCURRENCY,
    screenshot_dir: str | None = None,
    cookies_file: str | None = None,
) -> IndexReport:
    """Check Google indexation for URLs with configurable concurrency."""
    run_id = uuid.uuid4().hex[:8]
    started_at = datetime.now(timezone.utc).isoformat()

    report = IndexReport(
        run_id=run_id,
        started_at=started_at,
        total_urls=len(urls),
    )

    console = Console()
    semaphore = asyncio.Semaphore(concurrency)
    results: list[IndexResult | None] = [None] * len(urls)

    async with GoogleIndexChecker(delay=delay, screenshot_dir=screenshot_dir, cookies_file=cookies_file) as checker:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Checking indexation...", total=len(urls))
            completed = 0

            async def _check_one(idx: int, url: str) -> None:
                nonlocal completed
                async with semaphore:
                    result = await checker.check_url(url)
                    results[idx] = result
                    completed += 1
                    progress.update(
                        task,
                        description=f"[{completed}/{len(urls)}] Checked {url}",
                    )
                    progress.advance(task)
                    # Per-worker politeness delay (inside semaphore to
                    # limit throughput to concurrency/delay URLs per second)
                    if idx < len(urls) - 1:
                        await asyncio.sleep(delay)

            tasks = [_check_one(i, u) for i, u in enumerate(urls)]
            await asyncio.gather(*tasks)

    for r in results:
        report.results.append(r)
        if r.status == IndexStatus.INDEXED:
            report.indexed += 1
        elif r.status == IndexStatus.NOT_INDEXED:
            report.not_indexed += 1
        elif r.status == IndexStatus.BLOCKED:
            report.blocked += 1
        else:
            report.errors += 1

    report.finished_at = datetime.now(timezone.utc).isoformat()
    return report
