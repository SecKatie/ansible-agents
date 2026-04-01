"""Action plugin for seckatie.agents.mcp — direct MCP server interactions."""

from __future__ import annotations

import asyncio
from typing import Any

from ansible.plugins.action import ActionBase

from ansible_collections.seckatie.agents.plugins.module_utils.macos_safety import (
    check_fork_safety,
)

_VALID_ACTIONS = {
    "call_tool",
    "list_tools",
    "read_resource",
    "list_resources",
    "get_prompt",
    "list_prompts",
}

# Read-only actions always return changed=false
_READ_ONLY_ACTIONS = {
    "list_tools",
    "list_resources",
    "read_resource",
    "list_prompts",
    "get_prompt",
}


class ActionModule(ActionBase):
    """Interact with MCP servers directly from Ansible."""

    TRANSFERS_FILES = False

    def run(self, tmp=None, task_vars=None):
        super().run(tmp, task_vars)

        fork_error = check_fork_safety()
        if fork_error:
            return fork_error

        try:
            from ansible_collections.seckatie.agents.plugins.module_utils.mcp_config import (
                parse_server_config,
                parse_tools_filter,
            )
        except ImportError:
            return dict(
                failed=True,
                msg=(
                    "The mcp package is required for the seckatie.agents.mcp module. "
                    "Install it on the Ansible controller: "
                    "pip install 'pydantic-ai-slim[mcp]'"
                ),
            )

        args = self._task.args
        server_dict = args.get("server")
        action = args.get("action")
        tool_name = args.get("tool_name")
        arguments = args.get("arguments", {}) or {}
        uri = args.get("uri")
        prompt_name = args.get("prompt_name")
        prompt_arguments = args.get("prompt_arguments", {}) or {}

        if not server_dict:
            return dict(failed=True, msg="'server' parameter is required")

        if not action:
            return dict(failed=True, msg="'action' parameter is required")

        if action not in _VALID_ACTIONS:
            return dict(
                failed=True,
                msg=(
                    f"Invalid action: '{action}'. "
                    f"Valid actions are: {', '.join(sorted(_VALID_ACTIONS))}"
                ),
            )

        # Validate required params per action
        if action == "call_tool" and not tool_name:
            return dict(
                failed=True,
                msg="'tool_name' is required when action is 'call_tool'",
            )
        if action == "read_resource" and not uri:
            return dict(
                failed=True,
                msg="'uri' is required when action is 'read_resource'",
            )
        if action == "get_prompt" and not prompt_name:
            return dict(
                failed=True,
                msg="'prompt_name' is required when action is 'get_prompt'",
            )

        # Parse server config
        try:
            server = parse_server_config(server_dict)
        except (ValueError, ImportError) as e:
            return dict(failed=True, msg=f"Failed to configure MCP server: {e}")

        # Parse tools filter for changed tracking
        tools_filter = parse_tools_filter(server_dict.get("tools"))

        # Dispatch to the appropriate action
        try:
            output = asyncio.run(
                self._dispatch(
                    server,
                    action,
                    tool_name,
                    arguments,
                    uri,
                    prompt_name,
                    prompt_arguments,
                )
            )
        except Exception as e:
            return dict(failed=True, msg=f"MCP operation failed: {e}")

        # Determine changed status
        if action in _READ_ONLY_ACTIONS:
            changed = False
        elif action == "call_tool":
            # Default to changed=true for tool calls
            changed = True
            # Check if server config overrides changed for this tool
            if tools_filter and tool_name in tools_filter:
                changed = tools_filter[tool_name].changed
        else:
            changed = False

        return dict(changed=changed, output=output)

    async def _dispatch(
        self,
        server: Any,
        action: str,
        tool_name: str | None,
        arguments: dict[str, Any],
        uri: str | None,
        prompt_name: str | None,
        prompt_arguments: dict[str, Any],
    ) -> Any:
        """Connect to MCP server and execute the requested action."""
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        from mcp.client.sse import sse_client
        from mcp.client.streamable_http import streamablehttp_client
        from pydantic_ai.mcp import (
            MCPServerStdio,
            MCPServerSSE,
            MCPServerStreamableHTTP,
        )

        from ansible_collections.seckatie.agents.plugins.module_utils.mcp_actions import (
            execute_mcp_action,
        )

        # Determine transport and create client context
        if isinstance(server, MCPServerStdio):
            client_cm = stdio_client(
                server.command,
                args=list(server.args),
                env=server.env,
            )
        elif isinstance(server, MCPServerSSE):
            client_cm = sse_client(
                server.url,
                headers=server.headers or {},
            )
        elif isinstance(server, MCPServerStreamableHTTP):
            client_cm = streamablehttp_client(
                server.url,
                headers=server.headers or {},
            )
        else:
            raise ValueError(f"Unsupported server type: {type(server)}")

        async with client_cm as (read_stream, write_stream, *_):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await execute_mcp_action(
                    session,
                    action,
                    tool_name,
                    arguments,
                    uri,
                    prompt_name,
                    prompt_arguments,
                )
