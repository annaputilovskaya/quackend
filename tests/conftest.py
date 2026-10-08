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
def patch_start(monkeypatch: pytest.MonkeyPatch) -> Callable[..., dict[str, object]]:
    """Replace every hop of `start` so no socket is opened and no spec is read.

    This fixture is the only patcher of ``cli_module.build_app``, so two
    fixtures can never fight over the attribute. The returned installer
    records what ``start`` passed to ``uvicorn.run`` and exposes the kwargs
    handed to ``build_app`` under the ``"build_app"`` key.

    Args:
        record_warnings: fire the ``warn`` callback once inside the fake
            ``build_app``; otherwise ``warn`` is recorded but never invoked.

    Returns:
        An installer that patches the hops and returns the recorder dict.
    """

    def _install(*, record_warnings: bool = False) -> dict[str, object]:
        served: dict[str, object] = {}
        seen: dict[str, object] = {}

        def fake_build_app(*args: object, **kwargs: object) -> object:
            seen.update(kwargs)
            warn = kwargs.get("warn")
            if record_warnings and callable(warn):
                warn("unsupported type 'weird-unknown-type'")
            return object()

        monkeypatch.setattr(cli_module, "load_openapi", lambda _: dict(PROBE_SPEC))
        monkeypatch.setattr(cli_module, "build_app", fake_build_app)
        monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: served.update(kwargs))
        served["build_app"] = seen
        return served

    return _install


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
