"""Tests for signal comparison and diff engine."""

from renderdiff.differ import diff_signals
from renderdiff.extractor import extract_signals
from renderdiff.models import (
    FetchResult,
    ImageInfo,
    SeoSignals,
    Severity,
    StructuredDataItem,
)
from ._fixtures import SAMPLE_HTML, SAMPLE_HTML_RENDERED


BASE_URL = "https://example.com/page"


def _make_fetch(**kwargs) -> FetchResult:
    defaults = dict(url=BASE_URL, final_url=BASE_URL, status_code=200)
    defaults.update(kwargs)
    return FetchResult(**defaults)


def test_no_diffs_identical():
    signals = extract_signals(SAMPLE_HTML, BASE_URL)
    diffs = diff_signals(signals, signals, _make_fetch())
    critical = [d for d in diffs if d.severity == Severity.CRITICAL]
    assert len(critical) == 0


def test_title_diff_is_critical():
    raw = SeoSignals(title="Original Title")
    rendered = SeoSignals(title="JS Modified Title")
    diffs = diff_signals(raw, rendered, _make_fetch())
    title_diffs = [d for d in diffs if d.field == "title"]
    assert len(title_diffs) == 1
    assert title_diffs[0].severity == Severity.CRITICAL


def test_canonical_diff_is_critical():
    raw = SeoSignals(canonical="https://example.com/a")
    rendered = SeoSignals(canonical="https://example.com/b")
    diffs = diff_signals(raw, rendered, _make_fetch())
    canon_diffs = [d for d in diffs if d.field == "canonical"]
    assert len(canon_diffs) == 1
    assert canon_diffs[0].severity == Severity.CRITICAL


def test_robots_diff_is_critical():
    raw = SeoSignals(robots_meta="index, follow")
    rendered = SeoSignals(robots_meta="noindex")
    diffs = diff_signals(raw, rendered, _make_fetch())
    robots_diffs = [d for d in diffs if d.field == "robots_meta"]
    assert len(robots_diffs) == 1
    assert robots_diffs[0].severity == Severity.CRITICAL


def test_h1_diff_is_warning():
    raw = SeoSignals(h1_texts=["Hello"])
    rendered = SeoSignals(h1_texts=["Hello World"])
    diffs = diff_signals(raw, rendered, _make_fetch())
    h1_diffs = [d for d in diffs if d.field == "h1_texts"]
    assert len(h1_diffs) == 1
    assert h1_diffs[0].severity == Severity.WARNING


def test_h2_diff_is_info():
    raw = SeoSignals(h2_texts=["A"])
    rendered = SeoSignals(h2_texts=["A", "B"])
    diffs = diff_signals(raw, rendered, _make_fetch())
    h2_diffs = [d for d in diffs if d.field == "h2_texts"]
    assert len(h2_diffs) == 1
    assert h2_diffs[0].severity == Severity.INFO


def test_structured_data_diff_is_critical():
    raw = SeoSignals(
        structured_data=[StructuredDataItem(sd_type="WebPage", raw_json={})]
    )
    rendered = SeoSignals(
        structured_data=[
            StructuredDataItem(sd_type="WebPage", raw_json={}),
            StructuredDataItem(sd_type="FAQPage", raw_json={}),
        ]
    )
    diffs = diff_signals(raw, rendered, _make_fetch())
    sd_diffs = [d for d in diffs if d.field == "structured_data"]
    assert len(sd_diffs) == 1
    assert sd_diffs[0].severity == Severity.CRITICAL
    assert "FAQPage" in sd_diffs[0].message


def test_word_count_threshold():
    raw = SeoSignals(word_count=100)
    rendered = SeoSignals(word_count=130)  # 30% > 20% threshold
    diffs = diff_signals(raw, rendered, _make_fetch())
    wc_diffs = [d for d in diffs if d.field == "word_count"]
    assert len(wc_diffs) == 1
    assert wc_diffs[0].severity == Severity.WARNING


def test_word_count_within_threshold():
    raw = SeoSignals(word_count=100)
    rendered = SeoSignals(word_count=110)  # 10% < 20% threshold
    diffs = diff_signals(raw, rendered, _make_fetch())
    wc_diffs = [d for d in diffs if d.field == "word_count"]
    assert len(wc_diffs) == 0


def test_html_size_over_2mb():
    raw = SeoSignals(html_size_bytes=3_000_000)
    rendered = SeoSignals(html_size_bytes=1_000_000)
    diffs = diff_signals(raw, rendered, _make_fetch())
    limit_diffs = [d for d in diffs if d.field == "html_size_limit"]
    assert len(limit_diffs) == 1
    assert limit_diffs[0].severity == Severity.CRITICAL
    assert "2MB" in limit_diffs[0].message


def test_images_lazy_loaded():
    raw = SeoSignals(images=[ImageInfo(src="/a.jpg")])
    rendered = SeoSignals(
        images=[ImageInfo(src="/a.jpg"), ImageInfo(src="/b.jpg"), ImageInfo(src="/c.jpg")]
    )
    diffs = diff_signals(raw, rendered, _make_fetch())
    img_diffs = [d for d in diffs if d.field == "images"]
    assert len(img_diffs) == 1
    assert "lazy-loaded" in img_diffs[0].message


def test_js_dependent_title():
    raw = SeoSignals(title=None)
    rendered = SeoSignals(title="JS-set Title")
    diffs = diff_signals(raw, rendered, _make_fetch())
    title_diffs = [d for d in diffs if d.field == "title"]
    assert len(title_diffs) == 1
    assert "JS-dependent" in title_diffs[0].message


def test_full_sample_diff():
    """Test with the sample HTML fixtures to verify end-to-end diff."""
    raw = extract_signals(SAMPLE_HTML, BASE_URL)
    rendered = extract_signals(SAMPLE_HTML_RENDERED, BASE_URL)
    diffs = diff_signals(raw, rendered, _make_fetch())

    fields_with_diffs = {d.field for d in diffs}
    assert "title" in fields_with_diffs
    assert "structured_data" in fields_with_diffs
