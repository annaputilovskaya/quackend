from pathlib import Path

from typer.testing import CliRunner

from quackend.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_routes_command_petstore_prints_paths_and_methods():
    result = runner.invoke(app, ["routes", str(FIXTURES / "petstore.yaml")])
    assert result.exit_code == 0
    assert "/users" in result.stdout
    assert "/users/{id}" in result.stdout
    assert "GET" in result.stdout


def test_start_command_defined():
    result = runner.invoke(app, ["start", "--help"])
    assert result.exit_code == 0
    assert "--port" in result.stdout
    assert "--fail-rate" in result.stdout
