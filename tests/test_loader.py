from pathlib import Path
from typing import Any

import pytest

from quackend.loader import (
    Route,
    SpecLoadError,
    is_templated,
    iter_operations,
    iter_success_responses,
    load_openapi,
    operation_response_schema,
    parse_route,
    path_resource,
    resolve_resource,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_openapi_petstore_resolves_refs() -> None:
    spec = load_openapi(FIXTURES / "petstore.yaml")
    operation = next(
        op for op in iter_operations(spec) if op.path == "/users" and op.method == "get"
    )

    assert operation.is_list is True
    schema = operation.item_schema
    assert schema is not None
    assert schema["type"] == "object"
    assert schema["properties"]["email"]["format"] == "email"


def test_load_openapi_swagger2_returns_paths() -> None:
    spec = load_openapi(FIXTURES / "swagger2.yaml")
    paths = {op.path for op in iter_operations(spec)}
    assert "/legacy" in paths


def test_path_resource_strips_only_trailing_params() -> None:
    assert path_resource("/pets") == "pets"
    assert path_resource("/users/{id}") == "users"
    assert path_resource("/api/v2/users/{user_id}/posts") == "api/v2/users/{user_id}/posts"
    assert path_resource("/monitors/{id}/checks") == "monitors/{id}/checks"


@pytest.mark.parametrize("fixture", ["petstore.yaml", "react_local.yaml", "swagger2.yaml"])
def test_load_openapi_all_fixtures_return_paths(fixture: str) -> None:
    spec = load_openapi(FIXTURES / fixture)
    assert spec.get("paths")


def test_operation_response_schema_first_2xx_returns_array() -> None:
    spec = load_openapi(FIXTURES / "petstore.yaml")
    schema = operation_response_schema(spec["paths"]["/users"]["get"])

    assert schema is not None
    assert schema["type"] == "array"


def test_operation_response_schema_non_json_media_returns_none() -> None:
    operation = {
        "responses": {
            "200": {
                "description": "ok",
                "content": {"text/plain": {"schema": {"type": "string"}}},
            }
        }
    }

    assert operation_response_schema(operation) is None


def test_operation_response_schema_mixed_media_returns_json() -> None:
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

    schema = operation_response_schema(operation)

    assert schema is not None
    assert schema["type"] == "object"


def test_operation_response_schema_json_with_charset_returns_schema() -> None:
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

    schema = operation_response_schema(operation)

    assert schema is not None
    assert schema["type"] == "object"


def test_operation_response_schema_swagger2_returns_array_schema() -> None:
    spec = load_openapi(FIXTURES / "swagger2.yaml")
    schema = operation_response_schema(spec["paths"]["/legacy"]["get"])

    assert schema is not None
    assert schema["type"] == "array"


def test_parse_route_splits_the_resource_and_the_parameters() -> None:
    route = parse_route("/orgs/{org_id}/members/{member_id}")

    assert route == Route(
        path="/orgs/{org_id}/members/{member_id}",
        resource="orgs/{org_id}/members",
        params=("org_id", "member_id"),
    )


def test_parse_route_of_a_collection_declares_no_parameters() -> None:
    route = parse_route("/users")

    assert route.resource == "users"
    assert route.params == ()


def test_iter_operations_yields_a_fully_resolved_operation() -> None:
    spec = load_openapi(FIXTURES / "nested_resources.yaml")

    operation = next(
        op
        for op in iter_operations(spec)
        if op.path == "/orgs/{org_id}/members/{member_id}" and op.method == "get"
    )

    assert operation.resource == "orgs/{org_id}/members"
    assert operation.params == ("org_id", "member_id")
    assert operation.ok_status == 200
    assert operation.is_list is False
    assert operation.item_schema is not None
    assert operation.item_schema["properties"]["name"]["type"] == "string"


def test_iter_operations_unwraps_an_array_schema_into_the_item_schema() -> None:
    spec: dict[str, Any] = {
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "array", "items": {"type": "object"}}
                                }
                            },
                        }
                    }
                }
            }
        }
    }

    operation = next(iter_operations(spec))

    assert operation.is_list is True
    assert operation.item_schema == {"type": "object"}


def test_iter_operations_reads_the_declared_success_status() -> None:
    spec = {"paths": {"/jobs": {"post": {"responses": {"202": {"description": "ok"}}}}}}

    operation = next(iter_operations(spec))

    assert operation.ok_status == 202
    assert operation.item_schema is None
    assert operation.is_list is False


def test_iter_operations_defaults_the_success_status_to_200() -> None:
    spec = {"paths": {"/ping": {"get": {"responses": {"default": {"description": "default"}}}}}}

    operation = next(iter_operations(spec))

    assert operation.ok_status == 200


def test_iter_operations_skips_methods_a_spec_does_not_declare() -> None:
    spec = {"paths": {"/items": {"get": {"responses": {"200": {"description": "ok"}}}}}}

    methods = [op.method for op in iter_operations(spec)]

    assert methods == ["get"]


def test_iter_success_responses_yields_the_range_key_as_its_lower_bound() -> None:
    # Key order, not numeric order: "2XX" sorts after "204", so an explicit status
    # is read before the range that would otherwise swallow it.
    operation = {
        "responses": {
            "2XX": {"description": "any success"},
            "204": {"description": "no content"},
            "4XX": {"description": "any client error"},
            "default": {"description": "anything"},
        }
    }

    pairs = list(iter_success_responses(operation))

    assert pairs == [
        (204, {"description": "no content"}),
        (200, {"description": "any success"}),
    ]


def test_operation_response_schema_range_only_returns_the_schema() -> None:
    operation = {
        "responses": {
            "2XX": {
                "description": "ok",
                "content": {"application/json": {"schema": {"type": "object"}}},
            }
        }
    }

    schema = operation_response_schema(operation)

    assert schema is not None
    assert schema["type"] == "object"


def test_iter_operations_range_only_reports_200_and_a_list() -> None:
    spec = {
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "2XX": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "array", "items": {"type": "object"}}
                                }
                            },
                        }
                    }
                }
            }
        }
    }

    operation = next(iter_operations(spec))

    assert operation.ok_status == 200
    assert operation.is_list is True
    assert operation.item_schema == {"type": "object"}


def test_is_templated_reports_a_resource_that_still_holds_a_parameter() -> None:
    assert is_templated("monitors/{monitor_id}/uptime") is True
    assert is_templated("monitors/xyz/uptime") is False


def test_resolve_resource_substitutes_only_the_supplied_parameters() -> None:
    route = parse_route("/orgs/{org_id}/members/{member_id}")
    nested = parse_route("/monitors/{monitor_id}/uptime")

    resolved = resolve_resource(route, {"org_id": "orgA", "member_id": "alice"})
    bound = resolve_resource(nested, {"monitor_id": "xyz"})
    partial = resolve_resource(nested, {})

    assert resolved == "orgs/orgA/members"
    assert bound == "monitors/xyz/uptime"
    # A parameter the request does not supply stays literal, so an unresolved key
    # is still recognisable as a template instead of silently losing a segment.
    assert partial == "monitors/{monitor_id}/uptime"


def test_iter_operations_yields_every_verb_the_path_declares() -> None:
    spec = {
        "paths": {
            "/items": {
                "get": {"responses": {"200": {"description": "ok"}}},
                "head": {"responses": {"200": {"description": "ok"}}},
                "options": {"responses": {"204": {"description": "no content"}}},
                "trace": {"responses": {"200": {"description": "ok"}}},
            }
        }
    }

    methods = [op.method for op in iter_operations(spec)]

    assert methods == ["get", "head", "options", "trace"]


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "malformed",
        "invalid",
        "directory",
        "empty",
        "mapping",
        "sequence",
        "tab",
        "multi_doc",
        "dup_key",
    ],
)
def test_load_openapi_reports_one_failure_family(tmp_path: Path, case: str) -> None:
    sources: dict[str, Path] = {
        "missing": tmp_path / "absent.yaml",
        "malformed": tmp_path / "broken.yaml",
        "invalid": tmp_path / "invalid.yaml",
        "directory": tmp_path,
        "empty": tmp_path / "empty.yaml",
        "mapping": tmp_path / "mapping.json",
        "sequence": tmp_path / "sequence.json",
        "tab": tmp_path / "tab.yaml",
        "multi_doc": tmp_path / "multi.yaml",
        "dup_key": tmp_path / "dup.yaml",
    }
    sources["empty"].touch()
    sources["malformed"].write_text("openapi: 3.0.0\npaths: [\n  - not yaml", encoding="utf-8")
    sources["invalid"].write_text(
        'openapi: 3.0.0\ninfo:\n  version: "1.0"\npaths: {}\n', encoding="utf-8"
    )
    sources["mapping"].write_text("{}", encoding="utf-8")
    sources["sequence"].write_text("[]", encoding="utf-8")
    sources["tab"].write_text("paths:\n\t- a\n", encoding="utf-8")
    sources["multi_doc"].write_text("openapi: 3.0.0\n---\nopenapi: 3.0.0\n", encoding="utf-8")
    sources["dup_key"].write_text("openapi: 3.0.0\nopenapi: 3.0.0\n", encoding="utf-8")

    with pytest.raises(SpecLoadError) as info:
        load_openapi(sources[case])

    assert type(info.value.__cause__).__module__.split(".")[0] in {
        "prance",
        "ruamel",
        "builtins",
    }
    assert type(info.value.__cause__).__name__ in str(info.value)
    assert "\n" not in str(info.value)


def _json_operation(raw: Any) -> dict[str, Any]:
    return {"responses": {"200": {"content": {"application/json": {"schema": raw}}}}}


def test_operation_response_schema_true_is_an_empty_object_schema() -> None:
    assert operation_response_schema(_json_operation(True)) == {
        "type": "object",
        "properties": {},
    }


def test_operation_response_schema_false_raises_spec_load_error() -> None:
    with pytest.raises(SpecLoadError, match="bool False"):
        operation_response_schema(_json_operation(False))


def test_operation_response_schema_non_schema_value_raises_spec_load_error() -> None:
    with pytest.raises(SpecLoadError, match="str 'text'"):
        operation_response_schema(_json_operation("text"))


def test_operation_response_schema_empty_object_is_served_as_a_schema() -> None:
    assert operation_response_schema(_json_operation({})) == {}


def test_iter_operations_serves_an_empty_schema_instead_of_dropping_it() -> None:
    spec = {"paths": {"/things": {"get": _json_operation({})}}}

    [operation] = list(iter_operations(spec))

    assert operation.item_schema == {}
    assert operation.is_list is False
