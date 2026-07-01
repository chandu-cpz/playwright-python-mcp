from __future__ import annotations

from urllib.parse import urlparse

from playwright.async_api import BrowserContext

from playwright_python_mcp.mcp.config import ServerConfig

from .tab import Tab


class Context:
    """Browser-context runtime.

    Upstream responsibility:
    - packages/playwright-core/src/tools/backend/context.ts
    """

    def __init__(self, browser_context: BrowserContext, config: ServerConfig) -> None:
        self.config = config
        self._browser_context = browser_context
        self._tabs: list[Tab] = []
        self._current_tab: Tab | None = None

    def has_tab(self) -> bool:
        return self._current_tab is not None

    def tabs(self) -> list[Tab]:
        return self._tabs

    async def dispose(self) -> None:
        await self._browser_context.close()
        self._tabs.clear()
        self._current_tab = None

    async def ensure_tab(self) -> Tab:
        if self._current_tab is None or self._current_tab.crashed:
            await self.new_tab()
        assert self._current_tab is not None
        return self._current_tab

    async def new_tab(self) -> Tab:
        page = await self._browser_context.new_page()
        tab = Tab(page)
        self._tabs.append(tab)
        self._current_tab = tab
        page.on("close", lambda _: self._on_page_closed(tab))
        page.on("crash", lambda _: self._on_page_crashed(tab))
        return tab

    async def close_current_tab(self) -> None:
        tab = self._current_tab
        if tab is None:
            return
        await tab.close()

    async def check_url_and_navigate(self, url: str) -> str:
        resolved_url = self._resolve_url(url)
        self._check_url_allowed(resolved_url)
        tab = await self.ensure_tab()
        await tab.navigate(resolved_url)
        return resolved_url

    def _resolve_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme:
            return url
        if url.startswith("localhost"):
            return "http://" + url
        return "https://" + url

    def _check_url_allowed(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme == "file" and not self.config.allow_unrestricted_file_access:
            raise ValueError(f'Error: Access to "file:" protocol is blocked. Attempted URL: "{url}"')

    def _on_page_closed(self, tab: Tab) -> None:
        if tab not in self._tabs:
            return
        index = self._tabs.index(tab)
        self._tabs.remove(tab)
        if self._current_tab is tab:
            self._current_tab = self._tabs[min(index, len(self._tabs) - 1)] if self._tabs else None

    def _on_page_crashed(self, tab: Tab) -> None:
        tab.crashed = True
