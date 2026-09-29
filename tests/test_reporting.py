import re
from io import StringIO

import rich
import rich.table
from rich.console import Console

from quackend.reporting import render_route_table

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


# A raw dict rather than load_openapi: the defect is in rendering, not parsing, and
# the validator would only add a second moving part to these assertions.
def make_spec(*paths):
    return {
        "openapi": "3.0.0",
        "info": {"title": "routes", "version": "1.0.0"},
        "paths": {path: {"get": {"responses": {"200": {"description": "ok"}}}} for path in paths},
    }


def test_route_table_renders_closing_markup_tag_path(capfd):
    render_route_table(make_spec("/a[/]b"))
    out = capfd.readouterr().out

    assert "/a[/]b" in out


def test_route_table_renders_opening_markup_tag_path_verbatim(capfd):
    render_route_table(make_spec("/items/[id]"))
    out = capfd.readouterr().out

    assert "/items/[id]" in out


def test_route_table_renders_ordinary_paths_and_keeps_column_style(monkeypatch):
    # A terminal-style console writing to a buffer, so the assertions read the
    # rendered table rather than the Table object: capfd sees a non-tty and Rich
    # would drop the colour the Method column is supposed to keep.
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, color_system="standard", width=120)
    monkeypatch.setattr(rich, "get_console", lambda: console)

    # box=None is the test's own choice rather than Rich's default: with a box the
    # cells are separated by a glyph of Rich's choosing, and every assertion below
    # would then fail for a reason that has nothing to do with the escaping.
    class BoxlessTable(rich.table.Table):
        def __init__(self, *args, **kwargs):
            kwargs["box"] = None
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(rich.table, "Table", BoxlessTable)

    render_route_table(make_spec("/users", "/users/{id}"))

    rows = [line for line in buffer.getvalue().splitlines() if "GET" in line]

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
