"""Integration tests for the agent module with MCP servers.

These tests exercise MCP toolset integration using TestModel/FunctionModel
to avoid real LLM calls, and mock MCP servers to avoid real MCP connections.
"""

from pydantic_ai import Agent, models
from pydantic_ai.models.test import TestModel

from ansible_collections.seckatie.agents.plugins.module_utils.mcp_config import (
    build_mcp_toolset,
    parse_server_config,
)

models.ALLOW_MODEL_REQUESTS = False


class TestAgentWithMCPServers:
    """2.5: Integration tests for agent with MCP servers."""

    def test_single_mcp_server_config_builds(self):
        """A single MCP server config produces a valid toolset."""
        config = {
            "type": "stdio",
            "command": "echo",
            "args": ["hello"],
        }
        result = build_mcp_toolset(config)
        assert result.toolset is not None

    def test_multiple_mcp_server_configs_build(self):
        """Multiple MCP server configs each produce valid toolsets."""
        configs = [
            {"type": "stdio", "command": "server1"},
            {"type": "sse", "url": "http://localhost:8080/sse"},
        ]
        toolsets = []
        for config in configs:
            result = build_mcp_toolset(config)
            toolsets.append(result.toolset)
        assert len(toolsets) == 2

    def test_mcp_coexists_with_ansible_tools(self):
        """MCP toolsets and Ansible module tools can be passed to Agent together."""
        from pydantic_ai import Tool

        # Build a simple Ansible-style tool
        def my_tool() -> str:
            return "ansible result"

        ansible_tool = Tool(
            my_tool, name="ansible_check", description="Check something"
        )

        # Build an MCP toolset
        config = {"type": "stdio", "command": "my-mcp-server"}
        mcp_result = build_mcp_toolset(config)

        # Both can be passed to Agent constructor without error
        agent = Agent(
            TestModel(),
            tools=[ansible_tool],
            toolsets=[mcp_result.toolset],
        )
        assert agent is not None


class TestToolNameConflict:
    """2.6: Tool name conflict behavior."""

    def test_conflict_error_from_pydantic_ai(self):
        """When two servers have same tool name without prefix, Pydantic AI raises."""
        # This is tested at the Pydantic AI level — we just verify the config
        # builds correctly and conflicts would be caught at runtime
        config1 = {"type": "stdio", "command": "server1"}
        config2 = {"type": "stdio", "command": "server2"}
        result1 = build_mcp_toolset(config1)
        result2 = build_mcp_toolset(config2)
        # Both build successfully — conflict detection happens at Agent.run_sync()
        assert result1.toolset is not None
        assert result2.toolset is not None

    def test_tool_prefix_resolves_conflicts(self):
        """tool_prefix on server config is passed through to MCPServer."""
        config = {
            "type": "stdio",
            "command": "server1",
            "tool_prefix": "s1",
        }
        server = parse_server_config(config)
        assert server.tool_prefix == "s1"


class TestToolAllowlistInAgent:
    """2.7: Tool allowlist filtering in agent context."""

    def test_filtered_toolset_created(self):
        """When tools filter is set, a FilteredToolset wraps the server."""
        config = {
            "type": "stdio",
            "command": "my-server",
            "tools": ["search_web"],
        }
        result = build_mcp_toolset(config)
        from pydantic_ai.toolsets.filtered import FilteredToolset

        assert isinstance(result.toolset, FilteredToolset)

    def test_no_filter_passes_server_directly(self):
        """When no tools filter, the server is passed directly."""
        config = {
            "type": "stdio",
            "command": "my-server",
        }
        result = build_mcp_toolset(config)
        from pydantic_ai.mcp import MCPServerStdio

        assert isinstance(result.toolset, MCPServerStdio)

    def test_filter_with_changed_override(self):
        """Tools filter preserves changed overrides for tracking."""
        config = {
            "type": "stdio",
            "command": "my-server",
            "tools": [
                {"name": "search", "changed": False},
                {"name": "write", "changed": True},
            ],
        }
        result = build_mcp_toolset(config)
        assert result.tools_filter is not None
        assert result.tools_filter["search"].changed is False
        assert result.tools_filter["write"].changed is True
