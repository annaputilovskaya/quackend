"""Command-line interface for quackend."""

from __future__ import annotations

from typing import Any

import typer
import uvicorn
from rich.console import Console
from rich.markup import escape as escape_markup

from quackend import __version__
from quackend.loader import load_openapi
from quackend.reporting import render_route_table
from quackend.server import build_app
from quackend.store import QuackStore

app = typer.Typer(add_completion=False)
console = Console()


def _emit_warning(message: str) -> None:
    """Print a generator warning on the shared console.

    Args:
        message: the fail-soft message reported by the library.
    """
    console.print(f"[yellow][WARNING][/yellow] {escape_markup(message)}")


@app.callback()
def _callback() -> None:
    """Quackend command-line interface."""


@app.command()
def routes(spec: str) -> None:
    """Print the routes declared in an OpenAPI spec.

    Args:
        spec: path or URL of the OpenAPI spec.
    """
    console.print(render_route_table(_load_or_exit(spec)))


def _load_or_exit(spec: str) -> dict[str, Any]:
    """Load a spec, reporting any failure as a CLI error instead of a traceback.

    Args:
        spec: path or URL of the OpenAPI spec.

    Returns:
        The fully resolved specification.

    Raises:
        typer.Exit: with code 2, after one line naming the reason has gone to stderr.
    """
    try:
        return load_openapi(spec)
    except Exception as exc:
        typer.echo(f"quackend: cannot load spec {spec!r}: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@app.command()
def start(
    spec: str,
    port: int = typer.Option(8000, "--port", min=1, max=65535),
    host: str = typer.Option("127.0.0.1", "--host"),
    latency: int = typer.Option(0, "--latency"),
    fail_rate: float = typer.Option(0.0, "--fail-rate", min=0.0, max=1.0),
    seed: int | None = typer.Option(None, "--seed"),
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    """Start the mock server for an OpenAPI spec.

    Loads the spec, seeds the store, prints the route table unless quiet, and
    serves generated mock responses until interrupted. All parameters except
    spec are command-line options that tune the simulation.

    Args:
        spec: path or URL of the OpenAPI spec to simulate.
        port: TCP port to bind the mock server to.
        host: interface hostname or IP to bind the mock server to.
        latency: artificial delay in milliseconds applied to every request.
        fail_rate: probability in [0, 1] that a request fails with HTTP 500.
        seed: random seed for reproducible generated data; unset means random.
        quiet: when True, suppress banner output and reduce uvicorn logging.
    """
    spec_data = _load_or_exit(spec)
    store = QuackStore()
    store.set_seed(seed)
    if not quiet:
        console.print(render_route_table(spec_data))
        typer.echo(f"quackend v{__version__}")
    app_obj = build_app(
        spec_data,
        store,
        latency_ms=latency,
        fail_rate=fail_rate,
        warn=None if quiet else _emit_warning,
    )
    if not quiet:
        typer.echo(f"Starting quackend on http://{host}:{port} (Ctrl+C to stop)")
    uvicorn.run(app_obj, host=host, port=port, log_level="warning" if quiet else "info")


def main() -> None:
    """Run the quackend command-line application."""
    app()


if __name__ == "__main__":
    main()
