from __future__ import annotations

import json
from typing import Any

from playwright_python_mcp.backend.codegen import python_literal
from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool, param


async def _handle_evaluate(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    expression = params["function"]
    resolved = None
    if params.get("target") is not None:
        resolved = await tab.resolve_target(target=params["target"], element=params.get("element") or "element")
    result, is_function = await tab.evaluate(expression, resolved)
    code_expression = expression if is_function else f"() => ({expression})"
    if resolved is not None:
        response.add_code(f"await page.{resolved.code}.evaluate({python_literal(code_expression)})")
    else:
        response.add_code(f"await page.evaluate({python_literal(code_expression)})")
    response.add_text_result("undefined" if result is None else json.dumps(result, indent=2))


evaluate_tools = [
    Tool(
        name="browser_evaluate",
        capability="core",
        parameters=(
            param("function", str),
            param("target", str | None, None),
            param("element", str | None, None),
            param("filename", str | None, None),
        ),
        handler=_handle_evaluate,
    )
]
