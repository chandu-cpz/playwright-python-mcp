from __future__ import annotations

from typing import Any

from playwright_python_mcp.backend.context import Context, FilenameTemplate
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool, param


async def _handle_pdf_save(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    data = await tab.page.pdf()
    resolved_file = await response.resolve_client_file(
        FilenameTemplate(prefix="page", ext="pdf", suggested_filename=params.get("filename")),
        "Page as pdf",
    )
    await response.add_file_result(resolved_file, data)
    response.add_code(f"await page.pdf(path={resolved_file.relative_name!r})")


pdf_tools = [
    Tool(
        name="browser_pdf_save",
        capability="pdf",
        tool_type="readOnly",
        parameters=(param("filename", str | None, None),),
        handler=_handle_pdf_save,
    )
]
