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


def start_with_recorder(monkeypatch: pytest.MonkeyPatch) -> tuple[CliRunner, dict[str, object]]:
    seen: dict[str, object] = {}

    def fake_build_app(*build_args: object, **build_kwargs: object) -> object:
        seen.update(build_kwargs)
        warn = build_kwargs.get("warn")
        if callable(warn):
            warn("unsupported type 'weird-unknown-type'")
        return object()

    monkeypatch.setattr(cli_module, "load_openapi", lambda _: {"paths": {}})
    monkeypatch.setattr(cli_module, "build_app", fake_build_app)
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: None)
    return runner, seen


def test_start_prints_warnings_through_the_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli, seen = start_with_recorder(monkeypatch)

    result = cli.invoke(app, ["start", "spec.yaml"])

    assert result.exit_code == 0
    assert callable(seen["warn"])
    assert "unsupported type 'weird-unknown-type'" in _strip_ansi(result.stdout)


def test_start_swallows_warnings_when_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    cli, seen = start_with_recorder(monkeypatch)

    result = cli.invoke(app, ["start", "spec.yaml", "--quiet"])

    assert result.exit_code == 0
    assert seen["warn"] is None
    assert "weird-unknown-type" not in result.stdout


def _patch_start(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "probe", "version": "1"},
        "paths": {"/users": {"get": {"responses": {"200": {"content": {}}}}}},
    }
    monkeypatch.setattr(cli_module, "load_openapi", lambda _: spec)
    monkeypatch.setattr(cli_module, "build_app", lambda *args, **kwargs: object())
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: None)


def test_start_quiet_omits_the_route_table(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_start(monkeypatch)

    result = runner.invoke(app, ["start", "spec.yaml", "--quiet"])

    assert result.exit_code == 0
    assert "/users" not in _strip_ansi(result.stdout)


def test_start_prints_the_route_table_without_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_start(monkeypatch)

    result = runner.invoke(app, ["start", "spec.yaml"])

    assert result.exit_code == 0
    assert "/users" in _strip_ansi(result.stdout)


def test_emit_warning_escapes_rich_markup(capsys: pytest.CaptureFixture[str]) -> None:
    cli_module._emit_warning("unsupported type '[/]'")

    assert "[/]" in _strip_ansi(capsys.readouterr().out)


def _broken_specs(tmp_path: Path) -> dict[str, Path]:
    malformed = tmp_path / "malformed.yaml"
    malformed.write_text("openapi: 3.0.0\npaths: [\n  - not yaml", encoding="utf-8")
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text('openapi: 3.0.0\ninfo:\n  version: "1.0"\npaths: {}\n', encoding="utf-8")
    return {
        "missing": tmp_path / "absent.yaml",
        "malformed": malformed,
        "invalid": invalid,
        "directory": tmp_path,
    }


@pytest.mark.parametrize("command", ["start", "routes"])
@pytest.mark.parametrize("case", ["missing", "malformed", "invalid", "directory"])
def test_with_an_unusable_spec_exits_with_one_line(tmp_path: Path, command: str, case: str) -> None:
    result = runner.invoke(app, [command, str(_broken_specs(tmp_path)[case])])

    assert result.exit_code == 2
    assert "Traceback" not in result.output
    assert result.stderr.strip().startswith("quackend: cannot load spec")
    assert len(result.stderr.strip().splitlines()) == 1
