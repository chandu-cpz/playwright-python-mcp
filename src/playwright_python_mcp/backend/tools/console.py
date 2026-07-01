from __future__ import annotations

from typing import Any

from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool, param


async def _handle_console_messages(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    level = params.get("level", "info")
    count = tab.console_message_count()
    header = [f"Total messages: {count['total']} (Errors: {count['errors']}, Warnings: {count['warnings']})"]
    messages = tab.console_messages(level=level, all_messages=params.get("all", False))
    if len(messages) != count["total"]:
        header.append(f'Returning {len(messages)} messages for level "{level}"')
    text = "\n".join([*header, "", *messages])
    await response.add_result(
        "Console",
        text,
        prefix="console",
        ext="log",
        suggested_filename=params.get("filename"),
    )


async def _handle_console_clear(context: Context, _params: dict[str, Any], _response: Response) -> None:
    tab = await context.ensure_tab()
    tab.clear_console_messages()


console_tools = [
    Tool(
        name="browser_console_messages",
        capability="core",
        parameters=(
            param("level", str, "info"),
            param("all", bool, False),
            param("filename", str | None, None),
        ),
        handler=_handle_console_messages,
    ),
    Tool(
        name="browser_console_clear",
        capability="core",
        handler=_handle_console_clear,
        skill_only=True,
    ),
]
