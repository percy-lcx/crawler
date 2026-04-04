"""Typer CLI entry point for renderdiff."""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

import typer

from .input import resolve_urls
from .pipeline import run
from .reporter import (
    print_cli_summary,
    print_index_summary,
    write_html_report,
    write_index_html_report,
    write_index_json_report,
    write_json_report,
)

app = typer.Typer(
    name="renderdiff",
    help="Compare raw HTML vs rendered DOM for SEO signal discrepancies.",
    no_args_is_help=True,
)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8000, help="Port number"),
    cookies: Optional[str] = typer.Option(
        None,
        "--cookies",
        "-k",
        help="Path to cookies JSON file for Google CAPTCHA session.",
    ),
) -> None:
    """Launch the web UI."""
    import uvicorn

    from .web.app import create_app

    typer.echo(f"Starting renderdiff web UI at http://{host}:{port}")
    uvicorn.run(create_app(cookies_file=cookies), host=host, port=port)


@app.command()
def index(
    url: Optional[str] = typer.Argument(None, help="Single URL to check"),
    input_file: Optional[str] = typer.Option(
        None, "--input", "-i", help="File with newline-delimited URLs"
    ),
    sitemap: Optional[str] = typer.Option(
        None, "--sitemap", "-s", help="Sitemap URL to parse for URLs"
    ),
    delay: float = typer.Option(
        5.0, "--delay", "-d", help="Delay between Google queries in seconds"
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Max number of URLs to check"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Path to write JSON report"
    ),
    html_report: Optional[str] = typer.Option(
        None, "--html", help="Path to write HTML report with SERP screenshots"
    ),
    cookies: Optional[str] = typer.Option(
        None,
        "--cookies",
        "-k",
        help="Path to cookies JSON file. If file doesn't exist, launches browser for CAPTCHA solving.",
    ),
) -> None:
    """Check whether URLs are indexed by Google via site: search."""
    if not url and not input_file and not sitemap:
        typer.echo(
            "Error: provide a URL argument, --input file, or --sitemap URL", err=True
        )
        raise typer.Exit(1)

    try:
        asyncio.run(
            _index_async(
                url=url,
                input_file=input_file,
                sitemap=sitemap,
                delay=delay,
                limit=limit,
                output=output,
                html_report=html_report,
                cookies=cookies,
            )
        )
    except KeyboardInterrupt:
        typer.echo("\nInterrupted.", err=True)
        raise typer.Exit(130)


async def _index_async(
    url: str | None,
    input_file: str | None,
    sitemap: str | None,
    delay: float,
    limit: int | None,
    output: str | None,
    html_report: str | None,
    cookies: str | None = None,
) -> None:
    urls = await resolve_urls(
        url=url,
        file_path=input_file,
        sitemap_url=sitemap,
        limit=limit,
    )

    if not urls:
        typer.echo("No URLs to process.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Checking indexation for {len(urls)} URL(s) (delay={delay}s)...\n")

    screenshot_dir = None
    if html_report:
        from pathlib import Path

        screenshot_dir = str(Path(html_report).parent / ".renderdiff-screenshots")

    from .indexation import check_indexation

    report = await check_indexation(urls, delay=delay, screenshot_dir=screenshot_dir, cookies_file=cookies)

    print_index_summary(report)

    if output:
        write_index_json_report(report, output)
        typer.echo(f"JSON report written to {output}")

    if html_report:
        write_index_html_report(report, html_report)
        typer.echo(f"HTML report written to {html_report}")

    if report.blocked > 0:
        raise typer.Exit(3)
    elif report.not_indexed > 0:
        raise typer.Exit(1)


@app.command()
def scan(
    url: Optional[str] = typer.Argument(None, help="Single URL to scan"),
    input_file: Optional[str] = typer.Option(
        None, "--input", "-i", help="File with newline-delimited URLs"
    ),
    sitemap: Optional[str] = typer.Option(
        None, "--sitemap", "-s", help="Sitemap URL to parse for URLs"
    ),
    delay: float = typer.Option(
        1.0, "--delay", "-d", help="Delay between requests in seconds"
    ),
    concurrency: int = typer.Option(
        3, "--concurrency", "-c", help="Max concurrent URL processing"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Path to write JSON report"
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Max number of URLs to process"
    ),
    html_report: Optional[str] = typer.Option(
        None, "--html", help="Path to write visual HTML report with screenshots"
    ),
) -> None:
    """Scan URLs and compare raw HTML vs rendered DOM."""
    if not url and not input_file and not sitemap:
        typer.echo("Error: provide a URL argument, --input file, or --sitemap URL", err=True)
        raise typer.Exit(1)

    try:
        asyncio.run(
            _scan_async(
                url=url,
                input_file=input_file,
                sitemap=sitemap,
                delay=delay,
                concurrency=concurrency,
                output=output,
                limit=limit,
                html_report=html_report,
            )
        )
    except KeyboardInterrupt:
        typer.echo("\nInterrupted.", err=True)
        raise typer.Exit(130)


async def _scan_async(
    url: str | None,
    input_file: str | None,
    sitemap: str | None,
    delay: float,
    concurrency: int,
    output: str | None,
    limit: int | None,
    html_report: str | None,
) -> None:
    urls = await resolve_urls(
        url=url,
        file_path=input_file,
        sitemap_url=sitemap,
        limit=limit,
    )

    if not urls:
        typer.echo("No URLs to process.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Processing {len(urls)} URL(s) (concurrency={concurrency}, delay={delay}s)...\n")

    # Enable screenshots when HTML report is requested
    screenshot_dir = None
    if html_report:
        from pathlib import Path

        screenshot_dir = str(Path(html_report).parent / ".renderdiff-screenshots")

    report = await run(
        urls,
        concurrency=concurrency,
        delay=delay,
        screenshot_dir=screenshot_dir,
    )

    print_cli_summary(report)

    if output:
        write_json_report(report, output)
        typer.echo(f"JSON report written to {output}")

    if html_report:
        write_html_report(report, html_report)
        typer.echo(f"HTML report written to {html_report}")

    # Exit code based on severity
    if report.failed > 0:
        raise typer.Exit(2)
    elif report.warned > 0:
        raise typer.Exit(1)
