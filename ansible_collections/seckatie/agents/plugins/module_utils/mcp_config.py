"""MCP server configuration parsing and tool filtering utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolConfig:
    """Configuration for a single MCP tool."""

    changed: bool = True


def parse_server_config(server_dict: dict[str, Any]) -> Any:
    """Map a server config dict to the appropriate Pydantic AI MCPServer instance.

    Args:
        server_dict: Server configuration dict with 'type' and transport-specific params.

    Returns:
        An MCPServerStdio, MCPServerSSE, or MCPServerStreamableHTTP instance.

    Raises:
        ValueError: If the transport type is unknown or required fields are missing.
    """
    from pydantic_ai.mcp import MCPServerStdio, MCPServerSSE, MCPServerStreamableHTTP

    transport_type = server_dict.get("type")
    if not transport_type:
        raise ValueError("Server config must include a 'type' field")

    # Common optional params
    common_kwargs: dict[str, Any] = {}
    if "tool_prefix" in server_dict:
        common_kwargs["tool_prefix"] = server_dict["tool_prefix"]
    if "timeout" in server_dict:
        common_kwargs["timeout"] = server_dict["timeout"]
    if "read_timeout" in server_dict:
        common_kwargs["read_timeout"] = server_dict["read_timeout"]

    if transport_type == "stdio":
        command = server_dict.get("command")
        if not command:
            raise ValueError("stdio transport requires a 'command' parameter")
        kwargs: dict[str, Any] = {**common_kwargs}
        if "args" in server_dict:
            kwargs["args"] = server_dict["args"]
        else:
            kwargs["args"] = []
        if "env" in server_dict:
            kwargs["env"] = server_dict["env"]
        return MCPServerStdio(command, **kwargs)

    elif transport_type == "sse":
        url = server_dict.get("url")
        if not url:
            raise ValueError("sse transport requires a 'url' parameter")
        kwargs = {**common_kwargs}
        if "headers" in server_dict:
            kwargs["headers"] = server_dict["headers"]
        return MCPServerSSE(url, **kwargs)

    elif transport_type == "streamable_http":
        url = server_dict.get("url")
        if not url:
            raise ValueError("streamable_http transport requires a 'url' parameter")
        kwargs = {**common_kwargs}
        if "headers" in server_dict:
            kwargs["headers"] = server_dict["headers"]
        return MCPServerStreamableHTTP(url, **kwargs)

    else:
        raise ValueError(
            f"Unknown MCP transport type: '{transport_type}'. "
            f"Valid types are: stdio, sse, streamable_http"
        )


def parse_tools_filter(
    tools_list: list[str | dict[str, Any]] | None,
) -> dict[str, ToolConfig] | None:
    """Normalize the polymorphic tools field into a uniform dict.

    Args:
        tools_list: List of tool names (strings) or objects with 'name' and optional 'changed'.
            None or empty list means no filtering (all tools allowed).

    Returns:
        Dict mapping tool names to ToolConfig, or None if no filter is set.
    """
    if not tools_list:
        return None

    result: dict[str, ToolConfig] = {}
    for entry in tools_list:
        if isinstance(entry, str):
            result[entry] = ToolConfig(changed=True)
        elif isinstance(entry, dict):
            name = entry.get("name")
            if not name:
                raise ValueError("Tool filter object must include a 'name' field")
            changed = entry.get("changed", True)
            result[name] = ToolConfig(changed=changed)
        else:
            raise ValueError(
                f"Tool filter entries must be strings or dicts, got: {type(entry)}"
            )

    return result


@dataclass
class FilteredMCPToolset:
    """Wrapper toolset that filters MCP server tools by allowed names.

    Wraps a Pydantic AI MCPServer and its WrapperToolset to filter tools
    returned by get_tools() to only include allowed tool names.
    """

    server: Any
    allowed_tools: dict[str, ToolConfig] | None = None

    def build_toolset(self) -> Any:
        """Build the appropriate toolset, applying filtering if needed.

        Returns:
            The MCPServer directly if no filter, or a FilteredToolset wrapping it.

        Raises:
            ValueError: If filtered tool names don't exist on the server
                (validated at runtime when get_tools is called).
        """
        if not self.allowed_tools:
            return self.server

        allowed_names = set(self.allowed_tools.keys())

        from pydantic_ai.toolsets.filtered import FilteredToolset

        def filter_func(ctx: Any, tool_def: Any) -> bool:
            return tool_def.name in allowed_names

        return FilteredToolset(
            wrapped=self.server,
            filter_func=filter_func,
        )


@dataclass
class MCPToolsetResult:
    """Result of building an MCP toolset, including the toolset and tool configs."""

    toolset: Any
    tools_filter: dict[str, ToolConfig] | None = None


def build_mcp_toolset(server_dict: dict[str, Any]) -> MCPToolsetResult:
    """Build an MCP toolset from a server config dict.

    Combines parse_server_config, parse_tools_filter, and FilteredMCPToolset.

    Args:
        server_dict: Server configuration dict.

    Returns:
        MCPToolsetResult with the toolset and tools filter for change tracking.
    """
    server = parse_server_config(server_dict)
    tools_filter = parse_tools_filter(server_dict.get("tools"))
    filtered = FilteredMCPToolset(server=server, allowed_tools=tools_filter)
    toolset = filtered.build_toolset()
    return MCPToolsetResult(toolset=toolset, tools_filter=tools_filter)
