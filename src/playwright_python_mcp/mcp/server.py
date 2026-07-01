from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from inspect import Parameter, Signature
from typing import Any
from urllib.parse import unquote, urlparse

from fastmcp import FastMCP
from fastmcp.server.context import Context as FastMCPContext

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
        signature = tool.signature()
        handler.__signature__ = Signature(
            parameters=[
                *signature.parameters.values(),
                Parameter("ctx", Parameter.KEYWORD_ONLY, annotation=FastMCPContext),
            ]
        )
        handler.__annotations__ = {parameter.name: parameter.annotation for parameter in tool.parameters}
        handler.__annotations__["ctx"] = FastMCPContext
        handler.__annotations__["return"] = Any
        app.tool(name=tool.name)(handler)

    return PlaywrightMCPServer(app=app)


def _make_fastmcp_handler(backend: BrowserBackend, tool_name: str):
    @wraps(_tool_handler)
    async def handler(**kwargs: Any):
        ctx = kwargs.pop("ctx", None)
        roots = await _list_roots(ctx)
        return await backend.call_tool(tool_name, kwargs, roots=roots)

    return handler


async def _tool_handler(**_kwargs: Any):
    raise RuntimeError("unreachable")


async def _list_roots(ctx: FastMCPContext | None) -> list[str] | None:
    if ctx is None:
        return None
    try:
        roots = await ctx.list_roots()
    except Exception:
        return None
    result: list[str] = []
    for root in roots:
        uri = str(root.uri)
        if uri.startswith("file://"):
            result.append(unquote(urlparse(uri).path))
    return result
