from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Any

from fastmcp import FastMCP

from playwright_python_mcp.backend import BrowserBackend
from playwright_python_mcp.backend.tools import filtered_tools
from playwright_python_mcp.mcp.config import ServerConfig


@dataclass(slots=True)
class PlaywrightMCPServer:
    app: FastMCP

    def run(self) -> None:
        self.app.run(transport="stdio", show_banner=False, log_level="ERROR")


def create_server(config: ServerConfig) -> PlaywrightMCPServer:
    tools = filtered_tools(config)
    backend = BrowserBackend(config, tools)
    app = FastMCP(name="Playwright", version="0.1.0")

    for tool in tools:
        handler = _make_fastmcp_handler(backend, tool.name)
        handler.__signature__ = tool.signature()
        handler.__annotations__ = {parameter.name: parameter.annotation for parameter in tool.parameters}
        handler.__annotations__["return"] = Any
        app.tool(name=tool.name)(handler)

    return PlaywrightMCPServer(app=app)


def _make_fastmcp_handler(backend: BrowserBackend, tool_name: str):
    @wraps(_tool_handler)
    async def handler(**kwargs: Any):
        return await backend.call_tool(tool_name, kwargs)

    return handler


async def _tool_handler(**_kwargs: Any):
    raise RuntimeError("unreachable")
