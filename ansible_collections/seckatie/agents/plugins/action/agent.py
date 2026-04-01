"""Action plugin for seckatie.agents.agent — runs a Pydantic AI agent on the controller."""

from __future__ import annotations

import json
from typing import Any

from ansible.plugins.action import ActionBase

from ansible_collections.seckatie.agents.plugins.module_utils.macos_safety import (
    check_fork_safety,
)


class ActionModule(ActionBase):
    """Run a Pydantic AI agent as an Ansible action plugin."""

    # This action runs entirely on the controller — no need to transfer files
    TRANSFERS_FILES = False

    def run(self, tmp=None, task_vars=None):
        super().run(tmp, task_vars)
        self._task_vars = task_vars or {}

        fork_error = check_fork_safety()
        if fork_error:
            return fork_error

        # Defer all heavy imports to after fork to avoid segfaults
        try:
            from pydantic_ai import Agent
            from pydantic_ai.messages import ModelMessagesTypeAdapter
            from pydantic_ai.settings import ModelSettings
            from pydantic_ai.usage import UsageLimits
            from pydantic_ai.exceptions import (
                UsageLimitExceeded,
                UnexpectedModelBehavior,
                ModelAPIError,
            )
        except ImportError:
            return dict(
                failed=True,
                msg=(
                    "pydantic-ai is required for the seckatie.agents.agent module. "
                    "Install it on the Ansible controller: pip install pydantic-ai"
                ),
            )

        from ansible_collections.seckatie.agents.plugins.module_utils.schema_builder import (
            build_model,
            resolve_schema,
        )
        from ansible_collections.seckatie.agents.plugins.module_utils.tool_builder import (
            build_tools,
        )

        # Extract arguments from task
        args = self._task.args
        model_name = args.get("model")
        system_prompt = args.get("system_prompt", "")
        prompt = args.get("prompt")
        message_history_raw = args.get("message_history")
        tool_defs = args.get("tools", []) or []
        mcp_server_defs = args.get("mcp_servers", []) or []
        max_tool_calls = args.get("max_tool_calls", 25)
        model_settings_raw = args.get("model_settings")

        if not model_name:
            return dict(failed=True, msg="'model' parameter is required")
        if not prompt:
            return dict(failed=True, msg="'prompt' parameter is required")

        # Build output type from schema
        output_schema = args.get("output_schema")
        output_type = str
        if output_schema:
            try:
                basedir = self._loader.get_basedir()
                schema = resolve_schema(output_schema, basedir=basedir)
                output_type = build_model(schema)
            except (ValueError, OSError) as e:
                return dict(failed=True, msg=f"Invalid output_schema: {e}")

        # Build tools
        tracker = None
        pydantic_tools = []
        if tool_defs:
            try:
                pydantic_tools, tracker = build_tools(
                    tool_defs,
                    self._execute_ansible_module,
                    execute_on_controller_fn=self._execute_on_controller,
                )
            except Exception as e:
                return dict(failed=True, msg=f"Failed to build tools: {e}")

        # Build MCP toolsets
        mcp_toolsets = []
        mcp_tools_filters = []
        if mcp_server_defs:
            try:
                from ansible_collections.seckatie.agents.plugins.module_utils.mcp_config import (
                    build_mcp_toolset,
                )
            except ImportError:
                return dict(
                    failed=True,
                    msg=(
                        "The mcp package is required to use mcp_servers. "
                        "Install it on the Ansible controller: "
                        "pip install 'pydantic-ai-slim[mcp]'"
                    ),
                )

            for server_def in mcp_server_defs:
                try:
                    result = build_mcp_toolset(server_def)
                    mcp_toolsets.append(result.toolset)
                    if result.tools_filter:
                        mcp_tools_filters.append(result.tools_filter)
                except (ValueError, ImportError) as e:
                    return dict(failed=True, msg=f"Failed to configure MCP server: {e}")

        # Deserialize message history
        message_history = None
        if message_history_raw:
            try:
                if isinstance(message_history_raw, (str, bytes)):
                    message_history = ModelMessagesTypeAdapter.validate_json(
                        message_history_raw
                    )
                else:
                    message_history = ModelMessagesTypeAdapter.validate_python(
                        message_history_raw
                    )
            except Exception as e:
                return dict(
                    failed=True,
                    msg=f"Failed to deserialize message_history: {e}",
                )

        # Build model settings
        model_settings = None
        if model_settings_raw:
            model_settings = ModelSettings(**model_settings_raw)

        # Build usage limits
        usage_limits = UsageLimits(tool_calls_limit=max_tool_calls)

        # Construct and run the agent
        try:
            agent_kwargs: dict[str, Any] = dict(
                instructions=system_prompt or None,
                output_type=output_type,
                tools=pydantic_tools,
                model_settings=model_settings,
            )
            if mcp_toolsets:
                agent_kwargs["toolsets"] = mcp_toolsets

            agent = Agent(model_name, **agent_kwargs)

            result = agent.run_sync(
                prompt,
                message_history=message_history,
                usage_limits=usage_limits,
            )
        except UsageLimitExceeded as e:
            return dict(failed=True, msg=f"Usage limit exceeded: {e}")
        except ModelAPIError as e:
            return dict(failed=True, msg=f"LLM API error: {e}")
        except UnexpectedModelBehavior as e:
            return dict(failed=True, msg=f"Unexpected model behavior: {e}")
        except Exception as e:
            return dict(failed=True, msg=f"Agent execution failed: {e}")

        # Serialize output
        output = result.output
        if hasattr(output, "model_dump"):
            output = output.model_dump()

        # Serialize message history for Ansible result passthrough
        try:
            message_history_out = json.loads(result.all_messages_json())
        except (json.JSONDecodeError, TypeError):
            message_history_out = str(result.all_messages_json())

        # Get usage stats
        usage = result.usage()
        usage_dict = {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "requests": usage.requests,
            "tool_calls": usage.tool_calls,
        }

        # Determine changed status from Ansible tools
        changed = tracker.changed if tracker else False

        if not changed and mcp_server_defs:
            from pydantic_ai.messages import ToolCallPart

            # Build lookup: tool_name → changed flag (from filters)
            mcp_tool_configs: dict[str, bool] = {}
            for tf in mcp_tools_filters:
                for tool_name, tool_config in tf.items():
                    mcp_tool_configs[tool_name] = tool_config.changed

            ansible_tool_names = {td["name"] for td in tool_defs}

            for msg in result.all_messages():
                for part in getattr(msg, "parts", []):
                    if isinstance(part, ToolCallPart):
                        name = part.tool_name
                        if name in mcp_tool_configs:
                            if mcp_tool_configs[name]:
                                changed = True
                        elif name not in ansible_tool_names:
                            # Unfiltered MCP tool — default changed=true
                            changed = True
                if changed:
                    break

        return dict(
            changed=changed,
            output=output,
            message_history=message_history_out,
            usage=usage_dict,
            model=model_name,
            run_id=result.run_id,
        )

    def _execute_ansible_module(
        self, module_name: str, module_args: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute an Ansible module on the target host via the action plugin machinery."""
        result = self._execute_module(
            module_name=module_name,
            module_args=module_args,
            task_vars=self._task_vars,
        )
        return result

    def _execute_on_controller(
        self, module_name: str, module_args: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute an Ansible module on the controller (localhost) via local connection."""
        from ansible.plugins.connection.local import Connection as LocalConnection

        # Save the current connection and swap to local
        original_connection = self._connection
        try:
            self._connection = LocalConnection(
                play_context=self._play_context,
                new_stdin=original_connection._new_stdin,
            )
            result = self._execute_module(
                module_name=module_name,
                module_args=module_args,
                task_vars=self._task_vars,
            )
        finally:
            self._connection = original_connection
        return result
