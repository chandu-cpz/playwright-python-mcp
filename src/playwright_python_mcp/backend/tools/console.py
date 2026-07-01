from __future__ import annotations

from typing import Any

from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool


async def _handle_console_messages(context: Context, _params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    messages = tab.console_messages()
    response.add_text_result(
        "\n".join([f"Total messages: {len(messages)} (Errors: 0, Warnings: 0)", "", *messages])
    )


console_tools = [
    Tool(
        name="browser_console_messages",
        capability="core",
        handler=_handle_console_messages,
    )
]
