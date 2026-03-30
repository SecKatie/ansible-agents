"""Convert JSON Schema dicts to dynamic Pydantic BaseModel classes at runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, create_model

# JSON Schema type -> Python type mapping
_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}

_UNSUPPORTED_KEYWORDS = {"oneOf", "anyOf", "allOf", "$ref"}


def build_model(
    schema: dict[str, Any], model_name: str = "DynamicModel"
) -> type[BaseModel]:
    """Build a Pydantic BaseModel class from a JSON Schema dict.

    Args:
        schema: A JSON Schema dict (as parsed from YAML).
        model_name: Name for the generated model class.

    Returns:
        A dynamically-created Pydantic BaseModel subclass.

    Raises:
        ValueError: If the schema uses unsupported features.
    """
    schema_type = schema.get("type", "object")
    if schema_type != "object":
        raise ValueError(
            f"Top-level schema must have type 'object', got '{schema_type}'"
        )

    return _build_object_model(schema, model_name)


def _check_unsupported(schema: dict[str, Any]) -> None:
    """Raise ValueError if schema uses unsupported keywords."""
    for key in _UNSUPPORTED_KEYWORDS:
        if key in schema:
            raise ValueError(
                f"Unsupported JSON Schema feature: '{key}'. "
                f"The schema builder supports objects, arrays, basic types, "
                f"enums, patterns, and numeric constraints."
            )


def _build_object_model(schema: dict[str, Any], model_name: str) -> type[BaseModel]:
    """Build a Pydantic model from an object-type JSON Schema."""
    _check_unsupported(schema)
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))
    field_definitions: dict[str, Any] = {}

    for prop_name, prop_schema in properties.items():
        python_type = _resolve_type(prop_schema, f"{model_name}_{prop_name}")
        field_kwargs = _build_field_kwargs(prop_schema)
        is_required = prop_name in required_fields

        if is_required:
            field_definitions[prop_name] = (python_type, Field(**field_kwargs))
        else:
            field_definitions[prop_name] = (
                Optional[python_type],
                Field(default=None, **field_kwargs),
            )

    return create_model(model_name, **field_definitions)


def _resolve_type(prop_schema: dict[str, Any], nested_name: str) -> type:
    """Resolve a JSON Schema property to a Python type."""
    _check_unsupported(prop_schema)
    prop_type = prop_schema.get("type", "string")

    if prop_type == "object":
        return _build_object_model(prop_schema, nested_name)

    if prop_type == "array":
        items_schema = prop_schema.get("items", {"type": "string"})
        item_type = _resolve_type(items_schema, f"{nested_name}_item")
        return list[item_type]  # type: ignore[valid-type]

    base_type = _TYPE_MAP.get(prop_type)
    if base_type is None:
        raise ValueError(
            f"Unsupported JSON Schema type: '{prop_type}'. "
            f"Supported types: {', '.join(sorted(_TYPE_MAP.keys()))}, object, array."
        )

    return base_type


def _build_field_kwargs(prop_schema: dict[str, Any]) -> dict[str, Any]:
    """Build Pydantic Field keyword arguments from JSON Schema constraints."""
    kwargs: dict[str, Any] = {}

    if "description" in prop_schema:
        kwargs["description"] = prop_schema["description"]

    if "enum" in prop_schema:
        kwargs["json_schema_extra"] = {"enum": prop_schema["enum"]}

    if "pattern" in prop_schema:
        kwargs["pattern"] = prop_schema["pattern"]

    if "minimum" in prop_schema:
        kwargs["ge"] = prop_schema["minimum"]

    if "maximum" in prop_schema:
        kwargs["le"] = prop_schema["maximum"]

    if "minLength" in prop_schema:
        kwargs["min_length"] = prop_schema["minLength"]

    if "maxLength" in prop_schema:
        kwargs["max_length"] = prop_schema["maxLength"]

    return kwargs


def resolve_schema(
    output_schema: str | dict[str, Any], basedir: str = "."
) -> dict[str, Any]:
    """Resolve output_schema from an inline dict or a file path.

    Args:
        output_schema: An inline JSON Schema dict, or a file path (str)
            pointing to a .json or .yaml/.yml schema file.
        basedir: Base directory for resolving relative paths.

    Returns:
        A JSON Schema dict.

    Raises:
        ValueError: If the file format is unsupported or content is invalid.
        FileNotFoundError: If the schema file does not exist.
    """
    if isinstance(output_schema, dict):
        return output_schema

    if isinstance(output_schema, str):
        schema_path = Path(output_schema)
        if not schema_path.is_absolute():
            schema_path = Path(basedir) / schema_path

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        suffix = schema_path.suffix.lower()
        text = schema_path.read_text(encoding="utf-8")

        if suffix == ".json":
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in schema file {schema_path}: {e}")
        elif suffix in (".yaml", ".yml"):
            try:
                return yaml.safe_load(text)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in schema file {schema_path}: {e}")
        else:
            raise ValueError(
                f"Unsupported schema file format '{suffix}'. "
                f"Supported formats: .json, .yaml, .yml"
            )

    raise ValueError(
        f"output_schema must be a dict or a file path string, "
        f"got {type(output_schema).__name__}"
    )
