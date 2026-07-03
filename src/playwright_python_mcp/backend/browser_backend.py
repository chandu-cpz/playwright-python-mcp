from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastmcp.tools.base import ToolResult
from playwright.async_api import Browser, BrowserContext as PlaywrightBrowserContext, Playwright, async_playwright

from playwright_python_mcp.mcp.config import ServerConfig

from .context import Context
from .response import Response
from .session_log import SessionLog
from .tool import Tool

if TYPE_CHECKING:
    from .extension_relay import CDPRelayServer


class BrowserBackend:
    """Thin browser backend dispatcher.

    Upstream responsibility:
    - packages/playwright-core/src/tools/backend/browserBackend.ts
    """

    def __init__(
        self,
        config: ServerConfig,
        tools: list[Tool],
        *,
        shared_browser_owner: BrowserBackend | None = None,
        close_shared_browser: bool = True,
    ) -> None:
        self._config = config
        self._tools = {tool.name: tool for tool in tools}
        self._shared_browser_owner = shared_browser_owner
        self._close_shared_browser = close_shared_browser
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._playwright_context: PlaywrightBrowserContext | None = None
        self._extension_relay: CDPRelayServer | None = None
        self._context: Context | None = None
        self._session_log: SessionLog | None = None
        self._disconnected = False
        self._closed = False
        self._disconnect_listeners_registered = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    def has_page(self) -> bool:
        return self._context is not None and self._context.has_tab()

    async def call_tool(
        self,
        name: str,
        args: dict[str, Any],
        *,
        roots: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> str | ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return _format_error(f'Tool "{name}" not found', json_mode=bool(meta and meta.get("json")))

        client_cwd = _client_cwd(meta=meta, roots=roots)

        try:
            context = await self._ensure_context(cwd=client_cwd, roots=roots)
            response = Response(
                context,
                tool_name=name,
                tool_args=args,
                relative_to=client_cwd,
                raw=bool(meta and meta.get("raw")),
                json_mode=bool(meta and meta.get("json")),
            )
            if _blocks_on_modal_state(context, tool):
                if tool.clears_modal_state:
                    response.add_error(
                        f'Error: The tool "{name}" can only be used when there is related modal state present.'
                    )
                else:
                    response.add_error(f'Error: Tool "{name}" does not handle the modal state.')
                result = await response.serialize()
                if self._disconnected:
                    result = _attach_close_marker(result)
                    await self.close()
                return result
            await tool.handler(context, args, response)
            _drain_unhandled_errors(context, response)
            result = await response.serialize()
            if self._session_log is not None:
                await self._session_log.log_response(name, args, result)
        except ValueError as exc:
            result = _format_error(str(exc), json_mode=bool(meta and meta.get("json")))
            if self._disconnected:
                result = _attach_close_marker(result)
                await self.close()
            return result
        except Exception as exc:
            result = _format_error(str(exc), json_mode=bool(meta and meta.get("json")))
            if self._disconnected:
                result = _attach_close_marker(result)
                await self.close()
            return result

        if response.is_close or self._disconnected:
            result = _attach_close_marker(result)
            await self.close()
        return result

    async def close(self) -> None:
        browser_context = self._context.browser_context() if self._context is not None else None
        try:
            if self._context is not None:
                with suppress(Exception):
                    await self._context.dispose()
            if browser_context is not None and self._should_close_browser_context():
                with suppress(Exception):
                    await browser_context.close()
            if self._browser is not None and self._shared_browser_owner is None:
                with suppress(Exception):
                    await self._browser.close()
            if self._extension_relay is not None:
                with suppress(Exception):
                    await self._extension_relay.stop()
            if self._playwright is not None and self._shared_browser_owner is None:
                with suppress(Exception):
                    await self._playwright.stop()
        finally:
            self._playwright = None
            if self._close_shared_browser and self._shared_browser_owner is not None:
                with suppress(Exception):
                    await self._shared_browser_owner.close()
            self._browser = None
            self._playwright_context = None
            self._extension_relay = None
            self._context = None
            self._session_log = None
            self._disconnected = False
            self._closed = True
            self._disconnect_listeners_registered = False

    def _should_close_browser_context(self) -> bool:
        if self._playwright_context is not None:
            return False
        if self._shared_browser_owner is not None and not self._config.browser_isolated:
            return False
        return True

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
        cwd = self._context.cwd if self._context is not None else Path.cwd()
        context = await self._ensure_context(cwd=cwd, roots=None)
        return await context.ensure_tab()

    async def _ensure_context(self, *, cwd: Path, roots: list[str] | None) -> Context:
        if self._context is not None:
            self._closed = False
            self._context.configure_client(
                roots=[Path(root) for root in roots] if roots is not None else None,
                cwd=cwd,
            )
            return self._context
        if self._shared_browser_owner is not None:
            self._browser = await self._shared_browser_owner._ensure_browser(cwd)
        if self._shared_browser_owner is None and self._playwright is None:
            self._playwright = await async_playwright().start()
            self._playwright.selectors.set_test_id_attribute(self._config.test_id_attribute)
        if self._browser is None and self._playwright_context is None:
            self._browser = await self._launch_browser(cwd)
        if self._playwright_context is not None:
            browser_context = self._playwright_context
        else:
            assert self._browser is not None
            if not self._config.browser_isolated and self._browser.contexts:
                browser_context = self._browser.contexts[0]
            else:
                browser_context = await self._browser.new_context(**self._config.browser_context_options)
        self._register_disconnect_listeners(browser_context)
        if self._config.action_timeout is not None:
            browser_context.set_default_timeout(self._config.action_timeout)
        if self._config.navigation_timeout is not None:
            browser_context.set_default_navigation_timeout(self._config.navigation_timeout)
        self._context = Context(browser_context, self._config, cwd=cwd)
        self._context.configure_client(
            roots=[Path(root) for root in roots] if roots is not None else None,
            cwd=cwd,
        )
        await self._context.initialize()
        self._closed = False
        if self._config.save_session:
            self._session_log = await SessionLog.create(self._context)
            self._context.session_log = self._session_log
        return self._context

    async def _ensure_browser(self, cwd: Path) -> Browser:
        if self._browser is not None:
            return self._browser
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._playwright.selectors.set_test_id_attribute(self._config.test_id_attribute)
        if self._browser is None and self._playwright_context is None:
            self._browser = await self._launch_browser(cwd)
        if self._browser is None and self._playwright_context is not None:
            browser = self._playwright_context.browser
            if browser is None:
                raise ValueError("Persistent browser context did not expose a browser instance.")
            self._browser = browser
        assert self._browser is not None
        return self._browser

    async def _launch_browser(self, cwd: Path | None = None) -> Browser:
        cwd = cwd or Path.cwd()
        assert self._playwright is not None
        if self._config.cdp_endpoint:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self._config.cdp_endpoint,
                headers=self._config.cdp_headers,
                timeout=self._config.cdp_timeout,
                artifacts_dir=self._traces_dir(cwd),
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
            try:
                from .extension_relay import CDPRelayServer
            except ModuleNotFoundError as exc:
                if exc.name and exc.name.startswith("websockets"):
                    raise ValueError(
                        '--extension requires the optional "extension" dependency group. '
                        'Install playwright-python-mcp[extension].'
                    ) from exc
                raise
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
        launch_options.setdefault("traces_dir", self._traces_dir(cwd))
        launch_options["handle_sigint"] = False
        launch_options["handle_sigterm"] = False

        browser_type = getattr(self._playwright, self._config.browser_name)
        if self._config.browser_user_data_dir is not None and self._config.browser_isolated:
            raise ValueError("Browser userDataDir is not supported in isolated mode.")
        if not self._config.browser_isolated:
            user_data_dir = self._config.browser_user_data_dir or await self._default_user_data_dir(cwd)
            if await _is_profile_locked_5_times(user_data_dir):
                raise ValueError(
                    f"Browser is already in use for {user_data_dir}, "
                    "use --isolated to run multiple instances of the same browser"
                )
            launch_options["ignore_default_args"] = _persistent_ignore_default_args(
                launch_options.get("ignore_default_args")
            )
            self._playwright_context = await browser_type.launch_persistent_context(
                user_data_dir,
                **launch_options,
                **self._config.browser_context_options,
            )
            browser = self._playwright_context.browser
            if browser is None:
                raise ValueError("Persistent browser context did not expose a browser instance.")
            return browser
        return await browser_type.launch(**launch_options)

    def _traces_dir(self, cwd: Path | None = None) -> Path:
        cwd = cwd or Path.cwd()
        return _output_dir(self._config, cwd) / "traces"

    async def _default_user_data_dir(self, cwd: Path | None = None) -> Path:
        cwd = cwd or Path.cwd()
        cache_root = _cache_root() / "ms-playwright-mcp"
        browser_token = self._config.browser_channel or self._config.browser_name
        cwd_hash = hashlib.sha256(str(cwd).encode()).hexdigest()[:7]
        user_data_dir = cache_root / f"mcp-{browser_token}-{cwd_hash}"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        return user_data_dir

    def _register_disconnect_listeners(self, browser_context: PlaywrightBrowserContext) -> None:
        if self._disconnect_listeners_registered:
            return

        def mark_disconnected(*_args: Any) -> None:
            self._disconnected = True

        browser_context.on("close", mark_disconnected)
        browser = browser_context.browser
        if browser is not None:
            browser.on("disconnected", mark_disconnected)
        self._disconnect_listeners_registered = True


def _blocks_on_modal_state(context: Context, tool: Tool) -> bool:
    if not tool.blocks_on_modal_state and tool.clears_modal_state is None:
        return False
    tab = context.current_tab()
    if tab is None:
        return False
    modal_states = tab.modal_states()
    if not modal_states:
        return tool.clears_modal_state is not None
    if tool.clears_modal_state is not None:
        return not any(state.get("type") == tool.clears_modal_state for state in modal_states)
    return True


def _drain_unhandled_errors(context: Context, response: Response) -> None:
    errors: list[str] = getattr(context, "drain_unhandled_errors", lambda: [])()
    for error in errors:
        response.add_error(error)


def _output_dir(config: ServerConfig, cwd: Path) -> Path:
    if config.output_dir is not None:
        return config.output_dir.resolve()
    base_name = ".playwright-mcp"
    if _is_system_directory(cwd) or not os.access(cwd, os.W_OK):
        return Path(tempfile.gettempdir()) / base_name
    return cwd / base_name


def _client_cwd(*, meta: dict[str, Any] | None, roots: list[str] | None) -> Path:
    if meta and meta.get("cwd"):
        return Path(str(meta["cwd"]))
    if roots:
        return Path(roots[0])
    return Path.cwd()


def _format_error(message: str, *, json_mode: bool) -> ToolResult:
    if json_mode:
        return ToolResult(content=json.dumps({"isError": True, "error": message}, indent=2), is_error=True)
    return ToolResult(content=f"### Error\n{message}", is_error=True)


def _attach_close_marker(result: str | ToolResult) -> ToolResult:
    if isinstance(result, ToolResult):
        meta = dict(getattr(result, "meta", None) or {})
        meta["isClose"] = True
        result.meta = meta
        return result
    return ToolResult(content=result, meta={"isClose": True})


def _cache_root() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")


def _is_system_directory(path: Path) -> bool:
    resolved = path.resolve()
    return resolved in {Path("/"), Path("/tmp"), Path("/var"), Path("/usr"), Path("/bin"), Path("/etc")}


def _persistent_ignore_default_args(value: Any) -> bool | list[str]:
    if value is True:
        return True
    args: list[str] = [str(item) for item in value] if isinstance(value, list) else []
    return ["--disable-extensions", *args]


async def _is_profile_locked_5_times(user_data_dir: Path) -> bool:
    for _ in range(5):
        if not _is_profile_locked(user_data_dir):
            return False
        await asyncio.sleep(1)
    return True


def _is_profile_locked(user_data_dir: Path) -> bool:
    lock_file = "lockfile" if os.name == "nt" else "SingletonLock"
    lock_path = user_data_dir / lock_file
    if os.name == "nt":
        if not lock_path.exists():
            return False
        try:
            with lock_path.open("r+b"):
                return False
        except OSError:
            return True

    try:
        target = os.readlink(lock_path)
        pid = int(target.rsplit("-", 1)[-1])
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
