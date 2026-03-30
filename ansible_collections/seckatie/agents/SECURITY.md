# Security Model

The `seckatie.agents.agent` module allows an LLM to execute Ansible modules as tools during its run. This document describes the security model and the controls available to playbook authors.

## Threat Model

The primary risk is that an LLM, given access to tools, may execute actions that the playbook author did not intend. The security model is designed to give the playbook author full control over what the agent can do.

## Controls

### 1. Explicit Tool Whitelisting

The agent can **only** call modules that are explicitly listed in the `tools` parameter. There is no auto-discovery of available modules. If `tools` is omitted or empty, the agent has no tools and can only return text/structured output.

### 2. fixed_args vs agent_args Separation

Each tool definition separates arguments into two categories:

- **`fixed_args`**: Set by the playbook author. The LLM never sees these values and cannot modify them. They are merged into the final module arguments at execution time, overriding any LLM-provided values with the same key.

- **`agent_args`**: Controlled by the LLM. These are defined as JSON Schema properties, and the LLM provides values at runtime. Pydantic AI validates the LLM's values against the schema before execution.

### 3. Schema Constraints on agent_args

Use JSON Schema constraints to limit what the LLM can provide:

- **`enum`**: Restrict to a fixed set of values (strongest constraint)
  ```yaml
  agent_args:
    log_file:
      type: string
      enum: ["/var/log/syslog", "/var/log/nginx/error.log"]
  ```

- **`pattern`**: Restrict to values matching a regex
  ```yaml
  agent_args:
    service_name:
      type: string
      pattern: "^[a-zA-Z0-9_-]+$"
  ```

- **`minimum` / `maximum`**: Restrict numeric ranges
  ```yaml
  agent_args:
    lines:
      type: integer
      minimum: 1
      maximum: 1000
  ```

- **`minLength` / `maxLength`**: Restrict string length

### 4. Template Interpolation with shlex.quote()

When `fixed_args` values contain `{{ placeholder }}` patterns, the placeholders are replaced with values from `agent_args`, wrapped in `shlex.quote()` to prevent shell injection.

```yaml
tools:
  - name: read_log
    module: ansible.builtin.command
    fixed_args:
      cmd: "tail -{{ lines }} {{ path }}"
    agent_args:
      lines:
        type: integer
        minimum: 1
        maximum: 1000
      path:
        type: string
        enum: ["/var/log/syslog", "/var/log/nginx/error.log"]
```

Even if the LLM provides a malicious value (e.g., `path: "/tmp; rm -rf /"`), `shlex.quote()` neutralizes shell metacharacters: the resulting command would be `tail -100 '/tmp; rm -rf /'`.

### 5. Error Passthrough (Not Failure)

When an Ansible module called as a tool returns `failed: true`, the failure is **returned to the LLM** as the tool's return value — it does not fail the Ansible task. This lets the LLM adapt to failures. The agent task itself only fails on LLM API errors, usage limit exceeded, or output schema validation failure.

## Risk Matrix

| Scenario | Risk | Mitigation |
|---|---|---|
| LLM calls destructive module | High | Explicit whitelist — only listed modules are callable |
| LLM provides malicious arg values | Medium | JSON Schema constraints (enum, pattern, min/max) + shlex.quote() |
| LLM makes too many tool calls | Low | `max_tool_calls` parameter (default: 25) |
| Unconstrained string agent_arg | **High** | **Author responsibility** — if you allow free-form strings as module args, the LLM can pass anything that the module accepts |

## Recommendations

1. **Prefer `enum` over free-form strings** for `agent_args` whenever possible
2. **Use `pattern` constraints** for string args that must follow a format
3. **Use `fixed_args` for all security-sensitive values** (paths, states, credentials)
4. **Use template interpolation** for command-line tools to get automatic shell escaping
5. **Set `max_tool_calls`** to a reasonable limit for your use case
6. **Review tool definitions carefully** — the security posture is only as strong as the constraints you define
