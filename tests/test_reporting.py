import re
from collections.abc import Mapping
from io import StringIO
from typing import Any

import pytest
import rich
import rich.table
from rich.console import Console

from quackend.reporting import render_route_table

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


# A raw dict rather than load_openapi: the defect is in rendering, not parsing, and
# the validator would only add a second moving part to these assertions.
def make_spec(*paths: str) -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "routes", "version": "1.0.0"},
        "paths": {path: {"get": {"responses": {"200": {"description": "ok"}}}} for path in paths},
    }


# A terminal-style console writing to a buffer, so the assertions read what a user
# would see rather than the Table object: Rich drops the colour the Method column
# is supposed to keep whenever it does not see a terminal.
def render_to_buffer(spec: Mapping[str, Any]) -> str:
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, color_system="standard", width=120)
    console.print(render_route_table(spec))
    return buffer.getvalue()


def test_route_table_renders_closing_markup_tag_path() -> None:
    out = render_to_buffer(make_spec("/a[/]b"))

    assert "/a[/]b" in out


def test_route_table_renders_opening_markup_tag_path_verbatim() -> None:
    out = render_to_buffer(make_spec("/items/[id]"))

    assert "/items/[id]" in out


def test_route_table_renders_ordinary_paths_and_keeps_column_style(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # box=None is the test's own choice rather than Rich's default: with a box the
    # cells are separated by a glyph of Rich's choosing, and every assertion below
    # would then fail for a reason that has nothing to do with the escaping.
    class BoxlessTable(rich.table.Table):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["box"] = None
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(rich.table, "Table", BoxlessTable)

    rendered = render_to_buffer(make_spec("/users", "/users/{id}"))

    rows = [line for line in rendered.splitlines() if "GET" in line]

    assert len(rows) == 2
    for row in rows:
        # The Method cell still carries the cyan column style after the path was
        # escaped, and the assertions read one rendered line at a time so that
        # "." below can only ever mean "this row".
        assert re.search(r"\x1b\[36m.*GET", row)
        # Only padding can come between two cells once the test owns the box, so a
        # match here puts the Method cell and the Path cell that follows it in the
        # same row, in that order.
        assert re.fullmatch(r" *GET +/users(?:/\{id\})? *", ANSI_ESCAPE.sub("", row))


def test_render_route_table_prints_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    render_route_table(make_spec("/users"))

    assert capsys.readouterr().out == ""
