# Changelog

## 0.1.0 (2026-03-30)

Initial release.

- `seckatie.agents.agent` module — run a Pydantic AI agent as an Ansible task
- Structured output via JSON Schema (`output_schema`)
- Tool calling — agents invoke Ansible modules on target hosts
- Controller-side tool execution (`run_on: controller`)
- Conversation continuity via `message_history`
- Template interpolation in `fixed_args` with `shlex.quote()` shell safety
- macOS fork safety callback plugin and wrapper script
