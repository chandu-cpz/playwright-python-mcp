from __future__ import annotations

import inspect
import json
import textwrap
from typing import Any

from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool, param


async def _handle_run_code_unsafe(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    code = params.get("code")
    if params.get("filename"):
        resolved = await response.resolve_client_filename(params["filename"])
        code = resolved.read_text(encoding="utf-8")
    if not code:
        raise ValueError("Either code or filename must be provided")

    response.add_code(code)
    try:
        result = await _execute_python_code(code, tab.page)
    except Exception as exc:
        response.add_error(str(exc))
        return
    if result is not None:
        response.add_text_result(json.dumps(result, separators=(",", ":")))


async def _execute_python_code(code: str, page: Any) -> Any:
    namespace: dict[str, Any] = {"page": page}
    if code.lstrip().startswith("async def "):
        exec(code, namespace)  # noqa: S102 - this tool is explicitly unsafe.
        fn = namespace.get("run") or namespace.get("__fn__")
        if fn is None:
            candidates = [value for value in namespace.values() if inspect.iscoroutinefunction(value)]
            if not candidates:
                raise ValueError("Python code must define an async function")
            fn = candidates[0]
        return await fn(page)

    function_source = "async def __mcp_run(page):\n" + textwrap.indent(code, "    ")
    exec(function_source, namespace)  # noqa: S102 - this tool is explicitly unsafe.
    return await namespace["__mcp_run"](page)


run_code_tools = [
    Tool(
        name="browser_run_code_unsafe",
        capability="core",
        parameters=(param("code", str | None, None), param("filename", str | None, None)),
        handler=_handle_run_code_unsafe,
    )
]
