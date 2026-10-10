import datetime
import inspect
import json
import math
import re
from types import MappingProxyType
from typing import Any

import pytest
from faker import Faker

from quackend.generator import (
    ARRAY_MAX,
    DEPTH_LIMIT,
    _exclusive_shift,
    _inclusive_float,
    _inclusive_int,
    generate_object,
    generate_value,
)


@pytest.fixture()
def fake() -> Faker:
    return Faker()


def test_generate_value_example_returns_exact_value(fake: Faker) -> None:
    assert generate_value({"type": "string", "example": "fixed"}, fake) == "fixed"


def test_generate_value_enum_always_in_choices(fake: Faker) -> None:
    schema = {"type": "string", "enum": ["admin", "user"]}
    for _ in range(20):
        assert generate_value(schema, fake) in ["admin", "user"]


def test_generate_value_email_string_contains_at(fake: Faker) -> None:
    value = generate_value({"type": "string", "format": "email"}, fake)
    assert "email" in value or "@" in value


def test_generate_value_integer_within_bounds(fake: Faker) -> None:
    for _ in range(20):
        value = generate_value({"type": "integer", "minimum": 10, "maximum": 20}, fake)
        assert 10 <= value <= 20


def test_generate_value_number_within_bounds(fake: Faker) -> None:
    for _ in range(20):
        value = generate_value({"type": "number", "minimum": 1.5, "maximum": 2.5}, fake)
        assert 1.5 <= value <= 2.5


def test_generate_value_boolean_in_expected_values(fake: Faker) -> None:
    assert generate_value({"type": "boolean"}, fake) in (True, False)


def test_generate_value_array_returns_1_to_5_integers(fake: Faker) -> None:
    value = generate_value({"type": "array", "items": {"type": "integer"}}, fake)
    assert 1 <= len(value) <= 5
    assert all(isinstance(v, int) for v in value)


def test_generate_value_object_returns_string_property(fake: Faker) -> None:
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    value = generate_value(schema, fake)
    assert isinstance(value, dict)
    assert isinstance(value["name"], str)


def test_generate_value_missing_type_returns_none_with_warning(fake: Faker) -> None:
    warnings: list[str] = []
    value = generate_value({}, fake, warn=warnings.append)
    assert value is None
    assert any("missing type" in w for w in warnings)


def test_generate_value_unsupported_type_returns_none_with_warning(fake: Faker) -> None:
    warnings: list[str] = []
    value = generate_value({"type": "unknown"}, fake, warn=warnings.append)
    assert value is None
    assert any("unsupported type" in w for w in warnings)


def test_generate_value_one_of_uses_first_branch_with_warning(fake: Faker) -> None:
    warnings: list[str] = []
    schema = {"oneOf": [{"type": "integer"}, {"type": "string"}]}
    value = generate_value(schema, fake, warn=warnings.append)
    assert any("oneOf" in w or "anyOf" in w for w in warnings)
    assert isinstance(value, int)


def test_generate_value_any_of_uses_first_branch_with_warning(fake: Faker) -> None:
    warnings: list[str] = []
    schema = {"anyOf": [{"type": "integer"}, {"type": "string"}]}
    value = generate_value(schema, fake, warn=warnings.append)
    assert any("oneOf" in w or "anyOf" in w for w in warnings)
    assert isinstance(value, int)


def test_generate_value_all_of_merges_branches(fake: Faker) -> None:
    schema = {
        "allOf": [
            {"type": "object", "properties": {"a": {"type": "string"}}},
            {"properties": {"b": {"type": "integer"}}},
        ]
    }
    value = generate_value(schema, fake)
    assert set(value) == {"a", "b"}


def test_generate_value_empty_one_of_returns_none_with_warning(fake: Faker) -> None:
    warnings: list[str] = []
    schema: dict[str, Any] = {"oneOf": []}
    value = generate_value(schema, fake, warn=warnings.append)
    assert value is None
    assert any("oneOf" in w for w in warnings)


def test_generate_value_numeric_pattern_string_is_numeric(fake: Faker) -> None:
    schema = {"type": "string", "pattern": r"^\d*\.?\d*$"}
    for _ in range(20):
        value = generate_value(schema, fake)
        assert re.fullmatch(r"^\d*\.?\d*$", value)
        assert value != ""


def test_generate_value_any_of_numeric_string_prefers_real_value(fake: Faker) -> None:
    schema = {
        "anyOf": [
            {"type": "string", "pattern": r"^\d*\.?\d*$"},
            {"type": "null"},
        ]
    }
    for _ in range(20):
        value = generate_value(schema, fake)
        assert isinstance(value, str)
        assert re.fullmatch(r"^\d*\.?\d*$", value)
        assert value != ""


def test_generate_value_object_beyond_depth_stops_at_empty(fake: Faker) -> None:
    schema = {
        "type": "object",
        "properties": {
            "a": {
                "type": "object",
                "properties": {
                    "b": {
                        "type": "object",
                        "properties": {
                            "c": {
                                "type": "object",
                                "properties": {
                                    "d": {
                                        "type": "object",
                                        "properties": {"e": {"type": "string"}},
                                    }
                                },
                            }
                        },
                    }
                },
            }
        },
    }
    value = generate_value(schema, fake)
    assert value["a"]["b"]["c"]["d"] == {}


def test_generate_value_example_returns_a_detached_copy(fake: Faker) -> None:
    example = {"id": "from-spec", "name": "fixed"}
    value = generate_value({"type": "object", "example": example}, fake)

    value["name"] = "changed"

    assert example == {"id": "from-spec", "name": "fixed"}


def test_generate_value_enum_returns_a_detached_copy(fake: Faker) -> None:
    enum = [{"id": "a"}]
    value = generate_value({"type": "object", "enum": enum}, fake)

    value["id"] = "changed"

    assert enum == [{"id": "a"}]


def test_generate_value_example_with_yaml_date_returns_string(fake: Faker) -> None:
    value = generate_value({"type": "string", "example": datetime.date(2024, 1, 15)}, fake)

    assert value == "2024-01-15"


def test_generate_value_example_with_yaml_date_warns(fake: Faker) -> None:
    warnings: list[str] = []
    generate_value(
        {"type": "string", "example": datetime.date(2024, 1, 15)}, fake, warn=warnings.append
    )

    assert any("not JSON" in message for message in warnings)


def test_generate_value_example_with_nested_date_is_jsonable(fake: Faker) -> None:
    value = generate_value(
        {"type": "object", "example": {"when": datetime.date(2024, 1, 15)}}, fake
    )

    assert value == {"when": "2024-01-15"}
    assert json.dumps(value)


def test_generate_value_example_with_yaml_date_key_is_jsonable(fake: Faker) -> None:
    value = generate_value(
        {"type": "object", "example": {datetime.date(2024, 1, 15): "fixed"}}, fake
    )

    assert value == {"2024-01-15": "fixed"}
    assert json.dumps(value)


def test_generate_value_integer_with_inverted_bounds_warns(fake: Faker) -> None:
    warnings: list[str] = []
    for _ in range(20):
        value = generate_value(
            {"type": "integer", "minimum": 100, "maximum": 6}, fake, warn=warnings.append
        )
        assert 6 <= value <= 100

    assert any("inverted integer bounds" in message for message in warnings)


def test_generate_value_integer_with_only_minimum_keeps_minimum(fake: Faker) -> None:
    for _ in range(20):
        assert generate_value({"type": "integer", "minimum": 100_000}, fake) >= 100_000


def test_generate_value_integer_with_exclusive_bounds_stays_inside(fake: Faker) -> None:
    for _ in range(20):
        value = generate_value(
            {"type": "integer", "exclusiveMinimum": 10, "exclusiveMaximum": 20}, fake
        )
        assert 11 <= value <= 19


def test_generate_value_number_with_inverted_bounds_warns(fake: Faker) -> None:
    warnings: list[str] = []
    value = generate_value(
        {"type": "number", "minimum": 5, "maximum": 1}, fake, warn=warnings.append
    )

    assert 1 <= value <= 5
    assert any("inverted number bounds" in message for message in warnings)


def test_generate_value_integer_with_huge_minimum_is_exact(fake: Faker) -> None:
    huge = 2**53 + 1
    schema = {"type": "integer", "minimum": huge, "maximum": huge}

    for _ in range(20):
        assert generate_value(schema, fake) >= huge


def test_generate_object_returns_a_generated_object(fake: Faker) -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    }

    value = generate_object(schema, fake)

    assert set(value) == {"name", "age"}
    assert isinstance(value["name"], str)
    assert isinstance(value["age"], int)


def test_generate_object_wraps_a_scalar_schema_in_a_value_field(fake: Faker) -> None:
    value = generate_object({"type": "string"}, fake)

    assert list(value) == ["value"]
    assert isinstance(value["value"], str)


def test_generate_object_wraps_a_schema_without_a_type_in_a_value_field(fake: Faker) -> None:
    value = generate_object({}, fake)

    assert value == {"value": None}


def test_generate_object_accepts_a_read_only_mapping(fake: Faker) -> None:
    schema = MappingProxyType({"type": "object", "properties": {"name": {"type": "string"}}})

    value = generate_object(schema, fake)

    assert isinstance(value["name"], str)


def test_generate_value_accepts_a_read_only_object_mapping(fake: Faker) -> None:
    schema = MappingProxyType(
        {"type": "object", "properties": {"name": MappingProxyType({"type": "string"})}}
    )

    value = generate_value(schema, fake)

    assert isinstance(value["name"], str)


def test_generate_value_accepts_a_read_only_array_mapping(fake: Faker) -> None:
    schema = MappingProxyType(
        {"type": "array", "items": MappingProxyType({"type": "integer", "minimum": 1})}
    )

    values = generate_value(schema, fake)

    assert 1 <= len(values) <= 5
    assert all(isinstance(value, int) and value >= 1 for value in values)


def test_generate_value_public_call_takes_no_depth() -> None:
    assert list(inspect.signature(generate_value).parameters) == [
        "schema",
        "fake",
        "warn",
        "depth_limit",
        "array_max",
    ]


def test_generation_limits_are_published() -> None:
    assert DEPTH_LIMIT == 3
    assert ARRAY_MAX == 5


def test_generate_value_object_over_depth_limit_warns(fake: Faker) -> None:
    messages: list[str] = []
    deep = {
        "type": "object",
        "properties": {
            "a": {
                "type": "object",
                "properties": {"b": {"type": "object", "properties": {"c": {"type": "integer"}}}},
            }
        },
    }

    value = generate_value(deep, fake, messages.append, depth_limit=1)

    assert value == {"a": {"b": {}}}
    assert any("depth_limit=1" in message for message in messages)
    assert any("'c'" in message for message in messages)


def test_generate_value_any_of_names_the_branch_actually_taken(fake: Faker) -> None:
    messages: list[str] = []
    schema = {"anyOf": [{"type": "string"}, {"example": "chosen"}]}

    value = generate_value(schema, fake, messages.append)

    assert value == "chosen"
    assert "used branch 2 of 2 in oneOf/anyOf" in messages


def test_generate_value_any_of_without_example_names_the_first_branch(fake: Faker) -> None:
    messages: list[str] = []
    schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}

    generate_value(schema, fake, messages.append)

    assert "used branch 1 of 2 in oneOf/anyOf" in messages


def test_generate_value_format_wins_over_max_length_but_warns(fake: Faker) -> None:
    messages: list[str] = []
    schema = {"type": "string", "format": "email", "maxLength": 10}

    value = generate_value(schema, fake, messages.append)

    assert "@" in value
    assert any("format 'email' kept over maxLength 10" in message for message in messages)


def test_generate_value_format_that_fails_min_length_warns(fake: Faker) -> None:
    messages: list[str] = []
    schema = {"type": "string", "format": "date", "minLength": 64}

    generate_value(schema, fake, messages.append)

    assert any("format 'date' kept under minLength 64" in message for message in messages)


def test_generate_value_format_value_that_misses_the_pattern_warns(fake: Faker) -> None:
    messages: list[str] = []
    schema = {"type": "string", "format": "uuid", "pattern": r"^\d{4}$"}

    value = generate_value(schema, fake, messages.append)

    assert "-" in value
    assert any("format 'uuid' value does not match pattern" in message for message in messages)


def test_generate_value_unmatched_numeric_pattern_warns(fake: Faker) -> None:
    messages: list[str] = []
    schema = {"type": "string", "pattern": r"^(0|1\.25)$", "minimum": 50, "maximum": 100}

    value = generate_value(schema, fake, messages.append)

    assert any("no generated candidate matches" in message for message in messages)
    assert isinstance(value, str)


def test_generate_value_unsupported_pattern_warns(fake: Faker) -> None:
    messages: list[str] = []
    schema = {"type": "string", "pattern": r"^[A-Z]{3}$"}

    generate_value(schema, fake, messages.append)

    assert any("cannot honour pattern" in message for message in messages)


def test_generate_value_max_length_branch_under_min_length_warns(fake: Faker) -> None:
    messages: list[str] = []
    schema = {"type": "string", "minLength": 5, "maxLength": 3}

    generate_value(schema, fake, messages.append)

    assert any("under minLength 5" in message for message in messages)


def test_generate_value_numeric_string_is_checked_against_max_length(fake: Faker) -> None:
    messages: list[str] = []
    schema = {
        "type": "string",
        "pattern": r"^\d+(\.\d+)?$",
        "minimum": 0,
        "maximum": 9,
        "maxLength": 3,
    }

    generate_value(schema, fake, messages.append)

    assert any("over maxLength 3" in message for message in messages)


def test_generate_value_unanchored_pattern_uses_search_semantics(fake: Faker) -> None:
    messages: list[str] = []
    schema = {"type": "string", "format": "date", "pattern": r"\d{4}"}

    generate_value(schema, fake, messages.append)

    assert not any("does not match pattern" in message for message in messages)


def test_generate_value_non_string_pattern_warns(fake: Faker) -> None:
    messages: list[str] = []
    schema = {"type": "string", "pattern": 123}

    value = generate_value(schema, fake, messages.append)

    assert isinstance(value, str)
    assert any("cannot honour pattern" in message for message in messages)


def test_generate_value_openapi30_exclusive_minimum_stays_above_minimum(
    fake: Faker,
) -> None:
    schema = {"type": "integer", "minimum": 10, "exclusiveMinimum": True, "maximum": 12}
    for _ in range(20):
        assert generate_value(schema, fake) > 10


def test_generate_value_openapi30_false_flag_keeps_inclusive_minimum(fake: Faker) -> None:
    schema = {"type": "integer", "minimum": 10, "exclusiveMinimum": False, "maximum": 10}
    for _ in range(50):
        assert generate_value(schema, fake) >= 10


def test_generate_value_json_schema31_standalone_exclusive_is_strict(fake: Faker) -> None:
    schema = {"type": "number", "exclusiveMinimum": 10.5}
    for _ in range(20):
        assert generate_value(schema, fake) > 10.5


def test_generate_value_json_schema31_exclusive_respects_declared_minimum(
    fake: Faker,
) -> None:
    schema = {"type": "integer", "minimum": 10, "exclusiveMinimum": 5}
    for _ in range(20):
        assert generate_value(schema, fake) >= 10


def test_generate_value_exclusive_bounds_that_empty_the_range_warns(fake: Faker) -> None:
    messages: list[str] = []
    schema = {"type": "integer", "minimum": 10, "exclusiveMinimum": True, "maximum": 10}

    for _ in range(5):
        generate_value(schema, fake, messages.append)

    assert any("inverted integer bounds" in message for message in messages)


def test_generate_value_exclusive_bound_of_wrong_type_raises(fake: Faker) -> None:
    schema = {"type": "integer", "exclusiveMinimum": "yes"}

    with pytest.raises(ValueError, match="exclusive bound must be a boolean or a number"):
        generate_value(schema, fake)


def test_inclusive_int_honours_dialects_and_integer_steps() -> None:
    assert _inclusive_int(10, True, lower=True) == 11
    assert _inclusive_int(10, False, lower=False) == 10
    assert _inclusive_int(10, 5, lower=True) == 10
    assert _inclusive_int(10, 15, lower=True) == 16
    assert _inclusive_int(10, 10.5, lower=True) == 11
    assert _inclusive_int(None, True, lower=True) is None
    assert _inclusive_int(10, None, lower=True) == 10


def test_inclusive_float_exclusive_is_strict_at_the_bound() -> None:
    assert _inclusive_float(None, 10.5, lower=True) == math.nextafter(10.5, math.inf)
    assert _inclusive_float(None, 10.5, lower=False) == math.nextafter(10.5, -math.inf)
    assert _inclusive_float(10.0, True, lower=True) == math.nextafter(10.0, math.inf)


def test_exclusive_shift_rejects_a_non_numeric_value() -> None:
    with pytest.raises(ValueError, match="exclusive bound must be a boolean or a number"):
        _exclusive_shift(["yes"], 10, lower=True, integer=True)


def test_generate_value_openapi30_exclusive_maximum_stays_below_maximum(fake: Faker) -> None:
    schema = {"type": "integer", "minimum": 8, "exclusiveMaximum": True, "maximum": 10}

    for _ in range(20):
        assert 8 <= generate_value(schema, fake) <= 9


def test_generate_value_json_schema31_exclusive_maximum_is_strict(fake: Faker) -> None:
    schema = {"type": "number", "exclusiveMaximum": 10.5}

    for _ in range(20):
        assert generate_value(schema, fake) < 10.5


def test_generate_value_exclusive_maximum_narrows_declared_number_maximum(fake: Faker) -> None:
    schema = {"type": "number", "maximum": 10, "exclusiveMaximum": 5}

    for _ in range(20):
        assert generate_value(schema, fake) < 5
