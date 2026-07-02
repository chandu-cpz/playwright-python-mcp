from __future__ import annotations

import time
from typing import Any

from playwright_python_mcp.backend.context import Context, FilenameTemplate
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool


async def _handle_start_tracing(context: Context, _params: dict[str, Any], response: Response) -> None:
    if context.trace_file is not None:
        raise ValueError("Tracing is already started")
    trace_file = await context.output_file(
        FilenameTemplate(prefix="trace", ext="zip", suggested_filename=f"trace-{int(time.time() * 1000)}.zip"),
        origin="code",
    )
    context.trace_file = trace_file
    await context.browser_context().tracing.start(screenshots=True, snapshots=True)
    response.add_text_result("Trace recording started")


async def _handle_stop_tracing(context: Context, _params: dict[str, Any], response: Response) -> None:
    if context.trace_file is None:
        raise ValueError("Tracing is not started")
    trace_file = context.trace_file
    context.trace_file = None
    await context.browser_context().tracing.stop(path=trace_file)
    response.add_text_result("Trace recording stopped.")
    response.add_file_link("Trace", trace_file)


tracing_tools = [
    Tool(name="browser_start_tracing", capability="tracing", tool_type="readOnly", handler=_handle_start_tracing),
    Tool(name="browser_stop_tracing", capability="tracing", tool_type="readOnly", handler=_handle_stop_tracing),
]
