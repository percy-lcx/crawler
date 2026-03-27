"""Google indexation checker via site: search."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Self
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from playwright.async_api import Browser, Playwright, async_playwright
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .constants import (
    DEFAULT_INDEX_DELAY_S,
    GENERIC_BROWSER_UA,
    GOOGLE_SEARCH_URL,
    INDEX_NAVIGATION_TIMEOUT_MS,
    INDEX_SETTLE_SECONDS,
)
from .models import IndexReport, IndexResult, IndexStatus


class GoogleIndexChecker:
    """Checks URL indexation via Google site: searches using Playwright."""

    def __init__(self, delay: float = DEFAULT_INDEX_DELAY_S) -> None:
        self._delay = delay
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> Self:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            args=["--disable-blink-features=AutomationControlled"],
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def check_url(self, url: str) -> IndexResult:
        """Perform a site:{url} Google search and determine indexation status."""
        if not self._browser:
            raise RuntimeError("Checker not started — use 'async with'")

        query = f"site:{url}"
        search_url = f"{GOOGLE_SEARCH_URL}?q={quote_plus(query)}&hl=en&gl=us"
        start = time.monotonic()

        context = await self._browser.new_context(
            user_agent=GENERIC_BROWSER_UA,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )

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
                return IndexResult(
                    url=url,
                    status=IndexStatus.ERROR,
                    query=query,
                    check_time_ms=elapsed,
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

            html = await page.content()
            elapsed = (time.monotonic() - start) * 1000

            status, result_count, top_url = _parse_serp(html)

            return IndexResult(
                url=url,
                status=status,
                timestamp=datetime.now(timezone.utc).isoformat(),
                query=query,
                result_count=result_count,
                top_result_url=top_url,
                check_time_ms=elapsed,
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
) -> IndexReport:
    """Check Google indexation for all URLs sequentially."""
    run_id = uuid.uuid4().hex[:8]
    started_at = datetime.now(timezone.utc).isoformat()

    report = IndexReport(
        run_id=run_id,
        started_at=started_at,
        total_urls=len(urls),
    )

    console = Console()

    async with GoogleIndexChecker(delay=delay) as checker:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Checking indexation...", total=len(urls))

            for i, url in enumerate(urls):
                progress.update(
                    task,
                    description=f"[{i + 1}/{len(urls)}] Checking {url}",
                )

                result = await checker.check_url(url)
                report.results.append(result)

                if result.status == IndexStatus.INDEXED:
                    report.indexed += 1
                elif result.status == IndexStatus.NOT_INDEXED:
                    report.not_indexed += 1
                elif result.status == IndexStatus.BLOCKED:
                    report.blocked += 1
                else:
                    report.errors += 1

                progress.advance(task)

                # Politeness delay (skip after last URL)
                if i < len(urls) - 1:
                    await asyncio.sleep(delay)

    report.finished_at = datetime.now(timezone.utc).isoformat()
    return report
