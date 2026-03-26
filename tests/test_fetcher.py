"""Tests for raw HTTP fetcher."""

import pytest
import httpx
import respx

from renderdiff.fetcher import fetch_raw, create_client


BASE_URL = "https://example.com/page"


@pytest.mark.asyncio
async def test_fetch_basic_html():
    async with create_client() as client:
        with respx.mock:
            respx.get(BASE_URL).mock(
                return_value=httpx.Response(
                    200,
                    text="<html><body>Hello</body></html>",
                    headers={"content-type": "text/html; charset=utf-8"},
                )
            )
            result = await fetch_raw(BASE_URL, client)

    assert result.status_code == 200
    assert result.is_html is True
    assert "Hello" in result.html
    assert result.html_size_bytes > 0
    assert result.error is None


@pytest.mark.asyncio
async def test_fetch_non_html():
    async with create_client() as client:
        with respx.mock:
            respx.get(BASE_URL).mock(
                return_value=httpx.Response(
                    200,
                    text="{}",
                    headers={"content-type": "application/json"},
                )
            )
            result = await fetch_raw(BASE_URL, client)

    assert result.is_html is False
    assert result.html == ""


@pytest.mark.asyncio
async def test_fetch_cloudflare_detection():
    cf_html = "<html><body>Checking your browser before accessing</body></html>"
    async with create_client() as client:
        with respx.mock:
            respx.get(BASE_URL).mock(
                return_value=httpx.Response(
                    200,
                    text=cf_html,
                    headers={"content-type": "text/html"},
                )
            )
            result = await fetch_raw(BASE_URL, client)

    assert result.cloudflare_detected is True


@pytest.mark.asyncio
async def test_fetch_redirect_chain():
    async with create_client() as client:
        with respx.mock:
            respx.get("https://example.com/old").mock(
                return_value=httpx.Response(
                    301,
                    headers={
                        "location": "https://example.com/new",
                        "content-type": "text/html",
                    },
                )
            )
            respx.get("https://example.com/new").mock(
                return_value=httpx.Response(
                    200,
                    text="<html>Final</html>",
                    headers={"content-type": "text/html"},
                )
            )
            result = await fetch_raw("https://example.com/old", client)

    assert result.final_url == "https://example.com/new"
    assert len(result.redirect_chain) == 1


@pytest.mark.asyncio
async def test_fetch_timeout():
    async with create_client() as client:
        with respx.mock:
            respx.get(BASE_URL).mock(side_effect=httpx.ReadTimeout("timeout"))
            result = await fetch_raw(BASE_URL, client)

    assert result.error is not None
    assert "Timeout" in result.error


@pytest.mark.asyncio
async def test_fetch_x_robots_tag():
    async with create_client() as client:
        with respx.mock:
            respx.get(BASE_URL).mock(
                return_value=httpx.Response(
                    200,
                    text="<html><body>OK</body></html>",
                    headers={
                        "content-type": "text/html",
                        "x-robots-tag": "noindex",
                    },
                )
            )
            result = await fetch_raw(BASE_URL, client)

    assert result.headers.get("x-robots-tag") == "noindex"
