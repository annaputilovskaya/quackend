"""Load OpenAPI/Swagger specifications and extract their operations."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import prance


def load_openapi(source: str | Path) -> dict[str, Any]:
    """Parse an OpenAPI v3 or Swagger v2 spec and resolve all $refs.

    Args:
        source: local path or URL of the spec file.

    Returns:
        The fully resolved spec as a plain dict.

    Raises:
        prance.ValidationError: if the spec is invalid or cannot be loaded.
    """
    parser = prance.ResolvingParser(str(source), backend="openapi-spec-validator")
    spec: dict[str, Any] = parser.specification
    return spec


def path_resource(path_template: str) -> str:
    """Return the first non-parameter segment of a path template.

    Args:
        path_template: an OpenAPI path template such as "/users/{id}".

    Returns:
        The first segment that is not a "{param}" placeholder.
    """
    for segment in path_template.strip("/").split("/"):
        if not (segment.startswith("{") and segment.endswith("}")):
            return segment
    return path_template.strip("/")


def iter_operations(spec: Mapping[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield every operation declared in a spec.

    Args:
        spec: a resolved OpenAPI spec.

    Yields:
        Tuples of path template, lowercase HTTP method and operation object.
    """
    for path_template, path_item in (spec.get("paths") or {}).items():
        for method in ("get", "post", "put", "delete", "patch"):
            operation = path_item.get(method)
            if operation:
                yield path_template, method, operation


def operation_response_schema(operation: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the first 2xx application/json response schema of an operation.

    Args:
        operation: a single OpenAPI operation object.

    Returns:
        The response schema dict, or None when no 2xx JSON schema exists.
    """
    responses = operation.get("responses") or {}
    for raw_status in sorted(responses):
        try:
            code = int(raw_status)
        except (TypeError, ValueError):
            continue
        if not (200 <= code < 300):
            continue
        media = (responses[raw_status].get("content") or {}).get("application/json")
        if not media:
            continue
        schema: dict[str, Any] | None = media.get("schema")
        if schema:
            return schema
    return None
