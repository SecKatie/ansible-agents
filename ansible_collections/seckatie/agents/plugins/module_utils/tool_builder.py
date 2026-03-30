"""Convert YAML tool definitions to Pydantic AI Tool objects."""

from __future__ import annotations

import re
import shlex
from typing import Any, Callable

from pydantic_ai import Tool


class ChangeTracker:
    """Track whether any tool call resulted in a change."""

    def __init__(self) -> None:
        self.changed = False

    def record(self, result: dict[str, Any]) -> None:
        """Record a module result, updating changed state."""
        if result.get("changed", False):
            self.changed = True


# Regex matching {{ placeholder }} with optional whitespace
_TEMPLATE_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def build_tools(
    tool_defs: list[dict[str, Any]],
    execute_module_fn: Callable,
    execute_on_controller_fn: Callable | None = None,
) -> tuple[list[Tool], ChangeTracker]:
    """Build Pydantic AI Tool objects from YAML tool definitions.

    Args:
        tool_defs: List of tool definition dicts from the module's tools parameter.
        execute_module_fn: Callable that executes an Ansible module on the target host.
            Signature: execute_module_fn(module_name: str, module_args: dict) -> dict
        execute_on_controller_fn: Optional callable that executes an Ansible module on the controller.
            If not provided and a tool has run_on=controller, execute_module_fn is used as fallback.

    Returns:
        Tuple of (list of Tool objects, ChangeTracker instance).
    """
    tracker = ChangeTracker()
    tools: list[Tool] = []

    for tool_def in tool_defs:
        name = tool_def["name"]
        description = tool_def.get("description", "")
        module_name = tool_def["module"]
        fixed_args = tool_def.get("fixed_args", {}) or {}
        agent_args = tool_def.get("agent_args", {}) or {}
        run_on = tool_def.get("run_on", "target")

        # Select the appropriate execution function
        if run_on == "controller" and execute_on_controller_fn:
            exec_fn = execute_on_controller_fn
        else:
            exec_fn = execute_module_fn

        tool = _build_single_tool(
            name=name,
            description=description,
            module_name=module_name,
            fixed_args=fixed_args,
            agent_args_schema=agent_args,
            execute_module_fn=exec_fn,
            tracker=tracker,
        )
        tools.append(tool)

    return tools, tracker


def _build_single_tool(
    name: str,
    description: str,
    module_name: str,
    fixed_args: dict[str, Any],
    agent_args_schema: dict[str, Any],
    execute_module_fn: Callable,
    tracker: ChangeTracker,
) -> Tool:
    """Build a single Pydantic AI Tool."""

    json_schema = _agent_args_to_json_schema(agent_args_schema)

    def _execute(**kwargs: Any) -> dict[str, Any]:
        interpolated_fixed = _interpolate_templates(fixed_args, kwargs)
        merged_args = {**kwargs, **interpolated_fixed}
        result = execute_module_fn(module_name, merged_args)
        tracker.record(result)
        return result

    if agent_args_schema:
        return Tool.from_schema(
            function=_execute,
            name=name,
            description=description,
            json_schema=json_schema,
        )
    else:

        def _execute_no_args() -> dict[str, Any]:
            return _execute()

        return Tool(
            _execute_no_args,
            name=name,
            description=description,
        )


def _agent_args_to_json_schema(agent_args: dict[str, Any]) -> dict[str, Any]:
    """Convert agent_args property definitions to a proper JSON Schema object.

    agent_args is a dict of property_name -> property_schema, e.g.:
        {"path": {"type": "string", "description": "File path"}, "lines": {"type": "integer"}}

    Returns a full JSON Schema object with properties, type, and required.
    """
    if not agent_args:
        return {"type": "object", "properties": {}}

    # All agent_args are required by default (the LLM must provide them)
    return {
        "type": "object",
        "properties": agent_args,
        "required": list(agent_args.keys()),
    }


def _interpolate_templates(
    fixed_args: dict[str, Any], agent_values: dict[str, Any]
) -> dict[str, Any]:
    """Interpolate {{ placeholder }} patterns in fixed_args values.

    Each interpolated value is wrapped with shlex.quote() for shell safety.
    """
    result = {}
    for key, value in fixed_args.items():
        if isinstance(value, str):
            result[key] = _TEMPLATE_RE.sub(
                lambda m: shlex.quote(str(agent_values.get(m.group(1), ""))),
                value,
            )
        else:
            result[key] = value
    return result
