"""Action plugin for seckatie.agents.agent — runs a Pydantic AI agent on the controller."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from ansible.plugins.action import ActionBase

_MACOS_FORK_SAFETY_MSG = (
    "On macOS, Ansible workers crash when importing AI libraries due to an ObjC "
    "fork safety issue. Set the following environment variable before running "
    "ansible-playbook:\n\n"
    "    export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES\n\n"
    "Add this to your shell profile (~/.zshrc or ~/.bashrc) to make it permanent.\n"
    "See: https://docs.ansible.com/ansible/latest/reference_appendices/faq.html"
    "#running-on-macos-as-a-control-node"
)


class ActionModule(ActionBase):
    """Run a Pydantic AI agent as an Ansible action plugin."""

    # This action runs entirely on the controller — no need to transfer files
    TRANSFERS_FILES = False

    def run(self, tmp=None, task_vars=None):
        super().run(tmp, task_vars)
        self._task_vars = task_vars or {}

        # Detect macOS fork safety issue before importing AI libraries
        if (
            sys.platform == "darwin"
            and os.environ.get("OBJC_DISABLE_INITIALIZE_FORK_SAFETY") != "YES"
        ):
            return dict(failed=True, msg=_MACOS_FORK_SAFETY_MSG)

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
        )
        from ansible_collections.seckatie.agents.plugins.module_utils.tool_builder import (
            build_tools,
        )

        # Extract arguments from task
        args = self._task.args
        model_name = args.get("model")
        system_prompt = args.get("system_prompt", "")
        prompt = args.get("prompt")
        output_schema = args.get("output_schema")
        message_history_raw = args.get("message_history")
        tool_defs = args.get("tools", []) or []
        max_tool_calls = args.get("max_tool_calls", 25)
        model_settings_raw = args.get("model_settings")

        if not model_name:
            return dict(failed=True, msg="'model' parameter is required")
        if not prompt:
            return dict(failed=True, msg="'prompt' parameter is required")

        # Build output type from schema
        output_type = str
        if output_schema:
            try:
                output_type = build_model(output_schema)
            except ValueError as e:
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
            agent = Agent(
                model_name,
                instructions=system_prompt or None,
                output_type=output_type,
                tools=pydantic_tools,
                model_settings=model_settings,
            )

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

        # Determine changed status
        changed = tracker.changed if tracker else False

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
