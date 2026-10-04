# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The project is
still `0.x`: the public API may change in a minor release until `1.0.0`.

## [Unreleased]

### Added

- `store.StoreConfig` carries the three limits a store generates with —
  `collection_size`, `depth_limit` and `array_max` — and is passed to
  `QuackStore(config=...)`; every default is the generator's own default, so an
  unconfigured store generates exactly what it did before. `generate_value` and
  `generate_object` take `depth_limit` and `array_max` as keyword-only
  arguments. **Breaking**: `QuackStore` no longer takes a `Faker`, so a caller
  that built `QuackStore(fake)` now passes a `StoreConfig` instead and requests
  determinism with `set_seed`; a caller that needs an injected Faker (a fixed
  locale, say) has to keep one on its own side.
- The wheel ships `py.typed`, and `loader`, `store` and `server` declare
  `__all__`, so a consumer type-checks against the documented API instead of
  against `Any`.
- `SECURITY.md`, `CODE_OF_CONDUCT.md`, a bug report template and a pull request
  template.
- CI runs the whole Definition of Done on every push and pull request, on Linux
  and Windows, on Python 3.10 and 3.13, and validates the built distributions
  with `twine check --strict`.
- `loader` yields a resolved `Operation` record instead of a `(path, method,
  operation)` tuple, and exports `Route` next to it.
- `store` exports `StoreProtocol`, the contract `build_app` depends on: any
  adapter can be injected, and an adapter that is empty is no longer silently
  replaced by `QuackStore`.

### Fixed

- The startup banner now reads `Starting quackend on http://<host>:<port>
  (Ctrl+C to stop)`. It used to claim the mock server "is running" before
  `uvicorn.run` had bound anything, and it omitted the URL scheme.
- `--port` now rejects values outside `1..65535` with exit code 2. Previously
  `--port 99999` was accepted and only failed later with an `OverflowError`
  traceback from `bind()`.
- **Breaking**: `loader.load_openapi` now raises `loader.SpecLoadError` for every
  failure instead of leaking `prance`, `ruamel.yaml` and `OSError` families.
  Callers catching `prance.ValidationError` must catch `SpecLoadError`; the
  original exception is available as `__cause__`.
- An unusable spec now exits with code 2 and a single stderr line naming the
  reason, instead of a Rich traceback.
- `quackend start --quiet` no longer prints the route table. The flag promised to
  suppress banner output, and the table was printed on every start.
- Every value that crosses the store boundary is a deep copy: mutating an item,
  a list or a nested value that came out of `store` no longer changes what the
  store holds, and mutating a payload passed to `store.create` or `store.update`
  no longer changes what it stored. **Breaking**: a caller that relied on
  identity (`store.get(...) is store.get(...)`, or editing the store through a
  returned item) has to work on copies instead.
- `store.create` never reuses an id: deleting the highest id of a seeded
  collection and creating again now numbers the new item after it instead of
  filling the gap, so a client that already saw that id does not resolve to a
  different object. **Breaking**: the ids of a collection are not contiguous any
  more after a delete; code that assumed a collection is `1..N` has to count.
- An operation whose only success response is the `2XX` range serves generated
  data for its declared schema instead of `[]`, and both the status and the
  schema are now read through one parser, so they can no longer disagree.
  **Breaking**: such an operation now answers a body where it used to answer an
  empty list. An operation with no 2xx response and no schema still mocks `[]`;
  that part is unchanged.
- `store.create` derives `id` from the storage key, so `POST` and `GET` of the
  same resource always address the same object. **Breaking**: an `id` sent by a
  client in a `POST` body is ignored.
- Values taken from a spec's `example` are detached and normalised to JSON:
  every item of a collection no longer shares one `example` object, and a YAML
  date such as `2024-01-15` no longer breaks the response.
- Nested resources are keyed by every path parameter, so
  `/orgs/{org_id}/members/{member_id}` no longer addresses the same member for
  every parent.
- A collection nested under a path parameter belongs to the parent the request
  names, so `/monitors/m1/uptime` and `/monitors/m2/uptime` are two collections
  instead of one shared bucket. **Breaking**: the store key holds the bound
  parent (`api/v1/upcheck/monitors/xyz/uptime`), so a hand-written
  `QuackStore` consumer that looks up `orgs/{org_id}/members` directly sees
  nothing and has to resolve the parent first; such a collection is created on
  the first request instead of at startup.
- Inverted numeric bounds (`minimum` above `maximum`) are swapped and reported
  as a warning instead of raising `ValueError` while the server starts.
- Spec text that looks like Rich markup is escaped before it reaches the
  console, both in generator warnings and in the route table.
- A malformed request body answers `4xx` (`400` for unparsable or non-object
  JSON, `413` for an oversized body, `415` for a non-JSON content type)
  instead of `500`.
- Every operation answers the success status its own spec declares, a declared
  `204` answers with an empty body, and `DELETE` removes the item it addresses.

### Changed

- `build_app` takes an `rng` the simulated failures are drawn from, so
  `build_app(..., rng=random.Random(7))` makes them reproducible, and it rejects
  a negative `latency_ms` and a `fail_rate` outside `[0, 1]` with a `ValueError`
  instead of mocking something else. **Breaking**: a caller that passed an
  out-of-range `fail_rate` — say `2.0` by mistake — used to get an app that
  failed every request forever and now gets a loud error at startup.
- The generation limits are published as `generator.DEPTH_LIMIT` and
  `generator.ARRAY_MAX`, and every remaining magic number of the generator
  carries a name. **Breaking**: `generate_value` no longer takes `depth`, so a
  caller can no longer start the recursion below the top of a schema and skip the
  depth guard; `warn` is its third parameter now.
- Rendering a route table is pure: `render_route_table` returns the table and
  `quackend routes` and `quackend start` print it, so nothing below `cli` writes
  to a stream. **Breaking**: `quackend.reporting.console` moved to
  `quackend.cli.console`.
- A declared `HEAD` is answered with the status and headers of its own declared
  success and an empty body, and a declared `OPTIONS` answers `204` with an
  `Allow` header listing the methods the app serves for that path. **Breaking**:
  a declared `TRACE` now makes `build_app` raise
  `loader.UnsupportedOperationError` instead of returning an app that answers
  `405`, and the route table lists `TRACE` too.
- `mypy` checks `tests/` as strictly as `src/`, and the `tests.*` override that
  the old gate never executed is gone.
- `build_app` takes a `warn` callback instead of a `quiet` flag. **Breaking**:
  the library prints nothing of its own, so `quiet=True` becomes `warn=None`
  and `quiet=False` becomes `warn=<callable>`; the CLI decides how a warning
  reaches the terminal, and the whole application shares one Rich console.
- Public functions accept `Mapping` instead of `dict`, so a read-only mapping
  can be passed.
- A generated item is narrowed to an object once, in the generator
  (`generate_object`), instead of at the two call sites in `store`.
