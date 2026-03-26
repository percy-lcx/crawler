"""Tests for CLI entry point."""

from typer.testing import CliRunner

from renderdiff.cli import app


runner = CliRunner()


def test_no_args_shows_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "renderdiff" in result.output.lower() or "Usage" in result.output


def test_no_url_source_exits_with_error():
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 1
