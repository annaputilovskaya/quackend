# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The project is
still `0.x`: the public API may change in a minor release until `1.0.0`.

## [Unreleased]

### Added

- The wheel ships `py.typed`, and `loader`, `store` and `server` declare
  `__all__`, so a consumer type-checks against the documented API instead of
  against `Any`.
- `SECURITY.md`, `CODE_OF_CONDUCT.md`, a bug report template and a pull request
  template.
- CI runs the whole Definition of Done on every push and pull request, on Linux
  and Windows, on Python 3.10 and 3.13, and validates the built distributions
  with `twine check --strict`.

### Fixed

- `store.create` derives `id` from the storage key, so `POST` and `GET` of the
  same resource always address the same object. **Breaking**: an `id` sent by a
  client in a `POST` body is ignored.
- Values taken from a spec's `example` are detached and normalised to JSON:
  every item of a collection no longer shares one `example` object, and a YAML
  date such as `2024-01-15` no longer breaks the response.
- Nested resources are keyed by every path parameter, so
  `/orgs/{org_id}/members/{member_id}` no longer addresses the same member for
  every parent.
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

- `mypy` checks `tests/` as strictly as `src/`, and the `tests.*` override that
  the old gate never executed is gone.
