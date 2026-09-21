"""Command-line interface for quackend."""

from __future__ import annotations

import typer

from quackend.loader import load_openapi
from quackend.reporting import render_route_table

app = typer.Typer(add_completion=False)


@app.callback()
def _callback() -> None:
    """Quackend command-line interface."""


@app.command()
def routes(spec: str) -> None:
    """Print the routes declared in an OpenAPI spec.

    Args:
        spec: path or URL of the OpenAPI spec.
    """
    render_route_table(load_openapi(spec))


def main() -> None:
    """Run the quackend command-line application."""
    app()
