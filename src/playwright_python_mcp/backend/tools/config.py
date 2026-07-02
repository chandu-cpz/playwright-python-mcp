from __future__ import annotations

import json
from typing import Any

from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool


async def _handle_get_config(context: Context, _params: dict[str, Any], response: Response) -> None:
    response.add_text_result(json.dumps(context.config.as_public_dict(), indent=2))


config_tools = [
    Tool(name="browser_get_config", capability="config", handler=_handle_get_config),
]
