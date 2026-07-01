from __future__ import annotations

import asyncio
from typing import Any, cast

from playwright_python_mcp.backend.codegen import python_literal
from playwright_python_mcp.backend.context import Context
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool, param


async def _handle_file_upload(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    modal_state = next((state for state in tab.modal_states() if state.get("type") == "fileChooser"), None)
    if modal_state is None:
        raise ValueError('The tool "browser_file_upload" can only be used when there is related modal state present.')

    paths = params.get("paths")
    file_names = None
    if paths:
        file_names = await asyncio.gather(*(response.resolve_client_filename(path) for path in paths))

    response.set_include_snapshot()
    response.add_code(f"await file_chooser.set_files({python_literal(paths or [])})")
    tab.clear_modal_state(modal_state)
    file_chooser = modal_state["file_chooser"]
    if paths is not None:
        await tab.wait_for_completion(lambda: file_chooser.set_files(file_names or []))


async def _handle_drop(context: Context, params: dict[str, Any], response: Response) -> None:
    if not params.get("paths") and not params.get("data"):
        raise ValueError('At least one of "paths" or "data" must be provided.')

    tab = await context.ensure_tab()
    resolved = await tab.resolve_target(target=params["target"], element=params.get("element"))
    payload: dict[str, Any] = {}
    code_payload: dict[str, Any] = {}
    paths = params.get("paths")
    if paths:
        file_names = await asyncio.gather(*(response.resolve_client_filename(path) for path in paths))
        payload["files"] = file_names[0] if len(file_names) == 1 else file_names
        code_payload["files"] = paths[0] if len(paths) == 1 else paths
    if params.get("data"):
        payload["data"] = params["data"]
        code_payload["data"] = params["data"]

    response.set_include_snapshot()
    await tab.wait_for_completion(lambda: resolved.locator.drop(cast(Any, payload), timeout=tab.action_timeout))
    response.add_code(f"await page.{resolved.code}.drop({python_literal(code_payload)})")


file_tools = [
    Tool(
        name="browser_file_upload",
        capability="core",
        parameters=(param("paths", list[str] | None, None),),
        handler=_handle_file_upload,
        clears_modal_state="fileChooser",
    ),
    Tool(
        name="browser_drop",
        capability="core",
        parameters=(
            param("target", str),
            param("element", str | None, None),
            param("paths", list[str] | None, None),
            param("data", dict[str, str] | None, None),
        ),
        handler=_handle_drop,
    ),
]
