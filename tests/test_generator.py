import re

import pytest
from faker import Faker

from quackend.generator import generate_value


@pytest.fixture()
def fake():
    return Faker()


def test_generate_value_example_returns_exact_value(fake):
    assert generate_value({"type": "string", "example": "fixed"}, fake) == "fixed"


def test_generate_value_enum_always_in_choices(fake):
    schema = {"type": "string", "enum": ["admin", "user"]}
    for _ in range(20):
        assert generate_value(schema, fake) in ["admin", "user"]


def test_generate_value_email_string_contains_at(fake):
    value = generate_value({"type": "string", "format": "email"}, fake)
    assert "email" in value or "@" in value


def test_generate_value_integer_within_bounds(fake):
    for _ in range(20):
        value = generate_value({"type": "integer", "minimum": 10, "maximum": 20}, fake)
        assert 10 <= value <= 20


def test_generate_value_number_within_bounds(fake):
    for _ in range(20):
        value = generate_value({"type": "number", "minimum": 1.5, "maximum": 2.5}, fake)
        assert 1.5 <= value <= 2.5


def test_generate_value_boolean_in_expected_values(fake):
    assert generate_value({"type": "boolean"}, fake) in (True, False)


def test_generate_value_array_returns_1_to_5_integers(fake):
    value = generate_value({"type": "array", "items": {"type": "integer"}}, fake)
    assert 1 <= len(value) <= 5
    assert all(isinstance(v, int) for v in value)


def test_generate_value_object_returns_string_property(fake):
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    value = generate_value(schema, fake)
    assert isinstance(value, dict)
    assert isinstance(value["name"], str)


def test_generate_value_missing_type_returns_none_with_warning(fake):
    warnings = []
    value = generate_value({}, fake, warn=warnings.append)
    assert value is None
    assert any("missing type" in w for w in warnings)


def test_generate_value_unsupported_type_returns_none_with_warning(fake):
    warnings = []
    value = generate_value({"type": "unknown"}, fake, warn=warnings.append)
    assert value is None
    assert any("unsupported type" in w for w in warnings)


def test_generate_value_one_of_uses_first_branch_with_warning(fake):
    warnings = []
    schema = {"oneOf": [{"type": "integer"}, {"type": "string"}]}
    value = generate_value(schema, fake, warn=warnings.append)
    assert any("oneOf" in w or "anyOf" in w for w in warnings)
    assert isinstance(value, int)


def test_generate_value_any_of_uses_first_branch_with_warning(fake):
    warnings = []
    schema = {"anyOf": [{"type": "integer"}, {"type": "string"}]}
    value = generate_value(schema, fake, warn=warnings.append)
    assert any("oneOf" in w or "anyOf" in w for w in warnings)
    assert isinstance(value, int)


def test_generate_value_all_of_merges_branches(fake):
    schema = {
        "allOf": [
            {"type": "object", "properties": {"a": {"type": "string"}}},
            {"properties": {"b": {"type": "integer"}}},
        ]
    }
    value = generate_value(schema, fake)
    assert set(value) == {"a", "b"}


def test_generate_value_empty_one_of_returns_none_with_warning(fake):
    warnings = []
    schema = {"oneOf": []}
    value = generate_value(schema, fake, warn=warnings.append)
    assert value is None
    assert any("oneOf" in w for w in warnings)


def test_generate_value_numeric_pattern_string_is_numeric(fake):
    schema = {"type": "string", "pattern": r"^\d*\.?\d*$"}
    for _ in range(20):
        value = generate_value(schema, fake)
        assert re.fullmatch(r"^\d*\.?\d*$", value)
        assert value != ""


def test_generate_value_any_of_numeric_string_prefers_real_value(fake):
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


def test_generate_value_object_beyond_depth_stops_at_empty(fake):
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
