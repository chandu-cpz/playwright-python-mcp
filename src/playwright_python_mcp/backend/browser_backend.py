from __future__ import annotations

import os

from fastmcp.tools.base import ToolResult
from playwright.async_api import Browser, Playwright, async_playwright

from playwright_python_mcp.mcp.config import ServerConfig

from .codegen import python_call, python_dict, python_invocation, python_literal
from .context import Context
from .response import Response
from .tab import Button, Modifier


class BrowserBackend:
    """Top-level browser runtime.

    Upstream responsibility:
    - packages/playwright-core/src/tools/backend/browserBackend.ts
    """

    def __init__(self, config: ServerConfig) -> None:
        self._config = config
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: Context | None = None

    def has_page(self) -> bool:
        return self._context is not None and self._context.has_tab()

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

    async def run_tool(self, handler) -> str | ToolResult:
        response = Response(self)
        try:
            await handler(response)
            return await response.serialize()
        except ValueError as exc:
            return ToolResult(content=f"### Error\n{exc}", is_error=True)

    async def browser_snapshot(
        self,
        *,
        target: str | None = None,
        depth: int | None = None,
        boxes: bool | None = None,
    ) -> str | ToolResult:
        async def handler(response: Response) -> None:
            response.set_include_full_snapshot(target=target, depth=depth, boxes=boxes)

        return await self.run_tool(handler)

    async def browser_navigate(self, *, url: str) -> ToolResult | str:
        async def handler(response: Response) -> None:
            context = await self._ensure_context()
            resolved_url = await context.check_url_and_navigate(url)
            response.set_include_snapshot()
            response.add_code(f"await page.goto({python_literal(resolved_url)})")

        return await self.run_tool(handler)

    async def browser_navigate_back(self) -> str | ToolResult:
        async def handler(response: Response) -> None:
            tab = await self._ensure_tab()
            await tab.go_back()
            response.set_include_snapshot()
            response.add_code("await page.go_back()")

        return await self.run_tool(handler)

    async def browser_navigate_forward(self) -> str | ToolResult:
        async def handler(response: Response) -> None:
            tab = await self._ensure_tab()
            await tab.go_forward()
            response.set_include_snapshot()
            response.add_code("await page.go_forward()")

        return await self.run_tool(handler)

    async def browser_reload(self) -> str | ToolResult:
        async def handler(response: Response) -> None:
            tab = await self._ensure_tab()
            await tab.reload()
            response.set_include_snapshot()
            response.add_code("await page.reload()")

        return await self.run_tool(handler)

    async def browser_click(
        self,
        *,
        target: str,
        element: str | None = None,
        double_click: bool = False,
        button: Button | None = None,
        modifiers: list[Modifier] | None = None,
    ) -> str | ToolResult:
        async def handler(response: Response) -> None:
            tab = await self._ensure_tab()
            resolved = await tab.resolve_target(target=target, element=element)
            await tab.click(
                resolved,
                double_click=double_click,
                button=button,
                modifiers=modifiers,
            )
            response.set_include_snapshot()
            action = "dblclick" if double_click else "click"
            options: list[tuple[str, object]] = []
            if button is not None:
                options.append(("button", button))
            if modifiers is not None:
                options.append(("modifiers", modifiers))
            response.add_code(python_invocation(resolved.code, action, options or None))

        return await self.run_tool(handler)

    async def browser_select_option(
        self,
        *,
        target: str,
        values: list[str],
        element: str | None = None,
    ) -> str | ToolResult:
        async def handler(response: Response) -> None:
            tab = await self._ensure_tab()
            resolved = await tab.resolve_target(target=target, element=element)
            await tab.select_option(resolved, values=values)
            response.set_include_snapshot()
            response.add_code(python_call(resolved.code, "select_option", values))

        return await self.run_tool(handler)

    async def browser_hover(
        self,
        *,
        target: str,
        element: str | None = None,
    ) -> str | ToolResult:
        async def handler(response: Response) -> None:
            tab = await self._ensure_tab()
            resolved = await tab.resolve_target(target=target, element=element)
            response.set_include_snapshot()
            response.add_code(python_invocation(resolved.code, "hover"))
            await tab.hover(resolved)

        return await self.run_tool(handler)

    async def browser_drag(
        self,
        *,
        start_target: str,
        end_target: str,
        start_element: str | None = None,
        end_element: str | None = None,
    ) -> str | ToolResult:
        async def handler(response: Response) -> None:
            tab = await self._ensure_tab()
            start = await tab.resolve_target(target=start_target, element=start_element)
            end = await tab.resolve_target(target=end_target, element=end_element)
            response.set_include_snapshot()
            response.add_code(f"await page.{start.code}.drag_to(page.{end.code})")
            await tab.drag_to(start, end)

        return await self.run_tool(handler)

    async def browser_generate_locator(
        self,
        *,
        target: str,
        element: str | None = None,
    ) -> str | ToolResult:
        async def handler(response: Response) -> None:
            tab = await self._ensure_tab()
            resolved = await tab.resolve_target(target=target, element=element)
            response.add_text_result(resolved.code)

        return await self.run_tool(handler)

    async def browser_resize(self, *, width: int, height: int) -> str | ToolResult:
        async def handler(response: Response) -> None:
            tab = await self._ensure_tab()
            await tab.resize(width=width, height=height)
            response.add_code(f"await page.set_viewport_size({python_dict([('width', width), ('height', height)])})")

        return await self.run_tool(handler)

    async def browser_close(self) -> str | ToolResult:
        async def handler(response: Response) -> None:
            await self.close()
            response.add_text_result("No open tabs. Navigate to a URL to create one.")
            response.add_code("await page.close()")
            response.set_close()

        return await self.run_tool(handler)

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
