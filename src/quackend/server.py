"""Build a FastAPI mock application from an OpenAPI spec."""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from rich.console import Console

from quackend.loader import iter_operations, operation_response_schema, path_resource
from quackend.store import QuackStore

_CONSOLE = Console()


def _response_status(operation: dict[str, Any]) -> int:
    for raw_status in sorted(operation.get("responses") or {}):
        try:
            code = int(raw_status)
        except (TypeError, ValueError):
            continue
        if 200 <= code < 300:
            return code
    return 200


def _as_dict(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {"payload": payload}


def _seed_resources(
    spec: Mapping[str, Any],
    store: QuackStore,
    warn: Callable[[str], None] | None,
) -> None:
    for path, method, operation in iter_operations(spec):
        if method != "get":
            continue
        schema = operation_response_schema(operation)
        if schema:
            item_schema = _item_schema(schema)
            store.ensure(path_resource(path), item_schema, warn=warn)


def _item_schema(schema: dict[str, Any]) -> dict[str, Any]:
    items = schema.get("items")
    if schema.get("type") == "array" and isinstance(items, dict):
        return items
    return schema


def build_app(
    spec: dict[str, Any],
    store: QuackStore | None = None,
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
    resolved_store = store or QuackStore()

    def warn(message: str) -> None:
        if not quiet:
            _CONSOLE.print(f"[yellow][WARNING][/yellow] {message}")

    _seed_resources(spec, resolved_store, warn)

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

    for path_template, method, operation in iter_operations(spec):
        route_params = re.findall(r"\{(\w+)\}", path_template)
        resource = path_resource(path_template)
        status = _response_status(operation)

        def _register(
            route_path: str,
            m: str,
            res: str,
            params: list[str],
            ok_status: int,
        ) -> None:
            param_name = params[0] if params else ""

            @app.api_route(route_path, methods=[m.upper()], include_in_schema=False)
            async def _handler(request: Request) -> JSONResponse:
                values = request.path_params
                if m == "get":
                    if param_name:
                        payload = resolved_store.get(res, values.get(param_name, ""))
                        if payload is None:
                            return JSONResponse({"error": "not found"}, status_code=404)
                        return JSONResponse(content=payload, status_code=ok_status)
                    return JSONResponse(content=resolved_store.get_all(res), status_code=ok_status)
                if m == "post":
                    return JSONResponse(
                        content=resolved_store.create(res, _as_dict(await request.json())),
                        status_code=201,
                    )
                if m in ("put", "patch"):
                    updated = resolved_store.update(
                        res, values.get(param_name, ""), _as_dict(await request.json())
                    )
                    if updated is None:
                        return JSONResponse({"error": "not found"}, status_code=404)
                    return JSONResponse(content=updated, status_code=200)
                if m == "delete":
                    if not resolved_store.delete(res, values.get(param_name, "")):
                        return JSONResponse({"error": "not found"}, status_code=404)
                    return JSONResponse(
                        content={"deleted": values.get(param_name)}, status_code=200
                    )
                return JSONResponse({"error": "not implemented"}, status_code=405)

        _register(path_template, method, resource, route_params, status)

    return app
