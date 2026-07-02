from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from inspect import Parameter, Signature
from typing import Any
from urllib.parse import unquote, urlparse

from fastmcp import FastMCP
from fastmcp.server.context import Context as FastMCPContext
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse

from playwright_python_mcp.backend import BrowserBackend
from playwright_python_mcp.backend.tools import filtered_tools
from playwright_python_mcp.mcp.config import ServerConfig


@dataclass(slots=True)
class PlaywrightMCPServer:
    app: FastMCP
    config: ServerConfig

    def run(self) -> None:
        if self.config.server_port is None:
            self.app.run(transport="stdio", show_banner=False, log_level="ERROR")
            return
        self.app.run(
            transport="http",
            host=self.config.server_host or "localhost",
            port=self.config.server_port,
            show_banner=False,
            log_level="ERROR",
            middleware=_http_middleware(self.config),
        )


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

    return PlaywrightMCPServer(app=app, config=config)


class HostAllowlistMiddleware:
    def __init__(self, app: Any, allowed_hosts: list[str] | None, bind_host: str | None) -> None:
        self.app = app
        self.allowed_hosts = allowed_hosts or ([bind_host] if bind_host else ["localhost"])

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and "*" not in self.allowed_hosts:
            headers = dict(scope.get("headers") or [])
            host_header = headers.get(b"host", b"").decode("latin-1")
            host = host_header.rsplit(":", 1)[0] if ":" in host_header else host_header
            if host not in self.allowed_hosts:
                response = PlainTextResponse("Host is not allowed", status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _http_middleware(config: ServerConfig) -> list[Middleware]:
    return [Middleware(HostAllowlistMiddleware, allowed_hosts=config.allowed_hosts, bind_host=config.server_host)]


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
