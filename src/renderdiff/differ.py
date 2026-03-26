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

    # Internal links count
    _diff_count(
        diffs,
        "internal_links",
        len(raw.internal_links),
        len(rendered.internal_links),
        LINK_COUNT_THRESHOLD_PCT,
        Severity.WARNING,
    )

    # Images count
    raw_img_count = len(raw.images)
    rendered_img_count = len(rendered.images)
    if rendered_img_count > raw_img_count:
        diffs.append(
            SignalDiff(
                field="images",
                severity=Severity.WARNING,
                raw_value=raw_img_count,
                rendered_value=rendered_img_count,
                message=(
                    f"Rendered has {rendered_img_count - raw_img_count} more images "
                    f"than raw ({raw_img_count} vs {rendered_img_count}) — "
                    f"likely lazy-loaded"
                ),
            )
        )

    # Hreflang
    raw_langs = {e.lang for e in raw.hreflang}
    rendered_langs = {e.lang for e in rendered.hreflang}
    if raw_langs != rendered_langs:
        diffs.append(
            SignalDiff(
                field="hreflang",
                severity=Severity.WARNING,
                raw_value=sorted(raw_langs),
                rendered_value=sorted(rendered_langs),
                message="Hreflang languages differ between raw and rendered",
            )
        )

    # Word count
    _diff_count(
        diffs,
        "word_count",
        raw.word_count,
        rendered.word_count,
        WORD_COUNT_THRESHOLD_PCT,
        Severity.WARNING,
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
        diffs.append(
            SignalDiff(
                field=field,
                severity=severity,
                raw_value=raw_val,
                rendered_value=rendered_val,
                message=f"{field}: content differs between raw and rendered",
            )
        )


def _diff_count(
    diffs: list[SignalDiff],
    field: str,
    raw_count: int,
    rendered_count: int,
    threshold_pct: int,
    severity: Severity,
) -> None:
    pct = _pct_change(raw_count, rendered_count)
    if pct > threshold_pct:
        diffs.append(
            SignalDiff(
                field=field,
                severity=severity,
                raw_value=raw_count,
                rendered_value=rendered_count,
                message=(
                    f"{field}: count differs by {pct:.0f}% "
                    f"(raw={raw_count}, rendered={rendered_count})"
                ),
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
