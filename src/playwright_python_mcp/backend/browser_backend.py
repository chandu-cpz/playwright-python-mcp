from __future__ import annotations

import os
from typing import Any

from fastmcp.tools.base import ToolResult
from playwright.async_api import Browser, Playwright, async_playwright

from playwright_python_mcp.mcp.config import ServerConfig

from .context import Context
from .response import Response
from .tool import Tool


class BrowserBackend:
    """Thin browser backend dispatcher.

    Upstream responsibility:
    - packages/playwright-core/src/tools/backend/browserBackend.ts
    """

    def __init__(self, config: ServerConfig, tools: list[Tool]) -> None:
        self._config = config
        self._tools = {tool.name: tool for tool in tools}
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: Context | None = None

    def has_page(self) -> bool:
        return self._context is not None and self._context.has_tab()

    async def call_tool(self, name: str, args: dict[str, Any], *, roots: list[str] | None = None) -> str | ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(content=f'### Error\nTool "{name}" not found', is_error=True)

        try:
            context = await self._ensure_context()
            if roots is not None:
                from pathlib import Path

                context.client_roots = [Path(root) for root in roots]
            response = Response(context, tool_name=name, tool_args=args)
            if _blocks_on_modal_state(context, tool):
                response.add_error(f'Error: Tool "{name}" does not handle the modal state.')
                return await response.serialize()
            await tool.handler(context, args, response)
            result = await response.serialize()
        except ValueError as exc:
            return ToolResult(content=f"### Error\n{exc}", is_error=True)

        if response.is_close:
            await self.close()
        return result

    async def close(self) -> None:
        if self._context is not None:
            await self._context.dispose()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._context = None

    async def render_page_markdown(self) -> list[str]:
        tab = await self._ensure_tab()
        return await tab.render_page_markdown()

    async def capture_snapshot(
        self,
        *,
        target: str | None = None,
        depth: int | None = None,
        boxes: bool | None = None,
    ) -> str:
        tab = await self._ensure_tab()
        return await tab.capture_snapshot(target=target, depth=depth, boxes=boxes)

    async def _ensure_tab(self):
        context = await self._ensure_context()
        return await context.ensure_tab()

    async def _ensure_context(self) -> Context:
        if self._context is not None:
            return self._context
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._playwright.selectors.set_test_id_attribute(self._config.test_id_attribute)
        if self._browser is None:
            self._browser = await self._launch_browser()
        browser_context = await self._browser.new_context()
        self._context = Context(browser_context, self._config)
        return self._context

    async def _launch_browser(self) -> Browser:
        assert self._playwright is not None
        headless = self._config.headless
        if not headless and os.name == "posix" and not os.environ.get("DISPLAY"):
            headless = True

        if self._config.browser == "chromium":
            return await self._playwright.chromium.launch(headless=headless)
        if self._config.browser in {"firefox", "webkit"}:
            browser_type = getattr(self._playwright, self._config.browser)
            return await browser_type.launch(headless=headless)
        return await self._playwright.chromium.launch(
            channel=self._config.browser,
            headless=headless,
        )


def _blocks_on_modal_state(context: Context, tool: Tool) -> bool:
    tab = context.current_tab()
    if tab is None:
        return False
    modal_states = tab.modal_states()
    if not modal_states:
        return False
    return not any(state.get("type") == tool.clears_modal_state for state in modal_states)
