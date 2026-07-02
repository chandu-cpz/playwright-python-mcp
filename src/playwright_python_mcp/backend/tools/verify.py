from __future__ import annotations

from typing import Any, Literal

from playwright_python_mcp.backend.codegen import python_literal
from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.locator_generator import as_python_locator
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool, param


VerifyValueType = Literal["textbox", "checkbox", "radio", "combobox", "slider"]


async def _handle_verify_element_visible(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    role = params["role"]
    accessible_name = params["accessibleName"]
    for frame in tab.page.frames:
        locator = frame.get_by_role(role, name=accessible_name)
        if await locator.count() > 0:
            resolved = await locator.normalize()
            # Uses private _impl_obj because Playwright Python does not expose a
            # public `selector` property on normalized locators yet.
            response.add_code(f"await expect(page.{as_python_locator(resolved._impl_obj._selector)}).to_be_visible()")
            response.add_text_result("Done")
            return
    response.add_error(f'Element with role "{role}" and accessible name "{accessible_name}" not found')


async def _handle_verify_text_visible(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    text = params["text"]
    for frame in tab.page.frames:
        locator = frame.get_by_text(text).filter(visible=True)
        if await locator.count() > 0:
            resolved = await locator.normalize()
            # Uses private _impl_obj because Playwright Python does not expose a
            # public `selector` property on normalized locators yet.
            response.add_code(f"await expect(page.{as_python_locator(resolved._impl_obj._selector)}).to_be_visible()")
            response.add_text_result("Done")
            return
    response.add_error("Text not found")


async def _handle_verify_list_visible(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    resolved = await tab.resolve_target(target=params["target"], element=params.get("element"))
    item_texts: list[str] = []
    for item in params["items"]:
        item_locator = resolved.locator.get_by_text(item)
        if await item_locator.count() == 0:
            response.add_error(f'Item "{item}" not found')
            return
        item_texts.append((await item_locator.text_content(timeout=context.config.expect_timeout)) or "")
    aria_snapshot = "\n".join(["- list:", *(f"  - listitem: {python_literal(item)}" for item in item_texts)])
    response.add_code(f"await expect(page.locator(\"body\")).to_match_aria_snapshot({python_literal(aria_snapshot)})")
    response.add_text_result("Done")


async def _handle_verify_value(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    resolved = await tab.resolve_target(target=params["target"], element=params.get("element"))
    expected = params["value"]
    locator_source = f"page.{resolved.code}"
    if params["type"] in {"textbox", "slider", "combobox"}:
        actual = await resolved.locator.input_value(timeout=context.config.expect_timeout)
        if actual != expected:
            response.add_error(f'Expected value "{expected}", but got "{actual}"')
            return
        response.add_code(f"await expect({locator_source}).to_have_value({python_literal(expected)})")
    elif params["type"] in {"checkbox", "radio"}:
        actual_bool = await resolved.locator.is_checked(timeout=context.config.expect_timeout)
        expected_bool = expected == "true"
        if actual_bool != expected_bool:
            response.add_error(f'Expected value "{expected}", but got "{str(actual_bool).lower()}"')
            return
        matcher = "to_be_checked" if actual_bool else "not_to_be_checked"
        response.add_code(f"await expect({locator_source}).{matcher}()")
    response.add_text_result("Done")


verify_tools = [
    Tool(
        name="browser_verify_element_visible",
        capability="testing",
        parameters=(param("role", str), param("accessibleName", str)),
        handler=_handle_verify_element_visible,
    ),
    Tool(
        name="browser_verify_text_visible",
        capability="testing",
        parameters=(param("text", str),),
        handler=_handle_verify_text_visible,
    ),
    Tool(
        name="browser_verify_list_visible",
        capability="testing",
        parameters=(param("element", str), param("target", str), param("items", list[str])),
        handler=_handle_verify_list_visible,
    ),
    Tool(
        name="browser_verify_value",
        capability="testing",
        parameters=(
            param("type", VerifyValueType),
            param("element", str),
            param("target", str),
            param("value", str),
        ),
        handler=_handle_verify_value,
    ),
]
