from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urlparse

from playwright.async_api import BrowserContext

from playwright_python_mcp.mcp.config import ServerConfig
from .codegen import python_literal

if TYPE_CHECKING:
    from .tab import Tab


@dataclass(frozen=True, slots=True)
class FilenameTemplate:
    prefix: str
    ext: str
    suggested_filename: str | None = None
    date: datetime | None = None


@dataclass(frozen=True, slots=True)
class LookupSecret:
    value: str
    code: str


@dataclass(slots=True)
class RouteEntry:
    pattern: str
    status: int | None = None
    body: str | None = None
    content_type: str | None = None
    add_headers: dict[str, str] | None = None
    remove_headers: list[str] | None = None
    handler: Callable[[Any], Any] | None = None


class Context:
    """Browser-context runtime.

    Upstream responsibility:
    - packages/playwright-core/src/tools/backend/context.ts
    """

    def __init__(self, browser_context: BrowserContext, config: ServerConfig, *, cwd: Path | None = None) -> None:
        self.config = config
        self._browser_context = browser_context
        self.cwd = cwd or Path.cwd()
        self.client_roots: list[Path] | None = None
        self._tabs: list[Tab] = []
        self._current_tab: Tab | None = None
        self._routes: list[RouteEntry] = []
        self.trace_file: Path | None = None
        self.video_file: Path | None = None

    def has_tab(self) -> bool:
        return self._current_tab is not None

    def tabs(self) -> list[Tab]:
        return self._tabs

    def browser_context(self) -> BrowserContext:
        return self._browser_context

    def current_tab(self) -> Tab | None:
        return self._current_tab

    def current_tab_or_die(self) -> Tab:
        if self._current_tab is None:
            raise ValueError("No open pages available.")
        return self._current_tab

    async def dispose(self) -> None:
        for tab in self._tabs:
            await tab.dispose()
        await self._browser_context.close()
        self._tabs.clear()
        self._current_tab = None

    async def ensure_tab(self) -> Tab:
        if self._current_tab is None or self._current_tab.crashed:
            await self.new_tab()
        assert self._current_tab is not None
        return self._current_tab

    async def new_tab(self) -> Tab:
        from .tab import Tab

        page = await self._browser_context.new_page()
        tab = Tab(self, page)
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

    async def close_tab(self, index: int | None = None) -> None:
        if index is None:
            await self.close_current_tab()
            return
        if index < 0 or index >= len(self._tabs):
            raise ValueError(f"Tab index {index} is out of range")
        await self._tabs[index].close()

    async def select_tab(self, index: int) -> None:
        if index < 0 or index >= len(self._tabs):
            raise ValueError(f"Tab index {index} is out of range")
        self._current_tab = self._tabs[index]

    async def set_offline(self, offline: bool) -> None:
        await self._browser_context.set_offline(offline)

    def routes(self) -> list[RouteEntry]:
        return list(self._routes)

    async def add_route(self, entry: RouteEntry) -> None:
        if entry.handler is None:
            raise ValueError("Route handler is required")
        await self._browser_context.route(entry.pattern, entry.handler)
        self._routes.append(entry)

    async def remove_route(self, pattern: str | None = None) -> int:
        if pattern is None:
            removed = len(self._routes)
            await self._browser_context.unroute_all()
            self._routes.clear()
            return removed
        removed_entries = [entry for entry in self._routes if entry.pattern == pattern]
        for entry in removed_entries:
            await self._browser_context.unroute(pattern, entry.handler)
        self._routes = [entry for entry in self._routes if entry.pattern != pattern]
        return len(removed_entries)

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

    async def workspace_file(self, file_name: str, per_call_workspace_dir: Path | None = None) -> Path:
        workspace = per_call_workspace_dir or self.cwd
        resolved = (workspace / file_name).resolve()
        self._check_file(resolved, origin="llm")
        return resolved

    async def output_file(self, template: FilenameTemplate, *, origin: str) -> Path:
        date = template.date or datetime.now(UTC)
        safe_date = date.isoformat(timespec="milliseconds").replace("+00:00", "Z").replace(":", "-").replace(".", "-")
        base_name = template.suggested_filename or f"{template.prefix}-{safe_date}{'.' + template.ext if template.ext else ''}"
        resolved = (self.output_dir() / base_name).resolve()
        self._check_file(resolved, origin=origin)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved

    def output_dir(self) -> Path:
        if self.config.output_dir is not None:
            return self.config.output_dir.resolve()
        base_name = ".playwright-mcp"
        if self._is_system_directory(self.cwd) or not os.access(self.cwd, os.W_OK):
            return Path(tempfile.gettempdir()) / base_name
        return self.cwd / base_name

    def redact_secrets(self, text: str) -> str:
        for secret_name, secret_value in (self.config.secrets or {}).items():
            if secret_value:
                text = text.replace(secret_value, f"<secret>{secret_name}</secret>")
        return text

    def lookup_secret(self, secret_name: str) -> LookupSecret:
        secret_value = (self.config.secrets or {}).get(secret_name)
        if secret_value is None:
            return LookupSecret(value=secret_name, code=python_literal(secret_name))
        return LookupSecret(value=secret_value, code=f"os.environ[{python_literal(secret_name)}]")

    def _check_file(self, resolved: Path, *, origin: str) -> None:
        if origin == "code" or self.config.allow_unrestricted_file_access:
            return
        output = self.output_dir().resolve()
        workspace = self.cwd.resolve()
        allowed_roots = [output, *(self.client_roots or [workspace])]
        if not any(_is_relative_to(resolved, root.resolve()) for root in allowed_roots):
            roots_text = ", ".join(str(root) for root in allowed_roots)
            raise ValueError(f"File access denied: {resolved} is outside allowed roots. Allowed roots: {roots_text}")

    @staticmethod
    def _is_system_directory(path: Path) -> bool:
        resolved = path.resolve()
        return resolved in {Path("/"), Path("/tmp"), Path("/var"), Path("/usr"), Path("/bin"), Path("/etc")}

    def _on_page_closed(self, tab: Tab) -> None:
        if tab not in self._tabs:
            return
        index = self._tabs.index(tab)
        self._tabs.remove(tab)
        if self._current_tab is tab:
            self._current_tab = self._tabs[min(index, len(self._tabs) - 1)] if self._tabs else None

    def _on_page_crashed(self, tab: Tab) -> None:
        tab.crashed = True


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
