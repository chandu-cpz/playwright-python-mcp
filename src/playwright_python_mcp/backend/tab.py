from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from playwright.async_api import ConsoleMessage, Dialog, Download, Error, FileChooser, Locator, Page, Request

from .locator_generator import as_python_locator
from .log_file import LogFile

if TYPE_CHECKING:
    from .context import Context


Button = Literal["left", "middle", "right"]
Modifier = Literal["Alt", "Control", "ControlOrMeta", "Meta", "Shift"]
_REF_PATTERN = re.compile(r"^(?:f\d+)?e\d+$")


@dataclass(slots=True)
class ResolvedTarget:
    locator: Locator
    code: str


@dataclass(slots=True)
class ConsoleEntry:
    type: str
    text: str
    location_url: str | None = None
    location_line: int | None = None
    navigation_index: int = 0

    def render(self) -> str:
        line = f"[{self.type.upper()}] {self.text}"
        if self.location_url:
            line += f" @ {self.location_url}"
            if self.location_line is not None:
                line += f":{self.location_line}"
        return line


@dataclass(slots=True)
class RequestEntry:
    request: Request


@dataclass(slots=True)
class TabHeader:
    title: str
    url: str
    current: bool
    crashed: bool
    console: dict[str, int]
    changed: bool = False


@dataclass(slots=True)
class TabSnapshot:
    aria_snapshot: str
    modal_states: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    console_link: str | None = None


class Tab:
    """Page-level runtime.

    Upstream responsibility:
    - packages/playwright-core/src/tools/backend/tab.ts
    """

    def __init__(self, context: "Context", page: Page) -> None:
        self.context = context
        self.page = page
        self.crashed = False
        self._last_header = TabHeader(
            title="about:blank",
            url="about:blank",
            current=False,
            crashed=False,
            console={"total": 0, "errors": 0, "warnings": 0},
        )
        self._console_messages: list[ConsoleEntry] = []
        self._requests: list[RequestEntry] = []
        self._recent_event_entries: list[dict[str, Any]] = []
        self._modal_states: list[dict[str, Any]] = []
        self._modal_event = asyncio.Event()
        self._navigation_index = 0
        self._console_log = LogFile(context, file_prefix="console", title="Console")
        page.on("console", self._on_console_message)
        page.on("pageerror", self._on_page_error)
        page.on("request", self._on_request)
        page.on("dialog", self._on_dialog)
        page.on("filechooser", self._on_file_chooser)
        page.on("download", self._on_download)

    async def dispose(self) -> None:
        self._console_log.stop()

    async def close(self) -> None:
        await self.page.close()

    async def navigate(self, url: str) -> None:
        self._clear_collected_artifacts()
        await self.page.goto(url, wait_until="domcontentloaded")

    async def go_back(self) -> None:
        await self.page.go_back(wait_until="commit")

    async def go_forward(self) -> None:
        await self.page.go_forward(wait_until="commit")

    async def reload(self) -> None:
        await self.page.reload()

    async def resize(self, *, width: int, height: int) -> None:
        await self.page.set_viewport_size({"width": width, "height": height})

    async def click(
        self,
        resolved: ResolvedTarget,
        *,
        double_click: bool = False,
        button: Button | None = None,
        modifiers: list[Modifier] | None = None,
    ) -> None:
        async def action() -> None:
            if double_click:
                await resolved.locator.dblclick(button=button, modifiers=modifiers)
            else:
                await resolved.locator.click(button=button, modifiers=modifiers)

        await self.wait_for_completion(action)

    async def select_option(self, resolved: ResolvedTarget, *, values: list[str]) -> None:
        await resolved.locator.select_option(values)

    async def hover(self, resolved: ResolvedTarget) -> None:
        await resolved.locator.hover()

    async def drag_to(self, start: ResolvedTarget, end: ResolvedTarget) -> None:
        await self.wait_for_completion(lambda: start.locator.drag_to(end.locator))

    async def mouse_move_xy(self, *, x: int | float, y: int | float) -> None:
        await self.page.mouse.move(x, y)

    async def mouse_click_xy(
        self,
        *,
        x: int | float,
        y: int | float,
        button: Button | None = None,
        click_count: int | None = None,
        delay: int | float | None = None,
    ) -> None:
        await self.wait_for_completion(
            lambda: self.page.mouse.click(x, y, button=button, click_count=click_count, delay=delay)
        )

    async def mouse_drag_xy(
        self,
        *,
        start_x: int | float,
        start_y: int | float,
        end_x: int | float,
        end_y: int | float,
    ) -> None:
        async def action() -> None:
            await self.page.mouse.move(start_x, start_y)
            await self.page.mouse.down()
            await self.page.mouse.move(end_x, end_y)
            await self.page.mouse.up()

        await self.wait_for_completion(action)

    async def wait_for_completion(self, action) -> None:
        if self._modal_states:
            return
        self._modal_event = asyncio.Event()

        async def action_and_settle() -> None:
            await action()
            await asyncio.sleep(0.5)

        action_task = asyncio.create_task(action_and_settle())
        modal_task = asyncio.create_task(self._modal_event.wait())
        done, pending = await asyncio.wait({action_task, modal_task}, return_when=asyncio.FIRST_COMPLETED)
        if action_task in done:
            modal_task.cancel()
            await action_task
        else:
            action_task.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)

    async def press_key(self, key: str) -> None:
        await self.page.keyboard.press(key)

    async def type_text(
        self,
        resolved: ResolvedTarget,
        *,
        text: str,
        submit: bool = False,
        slowly: bool = False,
    ) -> None:
        if slowly:
            await resolved.locator.press_sequentially(text)
        else:
            await resolved.locator.fill(text)
        if submit:
            await resolved.locator.press("Enter")

    async def fill_form_field(self, resolved: ResolvedTarget, *, field_type: str, value: str) -> None:
        if field_type in {"textbox", "slider"}:
            await resolved.locator.fill(value)
        elif field_type in {"checkbox", "radio"}:
            await resolved.locator.set_checked(value == "true")
        elif field_type == "combobox":
            await resolved.locator.select_option(label=value)
        else:
            raise ValueError(f"Unsupported form field type: {field_type}")

    async def evaluate(self, expression: str, resolved: ResolvedTarget | None = None) -> tuple[Any, bool]:
        if resolved is not None:
            result = await resolved.locator.evaluate(
                """async (element, expr) => {
                    const value = eval(`(${expr})`);
                    const isFunction = typeof value === 'function';
                    const result = await (isFunction ? value(element) : value);
                    return { result, isFunction };
                }""",
                expression,
            )
        else:
            result = await self.page.evaluate(
                """async expr => {
                    const value = eval(`(${expr})`);
                    const isFunction = typeof value === 'function';
                    const result = await (isFunction ? value() : value);
                    return { result, isFunction };
                }""",
                expression,
            )
        return result["result"], result["isFunction"]

    async def capture_snapshot(
        self,
        *,
        target: str | None = None,
        depth: int | None = None,
        boxes: bool | None = None,
    ) -> str:
        return (await self.capture_tab_snapshot(target=target, depth=depth, boxes=boxes)).aria_snapshot

    async def capture_tab_snapshot(
        self,
        *,
        target: str | None = None,
        depth: int | None = None,
        boxes: bool | None = None,
        relative_to: Path | None = None,
    ) -> TabSnapshot:
        if self._modal_states:
            return TabSnapshot(
                aria_snapshot="",
                modal_states=list(self._modal_states),
                events=self._recent_event_entries,
                console_link=await self._console_log.take(relative_to=relative_to),
            )
        locator = await self.snapshot_locator(target)
        aria_snapshot = await locator.aria_snapshot(mode="ai", depth=depth, boxes=boxes)
        snapshot = TabSnapshot(
            aria_snapshot=aria_snapshot,
            modal_states=list(self._modal_states),
            events=self._recent_event_entries,
            console_link=await self._console_log.take(relative_to=relative_to),
        )
        self._recent_event_entries = []
        return snapshot

    async def header_snapshot(self) -> TabHeader:
        title = "" if self.crashed else await self.page.title()
        header = TabHeader(
            title=title,
            url=self.page.url,
            current=self.context.current_tab() is self,
            crashed=self.crashed,
            console=self.console_message_count(),
        )
        header.changed = header != self._last_header
        self._last_header = TabHeader(
            title=header.title,
            url=header.url,
            current=header.current,
            crashed=header.crashed,
            console=dict(header.console),
        )
        return header

    async def render_page_markdown(self) -> list[str]:
        lines = [f"- Page URL: {self.page.url}"]
        title = await self.page.title()
        if title:
            lines.append(f"- Page Title: {title}")
        return lines

    async def resolve_target(self, *, target: str, element: str | None = None) -> ResolvedTarget:
        if not _REF_PATTERN.match(target):
            handle = await self.page.query_selector(target)
            if handle is None:
                raise ValueError(f'"{target}" does not match any elements.')
            await handle.dispose()
            return ResolvedTarget(
                locator=self.page.locator(target),
                code=as_python_locator(target),
            )

        try:
            locator = self.page.locator(f"aria-ref={target}")
            if element:
                locator = locator.describe(element)
            normalized = await locator.normalize()
            return ResolvedTarget(
                locator=locator,
                code=as_python_locator(normalized._impl_obj._selector),
            )
        except Exception as exc:
            raise ValueError(
                f"Ref {target} not found in the current page snapshot. Try capturing new snapshot."
            ) from exc

    async def snapshot_locator(self, target: str | None) -> Locator:
        if target is None:
            return self.page.locator("body")
        return (await self.resolve_target(target=target)).locator

    def console_message_count(self) -> dict[str, int]:
        messages = self._console_entries(all_messages=False)
        return {
            "total": len(messages),
            "errors": sum(message.type == "error" for message in messages),
            "warnings": sum(message.type == "warning" for message in messages),
        }

    def console_messages(self, *, level: str = "info", all_messages: bool = False) -> list[str]:
        return [
            message.render()
            for message in self._console_entries(all_messages=all_messages)
            if _should_include_console_message(level, message.type)
        ]

    def requests(self) -> list[Request]:
        return [entry.request for entry in self._requests]

    def modal_states(self) -> list[dict[str, Any]]:
        return self._modal_states

    def clear_modal_state(self, modal_state: dict[str, Any]) -> None:
        self._modal_states = [state for state in self._modal_states if state is not modal_state]

    def clear_requests(self) -> None:
        self._requests.clear()

    def clear_console_messages(self) -> None:
        self._console_messages.clear()
        self._console_log.stop()
        self._console_log = LogFile(self.context, file_prefix="console", title="Console")

    def _console_entries(self, *, all_messages: bool) -> list[ConsoleEntry]:
        if all_messages:
            return list(self._console_messages)
        return [
            message
            for message in self._console_messages
            if message.navigation_index == self._navigation_index
        ]

    def _clear_collected_artifacts(self) -> None:
        self._navigation_index += 1
        self._requests.clear()
        self._recent_event_entries.clear()
        self._console_log.stop()
        self._console_log = LogFile(self.context, file_prefix="console", title="Console")

    def _on_console_message(self, message: ConsoleMessage) -> None:
        location = message.location
        entry = ConsoleEntry(
            type=message.type,
            text=message.text,
            location_url=location.get("url") or None,
            location_line=location.get("lineNumber") or location.get("line"),
            navigation_index=self._navigation_index,
        )
        self._console_messages.append(entry)
        self._add_log_entry({"type": "console", "message": entry})
        self._append_console_log(entry)

    def _on_page_error(self, error: Error) -> None:
        text = str(error)
        if not text.startswith("Error:"):
            text = f"Error: {text}"
        entry = ConsoleEntry(
            type="error",
            text=text,
            location_url=self.page.url,
            navigation_index=self._navigation_index,
        )
        self._console_messages.append(entry)
        self._add_log_entry({"type": "console", "message": entry})
        self._append_console_log(entry)

    def _on_request(self, request: Request) -> None:
        self._requests.append(RequestEntry(request=request))
        self._add_log_entry({"type": "request", "request": request})

    def _on_dialog(self, dialog: Dialog) -> None:
        self._modal_states.append(
            {
                "type": "dialog",
                "description": f'"{dialog.type}" dialog with message "{dialog.message}"',
                "dialog": dialog,
                "cleared_by": "browser_handle_dialog",
            }
        )
        self._modal_event.set()

    def _on_file_chooser(self, file_chooser: FileChooser) -> None:
        self._modal_states.append(
            {
                "type": "fileChooser",
                "description": "File chooser",
                "file_chooser": file_chooser,
                "cleared_by": "browser_file_upload",
            }
        )
        self._modal_event.set()

    def _on_download(self, download: Download) -> None:
        import asyncio

        asyncio.create_task(self._download_started(download))

    async def _download_started(self, download: Download) -> None:
        from .context import FilenameTemplate

        suggested_filename = download.suggested_filename
        output_file = await self.context.output_file(
            FilenameTemplate(
                prefix="download",
                ext="bin",
                suggested_filename=suggested_filename,
            ),
            origin="code",
        )
        self._add_log_entry({"type": "download-start", "suggested_filename": suggested_filename})
        await download.save_as(output_file)
        self._add_log_entry(
            {
                "type": "download-finish",
                "suggested_filename": suggested_filename,
                "output_file": output_file,
            }
        )

    def _add_log_entry(self, entry: dict[str, Any]) -> None:
        self._recent_event_entries.append(entry)

    def _append_console_log(self, entry: ConsoleEntry) -> None:
        import asyncio
        import time

        if not _should_include_console_message(self.context.config.console_level, entry.type):
            return
        asyncio.create_task(self._console_log.append_line(time.time() * 1000, entry.render()))


def _should_include_console_message(level: str, message_type: str) -> bool:
    severity = {
        "debug": 0,
        "log": 1,
        "info": 1,
        "warning": 2,
        "error": 3,
    }
    threshold = severity.get(level, severity["info"])
    return severity.get(message_type, severity["info"]) >= threshold
