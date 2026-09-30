"""Render OpenAPI information as rich console output."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import rich
import rich.table
from rich.markup import escape as escape_markup

from quackend.loader import iter_operations


def render_route_table(spec: Mapping[str, Any]) -> rich.table.Table:
    """Print the spec's routes as a rich table.

    Args:
        spec: a resolved OpenAPI spec.

    Returns:
        The rendered rich table.
    """
    table = rich.table.Table(title="Routes", show_header=True)
    table.add_column("Method", style="cyan")
    table.add_column("Path")
    for operation in iter_operations(spec):
        # Rich reads table cells as markup, so a spec path like "/a[/]b" would crash
        # the run and "/items/[id]" would print as "/items/". The method column keeps
        # its style, because that one is a column style and not cell content.
        table.add_row(operation.method.upper(), escape_markup(operation.path))
    rich.get_console().print(table)
    return table
