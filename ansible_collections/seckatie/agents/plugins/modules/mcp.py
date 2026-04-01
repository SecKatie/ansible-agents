#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2024, seckatie
# Apache License 2.0 (see LICENSE)

DOCUMENTATION = r"""
---
module: mcp
short_description: Interact with MCP servers directly from Ansible
version_added: "0.2.0"
description:
  - Connects to an MCP (Model Context Protocol) server and performs operations
    without requiring an LLM agent.
  - Supports calling tools, listing tools, reading resources, listing resources,
    getting prompts, and listing prompts.
  - Uses the same server configuration format as the C(mcp_servers) parameter
    on the C(seckatie.agents.agent) module.
  - "Requires the mcp package: C(pip install 'pydantic-ai-slim[mcp]')."
options:
  server:
    description:
      - MCP server configuration object.
      - Must include C(type) (C(stdio), C(sse), or C(streamable_http)) and transport-specific params.
      - "Common options: C(tool_prefix), C(timeout), C(read_timeout)."
      - "Optional C(tools) field for per-tool C(changed) overrides."
    type: dict
    required: true
  action:
    description:
      - The MCP operation to perform.
    type: str
    required: true
    choices:
      - call_tool
      - list_tools
      - read_resource
      - list_resources
      - get_prompt
      - list_prompts
  tool_name:
    description:
      - Name of the tool to call. Required when C(action=call_tool).
    type: str
    required: false
  arguments:
    description:
      - Arguments to pass to the tool. Used with C(action=call_tool).
    type: dict
    required: false
    default: {}
  uri:
    description:
      - URI of the resource to read. Required when C(action=read_resource).
    type: str
    required: false
  prompt_name:
    description:
      - Name of the prompt to retrieve. Required when C(action=get_prompt).
    type: str
    required: false
  prompt_arguments:
    description:
      - Arguments to pass when rendering a prompt. Used with C(action=get_prompt).
    type: dict
    required: false
    default: {}
author:
  - seckatie
"""

EXAMPLES = r"""
- name: List available tools
  seckatie.agents.mcp:
    server:
      type: stdio
      command: "uvx"
      args: ["mcp-server-fetch"]
    action: list_tools
  register: tools_result

- name: Call a tool
  seckatie.agents.mcp:
    server:
      type: stdio
      command: "uvx"
      args: ["mcp-server-fetch"]
      tools:
        - name: fetch
          changed: false
    action: call_tool
    tool_name: fetch
    arguments:
      url: "https://example.com"
  register: fetch_result

- name: List resources
  seckatie.agents.mcp:
    server:
      type: sse
      url: "http://localhost:8080/sse"
    action: list_resources
  register: resources

- name: Read a resource
  seckatie.agents.mcp:
    server:
      type: sse
      url: "http://localhost:8080/sse"
    action: read_resource
    uri: "file:///data/config.yaml"
  register: resource_content

- name: List prompts
  seckatie.agents.mcp:
    server:
      type: streamable_http
      url: "http://localhost:8080/mcp"
    action: list_prompts
  register: prompts

- name: Get a rendered prompt
  seckatie.agents.mcp:
    server:
      type: streamable_http
      url: "http://localhost:8080/mcp"
    action: get_prompt
    prompt_name: code_review
    prompt_arguments:
      language: python
  register: prompt_content
"""

RETURN = r"""
output:
  description: The result of the MCP operation. Structure varies by action.
  returned: success
  type: raw
changed:
  description: >
    Whether the operation caused a change. Always false for read-only actions.
    For call_tool, defaults to true unless overridden by server config.
  returned: success
  type: bool
"""

from ansible.module_utils.basic import AnsibleModule


def main():
    module = AnsibleModule(
        argument_spec=dict(
            server=dict(type="dict", required=True),
            action=dict(
                type="str",
                required=True,
                choices=[
                    "call_tool",
                    "list_tools",
                    "read_resource",
                    "list_resources",
                    "get_prompt",
                    "list_prompts",
                ],
            ),
            tool_name=dict(type="str", required=False, default=None),
            arguments=dict(type="dict", required=False, default={}),
            uri=dict(type="str", required=False, default=None),
            prompt_name=dict(type="str", required=False, default=None),
            prompt_arguments=dict(type="dict", required=False, default={}),
        ),
        supports_check_mode=False,
    )

    # This module is implemented as an action plugin.
    module.fail_json(
        msg="This module must be run as an action plugin on the controller. "
        "If you see this message, the action plugin was not found."
    )


if __name__ == "__main__":
    main()
