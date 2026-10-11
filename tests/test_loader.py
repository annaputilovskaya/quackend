import functools
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import requests as requests_lib
from prance.util.url import ResolutionError

from quackend import loader
from quackend.loader import (
    Route,
    SpecLoadError,
    _checked_url,
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


@pytest.mark.parametrize(
    "source",
    [
        "petstore.yaml",
        "./petstore.yaml",
        "C:\\specs\\petstore.yaml",
        "c:/specs/petstore.yaml",
        "file:///C:/specs/petstore.yaml",
        "/etc/quackend/petstore.yaml",
        "",
    ],
)
def test_checked_url_treats_local_sources_as_unfetched(source: str) -> None:
    assert _checked_url(source) is None


@pytest.mark.parametrize(
    "source",
    ["http://example.org/petstore.yaml", "https://example.org/petstore.yaml"],
)
def test_checked_url_keeps_allowed_urls(source: str) -> None:
    assert _checked_url(source) == source


@pytest.mark.parametrize("scheme", ["ftp", "gopher", "data"])
def test_checked_url_refuses_non_allowed_schemes(scheme: str) -> None:
    with pytest.raises(SpecLoadError, match="only http/https"):
        _checked_url(f"{scheme}://example.org/spec.yaml")


class _FakeResponse:
    """A requests.Response double exercising the wrapper's contract."""

    def __init__(
        self,
        *,
        status: int = 200,
        body: bytes = b"",
        read_error: Exception | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status
        self._body = body
        self._read_error = read_error
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        # Mirrors requests: raise for 4xx/5xx, stay silent for 2xx and 3xx.
        if self.status_code >= 400:
            raise requests_lib.HTTPError(f"{self.status_code} Client Error")

    @property
    def raw(self) -> "_FakeResponse":
        return self

    def read(self, amt: int, decode_content: bool = True) -> bytes:
        if self._read_error is not None:
            raise self._read_error
        return self._body


def _original_fetch(url: object, cache: object, encoding: object = None) -> tuple[str, str]:
    return "original content", "text/plain"


def _wrapper() -> Any:
    return loader._wrap_fetch_url_text(_original_fetch)


def _http_url() -> urllib.parse.ParseResult:
    return urllib.parse.urlparse("http://example.org/spec.yaml")


def test_wrapper_delegates_file_urls_to_the_original() -> None:
    url = urllib.parse.urlparse("file:///C:/specs/petstore.yaml")

    assert _wrapper()(url, {}) == ("original content", "text/plain")


def test_wrapper_fetches_bounded_and_fills_the_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse(body=b"openapi: 3.0.0\n", headers={"content-type": "text/yaml"})
    monkeypatch.setattr(requests_lib, "get", lambda *_a, **_k: response)
    cache: dict[str, Any] = {}

    content, content_type = _wrapper()(_http_url(), cache)

    assert content == "openapi: 3.0.0\n"
    assert content_type == "text/yaml"
    assert cache["text_http://example.org/spec.yaml"] == ("openapi: 3.0.0\n", "text/yaml")


def test_wrapper_passes_the_timeout_and_blocks_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kwargs: dict[str, Any] = {}
    monkeypatch.setattr(requests_lib, "get", lambda *_a, **kw: kwargs.update(kw) or _FakeResponse())

    _wrapper()(_http_url(), {})

    assert kwargs == {
        "timeout": loader._TIMEOUT_SECONDS,
        "stream": True,
        "allow_redirects": False,
    }


def test_wrapper_turns_http_errors_into_resolution_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(requests_lib, "get", lambda *_a, **_k: _FakeResponse(status=404))

    with pytest.raises(ResolutionError, match="404") as info:
        _wrapper()(_http_url(), {})

    assert isinstance(info.value.__cause__, requests_lib.HTTPError)


def test_wrapper_refuses_a_redirect_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # requests reports a 3xx as ok and raise_for_status() ignores it, so the
    # wrapper must refuse 3xx itself instead of parsing the redirect body.
    monkeypatch.setattr(requests_lib, "get", lambda *_a, **_k: _FakeResponse(status=302))

    with pytest.raises(ResolutionError, match="Cannot fetch URL") as info:
        _wrapper()(_http_url(), {})

    assert isinstance(info.value.__cause__, requests_lib.HTTPError)


def test_wrapper_refuses_a_body_whose_length_exceeds_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b"openapi: 3.0.0\n"
    monkeypatch.setattr(
        requests_lib,
        "get",
        lambda *_a, **_k: _FakeResponse(
            body=body, headers={"content-length": str(loader._MAX_SPEC_BYTES + 1)}
        ),
    )

    with pytest.raises(ResolutionError, match="over the 8388608-byte limit"):
        _wrapper()(_http_url(), {})


def test_wrapper_refuses_a_streamed_body_that_exceeds_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse(body=b"x" * (loader._MAX_SPEC_BYTES + 1))
    monkeypatch.setattr(requests_lib, "get", lambda *_a, **_k: response)

    with pytest.raises(ResolutionError, match="over the 8388608-byte limit"):
        _wrapper()(_http_url(), {})


def test_wrapper_refuses_schemes_outside_the_allow_list() -> None:
    url = urllib.parse.urlparse("ftp://example.org/spec.yaml")

    with pytest.raises(ResolutionError, match="only http/https"):
        _wrapper()(url, {})


def test_wrapper_wraps_transport_errors_from_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        requests_lib, "get", lambda *_a, **_k: (_ for _ in ()).throw(requests_lib.Timeout())
    )

    with pytest.raises(ResolutionError, match="Cannot fetch URL") as info:
        _wrapper()(_http_url(), {})

    assert isinstance(info.value.__cause__, requests_lib.Timeout)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def _serve_directory(directory: Path) -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        functools.partial(_QuietHandler, directory=str(directory)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_load_openapi_fetches_a_url_spec_with_an_external_ref(tmp_path: Path) -> None:
    (tmp_path / "items.yaml").write_text(
        "type: array\nitems:\n  type: object\n  properties:\n    name:\n      type: string\n",
        encoding="utf-8",
    )
    server, thread = _serve_directory(tmp_path)
    try:
        port = server.server_address[1]
        (tmp_path / "root.yaml").write_text(
            f"""openapi: 3.0.0
info:
  title: url probe
  version: "1"
paths:
  /things:
    get:
      responses:
        "200":
          description: ok
          content:
            application/json:
              schema:
                $ref: "http://127.0.0.1:{port}/items.yaml"
""",
            encoding="utf-8",
        )
        spec = load_openapi(f"http://127.0.0.1:{port}/root.yaml")
    finally:
        server.shutdown()
        thread.join(timeout=5)

    schema = spec["paths"]["/things"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert schema["type"] == "array"


def test_load_openapi_refuses_a_non_http_scheme_before_fetching() -> None:
    with pytest.raises(SpecLoadError, match="Refusing to fetch 'ftp'") as info:
        load_openapi("ftp://example.org/spec.yaml")

    assert info.value.__cause__ is None
    assert str(info.value).count("Refusing to fetch 'ftp'") == 1


def test_load_openapi_wraps_a_broken_url_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> object:
        raise requests_lib.Timeout("no route to host")

    monkeypatch.setattr(requests_lib, "get", refuse)

    with pytest.raises(SpecLoadError, match="ResolutionError: Cannot fetch URL") as info:
        load_openapi("http://example.org/spec.yaml")

    assert isinstance(info.value.__cause__, ResolutionError)
    assert str(info.value).count("Cannot fetch URL") == 1
