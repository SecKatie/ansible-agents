"""MCP action execution logic — no Ansible dependencies."""

from __future__ import annotations

from typing import Any


async def execute_mcp_action(
    session: Any,
    action: str,
    tool_name: str | None,
    arguments: dict[str, Any],
    uri: str | None,
    prompt_name: str | None,
    prompt_arguments: dict[str, Any],
) -> Any:
    """Execute an MCP action on an established session.

    Args:
        session: An MCP ClientSession.
        action: The action to perform.
        tool_name: Tool name for call_tool.
        arguments: Arguments for call_tool.
        uri: URI for read_resource.
        prompt_name: Prompt name for get_prompt.
        prompt_arguments: Arguments for get_prompt.

    Returns:
        The action result in a JSON-safe structure.
    """
    if action == "call_tool":
        result = await session.call_tool(tool_name, arguments=arguments)
        return serialize_tool_result(result)

    elif action == "list_tools":
        result = await session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
            }
            for tool in result.tools
        ]

    elif action == "read_resource":
        result = await session.read_resource(uri)
        contents = []
        for content in result.contents:
            item = {"uri": str(content.uri)}
            if hasattr(content, "text") and content.text is not None:
                item["text"] = content.text
            if hasattr(content, "mimeType") and content.mimeType is not None:
                item["mimeType"] = content.mimeType
            contents.append(item)
        return contents

    elif action == "list_resources":
        result = await session.list_resources()
        return [
            {
                "uri": str(resource.uri),
                "name": resource.name or "",
                "description": resource.description or "",
                "mimeType": getattr(resource, "mimeType", None) or "",
            }
            for resource in result.resources
        ]

    elif action == "get_prompt":
        result = await session.get_prompt(prompt_name, arguments=prompt_arguments)
        messages = []
        for msg in result.messages:
            message = {"role": msg.role}
            if hasattr(msg.content, "text"):
                message["content"] = msg.content.text
            else:
                message["content"] = str(msg.content)
            messages.append(message)
        return {"description": result.description or "", "messages": messages}

    elif action == "list_prompts":
        result = await session.list_prompts()
        return [
            {
                "name": prompt.name,
                "description": prompt.description or "",
                "arguments": [
                    {
                        "name": arg.name,
                        "description": arg.description or "",
                        "required": arg.required if hasattr(arg, "required") else False,
                    }
                    for arg in (prompt.arguments or [])
                ],
            }
            for prompt in result.prompts
        ]

    else:
        raise ValueError(f"Unknown action: {action}")


def serialize_tool_result(result: Any) -> Any:
    """Serialize an MCP CallToolResult to a JSON-safe structure."""
    if hasattr(result, "content") and result.content:
        parts = []
        for content in result.content:
            if hasattr(content, "text"):
                parts.append({"type": "text", "text": content.text})
            elif hasattr(content, "data"):
                parts.append({"type": "blob", "data": content.data})
            else:
                parts.append({"type": "unknown", "value": str(content)})
        if len(parts) == 1 and parts[0].get("type") == "text":
            return parts[0]["text"]
        return parts
    return None
