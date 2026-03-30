"""Unit tests for schema_builder module."""

import pytest
from pydantic import ValidationError

from ansible_collections.seckatie.agents.plugins.module_utils.schema_builder import (
    build_model,
)


class TestBasicTypes:
    def test_string_field(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        Model = build_model(schema)
        obj = Model(name="Alice")
        assert obj.name == "Alice"

    def test_integer_field(self):
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer"}},
            "required": ["age"],
        }
        Model = build_model(schema)
        obj = Model(age=30)
        assert obj.age == 30

    def test_number_field(self):
        schema = {
            "type": "object",
            "properties": {"score": {"type": "number"}},
            "required": ["score"],
        }
        Model = build_model(schema)
        obj = Model(score=3.14)
        assert obj.score == 3.14

    def test_boolean_field(self):
        schema = {
            "type": "object",
            "properties": {"active": {"type": "boolean"}},
            "required": ["active"],
        }
        Model = build_model(schema)
        obj = Model(active=True)
        assert obj.active is True

    def test_multiple_fields(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "score": {"type": "number"},
                "active": {"type": "boolean"},
            },
            "required": ["name", "age"],
        }
        Model = build_model(schema)
        obj = Model(name="Alice", age=30, score=9.5)
        assert obj.name == "Alice"
        assert obj.age == 30
        assert obj.score == 9.5
        assert obj.active is None


class TestNestedObjects:
    def test_nested_object(self):
        schema = {
            "type": "object",
            "properties": {
                "address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        "city": {"type": "string"},
                    },
                    "required": ["street", "city"],
                }
            },
            "required": ["address"],
        }
        Model = build_model(schema)
        obj = Model(address={"street": "123 Main St", "city": "Springfield"})
        assert obj.address.street == "123 Main St"
        assert obj.address.city == "Springfield"

    def test_deeply_nested_object(self):
        schema = {
            "type": "object",
            "properties": {
                "level1": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "string"},
                            },
                            "required": ["value"],
                        }
                    },
                    "required": ["level2"],
                }
            },
            "required": ["level1"],
        }
        Model = build_model(schema)
        obj = Model(level1={"level2": {"value": "deep"}})
        assert obj.level1.level2.value == "deep"


class TestArrays:
    def test_array_of_strings(self):
        schema = {
            "type": "object",
            "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
            "required": ["tags"],
        }
        Model = build_model(schema)
        obj = Model(tags=["a", "b", "c"])
        assert obj.tags == ["a", "b", "c"]

    def test_array_of_objects(self):
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "name": {"type": "string"},
                        },
                        "required": ["id", "name"],
                    },
                }
            },
            "required": ["items"],
        }
        Model = build_model(schema)
        obj = Model(items=[{"id": 1, "name": "first"}, {"id": 2, "name": "second"}])
        assert len(obj.items) == 2
        assert obj.items[0].id == 1
        assert obj.items[1].name == "second"

    def test_array_of_integers(self):
        schema = {
            "type": "object",
            "properties": {"numbers": {"type": "array", "items": {"type": "integer"}}},
            "required": ["numbers"],
        }
        Model = build_model(schema)
        obj = Model(numbers=[1, 2, 3])
        assert obj.numbers == [1, 2, 3]


class TestConstraints:
    def test_enum_constraint(self):
        schema = {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                }
            },
            "required": ["severity"],
        }
        Model = build_model(schema)
        obj = Model(severity="low")
        assert obj.severity == "low"

    def test_pattern_constraint(self):
        schema = {
            "type": "object",
            "properties": {
                "code": {"type": "string", "pattern": r"^[A-Z]{3}-\d{3}$"}
            },
            "required": ["code"],
        }
        Model = build_model(schema)
        obj = Model(code="ABC-123")
        assert obj.code == "ABC-123"

        with pytest.raises(ValidationError):
            Model(code="abc-123")

    def test_minimum_maximum(self):
        schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "minimum": 1, "maximum": 100}
            },
            "required": ["count"],
        }
        Model = build_model(schema)
        obj = Model(count=50)
        assert obj.count == 50

        with pytest.raises(ValidationError):
            Model(count=0)

        with pytest.raises(ValidationError):
            Model(count=101)

    def test_min_max_length(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 2, "maxLength": 10}
            },
            "required": ["name"],
        }
        Model = build_model(schema)
        obj = Model(name="Alice")
        assert obj.name == "Alice"

        with pytest.raises(ValidationError):
            Model(name="A")

        with pytest.raises(ValidationError):
            Model(name="A" * 11)


class TestRequiredOptional:
    def test_required_fields(self):
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "string"},
                "c": {"type": "string"},
            },
            "required": ["a", "c"],
        }
        Model = build_model(schema)

        # b is optional
        obj = Model(a="x", c="z")
        assert obj.a == "x"
        assert obj.b is None
        assert obj.c == "z"

        # Missing required field
        with pytest.raises(ValidationError):
            Model(b="y", c="z")

    def test_all_optional(self):
        schema = {
            "type": "object",
            "properties": {
                "x": {"type": "string"},
                "y": {"type": "integer"},
            },
        }
        Model = build_model(schema)
        obj = Model()
        assert obj.x is None
        assert obj.y is None


class TestDescriptions:
    def test_field_description_preserved(self):
        schema = {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "description": "The severity level of the issue",
                }
            },
            "required": ["severity"],
        }
        Model = build_model(schema)
        field_info = Model.model_fields["severity"]
        assert field_info.description == "The severity level of the issue"


class TestUnsupportedFeatures:
    def test_oneof_raises(self):
        schema = {
            "type": "object",
            "properties": {
                "value": {
                    "oneOf": [{"type": "string"}, {"type": "integer"}]
                }
            },
        }
        with pytest.raises(ValueError, match="oneOf"):
            build_model(schema)

    def test_anyof_raises(self):
        schema = {
            "type": "object",
            "properties": {
                "value": {
                    "anyOf": [{"type": "string"}, {"type": "integer"}]
                }
            },
        }
        with pytest.raises(ValueError, match="anyOf"):
            build_model(schema)

    def test_ref_raises(self):
        schema = {
            "type": "object",
            "properties": {
                "value": {"$ref": "#/definitions/Foo"}
            },
        }
        with pytest.raises(ValueError, match="\\$ref"):
            build_model(schema)

    def test_unsupported_type_raises(self):
        schema = {
            "type": "object",
            "properties": {"value": {"type": "null"}},
            "required": ["value"],
        }
        with pytest.raises(ValueError, match="Unsupported JSON Schema type"):
            build_model(schema)

    def test_non_object_top_level_raises(self):
        schema = {"type": "string"}
        with pytest.raises(ValueError, match="Top-level schema must have type 'object'"):
            build_model(schema)


class TestCustomModelName:
    def test_custom_name(self):
        schema = {
            "type": "object",
            "properties": {"x": {"type": "string"}},
        }
        Model = build_model(schema, model_name="MyCustomModel")
        assert Model.__name__ == "MyCustomModel"
