from __future__ import annotations

from typing import Any

from playwright_python_mcp.backend.codegen import python_call, python_invocation
from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tab import Button, Modifier
from playwright_python_mcp.backend.tool import Tool, param


async def _handle_snapshot(context: Context, params: dict[str, Any], response: Response) -> None:
    response.set_include_full_snapshot(
        target=params.get("target"),
        depth=params.get("depth"),
        boxes=params.get("boxes"),
    )


async def _handle_click(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    resolved = await tab.resolve_target(target=params["target"], element=params.get("element"))
    double_click = params.get("doubleClick", False)
    button = params.get("button")
    modifiers = params.get("modifiers")
    await tab.click(resolved, double_click=double_click, button=button, modifiers=modifiers)
    response.set_include_snapshot()
    action = "dblclick" if double_click else "click"
    options: list[tuple[str, object]] = []
    if button is not None:
        options.append(("button", button))
    if modifiers is not None:
        options.append(("modifiers", modifiers))
    response.add_code(python_invocation(resolved.code, action, options or None))


async def _handle_select_option(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    resolved = await tab.resolve_target(target=params["target"], element=params.get("element"))
    values = params["values"]
    await tab.select_option(resolved, values=values)
    response.set_include_snapshot()
    response.add_code(python_call(resolved.code, "select_option", values))


async def _handle_hover(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    resolved = await tab.resolve_target(target=params["target"], element=params.get("element"))
    response.set_include_snapshot()
    response.add_code(python_invocation(resolved.code, "hover"))
    await tab.hover(resolved)


async def _handle_drag(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    start = await tab.resolve_target(target=params["startTarget"], element=params.get("startElement"))
    end = await tab.resolve_target(target=params["endTarget"], element=params.get("endElement"))
    response.set_include_snapshot()
    response.add_code(f"await page.{start.code}.drag_to(page.{end.code})")
    await tab.drag_to(start, end)


async def _handle_generate_locator(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    resolved = await tab.resolve_target(target=params["target"], element=params.get("element"))
    response.add_text_result(resolved.code)


snapshot_tools = [
    Tool(
        name="browser_snapshot",
        capability="core",
        parameters=(
            param("target", str | None, None),
            param("depth", int | None, None),
            param("boxes", bool | None, None),
        ),
        handler=_handle_snapshot,
    ),
    Tool(
        name="browser_click",
        capability="core",
        parameters=(
            param("target", str),
            param("element", str | None, None),
            param("doubleClick", bool, False),
            param("button", Button | None, None),
            param("modifiers", list[Modifier] | None, None),
        ),
        handler=_handle_click,
    ),
    Tool(
        name="browser_select_option",
        capability="core",
        parameters=(
            param("target", str),
            param("values", list[str]),
            param("element", str | None, None),
        ),
        handler=_handle_select_option,
    ),
    Tool(
        name="browser_hover",
        capability="core",
        parameters=(param("target", str), param("element", str | None, None)),
        handler=_handle_hover,
    ),
    Tool(
        name="browser_drag",
        capability="core",
        parameters=(
            param("startTarget", str),
            param("endTarget", str),
            param("startElement", str | None, None),
            param("endElement", str | None, None),
        ),
        handler=_handle_drag,
    ),
    Tool(
        name="browser_generate_locator",
        capability="testing",
        parameters=(param("target", str), param("element", str | None, None)),
        handler=_handle_generate_locator,
    ),
]
