import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from typer.testing import CliRunner

from quackend import cli as cli_module

ANSI = re.compile(r"\x1b\[[0-9;]*m")

PROBE_SPEC: dict[str, Any] = {
    "openapi": "3.0.0",
    "info": {"title": "probe", "version": "1"},
    "paths": {"/users": {"get": {"responses": {"200": {"content": {}}}}}},
}

BROKEN_SPECS: dict[str, str] = {
    "malformed": "openapi: 3.0.0\npaths: [\n  - not yaml",
    "invalid": 'openapi: 3.0.0\ninfo:\n  version: "1.0"\npaths: {}\n',
    "tab": "paths:\n\t- a\n",
}


@pytest.fixture
def strip_ansi() -> Callable[[str], str]:
    """Drop ANSI colour codes so Rich output can be asserted on."""
    return lambda text: ANSI.sub("", text)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def patch_start(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Replace every hop of `start` so no socket is opened and no spec is read.

    Returns the dict that a replaced ``uvicorn.run`` records its keyword
    arguments into, so a test can assert what the server was asked to serve.
    """
    served: dict[str, object] = {}
    monkeypatch.setattr(cli_module, "load_openapi", lambda _: dict(PROBE_SPEC))
    monkeypatch.setattr(cli_module, "build_app", lambda *args, **kwargs: object())
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: served.update(kwargs))
    return served


@pytest.fixture
def warn_recorder(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Replace `build_app` so it records kwargs and fires the `warn` callback.

    `start` passes either a callable or None as `warn` depending on `--quiet`;
    firing the callable here is what proves a warning would reach the console.
    """
    seen: dict[str, object] = {}

    def fake_build_app(*args: object, **kwargs: object) -> object:
        seen.update(kwargs)
        warn = kwargs.get("warn")
        if callable(warn):
            warn("unsupported type 'weird-unknown-type'")
        return object()

    monkeypatch.setattr(cli_module, "build_app", fake_build_app)
    return seen


@pytest.fixture
def broken_specs(tmp_path: Path) -> dict[str, Path]:
    """Paths that `load_openapi` must reject, keyed by case name."""
    written = {name: tmp_path / f"{name}.yaml" for name in BROKEN_SPECS}
    for name, body in BROKEN_SPECS.items():
        written[name].write_text(body, encoding="utf-8")
    return {
        "missing": tmp_path / "absent.yaml",
        "malformed": written["malformed"],
        "invalid": written["invalid"],
        "tab": written["tab"],
        "directory": tmp_path,
    }
