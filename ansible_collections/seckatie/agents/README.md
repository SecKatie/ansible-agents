# seckatie.agents

[![Galaxy version](https://img.shields.io/badge/galaxy-seckatie.agents-blue)](https://galaxy.ansible.com/ui/repo/published/seckatie/agents/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)

Run AI agents inside Ansible playbooks. The agent thinks on the **controller**; tool calls execute Ansible modules on **target hosts** through the normal connection plugin.

Built on [Pydantic AI](https://ai.pydantic.dev/) -- works with OpenAI, Anthropic, Google Gemini, Ollama, and any other provider Pydantic AI supports.

## Features

- **Structured output** -- define a JSON Schema and get a validated dict back
- **Tool calling** -- the agent invokes Ansible modules you whitelist, with fixed and agent-controlled arguments
- **Conversation continuity** -- pass `message_history` between tasks to maintain context
- **Security by design** -- explicit tool whitelist, `fixed_args`/`agent_args` separation, `shlex.quote()` on template interpolation

## Installation

```bash
ansible-galaxy collection install seckatie.agents

# Python dependencies (on the controller)
pip install pydantic-ai pydantic
```

### macOS

On macOS you **must** set this before running playbooks:

```bash
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
```

Add it to `~/.zshrc` or `~/.bashrc`. This is a [known Ansible/macOS issue](https://docs.ansible.com/ansible/latest/reference_appendices/faq.html#running-on-macos-as-a-control-node). Alternatively, use the included wrapper: `bin/agent-playbook` (sets the variable for you).

## Quick Start

```yaml
---
- name: Ask an LLM a question
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Simple prompt
      seckatie.agents.agent:
        model: "anthropic:claude-sonnet-4-20250514"
        prompt: "What are three benefits of infrastructure as code?"
      register: result

    - debug:
        msg: "{{ result.output }}"
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `model` | str | yes | -- | LLM model in Pydantic AI format (`anthropic:claude-sonnet-4-20250514`, `openai:gpt-4o`, `google-gla:gemini-2.0-flash`) |
| `system_prompt` | str | no | `""` | System prompt for the agent |
| `prompt` | str | yes | -- | User prompt |
| `output_schema` | dict or str | no | -- | JSON Schema for structured output (inline dict or file path to `.json`/`.yaml`/`.yml`) |
| `message_history` | raw | no | -- | Message history from a previous run (for conversation continuity) |
| `tools` | list | no | `[]` | Tool definitions (see below) |
| `max_tool_calls` | int | no | `25` | Maximum tool calls the agent may make |
| `model_settings` | dict | no | -- | Provider settings (`temperature`, `max_tokens`, etc.) |

## Return Values

| Key | Type | Description |
|---|---|---|
| `output` | raw | Dict if `output_schema` was used, string otherwise |
| `message_history` | raw | Pass to a subsequent task's `message_history` for continuity |
| `usage` | dict | `input_tokens`, `output_tokens`, `requests`, `tool_calls` |
| `model` | str | Model that was used |
| `run_id` | str | Pydantic AI run identifier |
| `changed` | bool | `true` if any tool call reported a change |

## Tool Definitions

Each entry in `tools` is a dict:

| Key | Type | Required | Description |
|---|---|---|---|
| `name` | str | yes | Name shown to the LLM |
| `description` | str | yes | Tells the LLM when and how to use the tool |
| `module` | str | yes | Fully qualified Ansible module name |
| `fixed_args` | dict | no | Arguments locked by the playbook author (LLM cannot change) |
| `agent_args` | dict | no | Arguments the LLM controls, defined as JSON Schema properties |
| `run_on` | str | no | `target` (default) or `controller` |

`fixed_args` support `{{ placeholder }}` templates that are filled from `agent_args` values and shell-escaped with `shlex.quote()`.

## Examples

The [`examples/`](examples/) directory contains complete playbooks:

| Playbook | What it shows |
|---|---|
| [`simple_prompt.yml`](examples/simple_prompt.yml) | Plain-text LLM response with usage stats |
| [`structured_output.yml`](examples/structured_output.yml) | JSON Schema output for log analysis |
| [`tool_calling.yml`](examples/tool_calling.yml) | Agent calls `df -h` and `free -h` modules, returns structured summary |
| [`conversation_continuity.yml`](examples/conversation_continuity.yml) | Two-task conversation passing `message_history` |

## Security

See [SECURITY.md](SECURITY.md) for the full threat model, controls, and recommendations.

Key principles: explicit tool whitelist, `fixed_args`/`agent_args` separation, schema constraints (`enum`, `pattern`, `minimum`/`maximum`), and shell-safe template interpolation.

## API Keys

Set the environment variable for your provider:

```bash
export ANTHROPIC_API_KEY="sk-..."   # Anthropic
export OPENAI_API_KEY="sk-..."      # OpenAI
export GOOGLE_API_KEY="..."         # Google Gemini
```

Or use Ansible Vault to inject them.

## License

[Apache License 2.0](LICENSE)
