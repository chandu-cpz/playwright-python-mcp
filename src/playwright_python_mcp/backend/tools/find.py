from __future__ import annotations

import re
from typing import Any

from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool, param


async def _handle_find(context: Context, params: dict[str, Any], response: Response) -> None:
    text = params.get("text")
    regex = params.get("regex")
    if (text is None) == (regex is None):
        raise ValueError("Exactly one of text or regex must be provided")

    tab = await context.ensure_tab()
    snapshot = await tab.page.aria_snapshot(mode="ai")
    matcher = _matcher(text=text, regex=regex)
    snippets = _matching_snippets(snapshot, matcher)
    if snippets:
        response.add_text_result("\n\n".join(snippets))
    else:
        response.add_text_result("No matches found")


def _matcher(*, text: str | None, regex: str | None):
    if text is not None:
        return lambda line: text in line
    assert regex is not None
    pattern, flags = _parse_regex(regex)
    compiled = re.compile(pattern, flags)
    return lambda line: compiled.search(line) is not None


def _parse_regex(value: str) -> tuple[str, int]:
    if not value.startswith("/"):
        return value, 0
    slash = _last_unescaped_slash(value)
    if slash <= 0:
        return value, 0
    pattern = value[1:slash]
    flags_text = value[slash + 1 :]
    flags = 0
    for flag in flags_text:
        if flag == "i":
            flags |= re.IGNORECASE
        elif flag == "m":
            flags |= re.MULTILINE
        elif flag == "s":
            flags |= re.DOTALL
        elif flag in {"g", "u", "y"}:
            continue
        else:
            raise ValueError(f'Unsupported regex flag "{flag}"')
    return pattern, flags


def _last_unescaped_slash(value: str) -> int:
    for index in range(len(value) - 1, 0, -1):
        if value[index] != "/":
            continue
        backslashes = 0
        cursor = index - 1
        while cursor >= 0 and value[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2 == 0:
            return index
    return -1


def _matching_snippets(snapshot: str, matcher) -> list[str]:
    lines = snapshot.splitlines()
    snippets: list[str] = []
    seen: set[tuple[int, int]] = set()
    for index, line in enumerate(lines):
        if not matcher(line):
            continue
        start = max(0, index - 3)
        end = min(len(lines), index + 4)
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)
        snippets.append("\n".join(lines[start:end]))
    return snippets


find_tools = [
    Tool(
        name="browser_find",
        capability="core",
        tool_type="readOnly",
        parameters=(param("text", str | None, None), param("regex", str | None, None)),
        handler=_handle_find,
    )
]
