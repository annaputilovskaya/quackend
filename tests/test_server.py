import time
from pathlib import Path

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
