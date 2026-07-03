from __future__ import annotations

import signal
from dataclasses import dataclass, field
from functools import wraps
from importlib.metadata import PackageNotFoundError, version
from inspect import Parameter, Signature
from typing import Any, Literal
from urllib.parse import unquote, urlparse

import anyio
from fastmcp import FastMCP
from fastmcp.server.context import Context as FastMCPContext
from mcp.types import ToolAnnotations
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from playwright_python_mcp.backend import BrowserBackend
from playwright_python_mcp.backend.tools import filtered_tools
from playwright_python_mcp.mcp.config import ServerConfig


@dataclass(slots=True)
class PlaywrightMCPServer:
    app: FastMCP
    config: ServerConfig
    backend: BrowserBackend
    _cancel_scope: anyio.CancelScope | None = field(default=None, init=False)

    def trigger_shutdown(self) -> None:
        if self._cancel_scope is not None:
            self._cancel_scope.cancel()

    def run(self) -> None:
        anyio.run(self.run_async)

    async def run_async(self) -> None:
        if self.config.server_port is None:
            await self._run_with_watchdog("stdio", show_banner=False, log_level="ERROR")
            return
        await self._run_with_watchdog(
            "http",
            host=self.config.server_host or "localhost",
            port=self.config.server_port,
            show_banner=False,
            log_level="ERROR",
            middleware=_http_middleware(self.config),
        )

    async def _run_with_watchdog(
        self,
        transport: Literal["stdio", "http", "sse", "streamable-http"],
        **transport_kwargs: Any,
    ) -> None:
        async def watch_signals(scope: anyio.CancelScope) -> None:
            with anyio.open_signal_receiver(signal.SIGINT, signal.SIGTERM) as signals:
                async for _signum in signals:
                    scope.cancel()
                    return

        with anyio.CancelScope() as scope:
            self._cancel_scope = scope
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(watch_signals, scope)
                try:
                    await self.app.run_async(transport=transport, **transport_kwargs)
                finally:
                    task_group.cancel_scope.cancel()
                    await _close_backend_with_timeout(self.backend)


def create_server(config: ServerConfig) -> PlaywrightMCPServer:
    tools = filtered_tools(config)
    backend = BrowserBackend(config, tools)
    app = FastMCP(name="Playwright", version=_package_version())

    for tool in tools:
        read_only = tool.tool_type in {"readOnly", "assertion"}
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
        app.tool(
            name=tool.name,
            title=tool.title or _title_from_name(tool.name),
            description=tool.description or tool.name,
            annotations=ToolAnnotations(
                readOnlyHint=read_only,
                destructiveHint=not read_only,
                openWorldHint=True,
            ),
            run_in_thread=False,
        )(handler)

    server = PlaywrightMCPServer(app=app, config=config, backend=backend)
    _register_kill_endpoint(app, server)
    return server


def _register_kill_endpoint(app: FastMCP, server: PlaywrightMCPServer) -> None:
    @app.custom_route("/killkillkill", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])  # type: ignore[arg-type]
    async def _handle_kill(request: Request) -> PlainTextResponse:
        if request.method != "POST" or request.headers.get("x-pw-mcp-kill") != "1":
            return PlainTextResponse("", status_code=405)
        server.trigger_shutdown()
        return PlainTextResponse("Killing process", status_code=200)


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


def _title_from_name(name: str) -> str:
    return name.removeprefix("browser_").replace("_", " ").title()


def _package_version() -> str:
    try:
        return version("playwright-python-mcp")
    except PackageNotFoundError:
        return "0.0.0"


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


async def _close_backend_with_timeout(backend: BrowserBackend) -> None:
    with anyio.move_on_after(15, shield=True):
        await backend.close()
