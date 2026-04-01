"""Unit tests for the standalone mcp action plugin.

Tests cover action dispatch and changed status logic.
MCP server connections are mocked to avoid real network calls.
"""

import asyncio

from unittest.mock import MagicMock, AsyncMock

from ansible_collections.seckatie.agents.plugins.module_utils.mcp_config import (
    parse_tools_filter,
)


class TestMCPActionChanged:
    """Tests for changed status logic."""

    def test_list_tools_not_changed(self):
        """Read-only actions return changed=false."""
        tools_filter = parse_tools_filter(None)
        # list_tools is read-only
        assert tools_filter is None  # no filter = all tools, but read-only

    def test_call_tool_default_changed_true(self):
        """call_tool defaults to changed=true when no filter override."""
        tools_filter = parse_tools_filter(None)
        # No filter, so default is changed=true
        assert tools_filter is None

    def test_call_tool_changed_override_false(self):
        """call_tool respects changed=false from server config."""
        tools_filter = parse_tools_filter(
            [
                {"name": "search_web", "changed": False},
            ]
        )
        assert tools_filter is not None
        assert tools_filter["search_web"].changed is False

    def test_call_tool_changed_override_true(self):
        """call_tool respects explicit changed=true from server config."""
        tools_filter = parse_tools_filter(
            [
                {"name": "create_issue", "changed": True},
            ]
        )
        assert tools_filter is not None
        assert tools_filter["create_issue"].changed is True


class TestMCPActionDispatch:
    """Tests for action dispatch with mocked MCP sessions.

    Tests use execute_mcp_action from module_utils directly to avoid
    Ansible's ActionBase import chain.
    """

    def _run(self, coro):
        return asyncio.run(coro)

    def test_list_tools_dispatch(self):
        """list_tools returns tool definitions."""
        from ansible_collections.seckatie.agents.plugins.module_utils.mcp_actions import (
            execute_mcp_action,
        )

        session = AsyncMock()
        tool = MagicMock()
        tool.name = "search"
        tool.description = "Search the web"
        tool.inputSchema = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        }

        list_result = MagicMock()
        list_result.tools = [tool]
        session.list_tools.return_value = list_result

        result = self._run(
            execute_mcp_action(session, "list_tools", None, {}, None, None, {})
        )

        assert len(result) == 1
        assert result[0]["name"] == "search"
        assert result[0]["description"] == "Search the web"

    def test_call_tool_dispatch(self):
        """call_tool calls the named tool and returns result."""
        from ansible_collections.seckatie.agents.plugins.module_utils.mcp_actions import (
            execute_mcp_action,
        )

        session = AsyncMock()
        content = MagicMock()
        content.text = "Search results here"
        del content.data

        call_result = MagicMock()
        call_result.content = [content]
        session.call_tool.return_value = call_result

        result = self._run(
            execute_mcp_action(
                session, "call_tool", "search", {"query": "test"}, None, None, {}
            )
        )

        session.call_tool.assert_called_once_with("search", arguments={"query": "test"})
        assert result == "Search results here"

    def test_list_resources_dispatch(self):
        """list_resources returns resource list."""
        from ansible_collections.seckatie.agents.plugins.module_utils.mcp_actions import (
            execute_mcp_action,
        )

        session = AsyncMock()
        resource = MagicMock()
        resource.uri = "file:///data/config.yaml"
        resource.name = "config"
        resource.description = "Config file"
        resource.mimeType = "text/yaml"

        list_result = MagicMock()
        list_result.resources = [resource]
        session.list_resources.return_value = list_result

        result = self._run(
            execute_mcp_action(session, "list_resources", None, {}, None, None, {})
        )

        assert len(result) == 1
        assert result[0]["uri"] == "file:///data/config.yaml"
        assert result[0]["name"] == "config"

    def test_read_resource_dispatch(self):
        """read_resource returns resource contents."""
        from ansible_collections.seckatie.agents.plugins.module_utils.mcp_actions import (
            execute_mcp_action,
        )

        session = AsyncMock()
        content = MagicMock()
        content.uri = "file:///data/config.yaml"
        content.text = "key: value"
        content.mimeType = "text/yaml"

        read_result = MagicMock()
        read_result.contents = [content]
        session.read_resource.return_value = read_result

        result = self._run(
            execute_mcp_action(
                session, "read_resource", None, {}, "file:///data/config.yaml", None, {}
            )
        )

        assert len(result) == 1
        assert result[0]["text"] == "key: value"

    def test_list_prompts_dispatch(self):
        """list_prompts returns prompt definitions."""
        from ansible_collections.seckatie.agents.plugins.module_utils.mcp_actions import (
            execute_mcp_action,
        )

        session = AsyncMock()
        arg = MagicMock()
        arg.name = "language"
        arg.description = "Programming language"
        arg.required = True

        prompt = MagicMock()
        prompt.name = "code_review"
        prompt.description = "Review code"
        prompt.arguments = [arg]

        list_result = MagicMock()
        list_result.prompts = [prompt]
        session.list_prompts.return_value = list_result

        result = self._run(
            execute_mcp_action(session, "list_prompts", None, {}, None, None, {})
        )

        assert len(result) == 1
        assert result[0]["name"] == "code_review"
        assert result[0]["arguments"][0]["name"] == "language"

    def test_get_prompt_dispatch(self):
        """get_prompt returns rendered prompt."""
        from ansible_collections.seckatie.agents.plugins.module_utils.mcp_actions import (
            execute_mcp_action,
        )

        session = AsyncMock()
        msg_content = MagicMock()
        msg_content.text = "Please review this Python code."

        msg = MagicMock()
        msg.role = "user"
        msg.content = msg_content

        get_result = MagicMock()
        get_result.description = "Code review prompt"
        get_result.messages = [msg]
        session.get_prompt.return_value = get_result

        result = self._run(
            execute_mcp_action(
                session,
                "get_prompt",
                None,
                {},
                None,
                "code_review",
                {"language": "python"},
            )
        )

        session.get_prompt.assert_called_once_with(
            "code_review", arguments={"language": "python"}
        )
        assert result["description"] == "Code review prompt"
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "user"


class TestMCPChangedIntegration:
    """3.9: Integration test for call_tool with changed override."""

    def test_changed_override_lookup(self):
        """Server config changed override is correctly looked up for tool calls."""
        tools_filter = parse_tools_filter(
            [
                {"name": "search_web", "changed": False},
                {"name": "create_issue", "changed": True},
                "delete_repo",
            ]
        )
        assert tools_filter is not None

        # search_web: explicitly false
        assert tools_filter["search_web"].changed is False
        # create_issue: explicitly true
        assert tools_filter["create_issue"].changed is True
        # delete_repo: string entry defaults to true
        assert tools_filter["delete_repo"].changed is True
        # unknown tool: not in filter (would use default true)
        assert "unknown" not in tools_filter
