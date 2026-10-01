"""Build a FastAPI mock application from an OpenAPI spec."""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from rich.console import Console
from rich.markup import escape as escape_markup

from quackend.loader import Operation, iter_operations
from quackend.store import QuackStore, StoreProtocol

_CONSOLE = Console()
_MAX_BODY_BYTES = 1_048_576

__all__ = ["build_app"]


def _ok_response(content: Mapping[str, Any] | Sequence[Any], status: int) -> Response:
    if status == 204:
        return Response(status_code=204)
    return JSONResponse(content=content, status_code=status)


def _identity_key(values: Mapping[str, Any], params: Sequence[str]) -> str:
    """Return the store key addressing every path parameter of a route.

    Nested collections repeat a parent segment, so the first parameter alone
    would address the same item for every child of that parent.

    Args:
        values: the ASGI path parameters of the request.
        params: the ordered parameter names declared by the path template.

    Returns:
        A composite key such as ``"orgA/alice"``, or ``""`` without parameters.
    """
    return "/".join(str(values.get(name, "")) for name in params)


async def _json_object(request: Request) -> dict[str, Any]:
    """Read a bounded JSON object body, or fail with a 4xx status.

    The size check uses the declared content-length; a chunked body without
    that header is parsed as-is.

    Args:
        request: the incoming request.

    Returns:
        The decoded JSON object.

    Raises:
        HTTPException: 415 for a non-JSON content type, 413 for a body over
            _MAX_BODY_BYTES, 400 for an unparsable or non-object body.
    """
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type and media_type != "application/json":
        raise HTTPException(status_code=415, detail="expected application/json")
    declared = request.headers.get("content-length")
    if (
        declared is not None
        and declared.isascii()
        and declared.isdigit()
        and int(declared) > _MAX_BODY_BYTES
    ):
        raise HTTPException(status_code=413, detail="request body too large")
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="malformed JSON body") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    return payload


def _seed_resources(
    operations: Sequence[Operation],
    store: StoreProtocol,
    warn: Callable[[str], None],
) -> None:
    for operation in operations:
        if operation.method == "get" and operation.item_schema is not None:
            store.ensure(operation.resource, operation.item_schema, warn=warn)


async def _handle_get(
    operation: Operation,
    store: StoreProtocol,
    request: Request,
    warn: Callable[[str], None],
) -> Response:
    key = _identity_key(request.path_params, operation.params)
    if operation.is_list:
        return _ok_response(store.get_all(operation.resource), operation.ok_status)
    if operation.params:
        if operation.item_schema is None:
            payload = store.get(operation.resource, key)
            if payload is None:
                return JSONResponse({"error": "not found"}, status_code=404)
        else:
            payload = store.first_or_create(
                operation.resource, key, operation.item_schema, warn=warn
            )
        return _ok_response(payload, operation.ok_status)
    if operation.item_schema is not None:
        payload = store.first(operation.resource)
        if payload is None:
            payload = store.first_or_create(
                operation.resource, "", operation.item_schema, warn=warn
            )
        return _ok_response(payload, operation.ok_status)
    return _ok_response(store.get_all(operation.resource), operation.ok_status)


async def _handle_post(
    operation: Operation,
    store: StoreProtocol,
    request: Request,
    warn: Callable[[str], None],
) -> Response:
    return _ok_response(
        store.create(operation.resource, await _json_object(request)),
        operation.ok_status,
    )


async def _handle_update(
    operation: Operation,
    store: StoreProtocol,
    request: Request,
    warn: Callable[[str], None],
) -> Response:
    key = _identity_key(request.path_params, operation.params)
    updated = store.update(operation.resource, key, await _json_object(request))
    if updated is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return _ok_response(updated, operation.ok_status)


async def _handle_delete(
    operation: Operation,
    store: StoreProtocol,
    request: Request,
    warn: Callable[[str], None],
) -> Response:
    key = _identity_key(request.path_params, operation.params)
    if not store.delete(operation.resource, key):
        return JSONResponse({"error": "not found"}, status_code=404)
    return _ok_response({"deleted": key}, operation.ok_status)


_Handler = Callable[[Operation, StoreProtocol, Request, Callable[[str], None]], Awaitable[Response]]

_VERBS: dict[str, _Handler] = {
    "get": _handle_get,
    "post": _handle_post,
    "put": _handle_update,
    "patch": _handle_update,
    "delete": _handle_delete,
}


def _endpoint(
    handler: _Handler,
    operation: Operation,
    store: StoreProtocol,
    warn: Callable[[str], None],
) -> Callable[[Request], Awaitable[Response]]:
    async def _view(request: Request) -> Response:
        return await handler(operation, store, request, warn)

    return _view


def build_app(
    spec: Mapping[str, Any],
    store: StoreProtocol | None = None,
    *,
    latency_ms: int = 0,
    fail_rate: float = 0.0,
    quiet: bool = False,
) -> FastAPI:
    """Build a FastAPI app serving generated mock data for every spec operation.

    Args:
        spec: a resolved OpenAPI specification.
        store: an optional shared store; a fresh one is created otherwise.
        latency_ms: artificial delay applied to every request in milliseconds.
        fail_rate: probability in [0, 1] that a request fails with HTTP 500.
        quiet: when True, suppress generator warning output.

    Returns:
        A configured FastAPI application.
    """
    resolved_store = store if store is not None else QuackStore()

    def warn(message: str) -> None:
        if not quiet:
            _CONSOLE.print(f"[yellow][WARNING][/yellow] {escape_markup(message)}")

    operations = list(iter_operations(spec))
    _seed_resources(operations, resolved_store, warn)

    app = FastAPI(title=(spec.get("info") or {}).get("title", "quackend"))

    @app.middleware("http")
    async def _simulate(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if fail_rate and random.random() < fail_rate:
            return JSONResponse({"error": "mock failure"}, status_code=500)
        if latency_ms:
            await asyncio.sleep(latency_ms / 1000)
        return await call_next(request)

    for operation in operations:
        handler = _VERBS.get(operation.method)
        if handler is None:
            continue
        app.add_api_route(
            operation.path,
            _endpoint(handler, operation, resolved_store, warn),
            methods=[operation.method.upper()],
            include_in_schema=False,
        )

    return app
