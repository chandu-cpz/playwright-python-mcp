from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

from playwright_python_mcp.backend.browser_backend import BrowserBackend
from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.tool import Tool
from playwright_python_mcp.mcp.config import load_config


def _config(**options: Any):
    return load_config(
        browser=None,
        caps="",
        config_path=None,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
        **options,
    )


def test_default_launch_uses_persistent_context(monkeypatch, tmp_path: Path) -> None:
    async def run() -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        backend = BrowserBackend(_config(), [])
        playwright = FakePlaywright()
        backend._playwright = cast(Any, playwright)

        await backend._launch_browser()

        assert playwright.chromium.persistent_user_data_dir is not None
        assert "ms-playwright-mcp" in str(playwright.chromium.persistent_user_data_dir)
        assert playwright.chromium.launch_called is False
        assert playwright.chromium.persistent_options["handle_sigint"] is False
        assert playwright.chromium.persistent_options["handle_sigterm"] is False
        assert playwright.chromium.persistent_options["ignore_default_args"] == ["--disable-extensions"]

    asyncio.run(run())


def test_isolated_launch_uses_ephemeral_browser() -> None:
    async def run() -> None:
        backend = BrowserBackend(_config(isolated=True), [])
        playwright = FakePlaywright()
        backend._playwright = cast(Any, playwright)

        await backend._launch_browser()

        assert playwright.chromium.launch_called is True
        assert playwright.chromium.persistent_user_data_dir is None

    asyncio.run(run())


def test_unexpected_tool_error_does_not_close_browser_backend() -> None:
    async def broken_handler(_context: Any, _params: dict[str, Any], _response: Any) -> None:
        raise RuntimeError("boom")

    async def run() -> None:
        backend = ErrorBackend(_config(), [Tool(name="browser_broken", capability="core", handler=broken_handler)])

        result = await backend.call_tool("browser_broken", {})

        assert getattr(result, "is_error") is True
        assert "boom" in getattr(result, "content")[0].text
        assert backend.closed is False

    asyncio.run(run())


class ErrorBackend(BrowserBackend):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.closed = False

    async def _ensure_context(self) -> Context:
        return cast(Context, FakeContext())

    async def close(self) -> None:
        self.closed = True


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = FakeBrowserType()


class FakeBrowserType:
    def __init__(self) -> None:
        self.launch_called = False
        self.launch_options: dict[str, Any] | None = None
        self.persistent_user_data_dir: Path | None = None
        self.persistent_options: dict[str, Any] = {}

    async def launch(self, **options: Any) -> object:
        self.launch_called = True
        self.launch_options = options
        return object()

    async def launch_persistent_context(self, user_data_dir: Path, **options: Any) -> "FakePersistentContext":
        self.persistent_user_data_dir = user_data_dir
        self.persistent_options = options
        return FakePersistentContext()


class FakePersistentContext:
    browser = object()


class FakeContext:
    cwd = Path.cwd()

    def current_tab(self) -> None:
        return None
