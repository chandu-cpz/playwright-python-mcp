from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.session_log import SessionLog
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


def test_fastmcp_read_only_annotations_match_tool_surface() -> None:
    async def run() -> None:
        server = create_server(
            load_config(
                browser=None,
                caps="pdf,vision,network,tracing,devtools,storage,testing,config",
                config_path=None,
                headless=True,
                test_id_attribute="data-testid",
                vision=False,
            )
        )

        read_only_names = {
            "browser_snapshot",
            "browser_console_messages",
            "browser_take_screenshot",
            "browser_get_config",
            "browser_pdf_save",
            "browser_route_list",
            "browser_storage_state",
            "browser_localstorage_list",
            "browser_start_tracing",
            "browser_start_video",
            "browser_wait_for",
            "browser_verify_text_visible",
        }
        action_or_input_names = {
            "browser_click",
            "browser_type",
            "browser_navigate",
            "browser_cookie_set",
            "browser_route",
            "browser_set_storage_state",
            "browser_mouse_click_xy",
        }

        for name in read_only_names:
            tool = cast(Any, await server.app.get_tool(name))
            assert tool.annotations is not None
            assert tool.annotations.readOnlyHint is True, name
            assert tool.annotations.destructiveHint is False, name

        for name in action_or_input_names:
            tool = cast(Any, await server.app.get_tool(name))
            assert tool.annotations is not None
            assert tool.annotations.readOnlyHint is False, name
            assert tool.annotations.destructiveHint is True, name

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


def test_devtools_capability_exposes_tracing_tools() -> None:
    config = load_config(
        browser=None,
        caps="devtools",
        config_path=None,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
    )

    names = {tool.name for tool in filtered_tools(config)}

    assert "browser_start_tracing" in names
    assert "browser_stop_tracing" in names


def test_tracing_capability_alias_exposes_devtools_tools() -> None:
    config = load_config(
        browser=None,
        caps="tracing",
        config_path=None,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
    )

    names = {tool.name for tool in filtered_tools(config)}

    assert "browser_start_tracing" in names
    assert "browser_stop_tracing" in names
    assert "browser_resume" in names


def test_tool_types_match_upstream_families() -> None:
    config = load_config(
        browser=None,
        caps="vision,testing",
        config_path=None,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
    )
    tools = {tool.name: tool for tool in filtered_tools(config)}

    for name in {
        "browser_click",
        "browser_select_option",
        "browser_hover",
        "browser_drag",
        "browser_fill_form",
        "browser_press_key",
        "browser_type",
        "browser_mouse_move_xy",
        "browser_mouse_click_xy",
        "browser_mouse_down",
        "browser_mouse_up",
        "browser_mouse_wheel",
        "browser_mouse_drag_xy",
    }:
        assert tools[name].tool_type == "input", name

    for name in {
        "browser_verify_element_visible",
        "browser_verify_text_visible",
        "browser_verify_list_visible",
        "browser_verify_value",
        "browser_wait_for",
    }:
        assert tools[name].tool_type == "assertion", name


def test_response_does_not_capture_aria_snapshot_without_request(tmp_path) -> None:
    async def run() -> None:
        tab = FakeTab()
        context = FakeContext(tab, tmp_path)
        response = Response(cast(Context, context), tool_name="browser_console_messages", tool_args={})
        response.add_text_result("ok")

        await response.serialize()

        assert tab.capture_kwargs == {"target": None, "depth": None, "boxes": None, "relative_to": tmp_path, "include_aria": False}

    asyncio.run(run())


def test_explicit_snapshot_is_inline_by_default(tmp_path: Path) -> None:
    async def run() -> None:
        tab = FakeTab(aria_snapshot='- button "Submit" [ref=e1]')
        context = FakeContext(tab, tmp_path, snapshot_mode="full")
        response = Response(cast(Context, context), tool_name="browser_snapshot", tool_args={})
        response.set_include_full_snapshot()

        result = await response.serialize()

        assert isinstance(result, str)
        assert "```yaml" in result
        assert '- button "Submit" [ref=e1]' in result
        assert "[Snapshot](" not in result
        assert tab.capture_kwargs and tab.capture_kwargs["include_aria"] is True

    asyncio.run(run())


def test_action_snapshot_uses_file_for_full_mode(tmp_path: Path) -> None:
    async def run() -> None:
        tab = FakeTab(aria_snapshot='- button "Submit" [ref=e1]')
        context = FakeContext(tab, tmp_path, snapshot_mode="full", output_mode="file")
        response = Response(cast(Context, context), tool_name="browser_click", tool_args={})
        response.set_include_snapshot()

        result = await response.serialize()

        assert isinstance(result, str)
        assert "[Snapshot](" in result
        assert "```yaml" not in result
        assert (tmp_path / "page.yml").read_text(encoding="utf-8") == '- button "Submit" [ref=e1]'

    asyncio.run(run())


def test_action_snapshot_uses_inline_yaml_for_stdout_mode(tmp_path: Path) -> None:
    async def run() -> None:
        tab = FakeTab(aria_snapshot='- button "Submit" [ref=e1]')
        context = FakeContext(tab, tmp_path, snapshot_mode="full", output_mode="stdout")
        response = Response(cast(Context, context), tool_name="browser_click", tool_args={})
        response.set_include_snapshot()

        result = await response.serialize()

        assert isinstance(result, str)
        assert "```yaml" in result
        assert '- button "Submit" [ref=e1]' in result
        assert not (tmp_path / "page.yml").exists()

    asyncio.run(run())


def test_stdout_mode_returns_text_file_results_inline(tmp_path: Path) -> None:
    async def run() -> None:
        from playwright_python_mcp.backend.context import FilenameTemplate

        context = FakeContext(FakeTab(), tmp_path, output_mode="stdout")
        response = Response(cast(Context, context), tool_name="browser_console_messages", tool_args={})
        resolved = await response.resolve_client_file(FilenameTemplate(prefix="console", ext="log"), "Console")
        await response.add_file_result(resolved, "hello")

        result = await response.serialize()

        assert isinstance(result, str)
        assert "hello" in result
        assert "[Console]" not in result
        assert not resolved.file_name.exists()

    asyncio.run(run())


def test_action_snapshot_respects_none_mode(tmp_path: Path) -> None:
    async def run() -> None:
        tab = FakeTab(aria_snapshot='- button "Submit" [ref=e1]')
        context = FakeContext(tab, tmp_path, snapshot_mode="none")
        response = Response(cast(Context, context), tool_name="browser_click", tool_args={})
        response.set_include_snapshot()

        result = await response.serialize()

        assert isinstance(result, str)
        assert "### Snapshot" not in result
        assert tab.capture_kwargs and tab.capture_kwargs["include_aria"] is False

    asyncio.run(run())


def test_response_includes_paused_debugger_section(tmp_path: Path) -> None:
    async def run() -> None:
        context = FakeContext(FakeTab(), tmp_path)
        context.debugger.paused_details = {
            "title": "Paused on breakpoint",
            "location": {"file": str(tmp_path / "example.py"), "line": 12},
        }
        response = Response(cast(Context, context), tool_name="browser_snapshot", tool_args={})

        result = await response.serialize()

        assert isinstance(result, str)
        assert "### Paused" in result
        assert "- Paused on breakpoint at ./example.py:12" in result
        assert "resume by calling resume/step-over/pause-at" in result

    asyncio.run(run())


def test_session_log_writes_markdown_summary(tmp_path: Path) -> None:
    async def run() -> None:
        session_log = SessionLog(folder=tmp_path / "session-1", cwd=tmp_path)
        await session_log.log_response(
            "browser_snapshot",
            {"filename": "page.yml"},
            "### Result\nok\n### Snapshot\n```yaml\n- button \"Submit\" [ref=e1]\n```",
        )

        content = (tmp_path / "session-1" / "session.md").read_text(encoding="utf-8")
        assert "### Tool call: browser_snapshot" in content
        assert '"filename": "page.yml"' in content
        assert '"result": "ok"' in content
        assert '"inlineSnapshot": "- button \\"Submit\\" [ref=e1]"' in content

    asyncio.run(run())


class FakeTab:
    def __init__(self, aria_snapshot: str = "") -> None:
        self.capture_kwargs: dict[str, Any] | None = None
        self._aria_snapshot = aria_snapshot

    async def capture_tab_snapshot(self, **kwargs: Any) -> TabSnapshot:
        self.capture_kwargs = kwargs
        return TabSnapshot(aria_snapshot=self._aria_snapshot)

    async def header_snapshot(self) -> TabHeader:
        return TabHeader(title="title", url="about:blank", current=True, crashed=False, console={"total": 0, "errors": 0, "warnings": 0})


class FakeContext:
    def __init__(self, tab: FakeTab, cwd: Path, *, snapshot_mode: str = "none", output_mode: str = "stdout") -> None:
        self.cwd = cwd
        self.debugger = FakeDebugger()
        self.config = SimpleNamespace(
            codegen="python",
            snapshot_mode=snapshot_mode,
            output_mode=output_mode,
            image_responses="omit",
            output_max_size=None,
        )
        self._tab = tab

    def current_tab(self) -> FakeTab:
        return self._tab

    def tabs(self) -> list[FakeTab]:
        return [self._tab]

    def browser_context(self) -> FakeBrowserContext:
        return FakeBrowserContext(self.debugger)

    def redact_secrets(self, text: str) -> str:
        return text

    async def output_file(self, template: Any, origin: str) -> Path:
        return self.cwd / f"{template.prefix}.{template.ext}"


class FakeBrowserContext:
    def __init__(self, debugger: FakeDebugger) -> None:
        self.debugger = debugger


class FakeDebugger:
    def __init__(self) -> None:
        self.paused_details: Any = None


def test_killkillkill_endpoint_is_registered_on_http_app() -> None:
    server = create_server(_config())
    http = server.app.http_app()
    kill_routes = [route for route in http.routes if getattr(route, "path", "") == "/killkillkill"]
    assert len(kill_routes) == 1


def test_killkillkill_endpoint_requires_post_and_header() -> None:
    async def run() -> None:
        server = create_server(_config())

        missing_header = await _call_http_app(server.app.http_app(), method="POST", headers=[])
        wrong_method = await _call_http_app(
            server.app.http_app(),
            method="GET",
            headers=[(b"x-pw-mcp-kill", b"1")],
        )

        assert missing_header == (405, "")
        assert wrong_method == (405, "")

    asyncio.run(run())


def test_killkillkill_endpoint_triggers_shutdown() -> None:
    async def run() -> None:
        import anyio

        server = create_server(_config())
        with anyio.CancelScope() as scope:
            server._cancel_scope = scope
            status, body = await _call_http_app(
                server.app.http_app(),
                method="POST",
                headers=[(b"x-pw-mcp-kill", b"1")],
            )

            assert (status, body) == (200, "Killing process")
            assert scope.cancel_called is True

    asyncio.run(run())


def test_trigger_shutdown_cancels_active_scope() -> None:
    import anyio

    async def run() -> None:
        server = create_server(_config())
        with anyio.CancelScope() as scope:
            server._cancel_scope = scope
            server.trigger_shutdown()
            assert scope.cancel_called is True

    anyio.run(run)


async def _call_http_app(app: Any, *, method: str, headers: list[tuple[bytes, bytes]]) -> tuple[int, str]:
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": "/killkillkill",
            "raw_path": b"/killkillkill",
            "query_string": b"",
            "headers": [(b"host", b"localhost"), *headers],
            "client": ("127.0.0.1", 12345),
            "server": ("localhost", 80),
        },
        receive,
        send,
    )
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return int(start["status"]), body.decode("utf-8")
