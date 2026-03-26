"""Signal comparison and severity classification."""

from __future__ import annotations

from .constants import (
    HTML_SIZE_LIMIT_BYTES,
    LINK_COUNT_THRESHOLD_PCT,
    WORD_COUNT_THRESHOLD_PCT,
)
from .models import FetchResult, SeoSignals, Severity, SignalDiff


def diff_signals(
    raw: SeoSignals,
    rendered: SeoSignals,
    fetch: FetchResult,
) -> list[SignalDiff]:
    """Compare raw and rendered SEO signals, return classified diffs."""
    diffs: list[SignalDiff] = []

    # Critical: scalar meta fields
    _diff_scalar(diffs, "title", raw.title, rendered.title, Severity.CRITICAL)
    _diff_scalar(
        diffs, "meta_description", raw.meta_description, rendered.meta_description,
        Severity.CRITICAL,
    )
    _diff_scalar(
        diffs, "canonical", raw.canonical, rendered.canonical, Severity.CRITICAL,
    )
    _diff_scalar(
        diffs, "robots_meta", raw.robots_meta, rendered.robots_meta, Severity.CRITICAL,
    )

    # Headings
    _diff_list(diffs, "h1_texts", raw.h1_texts, rendered.h1_texts, Severity.WARNING)
    _diff_list(diffs, "h2_texts", raw.h2_texts, rendered.h2_texts, Severity.INFO)

    # Structured data
    _diff_structured_data(diffs, raw, rendered)

    # Internal links — itemized diff
    raw_link_hrefs = {li.href for li in raw.internal_links}
    rendered_link_hrefs = {li.href for li in rendered.internal_links}
    if raw_link_hrefs != rendered_link_hrefs:
        only_in_raw_links = sorted(raw_link_hrefs - rendered_link_hrefs)
        only_in_rendered_links = sorted(rendered_link_hrefs - raw_link_hrefs)
        raw_count = len(raw.internal_links)
        rendered_count = len(rendered.internal_links)
        pct = _pct_change(raw_count, rendered_count)

        link_details: dict[str, list[str]] = {}
        if only_in_rendered_links:
            link_details["only_in_rendered"] = only_in_rendered_links
        if only_in_raw_links:
            link_details["only_in_raw"] = only_in_raw_links

        if pct > LINK_COUNT_THRESHOLD_PCT or link_details:
            diffs.append(
                SignalDiff(
                    field="internal_links",
                    severity=Severity.WARNING,
                    raw_value=raw_count,
                    rendered_value=rendered_count,
                    message=(
                        f"internal_links: count differs by {pct:.0f}% "
                        f"(raw={raw_count}, rendered={rendered_count})"
                    ),
                    details=link_details if link_details else None,
                )
            )

    # Images — itemized diff
    raw_img_srcs = {img.src for img in raw.images}
    rendered_img_srcs = {img.src for img in rendered.images}
    if raw_img_srcs != rendered_img_srcs:
        only_in_raw_imgs = sorted(raw_img_srcs - rendered_img_srcs)
        only_in_rendered_imgs = sorted(rendered_img_srcs - raw_img_srcs)
        raw_img_count = len(raw.images)
        rendered_img_count = len(rendered.images)

        img_details: dict[str, list[str]] = {}
        if only_in_rendered_imgs:
            img_details["only_in_rendered"] = only_in_rendered_imgs
        if only_in_raw_imgs:
            img_details["only_in_raw"] = only_in_raw_imgs

        if rendered_img_count > raw_img_count:
            img_msg = (
                f"Rendered has {rendered_img_count - raw_img_count} more images "
                f"than raw ({raw_img_count} vs {rendered_img_count}) — "
                f"likely lazy-loaded"
            )
        else:
            img_msg = (
                f"Image sources differ (raw={raw_img_count}, rendered={rendered_img_count})"
            )

        diffs.append(
            SignalDiff(
                field="images",
                severity=Severity.WARNING,
                raw_value=raw_img_count,
                rendered_value=rendered_img_count,
                message=img_msg,
                details=img_details if img_details else None,
            )
        )

    # Hreflang — itemized diff
    raw_hreflang_set = {(e.lang, e.href) for e in raw.hreflang}
    rendered_hreflang_set = {(e.lang, e.href) for e in rendered.hreflang}
    if raw_hreflang_set != rendered_hreflang_set:
        only_in_raw_hl = sorted(
            f"{lang}: {href}" for lang, href in (raw_hreflang_set - rendered_hreflang_set)
        )
        only_in_rendered_hl = sorted(
            f"{lang}: {href}" for lang, href in (rendered_hreflang_set - raw_hreflang_set)
        )

        hl_details: dict[str, list[str]] = {}
        if only_in_rendered_hl:
            hl_details["only_in_rendered"] = only_in_rendered_hl
        if only_in_raw_hl:
            hl_details["only_in_raw"] = only_in_raw_hl

        diffs.append(
            SignalDiff(
                field="hreflang",
                severity=Severity.WARNING,
                raw_value=sorted(e.lang for e in raw.hreflang),
                rendered_value=sorted(e.lang for e in rendered.hreflang),
                message="Hreflang entries differ between raw and rendered",
                details=hl_details if hl_details else None,
            )
        )

    # Word count — itemized diff
    pct = _pct_change(raw.word_count, rendered.word_count)
    if pct > WORD_COUNT_THRESHOLD_PCT:
        only_in_raw_words = sorted(raw.body_text_words - rendered.body_text_words)
        only_in_rendered_words = sorted(rendered.body_text_words - raw.body_text_words)

        wc_details: dict[str, list[str]] = {}
        if only_in_rendered_words:
            wc_details["only_in_rendered"] = only_in_rendered_words
        if only_in_raw_words:
            wc_details["only_in_raw"] = only_in_raw_words

        diffs.append(
            SignalDiff(
                field="word_count",
                severity=Severity.WARNING,
                raw_value=raw.word_count,
                rendered_value=rendered.word_count,
                message=(
                    f"word_count: count differs by {pct:.0f}% "
                    f"(raw={raw.word_count}, rendered={rendered.word_count})"
                ),
                details=wc_details if wc_details else None,
            )
        )

    # HTML size
    if raw.html_size_bytes != rendered.html_size_bytes:
        diffs.append(
            SignalDiff(
                field="html_size_bytes",
                severity=Severity.INFO,
                raw_value=raw.html_size_bytes,
                rendered_value=rendered.html_size_bytes,
                message=(
                    f"HTML size: raw={raw.html_size_bytes:,}B, "
                    f"rendered={rendered.html_size_bytes:,}B"
                ),
            )
        )

    # 2 MB limit check
    for label, size in [("raw", raw.html_size_bytes), ("rendered", rendered.html_size_bytes)]:
        if size > HTML_SIZE_LIMIT_BYTES:
            diffs.append(
                SignalDiff(
                    field="html_size_limit",
                    severity=Severity.CRITICAL,
                    raw_value=None,
                    rendered_value=size,
                    message=(
                        f"{label.capitalize()} HTML exceeds 2MB limit "
                        f"({size:,}B) — Googlebot may truncate"
                    ),
                )
            )

    return diffs


def _diff_scalar(
    diffs: list[SignalDiff],
    field: str,
    raw_val: str | None,
    rendered_val: str | None,
    severity: Severity,
) -> None:
    r = (raw_val or "").strip()
    d = (rendered_val or "").strip()
    if r != d:
        if not r and d:
            msg = f"{field}: missing in raw, present in rendered (JS-dependent)"
        elif r and not d:
            msg = f"{field}: present in raw, missing in rendered"
        else:
            msg = f"{field}: differs — raw='{r}' vs rendered='{d}'"
        diffs.append(
            SignalDiff(
                field=field,
                severity=severity,
                raw_value=raw_val,
                rendered_value=rendered_val,
                message=msg,
            )
        )


def _diff_list(
    diffs: list[SignalDiff],
    field: str,
    raw_val: list[str],
    rendered_val: list[str],
    severity: Severity,
) -> None:
    if raw_val != rendered_val:
        raw_set = set(raw_val)
        rendered_set = set(rendered_val)
        only_in_raw = sorted(raw_set - rendered_set)
        only_in_rendered = sorted(rendered_set - raw_set)

        parts: list[str] = []
        if only_in_rendered:
            parts.append(f"{len(only_in_rendered)} only in rendered")
        if only_in_raw:
            parts.append(f"{len(only_in_raw)} only in raw")
        msg = f"{field}: content differs — {', '.join(parts)}" if parts else f"{field}: ordering differs"

        details: dict[str, list[str]] = {}
        if only_in_rendered:
            details["only_in_rendered"] = only_in_rendered
        if only_in_raw:
            details["only_in_raw"] = only_in_raw

        diffs.append(
            SignalDiff(
                field=field,
                severity=severity,
                raw_value=raw_val,
                rendered_value=rendered_val,
                message=msg,
                details=details if details else None,
            )
        )


def _diff_structured_data(
    diffs: list[SignalDiff],
    raw: SeoSignals,
    rendered: SeoSignals,
) -> None:
    raw_types = sorted(sd.sd_type for sd in raw.structured_data)
    rendered_types = sorted(sd.sd_type for sd in rendered.structured_data)
    if raw_types != rendered_types:
        missing_in_raw = set(rendered_types) - set(raw_types)
        missing_in_rendered = set(raw_types) - set(rendered_types)
        parts: list[str] = []
        if missing_in_raw:
            parts.append(f"JS-dependent types: {', '.join(sorted(missing_in_raw))}")
        if missing_in_rendered:
            parts.append(f"missing in rendered: {', '.join(sorted(missing_in_rendered))}")
        diffs.append(
            SignalDiff(
                field="structured_data",
                severity=Severity.CRITICAL,
                raw_value=raw_types,
                rendered_value=rendered_types,
                message=f"Structured data types differ — {'; '.join(parts)}",
            )
        )


def _pct_change(raw_val: int, rendered_val: int) -> float:
    if raw_val == 0:
        return 100.0 if rendered_val > 0 else 0.0
    return abs(rendered_val - raw_val) / raw_val * 100
