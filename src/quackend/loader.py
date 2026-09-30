"""Load OpenAPI/Swagger specifications and extract their operations."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import prance

__all__ = [
    "Operation",
    "Route",
    "iter_operations",
    "load_openapi",
    "operation_response_schema",
    "path_resource",
]

_PARAM_PATTERN = re.compile(r"\{(\w+)\}")
_METHODS: tuple[str, ...] = ("get", "post", "put", "delete", "patch")


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
    """Return the collection key for a path, dropping trailing parameters.

    Args:
        path_template: an OpenAPI path template such as "/users/{id}".

    Returns:
        The path without trailing "{param}" segments, so a list endpoint and
        its detail endpoint share one collection while nested routes stay
        separate keys.
    """
    segments = path_template.strip("/").split("/")
    while segments and segments[-1].startswith("{") and segments[-1].endswith("}"):
        segments.pop()
    return "/".join(segments) or path_template.strip("/")


@dataclass(frozen=True, slots=True)
class Route:
    """A path template split into its collection key and ordered parameters."""

    path: str
    resource: str
    params: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Operation:
    """A single OpenAPI operation with everything a mock route needs."""

    path: str
    method: str
    resource: str
    params: tuple[str, ...]
    ok_status: int
    item_schema: dict[str, Any] | None
    is_list: bool


def parse_route(path_template: str) -> Route:
    """Split a path template into its collection key and path parameters.

    Args:
        path_template: an OpenAPI path template such as "/orgs/{org_id}/members".

    Returns:
        The route with the store resource and the ordered parameter names.
    """
    return Route(
        path=path_template,
        resource=path_resource(path_template),
        params=tuple(_PARAM_PATTERN.findall(path_template)),
    )


def _item_schema(schema: dict[str, Any]) -> dict[str, Any]:
    items = schema.get("items")
    if schema.get("type") == "array" and isinstance(items, dict):
        return items
    return schema


def _first_success_status(operation: Mapping[str, Any]) -> int:
    for raw_status in sorted(operation.get("responses") or {}):
        try:
            code = int(raw_status)
        except (TypeError, ValueError):
            continue
        if 200 <= code < 300:
            return code
    return 200


def iter_operations(spec: Mapping[str, Any]) -> Iterator[Operation]:
    """Yield every supported operation declared in a spec, fully resolved.

    Args:
        spec: a resolved OpenAPI spec.

    Yields:
        One Operation per declared method, with its resource, path parameters,
        declared success status, item schema and list flag already resolved.
    """
    for path_template, path_item in (spec.get("paths") or {}).items():
        for method in _METHODS:
            operation = path_item.get(method)
            if not operation:
                continue
            route = parse_route(path_template)
            schema = operation_response_schema(operation)
            yield Operation(
                path=route.path,
                method=method,
                resource=route.resource,
                params=route.params,
                ok_status=_first_success_status(operation),
                item_schema=_item_schema(schema) if schema else None,
                is_list=schema is not None and schema.get("type") == "array",
            )


def _json_media(content: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return the application/json media object from a v3 content map, if any."""
    for media_type, media in content.items():
        if media_type.split(";", 1)[0].strip().lower() == "application/json":
            result: Mapping[str, Any] = media
            return result
    return None


def operation_response_schema(operation: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the first 2xx JSON response schema of an operation.

    Reads the OpenAPI 3 ``content["application/json"]`` entry (media-type
    parameters such as ``; charset=utf-8`` are ignored) and falls back to the
    Swagger 2.0 top-level ``schema`` field.

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
        response = responses[raw_status]
        media = _json_media(response.get("content") or {})
        schema: dict[str, Any] | None = media.get("schema") if media is not None else None
        if schema is None:
            schema = response.get("schema")
        if schema:
            return schema
    return None
