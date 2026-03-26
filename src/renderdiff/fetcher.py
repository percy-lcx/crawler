"""Raw HTTP fetching via httpx."""

from __future__ import annotations

import time

import httpx

from .constants import CLOUDFLARE_MARKERS, DEFAULT_TIMEOUT_MS, GENERIC_BROWSER_UA
from .models import FetchResult, RedirectHop


async def fetch_raw(url: str, client: httpx.AsyncClient) -> FetchResult:
    """Perform HTTP GET with redirect following, return FetchResult."""
    start = time.monotonic()
    try:
        response = await client.get(url)
    except httpx.TimeoutException:
        return FetchResult(
            url=url,
            final_url=url,
            status_code=0,
            error=f"Timeout after {DEFAULT_TIMEOUT_MS}ms",
        )
    except httpx.ConnectError as exc:
        return FetchResult(
            url=url,
            final_url=url,
            status_code=0,
            error=f"Connection error: {exc}",
        )
    except httpx.TooManyRedirects:
        return FetchResult(
            url=url,
            final_url=url,
            status_code=0,
            error="Too many redirects",
        )
    except httpx.HTTPError as exc:
        return FetchResult(
            url=url,
            final_url=url,
            status_code=0,
            error=f"HTTP error: {exc}",
        )

    elapsed_ms = (time.monotonic() - start) * 1000

    redirect_chain = [
        RedirectHop(url=str(r.url), status_code=r.status_code)
        for r in response.history
    ]

    content_type = response.headers.get("content-type", "")
    is_html = "text/html" in content_type

    html = response.text if is_html else ""
    html_size = len(html.encode("utf-8")) if html else 0

    cloudflare_detected = False
    if is_html:
        for marker in CLOUDFLARE_MARKERS:
            if marker in html:
                cloudflare_detected = True
                break

    headers = dict(response.headers)

    return FetchResult(
        url=url,
        final_url=str(response.url),
        status_code=response.status_code,
        headers=headers,
        redirect_chain=redirect_chain,
        html=html,
        html_size_bytes=html_size,
        content_type=content_type,
        fetch_time_ms=elapsed_ms,
        is_html=is_html,
        cloudflare_detected=cloudflare_detected,
    )


def create_client() -> httpx.AsyncClient:
    """Create a configured httpx async client."""
    return httpx.AsyncClient(
        follow_redirects=True,
        max_redirects=10,
        timeout=httpx.Timeout(DEFAULT_TIMEOUT_MS / 1000),
        headers={"User-Agent": GENERIC_BROWSER_UA},
    )
