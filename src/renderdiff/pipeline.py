"""Orchestrator: fetch -> render -> extract -> diff for URL batches."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from functools import partial

from .constants import DEFAULT_CONCURRENCY, DEFAULT_DELAY_S
from .differ import diff_signals
from .extractor import extract_signals
from .fetcher import create_client, fetch_raw
from .models import RunReport, Severity, UrlReport
from .renderer import HeadlessRenderer


async def process_url(
    url: str,
    client: object,
    renderer: HeadlessRenderer,
    semaphore: asyncio.Semaphore,
    delay: float,
) -> UrlReport:
    """Full pipeline for one URL: fetch -> render -> extract -> diff."""
    async with semaphore:
        timestamp = datetime.now(timezone.utc).isoformat()

        # Fetch and render in parallel
        fetch_result, render_result = await asyncio.gather(
            fetch_raw(url, client),  # type: ignore[arg-type]
            renderer.render(url),
        )

        # Skip non-HTML
        if not fetch_result.is_html:
            return UrlReport(
                url=url,
                timestamp=timestamp,
                fetch=fetch_result,
                skipped=True,
                skip_reason=f"Non-HTML content type: {fetch_result.content_type}",
            )

        # Skip if both failed
        if fetch_result.error and render_result.error:
            return UrlReport(
                url=url,
                timestamp=timestamp,
                fetch=fetch_result,
                render=render_result,
                skipped=True,
                skip_reason=f"Both fetch and render failed",
            )

        # Extract signals (CPU-bound, run in executor)
        loop = asyncio.get_running_loop()

        raw_signals = None
        if fetch_result.html:
            raw_signals = await loop.run_in_executor(
                None,
                partial(
                    extract_signals,
                    fetch_result.html,
                    url,
                    fetch_result.headers,
                ),
            )

        rendered_signals = None
        if render_result.rendered_html:
            rendered_signals = await loop.run_in_executor(
                None,
                partial(extract_signals, render_result.rendered_html, url),
            )

        # Diff
        diffs = []
        if raw_signals and rendered_signals:
            diffs = diff_signals(raw_signals, rendered_signals, fetch_result)

        # Determine overall status
        has_critical = any(d.severity == Severity.CRITICAL for d in diffs)
        has_warning = any(d.severity == Severity.WARNING for d in diffs)
        if has_critical:
            overall_status = "fail"
        elif has_warning:
            overall_status = "warn"
        else:
            overall_status = "pass"

        report = UrlReport(
            url=url,
            timestamp=timestamp,
            fetch=fetch_result,
            render=render_result,
            raw_signals=raw_signals,
            rendered_signals=rendered_signals,
            diffs=diffs,
            overall_status=overall_status,
            cloudflare_detected=fetch_result.cloudflare_detected,
        )

        # Politeness delay
        await asyncio.sleep(delay)

        return report


async def run(
    urls: list[str],
    concurrency: int = DEFAULT_CONCURRENCY,
    delay: float = DEFAULT_DELAY_S,
    screenshot_dir: str | None = None,
) -> RunReport:
    """Process all URLs with bounded concurrency."""
    run_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(timezone.utc).isoformat()

    semaphore = asyncio.Semaphore(concurrency)

    client = create_client()
    async with client, HeadlessRenderer(screenshot_dir=screenshot_dir) as renderer:
        tasks = [
            process_url(url, client, renderer, semaphore, delay) for url in urls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    url_reports: list[UrlReport] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            url_reports.append(
                UrlReport(
                    url=urls[i],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    skipped=True,
                    skip_reason=str(result),
                )
            )
        else:
            url_reports.append(result)

    finished_at = datetime.now(timezone.utc).isoformat()

    return RunReport(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        total_urls=len(urls),
        passed=sum(1 for r in url_reports if r.overall_status == "pass" and not r.skipped),
        warned=sum(1 for r in url_reports if r.overall_status == "warn"),
        failed=sum(1 for r in url_reports if r.overall_status == "fail"),
        skipped=sum(1 for r in url_reports if r.skipped),
        urls=url_reports,
    )
