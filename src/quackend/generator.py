"""Generate fake values from JSON Schema fragments with Faker."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from faker import Faker

_T = TypeVar("_T", int, float)

__all__ = ["ARRAY_MAX", "DEPTH_LIMIT", "generate_object", "generate_value"]

DEPTH_LIMIT = 3
ARRAY_MAX = 5
_ARRAY_MIN = 1
_BYTE_LENGTH = 4
_BINARY_LENGTH = 8
_STRING_PADDING = 20
_NUMERIC_STRING_LOW = 0
_NUMERIC_STRING_HIGH = 100
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
    "byte": lambda f: f.binary(_BYTE_LENGTH).hex(),
    "binary": lambda f: f.binary(_BINARY_LENGTH).hex(),
    "password": lambda f: f.password(),
}

_ScalarProducer = Callable[[Mapping[str, Any], Faker, Callable[[str], None]], Any]

_SCALAR_PRODUCERS: dict[str, _ScalarProducer] = {
    "integer": lambda schema, fake, emit: _integer_value(schema, fake, emit),
    "number": lambda schema, fake, emit: _number_value(schema, fake, emit),
    "boolean": lambda schema, fake, emit: fake.boolean(),
    "string": lambda schema, fake, emit: _string_value(schema, fake),
}


def _no_warn(_message: str) -> None:
    """Discard a fail-soft message."""


def generate_value(
    schema: Mapping[str, Any],
    fake: Faker,
    warn: Callable[[str], None] | None = None,
    *,
    depth_limit: int = DEPTH_LIMIT,
    array_max: int = ARRAY_MAX,
) -> Any:
    """Generate a fake value matching a JSON Schema fragment.

    Args:
        schema: a JSON Schema fragment to satisfy.
        fake: a Faker instance used to produce values.
        warn: optional callback invoked with a message for fail-soft cases.
        depth_limit: how deep an object nests before it becomes empty.
        array_max: the longest array a schema can produce.

    Returns:
        A generated value, or None when the schema is missing or unsupported.
    """
    emit = warn if warn is not None else _no_warn
    return _generate_value(schema, fake, 0, emit, depth_limit, array_max)


def _generate_value(
    schema: Mapping[str, Any],
    fake: Faker,
    depth: int,
    emit: Callable[[str], None],
    depth_limit: int,
    array_max: int,
) -> Any:
    """Generate a value at a known nesting depth.

    The depth is private on purpose: a caller that could pass one in would be
    able to start below the top of a schema and silently skip the depth guard.

    Args:
        schema: a JSON Schema fragment to satisfy.
        fake: a Faker instance used to produce values.
        depth: current nesting depth, guards against runaway recursion.
        emit: the fail-soft callback; never None after the public entry point.
        depth_limit: how deep an object nests before it becomes empty.
        array_max: the longest array a schema can produce.

    Returns:
        A generated value, or None when the schema is missing or unsupported.
    """
    example = schema.get("example")
    if example is not None:
        return _jsonable(copy.deepcopy(example), emit)
    if "enum" in schema:
        return _jsonable(copy.deepcopy(fake.random.choice(schema["enum"])), emit)
    if "oneOf" in schema or "anyOf" in schema or "allOf" in schema:
        return _composite_value(schema, fake, depth, emit, depth_limit, array_max)
    schema_type = schema.get("type")
    if schema_type == "object":
        return _object_value(schema, fake, depth, emit, depth_limit, array_max)
    if schema_type == "array":
        return _array_value(schema, fake, depth, emit, depth_limit, array_max)
    producer = _SCALAR_PRODUCERS.get(schema_type) if isinstance(schema_type, str) else None
    if producer is not None:
        return producer(schema, fake, emit)
    if not schema_type:
        emit("missing type, returning null")
    else:
        emit(f"unsupported type {schema_type!r}, returning null")
    return None


def generate_object(
    schema: Mapping[str, Any],
    fake: Faker,
    warn: Callable[[str], None] | None = None,
    *,
    depth_limit: int = DEPTH_LIMIT,
    array_max: int = ARRAY_MAX,
) -> dict[str, Any]:
    """Generate a JSON-Schema object, wrapping scalar schemas in a value field.

    Args:
        schema: a JSON Schema fragment expected to describe an object.
        fake: a Faker instance used to produce values.
        warn: an optional callback receiving fail-soft messages.
        depth_limit: how deep an object nests before it becomes empty.
        array_max: the longest array a schema can produce.

    Returns:
        A generated object; scalar schemas are wrapped as ``{"value": <scalar>}``.
    """
    value = generate_value(schema, fake, warn, depth_limit=depth_limit, array_max=array_max)
    return value if isinstance(value, dict) else {"value": value}


def _object_value(
    schema: Mapping[str, Any],
    fake: Faker,
    depth: int,
    emit: Callable[[str], None],
    depth_limit: int,
    array_max: int,
) -> dict[str, Any]:
    if depth > depth_limit:
        return {}
    return {
        name: _generate_value(sub_schema, fake, depth + 1, emit, depth_limit, array_max)
        for name, sub_schema in (schema.get("properties") or {}).items()
    }


def _array_value(
    schema: Mapping[str, Any],
    fake: Faker,
    depth: int,
    emit: Callable[[str], None],
    depth_limit: int,
    array_max: int,
) -> list[Any]:
    """Generate an array by recursing into ``items`` for each slot."""
    items = schema.get("items") or {}
    length = fake.random.randint(_ARRAY_MIN, array_max)
    return [
        _generate_value(items, fake, depth + 1, emit, depth_limit, array_max) for _ in range(length)
    ]


def _composite_value(
    schema: Mapping[str, Any],
    fake: Faker,
    depth: int,
    emit: Callable[[str], None],
    depth_limit: int,
    array_max: int,
) -> Any:
    """Resolve a ``oneOf``/``anyOf``/``allOf`` schema by picking or merging a branch.

    Branch order matches the historical cascade: ``oneOf``/``anyOf`` win over
    ``allOf`` when a schema declares both.
    """
    if "oneOf" in schema or "anyOf" in schema:
        branches: list[dict[str, Any]] = schema.get("oneOf") or schema.get("anyOf") or []
        if not branches:
            emit("empty oneOf/anyOf, returning null")
            return None
        branch = next((b for b in branches if b.get("example") is not None), branches[0])
        emit("used first branch of oneOf/anyOf")
        return _generate_value(branch, fake, depth + 1, emit, depth_limit, array_max)
    return _merged_all_of(schema, fake, depth, emit, depth_limit, array_max)


def _merged_all_of(
    schema: Mapping[str, Any],
    fake: Faker,
    depth: int,
    emit: Callable[[str], None],
    depth_limit: int,
    array_max: int,
) -> Any:
    """Merge every ``allOf`` branch (or take the one with an example) and generate."""
    all_branches: list[dict[str, Any]] = schema["allOf"]
    example_branch = next((b for b in all_branches if b.get("example") is not None), None)
    if example_branch is not None:
        return _generate_value(example_branch, fake, depth + 1, emit, depth_limit, array_max)
    merged: dict[str, Any] = {}
    for branch in all_branches:
        branch_props: Any = branch.get("properties")
        merged_props: Any = merged.get("properties")
        if isinstance(branch_props, dict) and isinstance(merged_props, dict):
            merged["properties"] = {**merged_props, **branch_props}
        else:
            merged.update(branch)
    return _generate_value(merged, fake, depth + 1, emit, depth_limit, array_max)


def _jsonable(value: Any, emit: Callable[[str], None]) -> Any:
    """Return a detached, JSON-serialisable copy of a value taken from a spec.

    YAML readers type unquoted dates as ``datetime.date``; such a value would
    break ``json.dumps`` on every response, so it is coerced to its string form.

    Args:
        value: a value produced by a YAML or JSON parser.
        emit: the fail-soft callback; never None after the public entry point.

    Returns:
        A value that ``json.dumps`` accepts, sharing no mutable state with the
        input.
    """
    if isinstance(value, _JSON_SCALARS):
        return value
    if isinstance(value, dict):
        return {str(name): _jsonable(item, emit) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item, emit) for item in value]
    emit(f"spec value of type {type(value).__name__} is not JSON, coerced to str")
    return str(value)


def _ordered_bounds(
    low: _T | None,
    high: _T | None,
    low_default: _T,
    default_high: _T,
    emit: Callable[[str], None],
    what: str,
) -> tuple[_T, _T]:
    """Return an inclusive range that satisfies both bounds of a schema.

    A spec declaring ``minimum`` above ``maximum`` passes OpenAPI validation but
    cannot be satisfied; the bounds are swapped and the swap is reported instead
    of raising, so one bad range never stops the server from starting.

    Args:
        low: the lower bound, or None when the schema omits it.
        high: the upper bound, or None when the schema omits it.
        low_default: the lower bound used when the schema declares none; it is
            typed like the bounds themselves so an integer range never passes
            through a float and lose precision above 2 ** 53.
        default_high: the upper bound used when the schema declares none.
        emit: the fail-soft callback; never None after the public entry point.
        what: the schema type name, used in the warning message.

    Returns:
        A ``(low, high)`` pair with ``low <= high``.
    """
    if low is None and high is None:
        return low_default, default_high
    low = low_default if low is None else low
    if high is None:
        high = low + default_high
    if low > high:
        low, high = high, low
        emit(f"inverted {what} bounds, swapped to {low:g}..{high:g}")
    return low, high


def _integer_value(
    schema: Mapping[str, Any],
    fake: Faker,
    emit: Callable[[str], None],
) -> int:
    low: int | None = schema.get("minimum")
    high: int | None = schema.get("maximum")
    if schema.get("exclusiveMinimum") is not None:
        low = schema["exclusiveMinimum"] + 1
    if schema.get("exclusiveMaximum") is not None:
        high = schema["exclusiveMaximum"] - 1
    low_bound, high_bound = _ordered_bounds(low, high, 0, _DEFAULT_INTEGER_MAX, emit, "integer")
    return fake.random_int(low_bound, high_bound)


def _number_value(
    schema: Mapping[str, Any],
    fake: Faker,
    emit: Callable[[str], None],
) -> float:
    low, high = _ordered_bounds(
        schema.get("minimum"), schema.get("maximum"), 0.0, _DEFAULT_NUMBER_MAX, emit, "number"
    )
    value: float = fake.random.uniform(low, high)
    return value


def _string_value(schema: Mapping[str, Any], fake: Faker) -> str:
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
        return fake.pystr(min_chars=min_length, max_chars=min_length + _STRING_PADDING)
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


def _numeric_string_value(schema: Mapping[str, Any], fake: Faker) -> str:
    low = float(schema.get("minimum", _NUMERIC_STRING_LOW))
    high = float(schema.get("maximum", _NUMERIC_STRING_HIGH))
    raw = fake.random.uniform(low, high)
    regex = re.compile(schema["pattern"])
    candidates = (f"{raw:.2f}", str(int(round(raw))))
    for candidate in candidates:
        if regex.fullmatch(candidate):
            return candidate
    return candidates[0]
