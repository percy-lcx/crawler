"""Output formatting: CLI summary and JSON report."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from .models import RunReport, Severity


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
