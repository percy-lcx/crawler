"""Tests for URL input resolution."""

import pytest
import httpx
import respx

from renderdiff.input import resolve_urls


@pytest.mark.asyncio
async def test_single_url():
    urls = await resolve_urls(url="https://example.com")
    assert urls == ["https://example.com"]


@pytest.mark.asyncio
async def test_url_file(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("https://a.com\nhttps://b.com\n# comment\n\nhttps://c.com\n")
    urls = await resolve_urls(file_path=str(f))
    assert urls == ["https://a.com", "https://b.com", "https://c.com"]


@pytest.mark.asyncio
async def test_url_file_not_found():
    with pytest.raises(FileNotFoundError):
        await resolve_urls(file_path="/nonexistent/file.txt")


@pytest.mark.asyncio
async def test_deduplication():
    f_path = None

    import tempfile
    import os

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("https://a.com\nhttps://a.com\nhttps://b.com\n")
        f_path = f.name

    try:
        urls = await resolve_urls(file_path=f_path)
        assert urls == ["https://a.com", "https://b.com"]
    finally:
        os.unlink(f_path)


@pytest.mark.asyncio
async def test_limit():
    urls = await resolve_urls(
        url="https://a.com",
        limit=0,
    )
    # limit=0 should not apply (only positive limits)
    assert urls == ["https://a.com"]


@pytest.mark.asyncio
async def test_limit_positive(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("https://a.com\nhttps://b.com\nhttps://c.com\n")
    urls = await resolve_urls(file_path=str(f), limit=2)
    assert urls == ["https://a.com", "https://b.com"]


@pytest.mark.asyncio
async def test_sitemap_parsing():
    sitemap_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
</urlset>
"""
    with respx.mock:
        respx.get("https://example.com/sitemap.xml").mock(
            return_value=httpx.Response(200, text=sitemap_xml)
        )
        urls = await resolve_urls(sitemap_url="https://example.com/sitemap.xml")

    assert urls == ["https://example.com/page1", "https://example.com/page2"]


@pytest.mark.asyncio
async def test_sitemap_index():
    index_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap1.xml</loc></sitemap>
</sitemapindex>
"""
    child_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a</loc></url>
</urlset>
"""
    with respx.mock:
        respx.get("https://example.com/sitemap.xml").mock(
            return_value=httpx.Response(200, text=index_xml)
        )
        respx.get("https://example.com/sitemap1.xml").mock(
            return_value=httpx.Response(200, text=child_xml)
        )
        urls = await resolve_urls(sitemap_url="https://example.com/sitemap.xml")

    assert urls == ["https://example.com/a"]
