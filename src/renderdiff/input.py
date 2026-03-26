"""URL input resolution: single URL, file, or sitemap."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

import httpx

from .constants import DEFAULT_TIMEOUT_MS, GENERIC_BROWSER_UA


async def resolve_urls(
    url: str | None = None,
    file_path: str | None = None,
    sitemap_url: str | None = None,
    limit: int | None = None,
) -> list[str]:
    """Return a deduplicated list of URLs to process."""
    urls: list[str] = []

    if url:
        urls.append(url.strip())

    if file_path:
        urls.extend(_read_url_file(file_path))

    if sitemap_url:
        urls.extend(await _fetch_sitemap(sitemap_url))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)

    if limit is not None and limit > 0:
        unique = unique[:limit]

    return unique


def _read_url_file(file_path: str) -> list[str]:
    """Read newline-delimited URLs from a file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"URL file not found: {file_path}")

    urls: list[str] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


async def _fetch_sitemap(sitemap_url: str) -> list[str]:
    """Fetch and parse a sitemap XML, handling sitemap indexes."""
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(DEFAULT_TIMEOUT_MS / 1000),
        headers={"User-Agent": GENERIC_BROWSER_UA},
    ) as client:
        return await _parse_sitemap(client, sitemap_url)


async def _parse_sitemap(client: httpx.AsyncClient, url: str) -> list[str]:
    """Recursively parse sitemap or sitemap index."""
    response = await client.get(url)
    response.raise_for_status()

    root = ElementTree.fromstring(response.text)
    ns = _detect_namespace(root)

    urls: list[str] = []

    # Check for sitemap index
    sitemaps = root.findall(f"{ns}sitemap")
    if sitemaps:
        for sm in sitemaps:
            loc = sm.find(f"{ns}loc")
            if loc is not None and loc.text:
                child_urls = await _parse_sitemap(client, loc.text.strip())
                urls.extend(child_urls)
    else:
        # Regular sitemap
        for url_elem in root.findall(f"{ns}url"):
            loc = url_elem.find(f"{ns}loc")
            if loc is not None and loc.text:
                urls.append(loc.text.strip())

    return urls


def _detect_namespace(root: ElementTree.Element) -> str:
    """Detect XML namespace from root element tag."""
    tag = root.tag
    if tag.startswith("{"):
        ns = tag.split("}")[0] + "}"
        return ns
    return ""
