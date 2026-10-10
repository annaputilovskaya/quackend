import asyncio
import copy
import logging
import random
import time
from collections.abc import Callable, Mapping, MutableMapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from fastapi.testclient import TestClient

from quackend.loader import load_openapi
from quackend.server import UnsupportedOperationError, build_app
from quackend.store import COLLECTION_SIZE, QuackStore, StoreProtocol

FIXTURES = Path(__file__).parent / "fixtures"


def make_client(**kwargs: Any) -> tuple[TestClient, QuackStore]:
    spec = load_openapi(FIXTURES / "petstore.yaml")
    store = QuackStore()
    app = build_app(spec, store, **kwargs)
    return TestClient(app), store


def test_list_endpoint_returns_collection() -> None:
    client, _ = make_client()

    response = client.get("/users")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 10
    assert all("id" in item for item in body)


def test_list_endpoint_items_are_flat_user_objects() -> None:
    client, _ = make_client()

    response = client.get("/users")

    assert response.status_code == 200
    for item in response.json():
        assert {"name", "email", "role", "active"} <= set(item)
        assert "value" not in item


def test_get_by_id_returns_the_stored_item() -> None:
    client, store = make_client()

    stored = store.get("users", "5")
    response = client.get("/users/5")

    assert response.status_code == 200
    assert stored is not None
    assert response.json() == stored


def test_item_unknown_id_generates_from_schema() -> None:
    client, _ = make_client()

    response = client.get("/users/999")

    assert response.status_code == 200
    assert response.json()["id"] == "999"


def make_array_detail_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "array-detail", "version": "1.0.0"},
        "paths": {
            "/widgets/{id}": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {"name": {"type": "string"}},
                                        },
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }


def test_array_response_on_a_detail_route_serves_the_collection() -> None:
    client = TestClient(build_app(make_array_detail_spec()))

    body = client.get("/widgets/7").json()

    # list-first: an array response wins over the path parameter, so the route
    # serves its collection and never wraps the array in a "value" field. A2 moved
    # this decision into a verb table, and the order of the is_list and params
    # branches is the contract it had to preserve.
    assert isinstance(body, list)
    assert all(isinstance(item, dict) and "value" not in item for item in body)
    assert all(isinstance(item["name"], str) for item in body)


def test_post_then_get_returns_created() -> None:
    client, _ = make_client()

    created = client.post("/users", json={"name": "Bob"}).json()

    assert created["id"] == "11"
    fetched = client.get("/users/11").json()
    assert fetched["name"] == "Bob"


def test_put_persists_the_update() -> None:
    client, _ = make_client()

    response = client.put("/users/3", json={"name": "Renamed"})

    assert response.status_code == 200
    assert client.get("/users/3").json()["name"] == "Renamed"


def test_put_unknown_id_answers_not_found() -> None:
    client, _ = make_client()

    assert client.put("/users/999", json={}).status_code == 404


def test_delete_removes_the_item_from_the_store() -> None:
    client, store = make_client()

    assert client.delete("/users/4").status_code == 200
    assert store.get("users", "4") is None


def test_get_after_delete_regenerates_the_item() -> None:
    client, _ = make_client()

    client.delete("/users/4")

    assert client.get("/users/4").json()["id"] == "4"


def test_latency_delays_response() -> None:
    client, _ = make_client(latency_ms=150)

    start = time.monotonic()
    client.get("/users")
    elapsed = time.monotonic() - start

    assert elapsed >= 0.12


def test_fail_rate_all_500_when_full() -> None:
    client, _ = make_client(fail_rate=1.0)

    assert client.get("/users").status_code == 500


def test_fail_rate_zero_passes() -> None:
    client, _ = make_client(fail_rate=0.0)

    assert client.get("/users").status_code == 200


def test_second_schema_custom_param_name() -> None:
    spec = load_openapi(FIXTURES / "react_local.yaml")

    app = build_app(spec)
    client = TestClient(app)

    assert client.get("/projects/1").status_code == 200
    assert client.get("/projects/999").json()["id"] == "999"


def make_nested_client() -> tuple[TestClient, QuackStore]:
    spec = load_openapi(FIXTURES / "nested.yaml")
    store = QuackStore()
    app = build_app(spec, store)
    return TestClient(app), store


def test_me_returns_single_object_not_array() -> None:
    client, _ = make_nested_client()

    body = client.get("/api/v1/auth/me").json()

    assert isinstance(body, dict)
    assert "email" in body


def test_same_prefix_resources_are_separate_collections() -> None:
    client, _ = make_nested_client()

    me = client.get("/api/v1/auth/me").json()
    status = client.get("/api/v1/auth/login-status").json()

    assert "email" in me
    assert "status" in status
    assert "email" not in status


def test_detail_unknown_id_generates_entity() -> None:
    client, _ = make_nested_client()

    monitor_id = "c5dfe3d0-998a-4e2c-b8f5-7f3d2c48a1b1"
    body = client.get(f"/api/v1/upcheck/monitors/{monitor_id}").json()

    assert body["id"] == monitor_id


def test_array_subresource_returns_list() -> None:
    client, _ = make_nested_client()

    body = client.get("/api/v1/upcheck/monitors/xyz/uptime").json()

    assert isinstance(body, list)
    assert len(body) >= 1
    assert "ts" in body[0]


def test_array_endpoint_returns_list() -> None:
    client, _ = make_nested_client()

    body = client.get("/api/v1/notifications/channels").json()

    assert isinstance(body, list)
    assert "id" in body[0]


def test_list_and_detail_share_collection() -> None:
    client, _ = make_nested_client()

    listed = client.get("/api/v1/upcheck/monitors").json()
    first_id = listed[0]["id"]

    detail = client.get(f"/api/v1/upcheck/monitors/{first_id}").json()

    assert detail["id"] == first_id


def test_patch_after_get_persists() -> None:
    client, _ = make_nested_client()

    client.get("/api/v1/upcheck/monitors/abc")
    client.patch("/api/v1/upcheck/monitors/abc", json={"name": "Renamed"})

    assert client.get("/api/v1/upcheck/monitors/abc").json()["name"] == "Renamed"


def make_weird_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "weird", "version": "1.0.0"},
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {"wat": {"type": "weird-unknown-type"}},
                                        },
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }


def test_fail_soft_unsupported_schema_does_not_crash() -> None:
    messages: list[str] = []
    spec = make_weird_spec()

    app = build_app(spec, warn=messages.append)
    client = TestClient(app)
    response = client.get("/items")

    assert response.status_code == 200
    assert any("weird-unknown-type" in message for message in messages)


def test_build_app_reports_default_diagnostics_through_logging(
    caplog: pytest.LogCaptureFixture, capfd: pytest.CaptureFixture[str]
) -> None:
    with caplog.at_level(logging.WARNING, logger="quackend"):
        build_app(make_weird_spec())

    assert any("weird-unknown-type" in record.getMessage() for record in caplog.records)
    assert "WARNING" not in capfd.readouterr().out


def make_example_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "example", "version": "1.0.0"},
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "example": {"id": "from-spec", "name": "fixed"},
                                            "properties": {
                                                "id": {"type": "string"},
                                                "name": {"type": "string"},
                                            },
                                        },
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }


def test_list_endpoint_with_item_example_has_unique_ids() -> None:
    client = TestClient(build_app(make_example_spec()))

    body = client.get("/items").json()

    assert len(body) == 10
    assert len({item["id"] for item in body}) == 10


def test_build_app_does_not_mutate_the_spec_dict() -> None:
    spec = make_example_spec()
    before = copy.deepcopy(spec)

    build_app(spec)

    assert spec == before


def test_get_with_yaml_date_example_answers_json() -> None:
    spec = load_openapi(FIXTURES / "yaml_date.yaml")
    client = TestClient(build_app(spec))

    response = client.get("/d")

    assert response.status_code == 200
    assert response.json()["when"] == "2024-01-15"


def test_post_with_client_id_is_retrievable_by_returned_id() -> None:
    client, _ = make_client()

    created = client.post("/users", json={"id": "custom", "name": "Bob"}).json()

    assert created["id"] == "11"
    assert client.get("/users/11").json()["name"] == "Bob"


def make_nested_resources_client() -> tuple[TestClient, QuackStore]:
    spec = load_openapi(FIXTURES / "nested_resources.yaml")
    store = QuackStore()
    return TestClient(build_app(spec, store)), store


def test_nested_detail_uses_every_path_param_as_identity() -> None:
    client, _ = make_nested_resources_client()

    alice = client.get("/orgs/orgA/members/alice").json()
    bob = client.get("/orgs/orgA/members/bob").json()
    other_org = client.get("/orgs/orgB/members/alice").json()

    assert alice["id"] == "orgA/alice"
    assert bob["id"] == "orgA/bob"
    assert len({alice["id"], bob["id"], other_org["id"]}) == 3


def test_nested_delete_removes_the_addressed_member() -> None:
    client, store = make_nested_resources_client()
    client.get("/orgs/orgA/members/alice")

    assert store.get("orgs/orgA/members", "orgA/alice") is not None
    assert client.delete("/orgs/orgA/members/alice").status_code == 200
    assert store.get("orgs/orgA/members", "orgA/alice") is None


def make_inverted_bounds_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "inverted", "version": "1.0.0"},
        "paths": {
            "/values": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "n": {
                                                    "type": "integer",
                                                    "minimum": 100,
                                                    "maximum": 6,
                                                }
                                            },
                                        },
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }


def test_build_app_survives_inverted_numeric_bounds() -> None:
    client = TestClient(build_app(make_inverted_bounds_spec()))

    response = client.get("/values")

    assert response.status_code == 200
    assert all(6 <= item["n"] <= 100 for item in response.json())


def make_markup_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "markup", "version": "1.0.0"},
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {"wat": {"type": "[/]"}},
                                        },
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }


def test_spec_text_with_rich_markup_still_serves_requests() -> None:
    messages: list[str] = []
    client = TestClient(build_app(make_markup_spec(), warn=messages.append))

    response = client.get("/items")

    assert response.status_code == 200
    assert any("unsupported type" in message for message in messages)
    assert any("[/]" in message for message in messages)


def make_status_spec() -> dict[str, Any]:
    item_schema = {
        "type": "object",
        "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
    }
    ok = {"description": "ok", "content": {"application/json": {"schema": item_schema}}}
    accepted = {"description": "accepted", "content": {"application/json": {"schema": item_schema}}}
    gone = {"description": "gone"}
    return {
        "openapi": "3.0.0",
        "info": {"title": "status", "version": "1.0.0"},
        "paths": {
            "/jobs": {"post": {"responses": {"202": accepted}}},
            "/jobs/{id}": {
                "get": {"responses": {"200": ok}},
                "put": {"responses": {"202": accepted}},
                "patch": {"responses": {"202": accepted}},
                "delete": {"responses": {"204": gone}},
            },
            "/pings": {"post": {"responses": {"204": gone}}},
            "/telemetry": {"get": {"responses": {"204": gone}}},
            "/tasks/{id}": {
                "get": {"responses": {"200": ok}},
                "delete": {"responses": {"200": ok}},
            },
        },
    }


@pytest.mark.parametrize(
    ("raw", "content_type", "expected"),
    [
        (b"{not json", "application/json", 400),
        (b"", "application/json", 400),
        (b'"hello"', "application/json", 400),
        (b"[1,2,3]", "application/json", 400),
        (b"<xml/>", "application/xml", 415),
        (b"\xff", "application/json", 400),
        (b"{not json", "application/json; charset=utf-8", 400),
        (b"{not json", "APPLICATION/JSON", 400),
    ],
)
def test_invalid_request_body_returns_client_error(
    raw: bytes, content_type: str, expected: int
) -> None:
    client = TestClient(build_app(make_status_spec()))

    response = client.post("/jobs", content=raw, headers={"content-type": content_type})

    assert response.status_code == expected


def test_oversized_request_body_returns_413() -> None:
    client = TestClient(build_app(make_status_spec()))
    raw = b'{"name": "' + b"x" * 1_048_576 + b'"}'

    response = client.post("/jobs", content=raw, headers={"content-type": "application/json"})

    assert response.status_code == 413


def test_non_ascii_declared_content_length_is_not_a_server_error() -> None:
    app = build_app(make_status_spec())
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/jobs",
        "raw_path": b"/jobs",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
            (b"content-length", b"\xb2"),
        ],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
    }
    messages: list[MutableMapping[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b'{"name": "job"}', "more_body": False}

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)

    asyncio.run(app(scope, receive, send))

    start = next(m for m in messages if m["type"] == "http.response.start")
    assert start["status"] < 500


def test_post_answers_the_status_declared_by_the_operation() -> None:
    client = TestClient(build_app(make_status_spec()))

    assert client.post("/jobs", json={"name": "job"}).status_code == 202


def test_put_answers_the_status_declared_by_the_operation() -> None:
    client = TestClient(build_app(make_status_spec()))

    assert client.put("/jobs/2", json={"name": "renamed"}).status_code == 202


def test_delete_with_declared_204_has_no_body() -> None:
    client = TestClient(build_app(make_status_spec()))

    response = client.delete("/jobs/2")

    assert response.status_code == 204
    assert response.content == b""


def test_post_with_declared_204_has_no_body() -> None:
    client = TestClient(build_app(make_status_spec()))

    response = client.post("/pings", json={"name": "ping"})

    assert response.status_code == 204
    assert response.content == b""


def test_get_collection_with_declared_204_has_no_body() -> None:
    client = TestClient(build_app(make_status_spec()))

    response = client.get("/telemetry")

    assert response.status_code == 204
    assert response.content == b""


def test_patch_answers_the_status_declared_by_the_operation() -> None:
    client = TestClient(build_app(make_status_spec()))

    response = client.patch("/jobs/2", json={"name": "patched"})

    assert response.status_code == 202


def test_delete_with_declared_200_returns_the_addressed_key() -> None:
    client = TestClient(build_app(make_status_spec()))

    response = client.delete("/tasks/2")

    assert response.status_code == 200
    assert response.json() == {"deleted": "2"}


def test_request_without_a_content_type_header_answers_400() -> None:
    client = TestClient(build_app(make_status_spec()))

    response = client.post("/jobs", content=b"{not json")

    assert response.status_code == 400


# No content key at all: operation_response_schema returns None, so the route reads
# the store instead of generating, and whatever is under the key is served as is.
def make_schemaless_nested_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "schemaless", "version": "1.0.0"},
        "paths": {
            "/orgs/{org_id}/members/{member_id}": {
                "get": {"responses": {"200": {"description": "ok"}}}
            }
        },
    }


def test_nested_get_without_a_response_schema_answers_404() -> None:
    # The store is seeded by hand because a schema-less GET never generates: only a
    # store that already holds the composite key can tell the nested identity apart
    # from a key built out of the first path parameter, which is what makes the
    # served member below the assertion that the name promises.
    spec = make_schemaless_nested_spec()
    store = QuackStore()
    member = {"type": "object", "properties": {"name": {"type": "string"}}}
    alice = store.first_or_create("orgs/orgA/members", "orgA/alice", member)
    store.first_or_create("orgs/orgA/members", "orgA/bob", member)
    client = TestClient(build_app(spec, store))

    served = client.get("/orgs/orgA/members/alice")
    missing = client.get("/orgs/orgB/members/alice")

    assert served.status_code == 200
    assert served.json() == alice
    assert missing.status_code == 404
    assert missing.json() == {"error": "not found"}


# A parameter-less GET with no 2xx JSON schema, which no seeding path covers: the
# store is filled by the POST on the same path instead, since path_resource drops
# no segment here and both verbs address one collection.
def make_schemaless_collection_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "schemaless", "version": "1.0.0"},
        "paths": {
            "/telemetry": {
                "get": {"responses": {"200": {"description": "ok"}}},
                "post": {"responses": {"200": {"description": "ok"}}},
            }
        },
    }


def test_schemaless_collection_get_returns_every_stored_item() -> None:
    client = TestClient(build_app(make_schemaless_collection_spec()))
    client.post("/telemetry", json={"name": "first"})
    client.post("/telemetry", json={"name": "second"})

    response = client.get("/telemetry")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["1", "2"]
    assert [item["name"] for item in response.json()] == ["first", "second"]


# The array schema is what makes this a list route, so the collection is served
# from the list branch with a 204; /telemetry above declares 204 with no content
# and therefore never gets there.
def make_204_list_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "list204", "version": "1.0.0"},
        "paths": {
            "/metrics": {
                "get": {
                    "responses": {
                        "204": {
                            "description": "accepted",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {"id": {"type": "string"}},
                                        },
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }


def test_list_route_with_declared_204_has_no_body() -> None:
    client = TestClient(build_app(make_204_list_spec()))

    response = client.get("/metrics")

    assert response.status_code == 204
    assert response.content == b""


# httpx hands the header value to the ASGI scope unstripped, so the whitespace
# reaches _json_object through the client as well as through a real parser.
def test_content_type_padded_with_whitespace_is_read_as_json() -> None:
    client = TestClient(build_app(make_status_spec()))

    response = client.post(
        "/jobs", content=b'{"name": "job"}', headers={"content-type": "  application/json  "}
    )

    assert response.status_code == 202
    assert response.json()["name"] == "job"


def make_store_spec() -> dict[str, Any]:
    return {
        "info": {"title": "Stub"},
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"type": "object", "properties": {}},
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }


class StubStore:
    """A store adapter whose items are recognisable, to prove the seam is honoured."""

    def __init__(self) -> None:
        self.seeded: list[int | None] = []
        self.ensured: list[str] = []

    def set_seed(self, seed: int | None) -> None:
        self.seeded.append(seed)

    def ensure(
        self,
        resource: str,
        schema: Mapping[str, Any],
        warn: Callable[[str], None] | None = None,
    ) -> None:
        self.ensured.append(resource)

    def get(self, resource: str, key: str) -> dict[str, Any] | None:
        return None

    def first(self, resource: str) -> dict[str, Any] | None:
        return {"id": "injected-0"}

    def get_all(self, resource: str) -> list[dict[str, Any]]:
        return [{"id": f"injected-{index}"} for index in range(3)]

    def first_or_create(
        self,
        resource: str,
        key: str,
        schema: Mapping[str, Any],
        warn: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        return {"id": "injected-0"}

    def create(self, resource: str, data: Mapping[str, Any]) -> dict[str, Any]:
        return {"id": "injected-0"}

    def update(
        self,
        resource: str,
        key: str,
        data: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        return {"id": "injected-0"}

    def delete(self, resource: str, key: str) -> bool:
        return True


class FalseyStore(StubStore):
    """An adapter that claims to be empty, so truthiness would drop it."""

    def __bool__(self) -> bool:
        return False


def test_build_app_honours_an_injected_store() -> None:
    store = StubStore()

    body = TestClient(build_app(make_store_spec(), store)).get("/items").json()

    assert [item["id"] for item in body] == ["injected-0", "injected-1", "injected-2"]
    assert store.ensured == ["items"]


def test_build_app_keeps_a_falsey_injected_store() -> None:
    store = FalseyStore()

    body = TestClient(build_app(make_store_spec(), store)).get("/items").json()

    assert [item["id"] for item in body] == ["injected-0", "injected-1", "injected-2"]


def test_stub_store_satisfies_the_store_protocol() -> None:
    store: StoreProtocol = StubStore()

    store.set_seed(1)
    store.ensure("items", {})

    assert store.get_all("items") == [
        {"id": "injected-0"},
        {"id": "injected-1"},
        {"id": "injected-2"},
    ]


def test_build_app_accepts_a_read_only_spec() -> None:
    app = build_app(MappingProxyType(make_store_spec()))

    assert TestClient(app).get("/items").status_code == 200


# The wildcard is the only success the operation declares, so it decides both the
# status and the schema: reading it as "no schema" would mock an empty list.
def make_range_only_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "range", "version": "1.0.0"},
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "2XX": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {"name": {"type": "string"}},
                                        },
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }


def test_range_only_response_serves_the_declared_array() -> None:
    client = TestClient(build_app(make_range_only_spec()))

    body = client.get("/items").json()

    assert len(body) == COLLECTION_SIZE
    assert all(isinstance(item["name"], str) for item in body)


def test_nested_collection_is_stored_per_concrete_parent() -> None:
    client, store = make_nested_client()

    client.get("/api/v1/upcheck/monitors/xyz/uptime")
    client.get("/api/v1/upcheck/monitors/other/uptime")

    assert len(store.get_all("api/v1/upcheck/monitors/xyz/uptime")) == COLLECTION_SIZE
    assert len(store.get_all("api/v1/upcheck/monitors/other/uptime")) == COLLECTION_SIZE
    # The templated key is never created: nested.yaml declares no verb here that
    # deletes, so a get_all on it is enough to show it stays empty forever.
    assert store.get_all("api/v1/upcheck/monitors/{monitor_id}/uptime") == []


def test_nested_detail_is_stored_under_the_parent_the_request_names() -> None:
    client, store = make_nested_resources_client()

    alice = client.get("/orgs/orgA/members/alice").json()

    assert alice["id"] == "orgA/alice"
    assert store.get("orgs/orgA/members", "orgA/alice") == alice


def test_nested_delete_removes_the_member_of_the_addressed_parent_only() -> None:
    client, store = make_nested_resources_client()
    client.get("/orgs/orgA/members/alice")
    client.get("/orgs/orgB/members/alice")

    assert client.delete("/orgs/orgA/members/alice").status_code == 200

    assert store.get("orgs/orgA/members", "orgA/alice") is None
    assert store.get("orgs/orgB/members", "orgB/alice") is not None


def make_head_only_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "head", "version": "1.0.0"},
        "paths": {
            "/probe": {
                "head": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"name": {"type": "string"}},
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }


def test_declared_head_answers_its_own_status_with_no_body() -> None:
    # No declared GET on this path: the HEAD operation is answered on its own, so
    # the mock serves what the spec declares rather than implying a GET.
    client = TestClient(build_app(make_head_only_spec()))

    response = client.head("/probe")

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["content-type"] == "application/json"


def make_options_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "options", "version": "1.0.0"},
        "paths": {
            "/items": {
                "get": {"responses": {"200": {"description": "ok"}}},
                "options": {"responses": {"204": {"description": "no content"}}},
            }
        },
    }


def test_declared_options_answers_allow_for_the_path() -> None:
    client = TestClient(build_app(make_options_spec()))

    response = client.options("/items")

    assert response.status_code == 204
    assert response.headers["allow"] == "GET, OPTIONS"


def make_trace_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "trace", "version": "1.0.0"},
        "paths": {"/items": {"trace": {"responses": {"200": {"description": "ok"}}}}},
    }


def test_declared_trace_refuses_to_build() -> None:
    with pytest.raises(UnsupportedOperationError) as raised:
        build_app(make_trace_spec())

    assert "TRACE" in str(raised.value)
    assert "/items" in str(raised.value)


def test_the_same_rng_reproduces_the_same_failures() -> None:
    first, _ = make_client(fail_rate=0.5, rng=random.Random(7))
    second, _ = make_client(fail_rate=0.5, rng=random.Random(7))

    statuses = [first.get("/users").status_code for _ in range(20)]
    again = [second.get("/users").status_code for _ in range(20)]

    assert statuses == again
    assert 500 in statuses


class _NeverFailRandom(random.Random):
    """An rng whose draw is above every probability, so no request can fail."""

    def random(self) -> float:
        return 1.0


def test_the_injected_rng_is_the_one_drawn_from() -> None:
    client, _ = make_client(fail_rate=0.5, rng=_NeverFailRandom())

    statuses = [client.get("/users").status_code for _ in range(5)]

    assert statuses == [200] * 5


def test_build_app_rejects_a_negative_latency() -> None:
    with pytest.raises(ValueError, match="latency_ms"):
        build_app(make_status_spec(), latency_ms=-1)


def test_build_app_rejects_an_out_of_range_fail_rate() -> None:
    for fail_rate in (1.5, -0.1):
        with pytest.raises(ValueError, match="fail_rate"):
            build_app(make_status_spec(), fail_rate=fail_rate)
