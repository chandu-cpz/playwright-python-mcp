from __future__ import annotations

from typing import Any

from playwright_python_mcp.backend.codegen import python_call, python_literal
from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool, param


async def _handle_press_key(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    key = params["key"]
    response.add_code(f"# Press {key}")
    response.add_code(f"await page.keyboard.press({python_literal(key)})")
    if key == "Enter":
        response.set_include_snapshot()
    await tab.press_key(key)


async def _handle_type(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    resolved = await tab.resolve_target(target=params["target"], element=params.get("element"))
    text = params["text"]
    submit = params.get("submit", False)
    slowly = params.get("slowly", False)
    if slowly:
        response.set_include_snapshot()
        response.add_code(python_call(resolved.code, "press_sequentially", text))
    else:
        response.add_code(python_call(resolved.code, "fill", text))
    if submit:
        response.set_include_snapshot()
        response.add_code(python_call(resolved.code, "press", "Enter"))
    await tab.type_text(resolved, text=text, submit=submit, slowly=slowly)


keyboard_tools = [
    Tool(
        name="browser_press_key",
        capability="core-input",
        parameters=(param("key", str),),
        handler=_handle_press_key,
    ),
    Tool(
        name="browser_type",
        capability="core-input",
        parameters=(
            param("target", str),
            param("text", str),
            param("element", str | None, None),
            param("submit", bool, False),
            param("slowly", bool, False),
        ),
        handler=_handle_type,
    ),
]
