"""Unit tests for mcp_config module."""

import pytest

from ansible_collections.seckatie.agents.plugins.module_utils.mcp_config import (
    FilteredMCPToolset,
    ToolConfig,
    build_mcp_toolset,
    parse_server_config,
    parse_tools_filter,
)


class TestParseServerConfig:
    """Tests for parse_server_config covering all three transport types."""

    def test_stdio_transport(self):
        config = {
            "type": "stdio",
            "command": "python",
            "args": ["-m", "my_mcp_server"],
            "env": {"API_KEY": "test"},
        }
        server = parse_server_config(config)
        from pydantic_ai.mcp import MCPServerStdio

        assert isinstance(server, MCPServerStdio)

    def test_stdio_requires_command(self):
        config = {"type": "stdio"}
        with pytest.raises(ValueError, match="'command' parameter"):
            parse_server_config(config)

    def test_stdio_default_args(self):
        config = {"type": "stdio", "command": "my-server"}
        server = parse_server_config(config)
        from pydantic_ai.mcp import MCPServerStdio

        assert isinstance(server, MCPServerStdio)

    def test_sse_transport(self):
        config = {
            "type": "sse",
            "url": "http://localhost:8080/sse",
            "headers": {"Authorization": "Bearer token"},
        }
        server = parse_server_config(config)
        from pydantic_ai.mcp import MCPServerSSE

        assert isinstance(server, MCPServerSSE)

    def test_sse_requires_url(self):
        config = {"type": "sse"}
        with pytest.raises(ValueError, match="'url' parameter"):
            parse_server_config(config)

    def test_streamable_http_transport(self):
        config = {
            "type": "streamable_http",
            "url": "http://localhost:8080/mcp",
            "headers": {"X-API-Key": "key"},
        }
        server = parse_server_config(config)
        from pydantic_ai.mcp import MCPServerStreamableHTTP

        assert isinstance(server, MCPServerStreamableHTTP)

    def test_streamable_http_requires_url(self):
        config = {"type": "streamable_http"}
        with pytest.raises(ValueError, match="'url' parameter"):
            parse_server_config(config)

    def test_unknown_type_error(self):
        config = {"type": "websocket", "url": "ws://localhost"}
        with pytest.raises(ValueError, match="Unknown MCP transport type: 'websocket'"):
            parse_server_config(config)

    def test_missing_type_error(self):
        config = {"url": "http://localhost"}
        with pytest.raises(ValueError, match="'type' field"):
            parse_server_config(config)

    def test_common_options_passed(self):
        config = {
            "type": "stdio",
            "command": "server",
            "tool_prefix": "myserver",
            "timeout": 10,
            "read_timeout": 600,
        }
        server = parse_server_config(config)
        assert server.tool_prefix == "myserver"
        assert server.timeout == 10
        assert server.read_timeout == 600


class TestParseToolsFilter:
    """Tests for parse_tools_filter covering all input forms."""

    def test_string_only(self):
        result = parse_tools_filter(["search_web", "scrape_page"])
        assert result is not None
        assert len(result) == 2
        assert result["search_web"].changed is True
        assert result["scrape_page"].changed is True

    def test_object_only(self):
        result = parse_tools_filter(
            [
                {"name": "search_web", "changed": False},
                {"name": "create_issue"},
            ]
        )
        assert result is not None
        assert result["search_web"].changed is False
        assert result["create_issue"].changed is True

    def test_mixed_string_and_object(self):
        result = parse_tools_filter(
            [
                "search_web",
                {"name": "get_repo", "changed": False},
            ]
        )
        assert result is not None
        assert result["search_web"].changed is True
        assert result["get_repo"].changed is False

    def test_empty_list_returns_none(self):
        result = parse_tools_filter([])
        assert result is None

    def test_none_returns_none(self):
        result = parse_tools_filter(None)
        assert result is None

    def test_object_missing_name_raises(self):
        with pytest.raises(ValueError, match="'name' field"):
            parse_tools_filter([{"changed": False}])


class TestFilteredMCPToolset:
    """Tests for FilteredMCPToolset."""

    def test_no_filter_returns_server_directly(self):
        """When no filter is set, build_toolset returns the server as-is."""
        mock_server = object()
        filtered = FilteredMCPToolset(server=mock_server, allowed_tools=None)
        result = filtered.build_toolset()
        assert result is mock_server

    def test_with_filter_returns_filtered_toolset(self):
        """When filter is set, build_toolset returns a FilteredToolset."""
        from pydantic_ai.mcp import MCPServerStdio

        server = MCPServerStdio("echo", args=["hello"])
        tools_filter = {"search": ToolConfig(changed=True)}
        filtered = FilteredMCPToolset(server=server, allowed_tools=tools_filter)
        result = filtered.build_toolset()

        from pydantic_ai.toolsets.filtered import FilteredToolset

        assert isinstance(result, FilteredToolset)

    def test_empty_filter_returns_server(self):
        """Empty dict filter returns server directly."""
        mock_server = object()
        filtered = FilteredMCPToolset(server=mock_server, allowed_tools={})
        result = filtered.build_toolset()
        assert result is mock_server


class TestBuildMCPToolset:
    """Tests for the build_mcp_toolset convenience function."""

    def test_basic_build(self):
        config = {"type": "stdio", "command": "my-server"}
        result = build_mcp_toolset(config)
        assert result.toolset is not None
        assert result.tools_filter is None

    def test_build_with_tools_filter(self):
        config = {
            "type": "stdio",
            "command": "my-server",
            "tools": ["search", {"name": "write", "changed": False}],
        }
        result = build_mcp_toolset(config)
        assert result.tools_filter is not None
        assert result.tools_filter["search"].changed is True
        assert result.tools_filter["write"].changed is False
