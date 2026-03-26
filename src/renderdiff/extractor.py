"""SEO signal extraction from HTML using BeautifulSoup."""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .models import (
    HreflangEntry,
    ImageInfo,
    LinkInfo,
    SeoSignals,
    StructuredDataItem,
)


def extract_signals(
    html: str,
    base_url: str,
    headers: dict[str, str] | None = None,
) -> SeoSignals:
    """Parse HTML and extract all SEO signals."""
    soup = BeautifulSoup(html, "lxml")
    base_domain = urlparse(base_url).netloc

    return SeoSignals(
        title=_extract_title(soup),
        meta_description=_extract_meta(soup, "description"),
        canonical=_extract_canonical(soup),
        robots_meta=_extract_meta(soup, "robots"),
        x_robots_tag=headers.get("x-robots-tag") or headers.get("X-Robots-Tag")
        if headers
        else None,
        h1_texts=_extract_headings(soup, "h1"),
        h2_texts=_extract_headings(soup, "h2"),
        structured_data=_extract_structured_data(soup),
        internal_links=_extract_links(soup, base_url, base_domain),
        images=_extract_images(soup, base_url),
        hreflang=_extract_hreflang(soup),
        word_count=_extract_word_count(soup),
        html_size_bytes=len(html.encode("utf-8")),
    )


def _extract_title(soup: BeautifulSoup) -> str | None:
    tag = soup.find("title")
    if tag and tag.string:
        return tag.string.strip()
    return None


def _extract_meta(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", attrs={"name": re.compile(f"^{name}$", re.IGNORECASE)})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None


def _extract_canonical(soup: BeautifulSoup) -> str | None:
    tag = soup.find("link", attrs={"rel": "canonical"})
    if tag and tag.get("href"):
        return tag["href"].strip()
    return None


def _extract_headings(soup: BeautifulSoup, tag_name: str) -> list[str]:
    return [
        tag.get_text(strip=True)
        for tag in soup.find_all(tag_name)
        if tag.get_text(strip=True)
    ]


def _extract_structured_data(soup: BeautifulSoup) -> list[StructuredDataItem]:
    items: list[StructuredDataItem] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string
        if not text:
            continue
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    items.append(
                        StructuredDataItem(
                            sd_type=entry.get("@type", "Unknown"),
                            raw_json=entry,
                        )
                    )
        elif isinstance(data, dict):
            items.append(
                StructuredDataItem(
                    sd_type=data.get("@type", "Unknown"),
                    raw_json=data,
                )
            )
    return items


def _extract_links(
    soup: BeautifulSoup, base_url: str, base_domain: str
) -> list[LinkInfo]:
    links: list[LinkInfo] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        resolved = urljoin(base_url, href)
        parsed = urlparse(resolved)
        is_internal = parsed.netloc == base_domain
        rel = a.get("rel")
        rel_str = " ".join(rel) if isinstance(rel, list) else rel
        links.append(
            LinkInfo(
                href=resolved,
                text=a.get_text(strip=True),
                rel=rel_str,
                is_internal=is_internal,
            )
        )
    return links


def _extract_images(soup: BeautifulSoup, base_url: str) -> list[ImageInfo]:
    images: list[ImageInfo] = []
    for img in soup.find_all("img"):
        src = img.get("src", "").strip()
        if not src:
            continue
        images.append(
            ImageInfo(
                src=urljoin(base_url, src),
                alt=img.get("alt"),
                loading=img.get("loading"),
            )
        )
    return images


def _extract_hreflang(soup: BeautifulSoup) -> list[HreflangEntry]:
    entries: list[HreflangEntry] = []
    for link in soup.find_all("link", attrs={"rel": "alternate", "hreflang": True}):
        href = link.get("href", "").strip()
        lang = link.get("hreflang", "").strip()
        if href and lang:
            entries.append(HreflangEntry(lang=lang, href=href))
    return entries


def _extract_word_count(soup: BeautifulSoup) -> int:
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    words = text.split()
    return len(words)
