from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from playwright.async_api import ConsoleMessage, Locator, Page

from .locator_generator import as_python_locator


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

    def render(self) -> str:
        return f"[{self.type.upper()}] {self.text}"


class Tab:
    """Page-level runtime.

    Upstream responsibility:
    - packages/playwright-core/src/tools/backend/tab.ts
    """

    def __init__(self, page: Page) -> None:
        self.page = page
        self.crashed = False
        self._console_messages: list[ConsoleEntry] = []
        page.on("console", self._on_console_message)

    async def close(self) -> None:
        await self.page.close()

    async def navigate(self, url: str) -> None:
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
        if double_click:
            await resolved.locator.dblclick(button=button, modifiers=modifiers)
        else:
            await resolved.locator.click(button=button, modifiers=modifiers)

    async def select_option(self, resolved: ResolvedTarget, *, values: list[str]) -> None:
        await resolved.locator.select_option(values)

    async def hover(self, resolved: ResolvedTarget) -> None:
        await resolved.locator.hover()

    async def drag_to(self, start: ResolvedTarget, end: ResolvedTarget) -> None:
        await start.locator.drag_to(end.locator)

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
        locator = await self.snapshot_locator(target)
        return await locator.aria_snapshot(mode="ai", depth=depth, boxes=boxes)

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

    def console_messages(self) -> list[str]:
        return [message.render() for message in self._console_messages]

    def _on_console_message(self, message: ConsoleMessage) -> None:
        self._console_messages.append(ConsoleEntry(type=message.type, text=message.text))
