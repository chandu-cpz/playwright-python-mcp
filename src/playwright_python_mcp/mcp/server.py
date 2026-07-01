from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastmcp import FastMCP
from fastmcp.tools.base import ToolResult

from playwright_python_mcp.backend import BrowserBackend
from playwright_python_mcp.mcp.config import ServerConfig
from playwright_python_mcp.tools.registry import (
    CORE_TOOL_NAMES,
    PDF_TOOL_NAMES,
    TESTING_TOOL_NAMES,
    VISION_TOOL_NAMES,
)


Button = Literal["left", "middle", "right"]
Modifier = Literal["Alt", "Control", "ControlOrMeta", "Meta", "Shift"]


@dataclass(slots=True)
class PlaywrightMCPServer:
    app: FastMCP

    def run(self) -> None:
        self.app.run(transport="stdio", show_banner=False, log_level="ERROR")


def create_server(config: ServerConfig) -> PlaywrightMCPServer:
    backend = BrowserBackend(config)
    app = FastMCP(name="Playwright", version="0.1.0")

    def add_placeholder(name: str) -> None:
        @app.tool(name=name)
        async def _placeholder() -> ToolResult:
            return ToolResult(
                content=f"### Error\nTool \"{name}\" is not implemented yet.",
                is_error=True,
            )

    @app.tool(name="browser_snapshot")
    async def browser_snapshot(
        target: str | None = None,
        depth: int | None = None,
        boxes: bool | None = None,
    ) -> str | ToolResult:
        return await backend.browser_snapshot(target=target, depth=depth, boxes=boxes)

    @app.tool(name="browser_navigate")
    async def browser_navigate(url: str) -> ToolResult | str:
        return await backend.browser_navigate(url=url)

    @app.tool(name="browser_navigate_back")
    async def browser_navigate_back() -> str | ToolResult:
        return await backend.browser_navigate_back()

    @app.tool(name="browser_click")
    async def browser_click(
        target: str,
        element: str | None = None,
        doubleClick: bool = False,
        button: Button | None = None,
        modifiers: list[Modifier] | None = None,
    ) -> str | ToolResult:
        return await backend.browser_click(
            target=target,
            element=element,
            double_click=doubleClick,
            button=button,
            modifiers=modifiers,
        )

    @app.tool(name="browser_select_option")
    async def browser_select_option(
        target: str,
        values: list[str],
        element: str | None = None,
    ) -> str | ToolResult:
        return await backend.browser_select_option(target=target, values=values, element=element)

    @app.tool(name="browser_hover")
    async def browser_hover(target: str, element: str | None = None) -> str | ToolResult:
        return await backend.browser_hover(target=target, element=element)

    @app.tool(name="browser_drag")
    async def browser_drag(
        startTarget: str,
        endTarget: str,
        startElement: str | None = None,
        endElement: str | None = None,
    ) -> str | ToolResult:
        return await backend.browser_drag(
            start_target=startTarget,
            end_target=endTarget,
            start_element=startElement,
            end_element=endElement,
        )

    @app.tool(name="browser_evaluate")
    async def browser_evaluate(
        function: str,
        target: str | None = None,
        element: str | None = None,
        filename: str | None = None,
    ) -> str | ToolResult:
        return await backend.browser_evaluate(
            function=function,
            target=target,
            element=element,
            filename=filename,
        )

    @app.tool(name="browser_press_key")
    async def browser_press_key(key: str) -> str | ToolResult:
        return await backend.browser_press_key(key=key)

    @app.tool(name="browser_type")
    async def browser_type(
        target: str,
        text: str,
        element: str | None = None,
        submit: bool = False,
        slowly: bool = False,
    ) -> str | ToolResult:
        return await backend.browser_type(
            target=target,
            text=text,
            element=element,
            submit=submit,
            slowly=slowly,
        )

    @app.tool(name="browser_fill_form")
    async def browser_fill_form(fields: list[dict[str, str]]) -> str | ToolResult:
        return await backend.browser_fill_form(fields=fields)

    @app.tool(name="browser_console_messages")
    async def browser_console_messages() -> str | ToolResult:
        return await backend.browser_console_messages()

    @app.tool(name="browser_resize")
    async def browser_resize(width: int, height: int) -> str | ToolResult:
        return await backend.browser_resize(width=width, height=height)

    @app.tool(name="browser_close")
    async def browser_close() -> str | ToolResult:
        return await backend.browser_close()

    implemented = {
        "browser_snapshot",
        "browser_navigate",
        "browser_navigate_back",
        "browser_click",
        "browser_drag",
        "browser_evaluate",
        "browser_hover",
        "browser_console_messages",
        "browser_fill_form",
        "browser_press_key",
        "browser_select_option",
        "browser_type",
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

    if config.caps and "testing" in config.caps:
        @app.tool(name="browser_generate_locator")
        async def browser_generate_locator(target: str, element: str | None = None) -> str | ToolResult:
            return await backend.browser_generate_locator(target=target, element=element)

        implemented.add("browser_generate_locator")

        for tool_name in TESTING_TOOL_NAMES:
            if tool_name not in implemented:
                add_placeholder(tool_name)

    return PlaywrightMCPServer(app=app)
