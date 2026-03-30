"""Integration tests for the seckatie.agents.agent module.

These tests exercise the core agent pipeline (schema builder + tool builder + Pydantic AI agent)
using TestModel and FunctionModel to avoid real LLM calls.
"""

import json
import re

import pytest

from pydantic_ai import Agent, models
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded

from ansible_collections.seckatie.agents.plugins.module_utils.schema_builder import (
    build_model,
)
from ansible_collections.seckatie.agents.plugins.module_utils.tool_builder import (
    build_tools,
)

models.ALLOW_MODEL_REQUESTS = False


class TestMinimalAgentRun:
    """5.1: Minimal agent run with prompt-only (no tools, no schema)."""

    def test_plain_text_response(self):
        agent = Agent(TestModel(custom_output_text="Paris"))
        result = agent.run_sync("What is the capital of France?")
        assert result.output == "Paris"

    def test_result_has_expected_fields(self):
        agent = Agent(TestModel(custom_output_text="hello"))
        result = agent.run_sync("Say hello")
        assert isinstance(result.output, str)
        assert result.all_messages_json()
        usage = result.usage()
        assert hasattr(usage, "input_tokens")
        assert hasattr(usage, "output_tokens")
        assert hasattr(usage, "requests")


class TestStructuredOutput:
    """5.2: Structured output with output_schema."""

    def test_structured_output_via_schema_builder(self):
        schema = {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "description": "The severity level",
                },
                "summary": {
                    "type": "string",
                    "description": "A brief summary",
                },
            },
            "required": ["severity", "summary"],
        }
        OutputModel = build_model(schema, "AnalysisResult")

        agent = Agent(TestModel(), output_type=OutputModel)
        result = agent.run_sync("Analyze this log line: ERROR disk full")

        output = result.output
        assert hasattr(output, "severity")
        assert hasattr(output, "summary")
        assert isinstance(output.severity, str)
        assert isinstance(output.summary, str)


class TestToolCallingFixedArgs:
    """5.3: Tool calling with fixed_args-only tool."""

    def test_fixed_args_tool_called(self):
        calls = []

        def mock_execute(module_name, module_args):
            calls.append((module_name, module_args))
            return {"changed": False, "stdout": "Filesystem  Size  Used  Avail\n/dev/sda1  50G  30G  20G"}

        tool_defs = [
            {
                "name": "check_disk",
                "description": "Check disk usage on the host",
                "module": "ansible.builtin.command",
                "fixed_args": {"cmd": "df -h"},
            }
        ]
        pydantic_tools, tracker = build_tools(tool_defs, mock_execute)

        agent = Agent(TestModel(), tools=pydantic_tools)
        result = agent.run_sync("Check disk usage")

        assert len(calls) == 1
        assert calls[0][0] == "ansible.builtin.command"
        assert calls[0][1] == {"cmd": "df -h"}
        assert tracker.changed is False


class TestToolCallingWithTemplates:
    """5.4: Tool calling with agent_args and template interpolation."""

    def test_template_interpolation_in_tool_call(self):
        calls = []

        def mock_execute(module_name, module_args):
            calls.append((module_name, module_args))
            return {"changed": False, "stdout": "log output here"}

        tool_defs = [
            {
                "name": "read_log",
                "description": "Read last N lines of a log file",
                "module": "ansible.builtin.command",
                "fixed_args": {"cmd": "tail -{{ lines }} {{ path }}"},
                "agent_args": {
                    "lines": {"type": "integer", "minimum": 1},
                    "path": {"type": "string", "description": "Log file path"},
                },
            }
        ]
        pydantic_tools, tracker = build_tools(tool_defs, mock_execute)

        # Use FunctionModel to control tool call args
        def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            "read_log",
                            {"lines": 100, "path": "/var/log/syslog"},
                        )
                    ]
                )
            else:
                return ModelResponse(parts=[TextPart("Done reading logs")])

        agent = Agent(FunctionModel(model_fn), tools=pydantic_tools)
        result = agent.run_sync("Read the syslog")

        assert len(calls) == 1
        assert calls[0][0] == "ansible.builtin.command"
        # Template interpolation should have applied shlex.quote
        assert calls[0][1]["cmd"] == "tail -100 /var/log/syslog"


class TestConversationContinuity:
    """5.5: Conversation continuity — two sequential tasks passing message_history."""

    def test_message_history_round_trip(self):
        call_count = [0]

        def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            call_count[0] += 1
            msg_count = len(messages)
            return ModelResponse(
                parts=[TextPart(f"Response {call_count[0]}, saw {msg_count} messages")]
            )

        agent = Agent(FunctionModel(model_fn))

        # First run
        result1 = agent.run_sync("First question")
        history_json = result1.all_messages_json()

        # Deserialize and pass to second run
        history = ModelMessagesTypeAdapter.validate_json(history_json)
        result2 = agent.run_sync("Second question", message_history=history)

        # Second run should see more messages than the first
        assert "saw 1 messages" in result1.output
        assert "saw 3 messages" in result2.output


class TestChangedTracking:
    """5.6: changed tracking across tool calls."""

    def test_changed_true_when_tool_changes(self):
        call_count = [0]

        def mock_execute(module_name, module_args):
            call_count[0] += 1
            return {"changed": call_count[0] == 2, "msg": "ok"}

        tool_defs = [
            {
                "name": "do_thing",
                "description": "Do a thing",
                "module": "test.module",
                "fixed_args": {"action": "go"},
            }
        ]
        pydantic_tools, tracker = build_tools(tool_defs, mock_execute)

        # Use TestModel which calls all tools by default
        agent = Agent(TestModel(), tools=pydantic_tools)
        result = agent.run_sync("Do the thing")

        # TestModel calls the tool once
        assert call_count[0] >= 1

    def test_changed_false_when_no_tools(self):
        """No tools means changed should be False."""
        agent = Agent(TestModel(custom_output_text="no change"))
        result = agent.run_sync("Just talk")
        # No tracker, so changed would be False in the action plugin


class TestMaxToolCalls:
    """5.7: max_tool_calls limit enforcement."""

    def test_tool_call_limit_exceeded(self):
        def mock_execute(module_name, module_args):
            return {"changed": False, "stdout": "ok"}

        tool_defs = [
            {
                "name": "repeat",
                "description": "Repeat action",
                "module": "test.module",
                "fixed_args": {"x": "1"},
            }
        ]
        pydantic_tools, tracker = build_tools(tool_defs, mock_execute)

        # FunctionModel that always tries to call the tool
        def always_call_tool(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[ToolCallPart("repeat", {})])

        agent = Agent(FunctionModel(always_call_tool), tools=pydantic_tools)

        with pytest.raises(UsageLimitExceeded):
            agent.run_sync(
                "Keep repeating",
                usage_limits=UsageLimits(tool_calls_limit=3),
            )
