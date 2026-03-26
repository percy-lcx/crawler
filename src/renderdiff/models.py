"""Pydantic data models for renderdiff."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class RedirectHop(BaseModel):
    url: str
    status_code: int


class FetchResult(BaseModel):
    """Result of a raw HTTP GET."""

    url: str
    final_url: str
    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)
    redirect_chain: list[RedirectHop] = Field(default_factory=list)
    html: str = ""
    html_size_bytes: int = 0
    content_type: str = ""
    fetch_time_ms: float = 0.0
    is_html: bool = True
    cloudflare_detected: bool = False
    error: str | None = None


class RenderResult(BaseModel):
    """Result of headless Chromium rendering."""

    url: str
    rendered_html: str = ""
    rendered_size_bytes: int = 0
    console_errors: list[str] = Field(default_factory=list)
    failed_requests: list[str] = Field(default_factory=list)
    render_time_ms: float = 0.0
    error: str | None = None


class ImageInfo(BaseModel):
    src: str
    alt: str | None = None
    loading: str | None = None


class LinkInfo(BaseModel):
    href: str
    text: str = ""
    rel: str | None = None
    is_internal: bool = False


class HreflangEntry(BaseModel):
    lang: str
    href: str


class StructuredDataItem(BaseModel):
    sd_type: str
    raw_json: dict[str, Any] = Field(default_factory=dict)


class SeoSignals(BaseModel):
    """Extracted SEO signals from one HTML source."""

    title: str | None = None
    meta_description: str | None = None
    canonical: str | None = None
    robots_meta: str | None = None
    x_robots_tag: str | None = None
    h1_texts: list[str] = Field(default_factory=list)
    h2_texts: list[str] = Field(default_factory=list)
    structured_data: list[StructuredDataItem] = Field(default_factory=list)
    internal_links: list[LinkInfo] = Field(default_factory=list)
    images: list[ImageInfo] = Field(default_factory=list)
    hreflang: list[HreflangEntry] = Field(default_factory=list)
    word_count: int = 0
    html_size_bytes: int = 0


class SignalDiff(BaseModel):
    """One difference between raw and rendered signals."""

    field: str
    severity: Severity
    raw_value: Any = None
    rendered_value: Any = None
    message: str


class UrlReport(BaseModel):
    """Full report for a single URL."""

    url: str
    timestamp: str = ""
    fetch: FetchResult | None = None
    render: RenderResult | None = None
    raw_signals: SeoSignals | None = None
    rendered_signals: SeoSignals | None = None
    diffs: list[SignalDiff] = Field(default_factory=list)
    overall_status: str = "pass"  # "pass" | "warn" | "fail"
    cloudflare_detected: bool = False
    skipped: bool = False
    skip_reason: str | None = None


class RunReport(BaseModel):
    """Top-level report for an entire run."""

    run_id: str
    started_at: str
    finished_at: str = ""
    total_urls: int = 0
    passed: int = 0
    warned: int = 0
    failed: int = 0
    skipped: int = 0
    urls: list[UrlReport] = Field(default_factory=list)
