from __future__ import annotations

import os
from typing import Any

from fastmcp.tools.base import ToolResult
from playwright.async_api import Browser, BrowserContext as PlaywrightBrowserContext, Playwright, async_playwright

from playwright_python_mcp.mcp.config import ServerConfig

from .context import Context
from .extension_relay import CDPRelayServer
from .response import Response
from .session_log import SessionLog
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
        self._playwright_context: PlaywrightBrowserContext | None = None
        self._extension_relay: CDPRelayServer | None = None
        self._context: Context | None = None
        self._session_log: SessionLog | None = None

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
            if self._session_log is not None:
                await self._session_log.log_response(name, args, result)
        except ValueError as exc:
            return ToolResult(content=f"### Error\n{exc}", is_error=True)
        except Exception as exc:
            await self.close()
            return ToolResult(content=f"### Error\n{exc}", is_error=True)

        if response.is_close:
            await self.close()
        return result

    async def close(self) -> None:
        if self._context is not None:
            await self._context.dispose()
        if self._browser is not None:
            await self._browser.close()
        if self._extension_relay is not None:
            await self._extension_relay.stop()
        if self._playwright is not None:
            await self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._playwright_context = None
        self._extension_relay = None
        self._context = None
        self._session_log = None

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
        if self._browser is None and self._playwright_context is None:
            self._browser = await self._launch_browser()
        if self._playwright_context is not None:
            browser_context = self._playwright_context
        else:
            assert self._browser is not None
            browser_context = await self._browser.new_context(**self._config.browser_context_options)
        if self._config.action_timeout is not None:
            browser_context.set_default_timeout(self._config.action_timeout)
        if self._config.navigation_timeout is not None:
            browser_context.set_default_navigation_timeout(self._config.navigation_timeout)
        self._context = Context(browser_context, self._config)
        if self._config.save_session:
            self._session_log = await SessionLog.create(self._context)
            self._context.session_log = self._session_log
        return self._context

    async def _launch_browser(self) -> Browser:
        assert self._playwright is not None
        if self._config.cdp_endpoint:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self._config.cdp_endpoint,
                headers=self._config.cdp_headers,
                timeout=self._config.cdp_timeout,
            )
            return self._browser
        if self._config.remote_endpoint:
            self._browser = await self._playwright.chromium.connect(
                self._config.remote_endpoint,
                headers=self._config.remote_headers,
            )
            return self._browser
        if self._config.extension:
            if self._config.browser_name != "chromium":
                raise ValueError(
                    f'Extension mode (--extension) is only supported with Chromium-based browsers, '
                    f'got "{self._config.browser_name}".'
                )
            self._extension_relay = CDPRelayServer(
                self._playwright,
                browser_channel=self._config.browser_channel or self._config.browser,
                executable_path=self._config.browser_launch_options.get("executable_path"),
                user_data_dir=self._config.browser_user_data_dir,
            )
            await self._extension_relay.start()
            await self._extension_relay.establish_extension_connection("playwright-python-mcp")
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self._extension_relay.cdp_endpoint(),
                timeout=0,
            )
            return self._browser

        launch_options = dict(self._config.browser_launch_options)
        headless = bool(launch_options.get("headless", self._config.headless))
        if not headless and os.name == "posix" and not os.environ.get("DISPLAY"):
            headless = True
        launch_options["headless"] = headless

        browser_type = getattr(self._playwright, self._config.browser_name)
        if self._config.browser_user_data_dir is not None and not self._config.browser_isolated:
            self._playwright_context = await browser_type.launch_persistent_context(
                str(self._config.browser_user_data_dir),
                **launch_options,
                **self._config.browser_context_options,
            )
            browser = self._playwright_context.browser
            if browser is None:
                raise ValueError("Persistent browser context did not expose a browser instance.")
            return browser
        return await browser_type.launch(**launch_options)


def _blocks_on_modal_state(context: Context, tool: Tool) -> bool:
    tab = context.current_tab()
    if tab is None:
        return False
    modal_states = tab.modal_states()
    if not modal_states:
        return False
    return not any(state.get("type") == tool.clears_modal_state for state in modal_states)
