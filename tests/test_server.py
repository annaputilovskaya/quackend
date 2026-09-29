import asyncio
import copy
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quackend.loader import load_openapi
from quackend.server import build_app
from quackend.store import QuackStore

FIXTURES = Path(__file__).parent / "fixtures"


def make_client(**kwargs):
    spec = load_openapi(FIXTURES / "petstore.yaml")
    store = QuackStore()
    app = build_app(spec, store, **kwargs)
    return TestClient(app), store


def test_list_endpoint_returns_collection():
    client, _ = make_client()

    response = client.get("/users")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 10
    assert all("id" in item for item in body)


def test_list_endpoint_items_are_flat_user_objects():
    client, _ = make_client()

    response = client.get("/users")

    assert response.status_code == 200
    for item in response.json():
        assert {"name", "email", "role", "active"} <= set(item)
        assert "value" not in item


def test_item_endpoint_by_id():
    client, _ = make_client()

    response = client.get("/users/5")

    assert response.status_code == 200
    assert response.json()["id"] == "5"


def test_item_unknown_id_generates_from_schema():
    client, _ = make_client()

    response = client.get("/users/999")

    assert response.status_code == 200
    assert response.json()["id"] == "999"


def test_post_then_get_returns_created():
    client, _ = make_client()

    created = client.post("/users", json={"name": "Bob"}).json()

    assert created["id"] == "11"
    fetched = client.get("/users/11").json()
    assert fetched["name"] == "Bob"


def test_put_persists():
    client, _ = make_client()

    response = client.put("/users/3", json={"name": "Renamed"})

    assert response.status_code == 200
    assert client.get("/users/3").json()["name"] == "Renamed"
    assert client.put("/users/999", json={}).status_code == 404


def test_delete_removes_then_get_regenerates():
    client, _ = make_client()

    assert client.delete("/users/4").status_code == 200
    assert client.get("/users/4").json()["id"] == "4"


def test_latency_delays_response():
    client, _ = make_client(latency_ms=150)

    start = time.monotonic()
    client.get("/users")
    elapsed = time.monotonic() - start

    assert elapsed >= 0.12


def test_fail_rate_all_500_when_full():
    client, _ = make_client(fail_rate=1.0)

    assert client.get("/users").status_code == 500


def test_fail_rate_zero_passes():
    client, _ = make_client(fail_rate=0.0)

    assert client.get("/users").status_code == 200


def test_second_schema_custom_param_name():
    spec = load_openapi(FIXTURES / "react_local.yaml")

    app = build_app(spec)
    client = TestClient(app)

    assert client.get("/projects/1").status_code == 200
    assert client.get("/projects/999").json()["id"] == "999"


def make_nested_client():
    spec = load_openapi(FIXTURES / "nested.yaml")
    store = QuackStore()
    app = build_app(spec, store)
    return TestClient(app), store


def test_me_returns_single_object_not_array():
    client, _ = make_nested_client()

    body = client.get("/api/v1/auth/me").json()

    assert isinstance(body, dict)
    assert "email" in body


def test_same_prefix_resources_are_separate_collections():
    client, _ = make_nested_client()

    me = client.get("/api/v1/auth/me").json()
    status = client.get("/api/v1/auth/login-status").json()

    assert "email" in me
    assert "status" in status
    assert "email" not in status


def test_detail_unknown_id_generates_entity():
    client, _ = make_nested_client()

    monitor_id = "c5dfe3d0-998a-4e2c-b8f5-7f3d2c48a1b1"
    body = client.get(f"/api/v1/upcheck/monitors/{monitor_id}").json()

    assert body["id"] == monitor_id


def test_array_subresource_returns_list():
    client, _ = make_nested_client()

    body = client.get("/api/v1/upcheck/monitors/xyz/uptime").json()

    assert isinstance(body, list)
    assert len(body) >= 1
    assert "ts" in body[0]


def test_array_endpoint_returns_list():
    client, _ = make_nested_client()

    body = client.get("/api/v1/notifications/channels").json()

    assert isinstance(body, list)
    assert "id" in body[0]


def test_list_and_detail_share_collection():
    client, _ = make_nested_client()

    listed = client.get("/api/v1/upcheck/monitors").json()
    first_id = listed[0]["id"]

    detail = client.get(f"/api/v1/upcheck/monitors/{first_id}").json()

    assert detail["id"] == first_id


def test_patch_after_get_persists():
    client, _ = make_nested_client()

    client.get("/api/v1/upcheck/monitors/abc")
    client.patch("/api/v1/upcheck/monitors/abc", json={"name": "Renamed"})

    assert client.get("/api/v1/upcheck/monitors/abc").json()["name"] == "Renamed"


def make_weird_spec():
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


def test_fail_soft_unsupported_schema_does_not_crash(capfd):
    spec = make_weird_spec()

    app = build_app(spec)
    client = TestClient(app)
    response = client.get("/items")
    out = capfd.readouterr().out

    assert response.status_code == 200
    assert "[WARNING]" in out
    assert "weird-unknown-type" in out


def test_quiet_suppresses_warnings(capfd):
    spec = make_weird_spec()

    build_app(spec, quiet=True)
    quiet_out = capfd.readouterr().out
    build_app(spec, quiet=False)
    loud_out = capfd.readouterr().out

    assert "[WARNING]" not in quiet_out
    assert "[WARNING]" in loud_out


def make_example_spec():
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


def test_list_endpoint_with_item_example_has_unique_ids():
    client = TestClient(build_app(make_example_spec(), quiet=True))

    body = client.get("/items").json()

    assert len(body) == 10
    assert len({item["id"] for item in body}) == 10


def test_build_app_does_not_mutate_the_spec_dict():
    spec = make_example_spec()
    before = copy.deepcopy(spec)

    build_app(spec, quiet=True)

    assert spec == before


def test_get_with_yaml_date_example_answers_json():
    spec = load_openapi(FIXTURES / "yaml_date.yaml")
    client = TestClient(build_app(spec, quiet=True))

    response = client.get("/d")

    assert response.status_code == 200
    assert response.json()["when"] == "2024-01-15"


def test_post_with_client_id_is_retrievable_by_returned_id():
    client, _ = make_client()

    created = client.post("/users", json={"id": "custom", "name": "Bob"}).json()

    assert created["id"] == "11"
    assert client.get("/users/11").json()["name"] == "Bob"


def make_nested_resources_client():
    spec = load_openapi(FIXTURES / "nested_resources.yaml")
    store = QuackStore()
    return TestClient(build_app(spec, store, quiet=True)), store


def test_nested_detail_uses_every_path_param_as_identity():
    client, _ = make_nested_resources_client()

    alice = client.get("/orgs/orgA/members/alice").json()
    bob = client.get("/orgs/orgA/members/bob").json()
    other_org = client.get("/orgs/orgB/members/alice").json()

    assert alice["id"] == "orgA/alice"
    assert bob["id"] == "orgA/bob"
    assert len({alice["id"], bob["id"], other_org["id"]}) == 3


def test_nested_delete_removes_the_addressed_member():
    client, store = make_nested_resources_client()
    client.get("/orgs/orgA/members/alice")

    assert store.get("orgs/{org_id}/members", "orgA/alice") is not None
    assert client.delete("/orgs/orgA/members/alice").status_code == 200
    assert store.get("orgs/{org_id}/members", "orgA/alice") is None


def make_inverted_bounds_spec():
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


def test_build_app_survives_inverted_numeric_bounds():
    client = TestClient(build_app(make_inverted_bounds_spec(), quiet=True))

    response = client.get("/values")

    assert response.status_code == 200
    assert all(6 <= item["n"] <= 100 for item in response.json())


def make_markup_spec():
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


def test_spec_text_with_rich_markup_still_serves_requests(capfd):
    client = TestClient(build_app(make_markup_spec(), quiet=False))

    response = client.get("/items")
    out = capfd.readouterr().out

    assert response.status_code == 200
    assert "unsupported type" in out
    assert "[/]" in out


def make_status_spec():
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
def test_invalid_request_body_returns_client_error(raw, content_type, expected):
    client = TestClient(build_app(make_status_spec(), quiet=True))

    response = client.post("/jobs", content=raw, headers={"content-type": content_type})

    assert response.status_code == expected


def test_oversized_request_body_returns_413():
    client = TestClient(build_app(make_status_spec(), quiet=True))
    raw = b'{"name": "' + b"x" * 1_048_576 + b'"}'

    response = client.post("/jobs", content=raw, headers={"content-type": "application/json"})

    assert response.status_code == 413


def test_non_ascii_declared_content_length_is_not_a_server_error():
    app = build_app(make_status_spec(), quiet=True)
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
    messages = []

    async def receive():
        return {"type": "http.request", "body": b'{"name": "job"}', "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))

    start = next(m for m in messages if m["type"] == "http.response.start")
    assert start["status"] < 500


def test_post_answers_the_status_declared_by_the_operation():
    client = TestClient(build_app(make_status_spec(), quiet=True))

    assert client.post("/jobs", json={"name": "job"}).status_code == 202


def test_put_answers_the_status_declared_by_the_operation():
    client = TestClient(build_app(make_status_spec(), quiet=True))

    assert client.put("/jobs/2", json={"name": "renamed"}).status_code == 202


def test_delete_with_declared_204_has_no_body():
    client = TestClient(build_app(make_status_spec(), quiet=True))

    response = client.delete("/jobs/2")

    assert response.status_code == 204
    assert response.content == b""


def test_post_with_declared_204_has_no_body():
    client = TestClient(build_app(make_status_spec(), quiet=True))

    response = client.post("/pings", json={"name": "ping"})

    assert response.status_code == 204
    assert response.content == b""


def test_get_collection_with_declared_204_has_no_body():
    client = TestClient(build_app(make_status_spec(), quiet=True))

    response = client.get("/telemetry")

    assert response.status_code == 204
    assert response.content == b""


def test_patch_answers_the_status_declared_by_the_operation():
    client = TestClient(build_app(make_status_spec(), quiet=True))

    response = client.patch("/jobs/2", json={"name": "patched"})

    assert response.status_code == 202


def test_delete_with_declared_200_returns_the_addressed_key():
    client = TestClient(build_app(make_status_spec(), quiet=True))

    response = client.delete("/tasks/2")

    assert response.status_code == 200
    assert response.json() == {"deleted": "2"}


def test_request_without_a_content_type_header_answers_400():
    client = TestClient(build_app(make_status_spec(), quiet=True))

    response = client.post("/jobs", content=b"{not json")

    assert response.status_code == 400


# No content key at all: operation_response_schema returns None, so the route reads
# the store instead of generating, and whatever is under the key is served as is.
def make_schemaless_nested_spec():
    return {
        "openapi": "3.0.0",
        "info": {"title": "schemaless", "version": "1.0.0"},
        "paths": {
            "/orgs/{org_id}/members/{member_id}": {
                "get": {"responses": {"200": {"description": "ok"}}}
            }
        },
    }


def test_nested_get_without_a_response_schema_answers_404():
    # The store is seeded by hand because a schema-less GET never generates: only a
    # store that already holds the composite key can tell the nested identity apart
    # from a key built out of the first path parameter, which is what makes the
    # served member below the assertion that the name promises.
    spec = make_schemaless_nested_spec()
    store = QuackStore()
    member = {"type": "object", "properties": {"name": {"type": "string"}}}
    alice = store.first_or_create("orgs/{org_id}/members", "orgA/alice", member)
    store.first_or_create("orgs/{org_id}/members", "orgA/bob", member)
    client = TestClient(build_app(spec, store, quiet=True))

    served = client.get("/orgs/orgA/members/alice")
    missing = client.get("/orgs/orgB/members/alice")

    assert served.status_code == 200
    assert served.json() == alice
    assert missing.status_code == 404
    assert missing.json() == {"error": "not found"}


# A parameter-less GET with no 2xx JSON schema, which no seeding path covers: the
# store is filled by the POST on the same path instead, since path_resource drops
# no segment here and both verbs address one collection.
def make_schemaless_collection_spec():
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


def test_schemaless_collection_get_returns_every_stored_item():
    client = TestClient(build_app(make_schemaless_collection_spec(), quiet=True))
    client.post("/telemetry", json={"name": "first"})
    client.post("/telemetry", json={"name": "second"})

    response = client.get("/telemetry")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["1", "2"]
    assert [item["name"] for item in response.json()] == ["first", "second"]


# The array schema is what makes this a list route, so the collection is served
# from the list branch with a 204; /telemetry above declares 204 with no content
# and therefore never gets there.
def make_204_list_spec():
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


def test_list_route_with_declared_204_has_no_body():
    client = TestClient(build_app(make_204_list_spec(), quiet=True))

    response = client.get("/metrics")

    assert response.status_code == 204
    assert response.content == b""


# httpx hands the header value to the ASGI scope unstripped, so the whitespace
# reaches _json_object through the client as well as through a real parser.
def test_content_type_padded_with_whitespace_is_read_as_json():
    client = TestClient(build_app(make_status_spec(), quiet=True))

    response = client.post(
        "/jobs", content=b'{"name": "job"}', headers={"content-type": "  application/json  "}
    )

    assert response.status_code == 202
    assert response.json()["name"] == "job"
