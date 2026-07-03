from __future__ import annotations

from typing import Any, Literal, TypedDict

from playwright_python_mcp.backend.codegen import python_call, python_literal
from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import param, tab_tool


class FormField(TypedDict):
    name: str
    target: str
    type: Literal["textbox", "checkbox", "radio", "combobox", "slider"]
    value: str


async def _handle_fill_form(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    for field in params["fields"]:
        resolved = await tab.resolve_target(target=field["target"], element=field.get("name"))
        field_type = field["type"]
        value = field["value"]
        if field_type in {"textbox", "slider"}:
            secret = context.lookup_secret(value)
            await tab.fill_form_field(resolved, field_type=field_type, value=secret.value)
            response.add_code(f"await page.{resolved.code}.fill({secret.code})")
        elif field_type in {"checkbox", "radio"}:
            await tab.fill_form_field(resolved, field_type=field_type, value=value)
            response.add_code(python_call(resolved.code, "set_checked", value == "true"))
        elif field_type == "combobox":
            await tab.fill_form_field(resolved, field_type=field_type, value=value)
            response.add_code(f"await page.{resolved.code}.select_option(label={python_literal(value)})")


form_tools = [
    tab_tool(
        name="browser_fill_form",
        capability="core",
        tool_type="input",
        parameters=(param("fields", list[FormField]),),
        handler=_handle_fill_form,
    )
]
