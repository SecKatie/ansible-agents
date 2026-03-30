"""Unit tests for tool_builder module."""

from ansible_collections.seckatie.agents.plugins.module_utils.tool_builder import (
    ChangeTracker,
    _agent_args_to_json_schema,
    _interpolate_templates,
    build_tools,
)


class TestInterpolateTemplates:
    def test_basic_interpolation(self):
        fixed = {"cmd": "tail -{{ lines }} {{ path }}"}
        agent_vals = {"lines": "200", "path": "/var/log/syslog"}
        result = _interpolate_templates(fixed, agent_vals)
        assert result["cmd"] == "tail -200 /var/log/syslog"

    def test_shlex_quote_applied(self):
        fixed = {"cmd": "cat {{ path }}"}
        agent_vals = {"path": "/tmp; rm -rf /"}
        result = _interpolate_templates(fixed, agent_vals)
        assert result["cmd"] == "cat '/tmp; rm -rf /'"

    def test_shlex_quote_spaces(self):
        fixed = {"cmd": "cat {{ path }}"}
        agent_vals = {"path": "/var/log/my file.log"}
        result = _interpolate_templates(fixed, agent_vals)
        assert result["cmd"] == "cat '/var/log/my file.log'"

    def test_no_templates_passthrough(self):
        fixed = {"state": "restarted", "name": "nginx"}
        result = _interpolate_templates(fixed, {})
        assert result == {"state": "restarted", "name": "nginx"}

    def test_non_string_values_passthrough(self):
        fixed = {"retries": 3, "delay": 5}
        result = _interpolate_templates(fixed, {})
        assert result == {"retries": 3, "delay": 5}

    def test_multiple_placeholders_same_value(self):
        fixed = {"cmd": "echo {{ name }} {{ name }}"}
        agent_vals = {"name": "hello"}
        result = _interpolate_templates(fixed, agent_vals)
        assert result["cmd"] == "echo hello hello"

    def test_missing_placeholder_value(self):
        fixed = {"cmd": "echo {{ missing }}"}
        result = _interpolate_templates(fixed, {})
        assert result["cmd"] == "echo ''"

    def test_whitespace_in_template(self):
        fixed = {"cmd": "echo {{  name  }}"}
        agent_vals = {"name": "world"}
        result = _interpolate_templates(fixed, agent_vals)
        assert result["cmd"] == "echo world"

    def test_integer_agent_value_converted(self):
        fixed = {"cmd": "tail -{{ lines }} /var/log/syslog"}
        agent_vals = {"lines": 200}
        result = _interpolate_templates(fixed, agent_vals)
        assert result["cmd"] == "tail -200 /var/log/syslog"


class TestAgentArgsToJsonSchema:
    def test_basic_conversion(self):
        agent_args = {
            "path": {"type": "string", "description": "File path"},
            "lines": {"type": "integer", "minimum": 1},
        }
        schema = _agent_args_to_json_schema(agent_args)
        assert schema["type"] == "object"
        assert "path" in schema["properties"]
        assert "lines" in schema["properties"]
        assert set(schema["required"]) == {"path", "lines"}

    def test_empty_agent_args(self):
        schema = _agent_args_to_json_schema({})
        assert schema["type"] == "object"
        assert schema["properties"] == {}


class TestChangeTracker:
    def test_initial_state(self):
        tracker = ChangeTracker()
        assert tracker.changed is False

    def test_no_change(self):
        tracker = ChangeTracker()
        tracker.record({"changed": False, "stdout": "ok"})
        assert tracker.changed is False

    def test_change_detected(self):
        tracker = ChangeTracker()
        tracker.record({"changed": True, "stdout": "restarted"})
        assert tracker.changed is True

    def test_change_persists(self):
        tracker = ChangeTracker()
        tracker.record({"changed": True})
        tracker.record({"changed": False})
        assert tracker.changed is True

    def test_no_changed_key(self):
        tracker = ChangeTracker()
        tracker.record({"stdout": "ok"})
        assert tracker.changed is False


class TestBuildTools:
    def test_fixed_args_only_tool(self):
        """Tool with only fixed_args: zero parameters for LLM."""
        calls = []

        def mock_execute(module_name, module_args):
            calls.append((module_name, module_args))
            return {"changed": False, "stdout": "ok"}

        tool_defs = [
            {
                "name": "check_disk",
                "description": "Check disk usage",
                "module": "ansible.builtin.command",
                "fixed_args": {"cmd": "df -h"},
            }
        ]
        tools, tracker = build_tools(tool_defs, mock_execute)
        assert len(tools) == 1
        assert tools[0].name == "check_disk"

    def test_agent_args_only_tool(self):
        """Tool with only agent_args: LLM provides all args."""
        calls = []

        def mock_execute(module_name, module_args):
            calls.append((module_name, module_args))
            return {"changed": True, "msg": "restarted"}

        tool_defs = [
            {
                "name": "restart_service",
                "description": "Restart a systemd service",
                "module": "ansible.builtin.systemd",
                "agent_args": {
                    "name": {"type": "string", "description": "Service name"},
                },
            }
        ]
        tools, tracker = build_tools(tool_defs, mock_execute)
        assert len(tools) == 1
        assert tools[0].name == "restart_service"

    def test_mixed_args_tool(self):
        """Tool with both fixed_args and agent_args."""
        calls = []

        def mock_execute(module_name, module_args):
            calls.append((module_name, module_args))
            return {"changed": True}

        tool_defs = [
            {
                "name": "restart_service",
                "description": "Restart a service",
                "module": "ansible.builtin.systemd",
                "fixed_args": {"state": "restarted"},
                "agent_args": {
                    "name": {"type": "string"},
                },
            }
        ]
        tools, tracker = build_tools(tool_defs, mock_execute)
        assert len(tools) == 1

    def test_template_interpolation_tool(self):
        """Tool with template interpolation in fixed_args."""
        calls = []

        def mock_execute(module_name, module_args):
            calls.append((module_name, module_args))
            return {"changed": False, "stdout": "output"}

        tool_defs = [
            {
                "name": "read_log",
                "description": "Read last N lines of a log file",
                "module": "ansible.builtin.command",
                "fixed_args": {"cmd": "tail -{{ lines }} {{ path }}"},
                "agent_args": {
                    "lines": {"type": "integer", "minimum": 1},
                    "path": {"type": "string"},
                },
            }
        ]
        tools, tracker = build_tools(tool_defs, mock_execute)
        assert len(tools) == 1

    def test_change_tracking(self):
        """Change tracker reflects tool call results."""
        call_count = [0]

        def mock_execute(module_name, module_args):
            call_count[0] += 1
            return {"changed": call_count[0] == 2}

        tool_defs = [
            {
                "name": "tool1",
                "description": "Tool 1",
                "module": "mod1",
                "fixed_args": {"x": "1"},
            },
        ]
        tools, tracker = build_tools(tool_defs, mock_execute)
        # Call the tool twice
        tools[0].function()
        assert tracker.changed is False
        tools[0].function()
        assert tracker.changed is True

    def test_fixed_args_override_agent_args(self):
        """fixed_args take precedence over agent_args with same key."""
        calls = []

        def mock_execute(module_name, module_args):
            calls.append((module_name, module_args))
            return {"changed": False}

        tool_defs = [
            {
                "name": "safe_service",
                "description": "Restart a service safely",
                "module": "ansible.builtin.systemd",
                "fixed_args": {"state": "restarted"},
                "agent_args": {
                    "name": {"type": "string"},
                },
            }
        ]
        tools, tracker = build_tools(tool_defs, mock_execute)
        # Simulate calling with agent providing state (shouldn't override)
        tools[0].function(name="nginx", state="stopped")
        assert calls[0][1]["state"] == "restarted"
        assert calls[0][1]["name"] == "nginx"

    def test_multiple_tools(self):
        """Building multiple tools at once."""

        def mock_execute(module_name, module_args):
            return {"changed": False}

        tool_defs = [
            {
                "name": "t1",
                "description": "T1",
                "module": "m1",
                "fixed_args": {"a": "1"},
            },
            {
                "name": "t2",
                "description": "T2",
                "module": "m2",
                "agent_args": {"b": {"type": "string"}},
            },
        ]
        tools, tracker = build_tools(tool_defs, mock_execute)
        assert len(tools) == 2
        assert tools[0].name == "t1"
        assert tools[1].name == "t2"
