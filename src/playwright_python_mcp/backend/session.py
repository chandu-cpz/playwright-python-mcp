from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    async_playwright,
)

from .locator_generator import as_python_locator


Button = Literal["left", "middle", "right"]
Modifier = Literal["Alt", "Control", "ControlOrMeta", "Meta", "Shift"]
_REF_PATTERN = re.compile(r"^(?:f\d+)?e\d+$")


@dataclass(slots=True)
class ResolvedTarget:
    locator: Locator
    code: str


class BrowserSession:
    def __init__(
        self,
        *,
        browser_name: str,
        headless: bool,
        allow_unrestricted_file_access: bool,
        test_id_attribute: str,
    ) -> None:
        self._browser_name = browser_name
        self._headless = headless
        self._allow_unrestricted_file_access = allow_unrestricted_file_access
        self._test_id_attribute = test_id_attribute
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def has_page(self) -> bool:
        return self._page is not None

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def check_url_and_navigate(self, url: str) -> str:
        parsed = urlparse(url)
        if not parsed.scheme:
            if url.startswith("localhost"):
                url = "http://" + url
            else:
                url = "https://" + url
        self._check_url_allowed(url)
        page = await self.ensure_page()
        await page.goto(url, wait_until="domcontentloaded")
        return url

    async def go_back(self) -> None:
        page = await self.ensure_page()
        await page.go_back(wait_until="commit")

    async def resize(self, *, width: int, height: int) -> None:
        page = await self.ensure_page()
        await page.set_viewport_size({"width": width, "height": height})

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
        page = await self.ensure_page()
        lines = [f"- Page URL: {page.url}"]
        title = await page.title()
        if title:
            lines.append(f"- Page Title: {title}")
        return lines

    async def resolve_target(self, *, target: str, element: str | None = None) -> ResolvedTarget:
        page = await self.ensure_page()
        if not _REF_PATTERN.match(target):
            handle = await page.query_selector(target)
            if handle is None:
                raise ValueError(f'"{target}" does not match any elements.')
            await handle.dispose()
            return ResolvedTarget(
                locator=page.locator(target),
                code=as_python_locator(target),
            )

        try:
            locator = page.locator(f"aria-ref={target}")
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
        page = await self.ensure_page()
        if target is None:
            return page.locator("body")
        return (await self.resolve_target(target=target)).locator

    async def ensure_page(self) -> Page:
        if self._page is not None:
            return self._page

        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._playwright.selectors.set_test_id_attribute(self._test_id_attribute)

        if self._browser is None:
            self._browser = await self._launch_browser()

        if self._context is None:
            self._context = await self._browser.new_context()

        self._page = await self._context.new_page()
        return self._page

    async def _launch_browser(self) -> Browser:
        assert self._playwright is not None
        headless = self._headless
        if not headless and os.name == "posix" and not os.environ.get("DISPLAY"):
            headless = True

        if self._browser_name == "chromium":
            return await self._playwright.chromium.launch(headless=headless)
        if self._browser_name in {"firefox", "webkit"}:
            browser_type = getattr(self._playwright, self._browser_name)
            return await browser_type.launch(headless=headless)
        return await self._playwright.chromium.launch(
            channel=self._browser_name,
            headless=headless,
        )

    def _check_url_allowed(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme == "file" and not self._allow_unrestricted_file_access:
            raise ValueError(f'Error: Access to "file:" protocol is blocked. Attempted URL: "{url}"')
