from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastmcp.tools.base import ToolResult

if TYPE_CHECKING:
    from .browser_backend import BrowserBackend


@dataclass(slots=True)
class SnapshotRequest:
    target: str | None = None
    depth: int | None = None
    boxes: bool | None = None


class Response:
    def __init__(self, backend: BrowserBackend) -> None:
        self._backend = backend
        self._results: list[str] = []
        self._errors: list[str] = []
        self._code: list[str] = []
        self._snapshot_request: SnapshotRequest | None = None
        self._is_close = False

    def add_text_result(self, text: str) -> None:
        self._results.append(text)

    def add_error(self, error: str) -> None:
        self._errors.append(error)

    def add_code(self, code: str) -> None:
        self._code.append(code)

    def set_include_snapshot(self) -> None:
        self._snapshot_request = SnapshotRequest()

    def set_include_full_snapshot(
        self,
        *,
        target: str | None = None,
        depth: int | None = None,
        boxes: bool | None = None,
    ) -> None:
        self._snapshot_request = SnapshotRequest(target=target, depth=depth, boxes=boxes)

    def set_close(self) -> None:
        self._is_close = True

    async def serialize(self) -> str | ToolResult:
        sections: list[str] = []

        if self._errors:
            sections.append("### Error\n" + "\n".join(self._errors))
        if self._results:
            sections.append("### Result\n" + "\n".join(self._results))
        if self._code:
            sections.append("### Ran Playwright code\n```python\n" + "\n".join(self._code) + "\n```")

        if self._snapshot_request is not None and self._backend.has_page():
            page_lines = await self._backend.render_page_markdown()
            sections.append("### Page\n" + "\n".join(page_lines))
            snapshot = await self._backend.capture_snapshot(
                target=self._snapshot_request.target,
                depth=self._snapshot_request.depth,
                boxes=self._snapshot_request.boxes,
            )
            sections.append("### Snapshot\n```yaml\n" + snapshot + "\n```")

        text = "\n\n".join(sections)
        if self._errors:
            return ToolResult(content=text, is_error=True, meta=_result_meta(self._is_close))
        if self._is_close:
            return ToolResult(content=text, meta=_result_meta(True))
        return text


def render_tabs_markdown(tabs: list[object]) -> list[str]:
    if not tabs:
        return ["No open tabs. Navigate to a URL to create one."]
    raise NotImplementedError("Multi-tab rendering is not implemented yet.")


def _result_meta(is_close: bool) -> dict[str, object] | None:
    if not is_close:
        return None
    return {"isClose": True}
