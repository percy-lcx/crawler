"""Tests for SEO signal extraction."""

from renderdiff.extractor import extract_signals
from ._fixtures import SAMPLE_HTML


BASE_URL = "https://example.com/page"


def test_extract_title():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    assert signals.title == "Test Page Title"


def test_extract_meta_description():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    assert signals.meta_description == "Test description for SEO"


def test_extract_canonical():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    assert signals.canonical == "https://example.com/page"


def test_extract_robots_meta():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    assert signals.robots_meta == "index, follow"


def test_extract_x_robots_tag():
    headers = {"X-Robots-Tag": "noindex, nofollow"}
    signals = extract_signals(SAMPLE_HTML, BASE_URL, headers=headers)
    assert signals.x_robots_tag == "noindex, nofollow"


def test_extract_h1():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    assert signals.h1_texts == ["Main Heading"]


def test_extract_h2():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    assert signals.h2_texts == ["Sub Heading One", "Sub Heading Two"]


def test_extract_structured_data():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    assert len(signals.structured_data) == 1
    assert signals.structured_data[0].sd_type == "WebPage"


def test_extract_internal_links():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    internal = [link for link in signals.internal_links if link.is_internal]
    assert len(internal) == 1
    assert internal[0].text == "About Us"
    assert internal[0].href == "https://example.com/about"


def test_extract_external_links():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    external = [link for link in signals.internal_links if not link.is_internal]
    assert len(external) == 1
    assert "nofollow" in (external[0].rel or "")


def test_extract_images():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    assert len(signals.images) == 2
    assert signals.images[0].alt == "A photo"
    assert signals.images[0].loading == "lazy"


def test_extract_hreflang():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    langs = {e.lang for e in signals.hreflang}
    assert langs == {"en", "es"}


def test_extract_word_count():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    assert signals.word_count > 0


def test_extract_html_size():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    assert signals.html_size_bytes == len(SAMPLE_HTML.encode("utf-8"))


def test_extract_missing_title():
    html = "<html><head></head><body><p>No title</p></body></html>"
    signals = extract_signals(html, BASE_URL)
    assert signals.title is None


def test_extract_empty_html():
    signals = extract_signals("", BASE_URL)
    assert signals.title is None
    assert signals.word_count == 0


def test_extract_malformed_json_ld():
    html = """
    <html><head>
    <script type="application/ld+json">{invalid json}</script>
    </head><body></body></html>
    """
    signals = extract_signals(html, BASE_URL)
    assert signals.structured_data == []


def test_extract_multiple_json_ld():
    html = """
    <html><head>
    <script type="application/ld+json">{"@type": "WebPage"}</script>
    <script type="application/ld+json">{"@type": "FAQPage"}</script>
    </head><body></body></html>
    """
    signals = extract_signals(html, BASE_URL)
    assert len(signals.structured_data) == 2
    types = {sd.sd_type for sd in signals.structured_data}
    assert types == {"WebPage", "FAQPage"}


def test_extract_json_ld_array():
    html = """
    <html><head>
    <script type="application/ld+json">[{"@type": "A"}, {"@type": "B"}]</script>
    </head><body></body></html>
    """
    signals = extract_signals(html, BASE_URL)
    assert len(signals.structured_data) == 2
