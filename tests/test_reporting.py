import re
from io import StringIO

import rich
from rich.console import Console

from quackend.reporting import render_route_table


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
    console = Console(file=buffer, force_terminal=True, color_system="standard", width=200)
    monkeypatch.setattr(rich, "get_console", lambda: console)

    render_route_table(make_spec("/users", "/users/{id}"))

    out = buffer.getvalue()
    # "." cannot cross a newline and the only thing between two cells is padding
    # and the table border, so these pin the Method cell and the Path cell that
    # follows it inside one rendered row, rather than two cells of the column.
    assert re.search(r"\x1b\[36m.*?GET", out)
    assert re.search(r"GET.*?│ +/users *│", out)
    assert re.search(r"GET.*?│ +/users/\{id\} *│", out)
