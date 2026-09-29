import re
from pathlib import Path

import pytest
import uvicorn
from typer.testing import CliRunner

from quackend import cli as cli_module
from quackend.cli import app
from quackend.store import QuackStore

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return ANSI.sub("", text)


def test_routes_command_petstore_prints_paths_and_methods() -> None:
    result = runner.invoke(app, ["routes", str(FIXTURES / "petstore.yaml")])
    assert result.exit_code == 0
    assert "/users" in result.stdout
    assert "/users/{id}" in result.stdout
    assert "GET" in result.stdout


def test_start_help_lists_port_and_fail_rate() -> None:
    result = runner.invoke(app, ["start", "--help"])
    assert result.exit_code == 0
    stdout = _strip_ansi(result.stdout)
    assert "--port" in stdout
    assert "--fail-rate" in stdout


# The help output only proves that typer registered the options. The command itself
# is the wiring load_openapi -> build_app -> uvicorn.run, so each hop is replaced by
# a recorder and the arguments uvicorn would have bound are asserted instead.
def test_start_passes_the_port_to_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(cli_module, "load_openapi", lambda _: {"paths": {}})
    monkeypatch.setattr(cli_module, "build_app", lambda *args, **kwargs: object())
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: seen.update(kwargs))

    result = runner.invoke(app, ["start", "spec.yaml", "--port", "9123"])

    assert result.exit_code == 0
    assert seen["port"] == 9123


def test_start_seeds_the_store_with_the_requested_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    seeded: list[int | None] = []
    monkeypatch.setattr(cli_module, "load_openapi", lambda _: {"paths": {}})
    monkeypatch.setattr(cli_module, "build_app", lambda *args, **kwargs: object())
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: None)
    monkeypatch.setattr(QuackStore, "set_seed", lambda self, seed: seeded.append(seed))

    result = runner.invoke(app, ["start", "spec.yaml", "--seed", "42"])

    assert result.exit_code == 0
    assert seeded == [42]
