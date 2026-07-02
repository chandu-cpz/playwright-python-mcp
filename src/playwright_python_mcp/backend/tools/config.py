from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool


async def _handle_get_config(context: Context, _params: dict[str, Any], response: Response) -> None:
    response.add_text_result(json.dumps(_jsonable(asdict(context.config)), indent=2))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value


config_tools = [
    Tool(name="browser_get_config", capability="config", handler=_handle_get_config),
]
