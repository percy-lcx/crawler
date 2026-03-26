"""Output formatting: CLI summary, JSON report, and HTML report."""

from __future__ import annotations

import base64
import html
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .models import RunReport, Severity, UrlReport


def print_cli_summary(report: RunReport) -> None:
    """Print colored pass/warn/fail summary to terminal."""
    console = Console()

    table = Table(title="renderdiff Results", show_lines=True)
    table.add_column("URL", style="cyan", max_width=70)
    table.add_column("Status", justify="center")
    table.add_column("Critical", justify="center", style="red")
    table.add_column("Warning", justify="center", style="yellow")
    table.add_column("Info", justify="center", style="blue")

    for url_report in report.urls:
        if url_report.skipped:
            status = "[dim]SKIP[/dim]"
            table.add_row(url_report.url, status, "-", "-", "-")
            continue

        critical = sum(
            1 for d in url_report.diffs if d.severity == Severity.CRITICAL
        )
        warning = sum(
            1 for d in url_report.diffs if d.severity == Severity.WARNING
        )
        info = sum(
            1 for d in url_report.diffs if d.severity == Severity.INFO
        )

        if url_report.overall_status == "fail":
            status = "[bold red]FAIL[/bold red]"
        elif url_report.overall_status == "warn":
            status = "[bold yellow]WARN[/bold yellow]"
        else:
            status = "[bold green]PASS[/bold green]"

        table.add_row(
            url_report.url,
            status,
            str(critical) if critical else "-",
            str(warning) if warning else "-",
            str(info) if info else "-",
        )

    console.print(table)

    # Summary line
    parts = []
    if report.passed:
        parts.append(f"[green]{report.passed} passed[/green]")
    if report.warned:
        parts.append(f"[yellow]{report.warned} warned[/yellow]")
    if report.failed:
        parts.append(f"[red]{report.failed} failed[/red]")
    if report.skipped:
        parts.append(f"[dim]{report.skipped} skipped[/dim]")

    console.print(f"\nTotal: {', '.join(parts)} out of {report.total_urls} URLs\n")


def write_json_report(report: RunReport, output_path: str) -> None:
    """Write RunReport as JSON to file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2))


def write_html_report(report: RunReport, output_path: str) -> None:
    """Write a visual HTML report with screenshots and color-coded diffs."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    url_sections = "\n".join(_render_url_section(r) for r in report.urls)

    page = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>renderdiff Report — {report.run_id}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0d1117; color: #c9d1d9; padding: 2rem; line-height: 1.5; }}
  h1 {{ color: #f0f6fc; margin-bottom: .5rem; }}
  .meta {{ color: #8b949e; margin-bottom: 2rem; font-size: .9rem; }}
  .summary {{ display: flex; gap: 1.5rem; margin-bottom: 2rem; }}
  .summary .stat {{ padding: .75rem 1.25rem; border-radius: 8px; font-weight: 600; font-size: 1.1rem; }}
  .stat-pass {{ background: #0d1f0d; color: #3fb950; border: 1px solid #238636; }}
  .stat-warn {{ background: #1f1d0d; color: #d29922; border: 1px solid #9e6a03; }}
  .stat-fail {{ background: #1f0d0d; color: #f85149; border: 1px solid #da3633; }}
  .stat-skip {{ background: #161b22; color: #8b949e; border: 1px solid #30363d; }}
  .url-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
               margin-bottom: 1.5rem; overflow: hidden; }}
  .url-header {{ padding: 1rem 1.25rem; border-bottom: 1px solid #30363d; display: flex;
                 justify-content: space-between; align-items: center; }}
  .url-header h2 {{ font-size: 1rem; color: #58a6ff; word-break: break-all; }}
  .badge {{ padding: .25rem .75rem; border-radius: 12px; font-size: .8rem; font-weight: 600; text-transform: uppercase; }}
  .badge-pass {{ background: #238636; color: #fff; }}
  .badge-warn {{ background: #9e6a03; color: #fff; }}
  .badge-fail {{ background: #da3633; color: #fff; }}
  .badge-skip {{ background: #30363d; color: #8b949e; }}
  .url-body {{ padding: 1.25rem; }}
  .diff-table {{ width: 100%; border-collapse: collapse; margin-bottom: 1rem; }}
  .diff-table th {{ text-align: left; padding: .5rem .75rem; background: #0d1117;
                    color: #8b949e; font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; }}
  .diff-table td {{ padding: .5rem .75rem; border-top: 1px solid #21262d; font-size: .9rem;
                    vertical-align: top; }}
  .diff-table tr.critical td {{ border-left: 3px solid #f85149; }}
  .diff-table tr.warning td {{ border-left: 3px solid #d29922; }}
  .diff-table tr.info td {{ border-left: 3px solid #58a6ff; }}
  .sev {{ font-weight: 600; text-transform: uppercase; font-size: .75rem; }}
  .sev-critical {{ color: #f85149; }}
  .sev-warning {{ color: #d29922; }}
  .sev-info {{ color: #58a6ff; }}
  .val {{ font-family: 'SF Mono', Consolas, monospace; font-size: .8rem; color: #8b949e;
          max-width: 300px; overflow-wrap: break-word; }}
  .val-raw {{ color: #f85149; }}
  .val-rendered {{ color: #3fb950; }}
  .screenshot {{ margin-top: 1rem; }}
  .screenshot img {{ max-width: 100%; border: 1px solid #30363d; border-radius: 6px; }}
  .screenshot summary {{ cursor: pointer; color: #58a6ff; font-size: .9rem; margin-bottom: .5rem; }}
  .signals {{ margin-top: 1rem; }}
  .signals summary {{ cursor: pointer; color: #58a6ff; font-size: .9rem; margin-bottom: .5rem; }}
  .signals-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; padding: .5rem 0; }}
  .signals-col h3 {{ font-size: .85rem; color: #8b949e; margin-bottom: .5rem; text-transform: uppercase;
                     letter-spacing: .05em; }}
  .signals-col table {{ width: 100%; font-size: .8rem; }}
  .signals-col td {{ padding: .25rem .5rem; border-top: 1px solid #21262d; }}
  .signals-col td:first-child {{ color: #8b949e; width: 40%; }}
  .no-diffs {{ color: #3fb950; padding: .5rem 0; }}
  .skip-reason {{ color: #8b949e; font-style: italic; }}
</style>
</head>
<body>
<h1>renderdiff Report</h1>
<div class="meta">
  Run ID: {html.escape(report.run_id)} &middot;
  {html.escape(report.started_at)} &middot;
  {report.total_urls} URL(s)
</div>
<div class="summary">
  <div class="stat stat-pass">{report.passed} Passed</div>
  <div class="stat stat-warn">{report.warned} Warned</div>
  <div class="stat stat-fail">{report.failed} Failed</div>
  <div class="stat stat-skip">{report.skipped} Skipped</div>
</div>
{url_sections}
</body>
</html>"""

    path.write_text(page)


def _render_url_section(r: UrlReport) -> str:
    """Render one URL card for the HTML report."""
    status = r.overall_status if not r.skipped else "skip"
    badge_class = f"badge-{status}"
    badge_text = status.upper()

    if r.skipped:
        body = f'<div class="skip-reason">Skipped: {html.escape(r.skip_reason or "unknown")}</div>'
    elif not r.diffs:
        body = '<div class="no-diffs">No differences found — raw and rendered HTML match.</div>'
    else:
        rows = ""
        for d in r.diffs:
            sev_class = d.severity.value
            raw_display = _format_value(d.raw_value)
            rendered_display = _format_value(d.rendered_value)
            rows += f"""\
<tr class="{sev_class}">
  <td><span class="sev sev-{sev_class}">{d.severity.value}</span></td>
  <td>{html.escape(d.field)}</td>
  <td>{html.escape(d.message)}</td>
  <td><span class="val val-raw">{raw_display}</span></td>
  <td><span class="val val-rendered">{rendered_display}</span></td>
</tr>"""
        body = f"""\
<table class="diff-table">
<thead><tr><th>Severity</th><th>Field</th><th>Message</th><th>Raw</th><th>Rendered</th></tr></thead>
<tbody>{rows}</tbody>
</table>"""

    # Screenshot
    screenshot_html = ""
    if r.render and r.render.screenshot_path:
        img_data = _embed_image(r.render.screenshot_path)
        if img_data:
            screenshot_html = f"""\
<details class="screenshot">
  <summary>Screenshot (rendered page)</summary>
  <img src="{img_data}" alt="Screenshot of {html.escape(r.url)}">
</details>"""

    # Signal comparison
    signals_html = ""
    if r.raw_signals and r.rendered_signals:
        signals_html = f"""\
<details class="signals">
  <summary>Full signal comparison</summary>
  <div class="signals-grid">
    <div class="signals-col">
      <h3>Raw HTML</h3>
      {_render_signals_table(r.raw_signals)}
    </div>
    <div class="signals-col">
      <h3>Rendered DOM</h3>
      {_render_signals_table(r.rendered_signals)}
    </div>
  </div>
</details>"""

    return f"""\
<div class="url-card">
  <div class="url-header">
    <h2>{html.escape(r.url)}</h2>
    <span class="badge {badge_class}">{badge_text}</span>
  </div>
  <div class="url-body">
    {body}
    {screenshot_html}
    {signals_html}
  </div>
</div>"""


def _format_value(val: object) -> str:
    """Format a diff value for HTML display."""
    if val is None:
        return "<em>none</em>"
    s = str(val)
    if len(s) > 200:
        s = s[:200] + "..."
    return html.escape(s)


def _embed_image(path: str) -> str | None:
    """Read an image file and return a data URI, or None."""
    try:
        data = Path(path).read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None


def _render_signals_table(signals: object) -> str:
    """Render an SeoSignals object as a compact HTML table."""
    from .models import SeoSignals

    s: SeoSignals = signals  # type: ignore[assignment]
    rows = [
        ("title", s.title or "—"),
        ("description", s.meta_description or "—"),
        ("canonical", s.canonical or "—"),
        ("robots", s.robots_meta or "—"),
        ("h1", ", ".join(s.h1_texts) if s.h1_texts else "—"),
        ("h2", ", ".join(s.h2_texts) if s.h2_texts else "—"),
        ("structured data", ", ".join(sd.sd_type for sd in s.structured_data) if s.structured_data else "—"),
        ("internal links", str(len(s.internal_links))),
        ("images", str(len(s.images))),
        ("hreflang", ", ".join(h.lang for h in s.hreflang) if s.hreflang else "—"),
        ("word count", str(s.word_count)),
        ("html size", f"{s.html_size_bytes:,} B"),
    ]
    row_html = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in rows
    )
    return f"<table>{row_html}</table>"
