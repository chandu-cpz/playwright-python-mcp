from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tab import TabHeader, TabSnapshot
from playwright_python_mcp.backend.tools import filtered_tools
from playwright_python_mcp.mcp.config import load_config
from playwright_python_mcp.mcp.server import create_server


def _config():
    return load_config(
        browser=None,
        caps="",
        config_path=None,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
    )


def test_fastmcp_registration_is_non_threaded_and_has_metadata() -> None:
    async def run() -> None:
        server = create_server(_config())
        tool = cast(Any, await server.app.get_tool("browser_click"))
        assert tool is not None

        assert tool.run_in_thread is False
        assert tool.title == "Click"
        assert tool.description
        assert tool.annotations is not None
        assert tool.annotations.openWorldHint is True

    asyncio.run(run())


def test_filtered_tools_hide_skill_only_tools() -> None:
    hidden_names = {
        "browser_press_sequentially",
        "browser_keydown",
        "browser_keyup",
        "browser_navigate_forward",
        "browser_reload",
        "browser_network_clear",
        "browser_check",
        "browser_uncheck",
    }

    assert hidden_names.isdisjoint({tool.name for tool in filtered_tools(_config())})


def test_response_does_not_capture_aria_snapshot_without_request(tmp_path) -> None:
    async def run() -> None:
        tab = FakeTab()
        context = FakeContext(tab, tmp_path)
        response = Response(cast(Context, context), tool_name="browser_console_messages", tool_args={})
        response.add_text_result("ok")

        await response.serialize()

        assert tab.capture_kwargs == {"target": None, "depth": None, "boxes": None, "relative_to": tmp_path, "include_aria": False}

    asyncio.run(run())


class FakeTab:
    def __init__(self) -> None:
        self.capture_kwargs: dict[str, Any] | None = None

    async def capture_tab_snapshot(self, **kwargs: Any) -> TabSnapshot:
        self.capture_kwargs = kwargs
        return TabSnapshot(aria_snapshot="")

    async def header_snapshot(self) -> TabHeader:
        return TabHeader(title="title", url="about:blank", current=True, crashed=False, console={"total": 0, "errors": 0, "warnings": 0})


class FakeContext:
    def __init__(self, tab: FakeTab, cwd) -> None:
        self.cwd = cwd
        self.config = SimpleNamespace(
            codegen="python",
            snapshot_mode="none",
            image_responses="omit",
            output_max_size=None,
        )
        self._tab = tab

    def current_tab(self) -> FakeTab:
        return self._tab

    def tabs(self) -> list[FakeTab]:
        return [self._tab]

    def redact_secrets(self, text: str) -> str:
        return text
