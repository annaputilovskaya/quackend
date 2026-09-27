"""Generate fake values from JSON Schema fragments with Faker."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from typing import Any

from faker import Faker

_DEPTH_LIMIT = 3
_ARRAY_MAX = 5
_DEFAULT_INTEGER_MAX = 9_999
_DEFAULT_NUMBER_MAX = 1_000_000
_JSON_SCALARS = (str, int, float, bool, type(None))

_FORMAT_PRODUCERS: dict[str, Callable[[Faker], str]] = {
    "email": lambda f: f.email(),
    "uuid": lambda f: f.uuid4(),
    "date": lambda f: f.date(),
    "date-time": lambda f: f.iso8601(),
    "uri": lambda f: f.uri(),
    "uri-reference": lambda f: f.url(),
    "hostname": lambda f: f.hostname(),
    "ipv4": lambda f: f.ipv4(),
    "ipv6": lambda f: f.ipv6(),
    "byte": lambda f: f.binary(4).hex(),
    "binary": lambda f: f.binary(8).hex(),
    "password": lambda f: f.password(),
}


def generate_value(
    schema: dict[str, Any],
    fake: Faker,
    depth: int = 0,
    warn: Callable[[str], None] | None = None,
) -> Any:
    """Generate a fake value matching a JSON Schema fragment.

    Args:
        schema: a JSON Schema fragment to satisfy.
        fake: a Faker instance used to produce values.
        depth: current nesting depth, guards against runaway recursion.
        warn: optional callback invoked with a message for fail-soft cases.

    Returns:
        A generated value, or None when the schema is missing or unsupported.
    """
    example = schema.get("example")
    if example is not None:
        return _jsonable(copy.deepcopy(example), warn)
    if "enum" in schema:
        return _jsonable(copy.deepcopy(fake.random.choice(schema["enum"])), warn)
    if "oneOf" in schema or "anyOf" in schema:
        branches: list[dict[str, Any]] = schema.get("oneOf") or schema.get("anyOf") or []
        if not branches:
            if warn:
                warn("empty oneOf/anyOf, returning null")
            return None
        branch = next((b for b in branches if b.get("example") is not None), branches[0])
        if warn:
            warn("used first branch of oneOf/anyOf")
        return generate_value(branch, fake, depth + 1, warn)
    if "allOf" in schema:
        all_branches: list[dict[str, Any]] = schema["allOf"]
        example_branch = next((b for b in all_branches if b.get("example") is not None), None)
        if example_branch is not None:
            return generate_value(example_branch, fake, depth + 1, warn)
        merged: dict[str, Any] = {}
        for branch in all_branches:
            branch_props: Any = branch.get("properties")
            merged_props: Any = merged.get("properties")
            if isinstance(branch_props, dict) and isinstance(merged_props, dict):
                merged["properties"] = {**merged_props, **branch_props}
            else:
                merged.update(branch)
        return generate_value(merged, fake, depth + 1, warn)
    schema_type = schema.get("type")
    if not schema_type:
        if warn:
            warn("missing type, returning null")
        return None
    if schema_type == "object":
        return _object_value(schema, fake, depth, warn)
    if schema_type == "array":
        items = schema.get("items") or {}
        length = fake.random.randint(1, _ARRAY_MAX)
        return [generate_value(items, fake, depth + 1, warn) for _ in range(length)]
    if schema_type == "integer":
        return _integer_value(schema, fake)
    if schema_type == "number":
        low = schema.get("minimum", 0)
        high = schema.get("maximum", 1_000_000)
        return fake.random.uniform(low, high)
    if schema_type == "boolean":
        return fake.boolean()
    if schema_type == "string":
        return _string_value(schema, fake)
    if warn:
        warn(f"unsupported type {schema_type!r}, returning null")
    return None


def _object_value(
    schema: dict[str, Any],
    fake: Faker,
    depth: int,
    warn: Callable[[str], None] | None,
) -> dict[str, Any]:
    if depth > _DEPTH_LIMIT:
        return {}
    return {
        name: generate_value(sub_schema, fake, depth + 1, warn)
        for name, sub_schema in (schema.get("properties") or {}).items()
    }


def _jsonable(value: Any, warn: Callable[[str], None] | None = None) -> Any:
    """Return a detached, JSON-serialisable copy of a value taken from a spec.

    YAML readers type unquoted dates as ``datetime.date``; such a value would
    break ``json.dumps`` on every response, so it is coerced to its string form.

    Args:
        value: a value produced by a YAML or JSON parser.
        warn: an optional callback invoked when a coercion was needed.

    Returns:
        A value that ``json.dumps`` accepts, sharing no mutable state with the
        input.
    """
    if isinstance(value, _JSON_SCALARS):
        return value
    if isinstance(value, dict):
        return {str(name): _jsonable(item, warn) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item, warn) for item in value]
    if warn:
        warn(f"spec value of type {type(value).__name__} is not JSON, coerced to str")
    return str(value)


def _integer_value(schema: dict[str, Any], fake: Faker) -> int:
    low: int | None = schema.get("minimum")
    high: int | None = schema.get("maximum")
    if schema.get("exclusiveMinimum") is not None:
        low = schema["exclusiveMinimum"] + 1
    if schema.get("exclusiveMaximum") is not None:
        high = schema["exclusiveMaximum"] - 1
    if low is None and high is None:
        return fake.random_int(0, 9999)
    low = low if low is not None else 0
    high = high if high is not None else low + 9999
    return fake.random_int(low, high)


def _string_value(schema: dict[str, Any], fake: Faker) -> str:
    format_name: str | None = schema.get("format")
    producer = _FORMAT_PRODUCERS.get(format_name) if format_name is not None else None
    if producer:
        return producer(fake)
    pattern: str | None = schema.get("pattern")
    if pattern is not None and _is_numeric_pattern(pattern):
        return _numeric_string_value(schema, fake)
    max_length: int | None = schema.get("maxLength")
    if max_length is not None:
        return fake.pystr(max_chars=max_length)
    min_length: int | None = schema.get("minLength")
    if min_length is not None:
        return fake.pystr(min_chars=min_length, max_chars=min_length + 20)
    return fake.word()


def _is_numeric_pattern(pattern: str) -> bool:
    r"""Return whether a pattern describes a decimal-as-string value.

    A pattern counts as numeric when it accepts plain numbers like "0" and
    "1.25" while rejecting ordinary words, e.g. :code:`^\d*\.?\d*$`.
    """
    try:
        regex = re.compile(pattern)
    except re.error:
        return False
    return bool(regex.fullmatch("0") and regex.fullmatch("1.25") and not regex.fullmatch("abc"))


def _numeric_string_value(schema: dict[str, Any], fake: Faker) -> str:
    low = float(schema.get("minimum", 0))
    high = float(schema.get("maximum", 100))
    raw = fake.random.uniform(low, high)
    regex = re.compile(schema["pattern"])
    candidates = (f"{raw:.2f}", str(int(round(raw))))
    for candidate in candidates:
        if regex.fullmatch(candidate):
            return candidate
    return candidates[0]
