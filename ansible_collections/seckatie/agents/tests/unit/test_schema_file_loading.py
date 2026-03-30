"""Unit tests for resolve_schema file loading in schema_builder."""

import json
from pathlib import Path

import pytest
import yaml

from ansible_collections.seckatie.agents.plugins.module_utils.schema_builder import (
    resolve_schema,
)


class TestDictPassthrough:
    """Inline dict schemas should pass through unchanged."""

    def test_dict_schema_returned_as_is(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        result = resolve_schema(schema)
        assert result is schema


class TestFileNotFound:
    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError, match="Schema file not found"):
            resolve_schema("nonexistent.json")

    def test_missing_relative_path_raises(self):
        with pytest.raises(FileNotFoundError, match="Schema file not found"):
            resolve_schema("schemas/missing.json", basedir="/tmp/playbooks")


class TestUnsupportedFormat:
    def test_unsupported_extension_raises(self, tmp_path: Path):
        path = tmp_path / "test_schema.txt"
        path.write_text("type: object")
        with pytest.raises(ValueError, match="Unsupported schema file format"):
            resolve_schema(str(path))


class TestJsonFile:
    def test_load_json_schema(self, tmp_path: Path):
        schema = {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["high", "low"]},
                "message": {"type": "string"},
            },
            "required": ["severity"],
        }
        schema_file = tmp_path / "test.json"
        schema_file.write_text(json.dumps(schema))

        result = resolve_schema(str(schema_file))
        assert result == schema

    def test_invalid_json_raises(self, tmp_path: Path):
        schema_file = tmp_path / "bad.json"
        schema_file.write_text("{not valid json")
        with pytest.raises(ValueError, match="Invalid JSON"):
            resolve_schema(str(schema_file))


class TestYamlFile:
    def test_load_yaml_schema(self, tmp_path: Path):
        schema = {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["high", "low"]},
                "message": {"type": "string"},
            },
            "required": ["severity"],
        }
        schema_file = tmp_path / "test.yaml"
        schema_file.write_text(yaml.dump(schema))

        result = resolve_schema(str(schema_file))
        assert result == schema

    def test_load_yml_extension(self, tmp_path: Path):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        schema_file = tmp_path / "test.yml"
        schema_file.write_text(yaml.dump(schema))

        result = resolve_schema(str(schema_file))
        assert result == schema

    def test_invalid_yaml_raises(self, tmp_path: Path):
        schema_file = tmp_path / "bad.yaml"
        schema_file.write_text(":\n  - :\n    - [invalid")
        with pytest.raises(ValueError, match="Invalid YAML"):
            resolve_schema(str(schema_file))


class TestRelativePathResolution:
    def test_relative_path_resolved_from_basedir(self, tmp_path: Path):
        basedir = tmp_path / "playbooks"
        basedir.mkdir()
        schema_file = basedir / "schemas" / "test.json"
        schema_file.parent.mkdir()
        schema_file.write_text(
            json.dumps(
                {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                }
            )
        )

        result = resolve_schema("schemas/test.json", basedir=str(basedir))
        assert "properties" in result

    def test_absolute_path_ignores_basedir(self, tmp_path: Path):
        schema_file = tmp_path / "absolute.json"
        schema_file.write_text(
            json.dumps(
                {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                }
            )
        )

        result = resolve_schema(str(schema_file), basedir="/nonexistent")
        assert "properties" in result


class TestInvalidType:
    def test_non_string_non_dict_raises(self):
        with pytest.raises(ValueError, match="must be a dict or a file path string"):
            resolve_schema(42)
