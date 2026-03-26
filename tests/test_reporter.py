"""Tests for the reporter detail rendering."""

from renderdiff.reporter import _render_details


def test_render_details_none():
    assert _render_details(None) == ""


def test_render_details_empty_dict():
    assert _render_details({}) == ""


def test_render_details_with_items():
    details = {
        "only_in_rendered": ["/a.jpg", "/b.jpg"],
        "only_in_raw": ["/c.jpg"],
    }
    result = _render_details(details)
    assert "Only in rendered (2)" in result
    assert "/a.jpg" in result
    assert "/b.jpg" in result
    assert "Only in raw (1)" in result
    assert "/c.jpg" in result


def test_render_details_truncation():
    details = {"only_in_rendered": [f"/img{i}.jpg" for i in range(25)]}
    result = _render_details(details)
    assert "Only in rendered (25)" in result
    assert "and 5 more" in result
    # First 20 should be present
    assert "/img0.jpg" in result
    assert "/img19.jpg" in result
    # Item 21+ should not be directly listed
    assert "/img20.jpg" not in result


def test_render_details_html_escapes():
    details = {"only_in_rendered": ['<script>alert("xss")</script>']}
    result = _render_details(details)
    assert "<script>" not in result
    assert "&lt;script&gt;" in result
