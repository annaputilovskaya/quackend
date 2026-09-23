import re
from pathlib import Path

from typer.testing import CliRunner

from quackend.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return ANSI.sub("", text)


def test_routes_command_petstore_prints_paths_and_methods():
    result = runner.invoke(app, ["routes", str(FIXTURES / "petstore.yaml")])
    assert result.exit_code == 0
    assert "/users" in result.stdout
    assert "/users/{id}" in result.stdout
    assert "GET" in result.stdout


def test_start_command_defined():
    result = runner.invoke(app, ["start", "--help"])
    assert result.exit_code == 0
    stdout = _strip_ansi(result.stdout)
    assert "--port" in stdout
    assert "--fail-rate" in stdout
