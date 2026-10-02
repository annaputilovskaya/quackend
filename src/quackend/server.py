"""Build a FastAPI mock application from an OpenAPI spec."""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from quackend.loader import (
    Operation,
    UnsupportedOperationError,
    is_templated,
    iter_operations,
    parse_route,
    resolve_resource,
)
from quackend.store import QuackStore, StoreProtocol

_MAX_BODY_BYTES = 1_048_576

__all__ = ["build_app"]


def _null_warn(_message: str) -> None:
    """Discard a fail-soft message."""


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
        if operation.method != "get" or operation.item_schema is None:
            continue
        # A collection under a path parameter belongs to the parent a request
        # names, and no request has named one yet, so it is created lazily by
        # _bind_resource instead of once per spec at startup.
        if is_templated(operation.resource):
            continue
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


def _served_methods(request: Request) -> set[str]:
    """Return the verbs this app registers for the requested path.

    Args:
        request: the incoming request.

    Returns:
        The lowercased methods of every registered route serving that exact path.
    """
    return {
        method.lower()
        for route in request.app.routes
        if getattr(route, "path", None) == request.url.path
        for method in getattr(route, "methods", ())
    }


async def _handle_head(
    operation: Operation,
    store: StoreProtocol,
    request: Request,
    warn: Callable[[str], None],
) -> Response:
    """Answer a declared HEAD with what its own declared success answers.

    The body is dropped because a server must not answer a HEAD with one, and so is
    the content length, which belongs to a body that is never sent. The GET handler
    reads nothing of the verb, so the HEAD operation is served on its own and no
    declared GET is required.

    Args:
        operation: the HEAD operation the request matched.
        store: the store backing the app.
        request: the incoming request.
        warn: the callback receiving generator warnings.

    Returns:
        The status and headers of the GET answer, with an empty body.
    """
    response = await _handle_get(operation, store, request, warn)
    headers = {
        name: value for name, value in response.headers.items() if name.lower() != "content-length"
    }
    head = Response(status_code=response.status_code, headers=headers)
    # Starlette fills a missing length in from the empty body, which is a claim
    # about a payload this route does not send.
    del head.headers["content-length"]
    return head


async def _handle_options(
    operation: Operation,
    store: StoreProtocol,
    request: Request,
    warn: Callable[[str], None],
) -> Response:
    """Answer a declared OPTIONS with the methods this app serves for the path.

    The operation and the store are ignored: OPTIONS answers about the path as a
    whole rather than about one operation of it. The handler keeps the signature
    every other verb shares so that the verb table stays one table.

    Args:
        operation: the OPTIONS operation the request matched; unused.
        store: the store backing the app; unused.
        request: the incoming request.
        warn: the callback receiving generator warnings; unused.

    Returns:
        A 204 response whose Allow header lists the served methods, ordered by the
        verb table rather than by the registration order of the routes.
    """
    served = _served_methods(request)
    allowed = [verb.upper() for verb in _VERBS if verb in served]
    return Response(status_code=204, headers={"allow": ", ".join(allowed)})


def _bind_resource(
    operation: Operation,
    store: StoreProtocol,
    values: Mapping[str, Any],
    warn: Callable[[str], None],
) -> Operation:
    """Return the operation addressed to the concrete parent this request names.

    Args:
        operation: the operation the request matched.
        store: the store backing the app.
        values: the path parameters of the request.
        warn: the callback receiving generator warnings.

    Returns:
        The operation unchanged when its collection is already concrete, otherwise
        a copy whose resource is the bound collection, seeded on the first request
        that names a parent.
    """
    if not is_templated(operation.resource):
        return operation
    resource = resolve_resource(parse_route(operation.path), values)
    if operation.method == "get" and operation.item_schema is not None:
        store.ensure(resource, operation.item_schema, warn=warn)
    return replace(operation, resource=resource)


_Handler = Callable[[Operation, StoreProtocol, Request, Callable[[str], None]], Awaitable[Response]]

_VERBS: dict[str, _Handler] = {
    "get": _handle_get,
    "post": _handle_post,
    "put": _handle_update,
    "patch": _handle_update,
    "delete": _handle_delete,
    "head": _handle_head,
    "options": _handle_options,
}


def _endpoint(
    handler: _Handler,
    operation: Operation,
    store: StoreProtocol,
    warn: Callable[[str], None],
) -> Callable[[Request], Awaitable[Response]]:
    async def _view(request: Request) -> Response:
        bound = _bind_resource(operation, store, request.path_params, warn)
        return await handler(bound, store, request, warn)

    return _view


def build_app(
    spec: Mapping[str, Any],
    store: StoreProtocol | None = None,
    *,
    latency_ms: int = 0,
    fail_rate: float = 0.0,
    warn: Callable[[str], None] | None = None,
    rng: random.Random | None = None,
) -> FastAPI:
    """Build a FastAPI app serving generated mock data for every spec operation.

    Args:
        spec: a resolved OpenAPI specification.
        store: an optional shared store; a fresh one is created otherwise.
        latency_ms: artificial delay applied to every request in milliseconds.
        fail_rate: probability in [0, 1] that a request fails with HTTP 500.
        warn: an optional callback receiving fail-soft messages. Nothing is
            printed by the library; the caller decides how to surface them.
        rng: the random source simulated failures are drawn from, so a seeded one
            makes them reproducible; the module-global ``random`` is used
            otherwise.

    Returns:
        A configured FastAPI application.

    Raises:
        ValueError: if ``latency_ms`` is negative or ``fail_rate`` falls outside
            [0, 1], because neither knob can do what it promises.
        UnsupportedOperationError: if the spec declares a verb the mock refuses
            to answer rather than drop it silently.
    """
    if latency_ms < 0:
        raise ValueError(f"latency_ms must not be negative, got {latency_ms}")
    if not 0.0 <= fail_rate <= 1.0:
        raise ValueError(f"fail_rate must be within [0, 1], got {fail_rate}")

    resolved_store = store if store is not None else QuackStore()
    emit = warn if warn is not None else _null_warn
    draw: Callable[[], float] = rng.random if rng is not None else random.random

    operations = list(iter_operations(spec))
    _seed_resources(operations, resolved_store, emit)

    app = FastAPI(title=(spec.get("info") or {}).get("title", "quackend"))

    @app.middleware("http")
    async def _simulate(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if fail_rate and draw() < fail_rate:
            return JSONResponse({"error": "mock failure"}, status_code=500)
        if latency_ms:
            await asyncio.sleep(latency_ms / 1000)
        return await call_next(request)

    for operation in operations:
        handler = _VERBS.get(operation.method)
        if handler is None:
            raise UnsupportedOperationError(
                f"quackend cannot mock {operation.method.upper()} declared at {operation.path}"
            )
        app.add_api_route(
            operation.path,
            _endpoint(handler, operation, resolved_store, emit),
            methods=[operation.method.upper()],
            include_in_schema=False,
        )

    return app
