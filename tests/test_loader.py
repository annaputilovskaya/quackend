from pathlib import Path

import pytest

from quackend.loader import (
    iter_operations,
    load_openapi,
    operation_response_schema,
    path_resource,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_openapi_petstore_resolves_refs():
    spec = load_openapi(FIXTURES / "petstore.yaml")
    users_get = next(op for p, m, op in iter_operations(spec) if p == "/users" and m == "get")
    schema = operation_response_schema(users_get)
    assert schema["type"] == "array"
    assert schema["items"]["properties"]["email"]["format"] == "email"


def test_load_openapi_swagger2_returns_paths():
    spec = load_openapi(FIXTURES / "swagger2.yaml")
    paths = {p for p, _, _ in iter_operations(spec)}
    assert "/legacy" in paths


def test_path_resource_with_params_returns_first_literal():
    assert path_resource("/users/{id}") == "users"
    assert path_resource("/api/v2/users/{user_id}/posts") == "api"


@pytest.mark.parametrize("fixture", ["petstore.yaml", "react_local.yaml", "swagger2.yaml"])
def test_load_openapi_all_fixtures_return_paths(fixture):
    spec = load_openapi(FIXTURES / fixture)
    assert spec.get("paths")


def test_operation_response_schema_first_2xx_returns_array():
    spec = load_openapi(FIXTURES / "petstore.yaml")
    users_get = next(op for p, m, op in iter_operations(spec) if p == "/users" and m == "get")
    assert operation_response_schema(users_get)["type"] == "array"


def test_operation_response_schema_non_json_media_returns_none():
    operation = {
        "responses": {
            "200": {
                "description": "ok",
                "content": {"text/plain": {"schema": {"type": "string"}}},
            }
        }
    }

    assert operation_response_schema(operation) is None


def test_operation_response_schema_mixed_media_returns_json():
    operation = {
        "responses": {
            "200": {
                "description": "ok",
                "content": {
                    "text/plain": {"schema": {"type": "string"}},
                    "application/json": {"schema": {"type": "object"}},
                },
            }
        }
    }

    assert operation_response_schema(operation)["type"] == "object"


def test_operation_response_schema_json_with_charset_returns_schema():
    operation = {
        "responses": {
            "200": {
                "description": "ok",
                "content": {
                    "application/json; charset=utf-8": {"schema": {"type": "object"}},
                },
            }
        }
    }

    assert operation_response_schema(operation)["type"] == "object"


def test_operation_response_schema_swagger2_returns_array_schema():
    spec = load_openapi(FIXTURES / "swagger2.yaml")
    legacy_get = next(op for p, m, op in iter_operations(spec) if p == "/legacy" and m == "get")

    assert operation_response_schema(legacy_get)["type"] == "array"
