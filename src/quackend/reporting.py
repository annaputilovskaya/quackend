"""Render OpenAPI information as rich console output."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import rich
import rich.table

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
    for path, method, _operation in iter_operations(spec):
        table.add_row(method.upper(), path)
    rich.get_console().print(table)
    return table
