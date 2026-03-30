#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2024, seckatie
# Apache License 2.0 (see LICENSE)

DOCUMENTATION = r"""
---
module: agent
short_description: Run a Pydantic AI agent as an Ansible task
version_added: "0.1.0"
description:
  - Runs a Pydantic AI agent on the Ansible controller.
  - Supports structured output via JSON Schema, tool calling via Ansible modules,
    and conversation continuity via message history.
  - The agent runs on the controller while tool calls execute modules on target hosts.
options:
  model:
    description:
      - The LLM model to use in Pydantic AI format.
      - "Examples: C(anthropic:claude-sonnet-4-20250514), C(openai:gpt-4o), C(ollama:llama3)."
    type: str
    required: true
  system_prompt:
    description:
      - The system prompt that gives the agent context and instructions.
    type: str
    required: false
    default: ""
  prompt:
    description:
      - The user prompt to send to the agent.
    type: str
    required: true
  output_schema:
    description:
      - A JSON Schema dict defining the expected structured output, or a file path
        (string) to a C(.json) or C(.yaml)/C(.yml) file containing a JSON Schema.
      - When provided, the agent returns a dict conforming to this schema.
      - When omitted, the agent returns plain text.
      - File paths are resolved relative to the playbook directory if not absolute.
    type: raw
    required: false
  message_history:
    description:
      - Serialized Pydantic AI message history from a previous agent run.
      - Pass the C(message_history) field from a previous result to continue a conversation.
    type: raw
    required: false
  tools:
    description:
      - List of tool definitions the agent can call during its run.
      - Each tool has C(name), C(description), C(module) (FQCN), optional C(fixed_args), optional C(agent_args), and optional C(run_on).
      - Set C(run_on) to C(controller) to execute the tool on the Ansible controller instead of the target host.
    type: list
    elements: dict
    required: false
    default: []
  max_tool_calls:
    description:
      - Maximum number of tool calls the agent is allowed to make.
    type: int
    required: false
    default: 25
  model_settings:
    description:
      - Optional model settings dict (e.g., C(temperature), C(max_tokens), C(top_p)).
    type: dict
    required: false
author:
  - seckatie
"""

EXAMPLES = r"""
- name: Simple prompt
  seckatie.agents.agent:
    model: "anthropic:claude-sonnet-4-20250514"
    system_prompt: "You are a helpful assistant."
    prompt: "What is the capital of France?"
  register: result

- name: Structured output
  seckatie.agents.agent:
    model: "openai:gpt-4o"
    system_prompt: "Analyze the given log line."
    prompt: "ERROR 2024-01-15 disk full on /dev/sda1"
    output_schema:
      type: object
      properties:
        severity:
          type: string
          enum: [info, warning, error, critical]
        summary:
          type: string
        action:
          type: string
      required: [severity, summary]
  register: analysis

- name: Structured output from file
  seckatie.agents.agent:
    model: "openai:gpt-4o"
    system_prompt: "Analyze the given log line."
    prompt: "ERROR 2024-01-15 disk full on /dev/sda1"
    output_schema: "schemas/log_analysis.json"
  register: analysis

- name: Tool calling
  seckatie.agents.agent:
    model: "anthropic:claude-sonnet-4-20250514"
    system_prompt: "You are a system administrator. Use tools to investigate."
    prompt: "Check disk usage on this host."
    tools:
      - name: check_disk
        description: "Check disk usage"
        module: ansible.builtin.command
        fixed_args:
          cmd: "df -h"
  register: result

- name: Conversation continuity
  seckatie.agents.agent:
    model: "anthropic:claude-sonnet-4-20250514"
    system_prompt: "You are a helpful assistant."
    prompt: "What did I just ask you about?"
    message_history: "{{ previous_result.message_history }}"
  register: result
"""

RETURN = r"""
output:
  description: The agent's output - structured dict if output_schema was provided, plain text string otherwise.
  returned: success
  type: raw
message_history:
  description: Serialized Pydantic AI message history for conversation continuity.
  returned: success
  type: raw
usage:
  description: Token usage statistics.
  returned: success
  type: dict
  contains:
    input_tokens:
      description: Number of input tokens used.
      type: int
    output_tokens:
      description: Number of output tokens used.
      type: int
    requests:
      description: Number of requests made to the model.
      type: int
    tool_calls:
      description: Number of tool calls made.
      type: int
model:
  description: The model string that was used.
  returned: success
  type: str
run_id:
  description: The Pydantic AI run identifier.
  returned: success
  type: str
changed:
  description: Whether any tool call resulted in a change on the target.
  returned: success
  type: bool
"""

from ansible.module_utils.basic import AnsibleModule


def main():
    module = AnsibleModule(
        argument_spec=dict(
            model=dict(type="str", required=True),
            system_prompt=dict(type="str", required=False, default=""),
            prompt=dict(type="str", required=True),
            output_schema=dict(type="raw", required=False, default=None),
            message_history=dict(type="raw", required=False, default=None),
            tools=dict(type="list", elements="dict", required=False, default=[]),
            max_tool_calls=dict(type="int", required=False, default=25),
            model_settings=dict(type="dict", required=False, default=None),
        ),
        supports_check_mode=False,
    )

    # This module is implemented as an action plugin.
    # The module stub exists for argument validation and documentation.
    module.fail_json(
        msg="This module must be run as an action plugin on the controller. "
        "If you see this message, the action plugin was not found."
    )


if __name__ == "__main__":
    main()
