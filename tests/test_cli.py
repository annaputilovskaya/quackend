from pathlib import Path

from typer.testing import CliRunner

from quackend.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_routes_command_lists_paths():
    result = runner.invoke(app, ["routes", str(FIXTURES / "petstore.yaml")])
    assert result.exit_code == 0
    assert "/users" in result.stdout
    assert "/users/{id}" in result.stdout
    assert "GET" in result.stdout
