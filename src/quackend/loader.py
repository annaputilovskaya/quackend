"""Load OpenAPI/Swagger specifications and extract their operations."""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import prance
import requests
from prance.util.url import ResolutionError, urlresource

__all__ = [
    "Operation",
    "Route",
    "SpecLoadError",
    "is_templated",
    "iter_operations",
    "iter_success_responses",
    "load_openapi",
    "operation_response_schema",
    "parse_route",
    "path_resource",
    "resolve_resource",
]

_PARAM_PATTERN = re.compile(r"\{(\w+)\}")
_RANGE_PATTERN = re.compile(r"\d[xX]{2}")
_METHODS: tuple[str, ...] = (
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "head",
    "options",
    "trace",
)
_URL_SCHEMES = ("http", "https")
_MAX_SPEC_BYTES = 8 * 1_048_576  # 8 MiB
_TIMEOUT_SECONDS = 10.0


def _checked_url(source: str) -> str | None:
    """Return a fetchable URL, or None for a source prance reads by itself.

    Local sources have no scheme, the ``file`` scheme, or a one-letter
    (Windows drive-letter) scheme; ``http``/``https`` URLs are returned
    unchanged so the bounded fetcher can pick them up.

    Raises:
        SpecLoadError: for a scheme outside the allow-list, naming the scheme
            so a spec author can find which URL was refused.
    """
    scheme = urllib.parse.urlparse(source).scheme
    if scheme in (None, "", "file") or len(scheme) == 1:
        return None
    if scheme in _URL_SCHEMES:
        return source
    raise SpecLoadError(f"Refusing to fetch {scheme!r}: only http/https URLs are allowed")


def _wrap_fetch_url_text(
    original: Callable[..., tuple[str, str]],
) -> Callable[..., tuple[str, str]]:
    """Bound prance's single network entry point for one parse.

    prance 26.7.19.0 has no ``url_fetcher`` parameter and reads every file or
    ``$ref`` through ``prance.util.url.fetch_url_text`` (``__init__.py:131-135``,
    ``resolver.py:623``, ``translator.py:100``). Replacing that module global
    around the parser is a deliberate bridge to prance — re-check on an upgrade.
    Local sources are delegated untouched; ``http``/``https`` are fetched with
    a timeout, a size cap and no redirects; every other scheme raises the same
    ``ResolutionError`` prance itself raises for an unroutable reference, so
    ``load_openapi`` wraps the failure exactly once.
    """

    def fetch(url: urllib.parse.SplitResult, cache: Any, encoding: Any = None) -> tuple[str, str]:
        scheme = url.scheme
        if scheme in (None, "", "file") or scheme == "python":
            return original(url, cache, encoding)
        if scheme not in _URL_SCHEMES:
            raise ResolutionError(f"Refusing to fetch {scheme!r}: only http/https URLs are allowed")
        try:
            response = requests.get(
                url.geturl(),
                timeout=_TIMEOUT_SECONDS,
                stream=True,
                allow_redirects=False,
            )
            response.raise_for_status()
            if 300 <= response.status_code < 400:
                # requests reports 3xx as ok; refuse the redirect body here.
                raise requests.HTTPError(
                    f"{response.status_code} redirect refused", response=response
                )
        except requests.RequestException as exc:
            raise ResolutionError(f"Cannot fetch URL {url.geturl()!r}: {exc}") from exc
        declared = response.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > _MAX_SPEC_BYTES:
            raise ResolutionError(f"URL {url.geturl()!r} is over the {_MAX_SPEC_BYTES}-byte limit")
        raw_body = response.raw
        if raw_body is None:
            raise ResolutionError(f"Cannot fetch URL {url.geturl()!r}: no body stream")
        try:
            raw = raw_body.read(_MAX_SPEC_BYTES + 1, decode_content=True)
        except (requests.RequestException, OSError) as exc:
            raise ResolutionError(f"Cannot fetch URL {url.geturl()!r}: {exc}") from exc
        if len(raw) > _MAX_SPEC_BYTES:
            raise ResolutionError(f"URL {url.geturl()!r} is over the {_MAX_SPEC_BYTES}-byte limit")
        content = raw.decode("utf-8")
        content_type = response.headers.get("content-type", "text/plain")
        cache["text_" + urlresource(url)] = (content, content_type)
        return content, content_type

    return fetch


class SpecLoadError(Exception):
    """A spec that cannot be read, parsed, resolved, validated, or served as declared.

    Wraps every failure from the spec toolchain so callers can catch one type
    instead of enumerating exception families that change between upstream
    releases. The message names the underlying exception class and is always a
    single line, so a caller can print it without reformatting; the original
    exception is attached as ``__cause__``.
    """


def load_openapi(source: str | Path) -> dict[str, Any]:
    """Parse an OpenAPI v3 or Swagger v2 spec and resolve all $refs.

    Args:
        source: local path or URL of the spec file.

    Returns:
        The fully resolved spec as a plain dict.

    Raises:
        SpecLoadError: the source cannot be read, parsed, resolved or
            validated. The message names the underlying exception class and is
            a single line. The original exception is prance, ruamel.yaml,
            openapi-spec-validator, requests or a filesystem error, and is
            attached as ``__cause__``. A URL with a scheme outside ``http``/
            ``https`` is refused before any fetch happens.
    """
    _checked_url(str(source))
    original_fetch = prance.util.url.fetch_url_text
    try:
        prance.util.url.fetch_url_text = _wrap_fetch_url_text(original_fetch)
        parser = prance.ResolvingParser(str(source), backend="openapi-spec-validator")
        spec: dict[str, Any] = parser.specification
    except Exception as exc:
        detail = "; ".join(str(exc).splitlines())
        raise SpecLoadError(f"{type(exc).__name__}: {detail}") from exc
    finally:
        prance.util.url.fetch_url_text = original_fetch
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
    ok_status: int | None  # None when the operation declares no 2xx response
    media_type: str | None  # first declared media type of the first 2xx
    item_schema: Mapping[str, Any] | None
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


def is_templated(resource: str) -> bool:
    """Report whether a collection key still holds a path parameter.

    Args:
        resource: a collection key such as ``"monitors/{monitor_id}/uptime"``.

    Returns:
        True when the key names a parent instead of one concrete collection, so
        it has to be bound to a request before it can address stored items.
    """
    return _PARAM_PATTERN.search(resource) is not None


def resolve_resource(route: Route, values: Mapping[str, Any]) -> str:
    """Return the collection key a route addresses for one request.

    Args:
        route: the parsed route of the requested path.
        values: the path parameters the request supplied.

    Returns:
        The collection key with every supplied parameter substituted. A parameter
        the request does not supply stays literal, so an unresolved key is still
        recognisable as a template instead of losing a segment.
    """

    def substitute(match: re.Match[str]) -> str:
        return str(values.get(match.group(1), match.group(0)))

    return _PARAM_PATTERN.sub(substitute, route.resource)


def _item_schema(schema: Mapping[str, Any]) -> Mapping[str, Any]:
    items = schema.get("items")
    if schema.get("type") == "array" and isinstance(items, dict):
        return items
    return schema


def _status_code(raw_status: object) -> int | None:
    """Read one response key as a status code.

    Args:
        raw_status: a response key such as ``"200"``, ``"2XX"`` or ``"default"``.

    Returns:
        The status code, a range key read as the lower bound of its range
        (``"2XX"`` becomes ``200``), or None when the key declares no status.
    """
    text = str(raw_status)
    if _RANGE_PATTERN.fullmatch(text):
        return int(text[0]) * 100
    try:
        return int(text)
    except ValueError:
        return None


def iter_success_responses(
    operation: Mapping[str, Any],
) -> Iterator[tuple[int, Mapping[str, Any]]]:
    """Yield every 2xx response of an operation together with its status code.

    This is the only place that decides whether a response key is a success, so an
    operation can never answer one status and serve the schema of another. Keys are
    read in ascending *key* order rather than numeric order: "204" then sorts before
    "2XX", so an explicit status wins over the range that would otherwise swallow it.

    Args:
        operation: a single OpenAPI operation object.

    Yields:
        One ``(status, response)`` pair per 2xx response, in ascending key order.
        A range key yields the lower bound of its range, so "2XX" yields 200.
    """
    responses = operation.get("responses") or {}
    for raw_status in sorted(responses):
        code = _status_code(raw_status)
        if code is None or not 200 <= code < 300:
            continue
        yield code, responses[raw_status]


def iter_operations(spec: Mapping[str, Any]) -> Iterator[Operation]:
    """Yield every operation a Path Item declares, fully resolved.

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
            first_success = next(iter_success_responses(operation), None)
            yield Operation(
                path=route.path,
                method=method,
                resource=route.resource,
                params=route.params,
                ok_status=first_success[0] if first_success is not None else None,
                media_type=_declared_media(operation),
                item_schema=_item_schema(schema) if schema is not None else None,
                is_list=schema is not None and schema.get("type") == "array",
            )


def _json_media(content: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return the application/json media object from a v3 content map, if any."""
    for media_type, media in content.items():
        if media_type.split(";", 1)[0].strip().lower() == "application/json":
            result: Mapping[str, Any] = media
            return result
    return None


def _declared_media(operation: Mapping[str, Any]) -> str | None:
    """Return the first declared media type of the operation's first 2xx.

    Content-type parameters such as ``; charset=utf-8`` are ignored, and the
    comparison is done on the lowercased base type so ``Application/JSON`` and
    ``text/csv`` come out the same as they will be sent.

    Returns:
        The first declared media type, or None when no 2xx response declares
        any content.
    """
    for _, response in iter_success_responses(operation):
        content: Mapping[str, Any] = response.get("content") or {}
        for media_type in content:
            return media_type.split(";", 1)[0].strip().lower()
    return None


def operation_response_schema(operation: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the first 2xx JSON response schema of an operation.

    Reads the OpenAPI 3 ``content["application/json"]`` entry (media-type
    parameters such as ``; charset=utf-8`` are ignored) and falls back to the
    Swagger 2.0 top-level ``schema`` field. The successes are read through
    :func:`iter_success_responses`, so the schema cannot be picked from a response
    the mock would not answer.

    Args:
        operation: a single OpenAPI operation object.

    Returns:
        The response schema dict normalized to a plain ``dict``, or None when no
        2xx JSON schema exists.
    """
    for _, response in iter_success_responses(operation):
        media = _json_media(response.get("content") or {})
        raw: Any = media.get("schema") if media is not None else None
        if raw is None:
            raw = response.get("schema")
        if raw is None:
            continue
        return _coerce_schema(raw)
    return None


def _coerce_schema(raw: Any) -> dict[str, Any]:
    """Read a raw ``schema`` value as an object, or refuse to serve it.

    Args:
        raw: the unparsed value of a response ``schema`` field.

    Returns:
        A concrete schema dict; ``True`` becomes an empty object schema, since
        the boolean form accepts any object and ``{}`` would read as missing.

    Raises:
        SpecLoadError: if the value is neither an object nor ``True``, naming
            its type and value so the spec author can find it.
    """
    if isinstance(raw, Mapping):
        return dict(raw)
    if raw is True:
        return {"type": "object", "properties": {}}
    raise SpecLoadError(f"schema must be an object or true, got {type(raw).__name__} {raw!r}")
