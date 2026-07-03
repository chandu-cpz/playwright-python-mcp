from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast
from collections.abc import Callable

from playwright_python_mcp.backend.browser_backend import BrowserBackend
from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool
from playwright_python_mcp.backend.tools.common import common_tools
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


def test_browser_close_does_not_prevent_next_tool_call() -> None:
    async def probe_handler(_context: Context, _params: dict[str, Any], response: Response) -> None:
        response.add_text_result("alive")

    async def run() -> None:
        backend = ErrorBackend(
            _config(),
            [*common_tools, Tool(name="browser_probe", capability="core", handler=probe_handler)],
        )

        close_result = await backend.call_tool("browser_close", {})
        next_result = await backend.call_tool("browser_probe", {})

        assert backend.closed is True
        assert getattr(close_result, "meta") == {"isClose": True}
        assert next_result.content[0].text == "### Result\nalive"

    asyncio.run(run())


def test_disconnected_backend_marks_result_as_close() -> None:
    async def probe_handler(_context: Context, _params: dict[str, Any], response: Response) -> None:
        response.add_text_result("alive")

    async def run() -> None:
        backend = ErrorBackend(_config(), [Tool(name="browser_probe", capability="core", handler=probe_handler)])
        backend._disconnected = True

        result = await backend.call_tool("browser_probe", {})

        assert getattr(result, "meta") == {"isClose": True}

    asyncio.run(run())


def test_context_initialize_tracks_existing_and_future_pages() -> None:
    async def run() -> None:
        existing_page = FakePage("existing")
        browser_context = FakeBrowserContext([existing_page])
        context = Context(cast(Any, browser_context), _config())

        await context.initialize()
        future_page = FakePage("future")
        browser_context.emit_page(future_page)

        assert [tab.page for tab in context.tabs()] == [existing_page, future_page]
        current_tab = context.current_tab()
        assert current_tab is not None
        assert current_tab.page is existing_page

    asyncio.run(run())


def test_context_new_tab_uses_page_event_without_double_registering() -> None:
    async def run() -> None:
        browser_context = FakeBrowserContext([])
        context = Context(cast(Any, browser_context), _config())
        await context.initialize()

        tab = await context.new_tab()

        assert context.tabs() == [tab]
        assert context.current_tab() is tab

    asyncio.run(run())


def test_context_video_recording_tracks_existing_and_future_pages(tmp_path: Path) -> None:
    async def run() -> None:
        existing_page = FakePage("existing")
        browser_context = FakeBrowserContext([existing_page])
        context = Context(cast(Any, browser_context), _config(), cwd=tmp_path)

        await context.initialize()
        await context.start_video_recording(tmp_path / "video.webm", {"size": {"width": 640, "height": 480}})

        future_page = FakePage("future")
        browser_context.pages.append(future_page)
        browser_context.emit_page(future_page)
        await asyncio.sleep(0)

        file_names = await context.stop_video_recording()

        assert existing_page.screencast.started == [(tmp_path / "video.webm", {"width": 640, "height": 480})]
        assert future_page.screencast.started == [(tmp_path / "video-1.webm", {"width": 640, "height": 480})]
        assert existing_page.screencast.stopped == 1
        assert future_page.screencast.stopped == 1
        assert file_names == [tmp_path / "video.webm", tmp_path / "video-1.webm"]

    asyncio.run(run())


def test_backend_close_cleans_up_after_context_dispose_failure() -> None:
    async def run() -> None:
        backend = BrowserBackend(_config(), [])
        fake_context = RaisingDisposeContext()
        fake_browser = FakeClosable()
        fake_extension_relay = FakeClosable()
        fake_playwright = FakeClosable()
        backend._context = cast(Any, fake_context)
        backend._browser = cast(Any, fake_browser)
        backend._extension_relay = cast(Any, fake_extension_relay)
        backend._playwright = cast(Any, fake_playwright)

        await backend.close()

        assert fake_context.dispose_called is True
        assert fake_browser.closed is True
        assert fake_extension_relay.closed is True
        assert fake_playwright.closed is True
        assert backend._context is None
        assert backend._browser is None
        assert backend._extension_relay is None
        assert backend._playwright is None

    asyncio.run(run())


class ErrorBackend(BrowserBackend):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.closed = False

    async def _ensure_context(self, *, cwd: Path, roots: list[str] | None) -> Context:
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


class FakeBrowserContext:
    def __init__(self, pages: list["FakePage"]) -> None:
        self.pages = pages
        self._page_listeners: list[Callable[["FakePage"], None]] = []

    async def add_init_script(self, *, path: Path) -> None:
        pass

    async def route(self, *args: Any) -> None:
        pass

    def on(self, event: str, callback: Any) -> None:
        if event == "page":
            self._page_listeners.append(callback)

    async def new_page(self) -> "FakePage":
        page = FakePage("new")
        self.pages.append(page)
        self.emit_page(page)
        return page

    def emit_page(self, page: "FakePage") -> None:
        for callback in self._page_listeners:
            callback(page)


class FakePage:
    def __init__(self, name: str) -> None:
        self.name = name
        self.listeners: dict[str, list[Any]] = {}
        self.screencast = FakeScreencast()

    def on(self, event: str, callback: Any) -> None:
        self.listeners.setdefault(event, []).append(callback)

    async def bring_to_front(self) -> None:
        pass


class FakeScreencast:
    def __init__(self) -> None:
        self.started: list[tuple[Path, dict[str, Any] | None]] = []
        self.stopped = 0

    async def start(self, *, path: Path, size: dict[str, Any] | None = None) -> None:
        self.started.append((path, size))

    async def stop(self) -> None:
        self.stopped += 1


class RaisingDisposeContext:
    def __init__(self) -> None:
        self.dispose_called = False

    def browser_context(self) -> None:
        return None

    async def dispose(self) -> None:
        self.dispose_called = True
        raise RuntimeError("dispose failed")


class FakeClosable:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def stop(self) -> None:
        self.closed = True


class FakeContext:
    cwd = Path.cwd()
    config = type(
        "FakeConfig",
        (),
        {
            "codegen": "python",
            "snapshot_mode": "none",
            "image_responses": "omit",
            "output_max_size": None,
            "output_mode": "stdout",
        },
    )()

    def current_tab(self) -> None:
        return None

    def tabs(self) -> list[object]:
        return []

    def configure_client(self, *, roots: list[Path] | None = None, cwd: Path | None = None) -> None:
        if cwd is not None:
            self.cwd = cwd

    def redact_secrets(self, text: str) -> str:
        return text
