from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quackend import cli as cli_module
from quackend.cli import app
from quackend.loader import SpecLoadError, load_openapi
from quackend.store import QuackStore

FIXTURES = Path(__file__).parent / "fixtures"


def test_routes_command_petstore_prints_paths_and_methods(runner: CliRunner) -> None:
    result = runner.invoke(app, ["routes", str(FIXTURES / "petstore.yaml")])

    assert result.exit_code == 0
    assert "/users" in result.stdout
    assert "/users/{id}" in result.stdout
    assert "GET" in result.stdout


def test_start_help_lists_port_and_fail_rate(
    runner: CliRunner, strip_ansi: Callable[[str], str]
) -> None:
    result = runner.invoke(app, ["start", "--help"])

    assert result.exit_code == 0
    stdout = strip_ansi(result.stdout)
    assert "--port" in stdout
    assert "--fail-rate" in stdout


# The help output only proves that typer registered the options. The command itself
# is the wiring load_openapi -> build_app -> uvicorn.run, so each hop is replaced by
# a recorder and the arguments uvicorn would have bound are asserted instead.
def test_start_passes_the_port_to_uvicorn(
    runner: CliRunner, patch_start: dict[str, object]
) -> None:
    result = runner.invoke(app, ["start", "spec.yaml", "--port", "9123"])

    assert result.exit_code == 0
    assert patch_start["port"] == 9123


def test_start_seeds_the_store_with_the_requested_seed(
    runner: CliRunner,
    patch_start: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded: list[int | None] = []
    monkeypatch.setattr(QuackStore, "set_seed", lambda self, seed: seeded.append(seed))

    result = runner.invoke(app, ["start", "spec.yaml", "--seed", "42"])

    assert result.exit_code == 0
    assert seeded == [42]


def test_start_prints_warnings_through_the_console(
    runner: CliRunner,
    patch_start: dict[str, object],
    warn_recorder: dict[str, object],
    strip_ansi: Callable[[str], str],
) -> None:
    result = runner.invoke(app, ["start", "spec.yaml"])

    assert result.exit_code == 0
    assert callable(warn_recorder["warn"])
    assert "unsupported type 'weird-unknown-type'" in strip_ansi(result.stdout)


def test_start_swallows_warnings_when_quiet(
    runner: CliRunner,
    patch_start: dict[str, object],
    warn_recorder: dict[str, object],
) -> None:
    result = runner.invoke(app, ["start", "spec.yaml", "--quiet"])

    assert result.exit_code == 0
    assert warn_recorder["warn"] is None
    assert "weird-unknown-type" not in result.stdout


def test_start_quiet_omits_the_route_table(
    runner: CliRunner, patch_start: dict[str, object], strip_ansi: Callable[[str], str]
) -> None:
    result = runner.invoke(app, ["start", "spec.yaml", "--quiet"])

    assert result.exit_code == 0
    assert "/users" not in strip_ansi(result.stdout)


def test_start_prints_the_route_table_without_quiet(
    runner: CliRunner, patch_start: dict[str, object], strip_ansi: Callable[[str], str]
) -> None:
    result = runner.invoke(app, ["start", "spec.yaml"])

    assert result.exit_code == 0
    assert "/users" in strip_ansi(result.stdout)


def test_emit_warning_escapes_rich_markup(
    capsys: pytest.CaptureFixture[str], strip_ansi: Callable[[str], str]
) -> None:
    cli_module._emit_warning("unsupported type '[/]'")

    assert "[/]" in strip_ansi(capsys.readouterr().out)


@pytest.mark.parametrize("command", ["start", "routes"])
@pytest.mark.parametrize("case", ["missing", "malformed", "invalid", "directory", "tab"])
def test_cli_with_an_unusable_spec_reports_one_line_and_exits_2(
    runner: CliRunner, broken_specs: dict[str, Path], command: str, case: str
) -> None:
    result = runner.invoke(app, [command, str(broken_specs[case])])

    assert result.exit_code == 2
    assert "Traceback" not in result.output
    assert result.stderr.strip().startswith("quackend: cannot load spec")
    assert len(result.stderr.strip().splitlines()) == 1


def test_cli_with_an_unusable_spec_reports_the_reason(
    runner: CliRunner, broken_specs: dict[str, Path]
) -> None:
    spec = str(broken_specs["invalid"])

    with pytest.raises(SpecLoadError) as info:
        load_openapi(spec)

    result = runner.invoke(app, ["routes", spec])

    assert result.stderr.strip() == f"quackend: cannot load spec {spec!r}: {info.value}"


def test_start_announces_the_address_before_it_serves(
    runner: CliRunner,
    patch_start: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    strip_ansi: Callable[[str], str],
) -> None:
    def refuse_to_serve(app: object, **kwargs: object) -> None:
        raise RuntimeError("the serve call is where the banner would have to follow")

    monkeypatch.setattr("uvicorn.run", refuse_to_serve)

    result = runner.invoke(app, ["start", "spec.yaml", "--port", "9123"])

    assert "Starting quackend on http://127.0.0.1:9123 (Ctrl+C to stop)" in strip_ansi(
        result.stdout
    )


def test_start_quiet_prints_no_banner(runner: CliRunner, patch_start: dict[str, object]) -> None:
    result = runner.invoke(app, ["start", "spec.yaml", "--quiet", "--port", "9123"])

    assert result.exit_code == 0
    assert "Starting quackend" not in result.stdout


@pytest.mark.parametrize("port", ["0", "65536", "99999"])
def test_start_rejects_a_port_outside_the_tcp_range(
    runner: CliRunner, patch_start: dict[str, object], port: str
) -> None:
    result = runner.invoke(app, ["start", "spec.yaml", "--port", port])

    assert result.exit_code == 2
    assert patch_start.get("port") is None


@pytest.mark.parametrize("port", [1, 65535])
def test_start_accepts_the_endpoints_of_the_tcp_range(
    runner: CliRunner, patch_start: dict[str, object], port: int
) -> None:
    result = runner.invoke(app, ["start", "spec.yaml", "--port", str(port)])

    assert result.exit_code == 0
    assert patch_start["port"] == port
