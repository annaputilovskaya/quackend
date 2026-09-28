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


def test_route_table_renders_ordinary_paths_and_keeps_column_style(capfd):
    table = render_route_table(make_spec("/users", "/users/{id}"))
    out = capfd.readouterr().out

    assert "GET" in out
    assert "/users" in out
    assert "/users/{id}" in out
    assert table.columns[0].style == "cyan"
