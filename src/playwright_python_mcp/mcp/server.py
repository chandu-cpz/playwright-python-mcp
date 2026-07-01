from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastmcp import FastMCP
from fastmcp.tools.base import ToolResult

from playwright_python_mcp.backend import BrowserSession, Response, render_tabs_markdown
from playwright_python_mcp.backend.codegen import python_call, python_dict, python_invocation, python_literal
from playwright_python_mcp.mcp.config import ServerConfig
from playwright_python_mcp.tools.registry import CORE_TOOL_NAMES, PDF_TOOL_NAMES, VISION_TOOL_NAMES


Button = Literal["left", "middle", "right"]
Modifier = Literal["Alt", "Control", "ControlOrMeta", "Meta", "Shift"]


@dataclass(slots=True)
class PlaywrightMCPServer:
    app: FastMCP

    def run(self) -> None:
        self.app.run(transport="stdio", show_banner=False, log_level="ERROR")


def create_server(config: ServerConfig) -> PlaywrightMCPServer:
    session = BrowserSession(
        browser_name=config.browser,
        headless=config.headless,
        allow_unrestricted_file_access=config.allow_unrestricted_file_access,
        test_id_attribute=config.test_id_attribute,
    )
    app = FastMCP(name="Playwright", version="0.1.0")

    def add_placeholder(name: str) -> None:
        @app.tool(name=name)
        async def _placeholder() -> ToolResult:
            return ToolResult(
                content=f"### Error\nTool \"{name}\" is not implemented yet.",
                is_error=True,
            )

    async def run_tool(handler) -> str | ToolResult:
        response = Response(session)
        try:
            await handler(response)
            return await response.serialize()
        except ValueError as exc:
            return ToolResult(content=f"### Error\n{exc}", is_error=True)

    @app.tool(name="browser_snapshot")
    async def browser_snapshot(
        target: str | None = None,
        depth: int | None = None,
        boxes: bool | None = None,
    ) -> str | ToolResult:
        async def handler(response: Response) -> None:
            response.set_include_full_snapshot(target=target, depth=depth, boxes=boxes)

        return await run_tool(handler)

    @app.tool(name="browser_navigate")
    async def browser_navigate(url: str) -> ToolResult | str:
        async def handler(response: Response) -> None:
            resolved_url = await session.check_url_and_navigate(url)
            response.set_include_snapshot()
            response.add_code(f"await page.goto({python_literal(resolved_url)})")

        return await run_tool(handler)

    @app.tool(name="browser_navigate_back")
    async def browser_navigate_back() -> str | ToolResult:
        async def handler(response: Response) -> None:
            await session.go_back()
            response.set_include_snapshot()
            response.add_code("await page.go_back()")

        return await run_tool(handler)

    @app.tool(name="browser_click")
    async def browser_click(
        target: str,
        element: str | None = None,
        doubleClick: bool = False,
        button: Button | None = None,
        modifiers: list[Modifier] | None = None,
    ) -> str | ToolResult:
        async def handler(response: Response) -> None:
            resolved = await session.resolve_target(target=target, element=element)
            await session.click(
                resolved,
                double_click=doubleClick,
                button=button,
                modifiers=modifiers,
            )
            response.set_include_snapshot()
            action = "dblclick" if doubleClick else "click"
            options: list[tuple[str, object]] = []
            if button is not None:
                options.append(("button", button))
            if modifiers is not None:
                options.append(("modifiers", modifiers))
            response.add_code(python_invocation(resolved.code, action, options or None))

        return await run_tool(handler)

    @app.tool(name="browser_select_option")
    async def browser_select_option(
        target: str,
        values: list[str],
        element: str | None = None,
    ) -> str | ToolResult:
        async def handler(response: Response) -> None:
            resolved = await session.resolve_target(target=target, element=element)
            await session.select_option(resolved, values=values)
            response.set_include_snapshot()
            response.add_code(python_call(resolved.code, "select_option", values))

        return await run_tool(handler)

    @app.tool(name="browser_resize")
    async def browser_resize(width: int, height: int) -> str | ToolResult:
        async def handler(response: Response) -> None:
            await session.resize(width=width, height=height)
            response.add_code(
                f"await page.set_viewport_size({python_dict([('width', width), ('height', height)])})"
            )

        return await run_tool(handler)

    @app.tool(name="browser_close")
    async def browser_close() -> str | ToolResult:
        async def handler(response: Response) -> None:
            await session.close()
            response.add_text_result("\n".join(render_tabs_markdown([])))
            response.add_code("await page.close()")
            response.set_close()

        return await run_tool(handler)

    implemented = {
        "browser_snapshot",
        "browser_navigate",
        "browser_navigate_back",
        "browser_click",
        "browser_select_option",
        "browser_resize",
        "browser_close",
    }

    for tool_name in CORE_TOOL_NAMES:
        if tool_name not in implemented:
            add_placeholder(tool_name)

    if config.caps and "pdf" in config.caps:
        for tool_name in PDF_TOOL_NAMES:
            add_placeholder(tool_name)

    if config.caps and "vision" in config.caps:
        for tool_name in VISION_TOOL_NAMES:
            add_placeholder(tool_name)

    return PlaywrightMCPServer(app=app)
