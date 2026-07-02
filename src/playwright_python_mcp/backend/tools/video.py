from __future__ import annotations

from typing import Any, Literal

from playwright_python_mcp.backend.context import Context, FilenameTemplate
from playwright_python_mcp.backend.response import Response
from playwright_python_mcp.backend.tool import Tool, param

ActionPosition = Literal["top-left", "top", "top-right", "bottom-left", "bottom", "bottom-right"]
ActionCursor = Literal["none", "pointer"]


async def _handle_start_video(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    resolved_file = await response.resolve_client_file(
        FilenameTemplate(prefix="video", ext="webm", suggested_filename=params.get("filename")),
        "Video",
    )
    context.video_file = resolved_file.file_name
    await tab.page.screencast.start(path=resolved_file.file_name, size=params.get("size"))
    response.add_text_result("Video recording started.")


async def _handle_stop_video(context: Context, _params: dict[str, Any], response: Response) -> None:
    tab = context.current_tab_or_die()
    if context.video_file is None:
        response.add_text_result("No videos were recorded.")
        return
    video_file = context.video_file
    context.video_file = None
    await tab.page.screencast.stop()
    response.add_file_link("Video", video_file)


async def _handle_video_chapter(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = context.current_tab_or_die()
    await tab.page.screencast.show_chapter(
        params["title"],
        description=params.get("description"),
        duration=params.get("duration"),
    )
    response.add_text_result(f"Chapter '{params['title']}' added.")


async def _handle_show_actions(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = context.current_tab_or_die()
    await tab.page.screencast.show_actions(
        duration=params.get("duration"),
        position=params.get("position"),
        cursor=params.get("cursor"),
    )
    response.add_text_result("Action annotations enabled.")


async def _handle_hide_actions(context: Context, _params: dict[str, Any], response: Response) -> None:
    tab = context.current_tab_or_die()
    await tab.page.screencast.hide_actions()
    response.add_text_result("Action annotations disabled.")


video_tools = [
    Tool(
        name="browser_start_video",
        capability="devtools",
        tool_type="readOnly",
        parameters=(param("filename", str | None, None), param("size", dict[str, int] | None, None)),
        handler=_handle_start_video,
    ),
    Tool(name="browser_stop_video", capability="devtools", tool_type="readOnly", handler=_handle_stop_video),
    Tool(
        name="browser_video_chapter",
        capability="devtools",
        tool_type="readOnly",
        parameters=(param("title", str), param("description", str | None, None), param("duration", int | float | None, None)),
        handler=_handle_video_chapter,
    ),
    Tool(
        name="browser_video_show_actions",
        capability="devtools",
        tool_type="readOnly",
        parameters=(
            param("duration", int | float | None, None),
            param("position", ActionPosition | None, None),
            param("cursor", ActionCursor | None, None),
        ),
        handler=_handle_show_actions,
    ),
    Tool(name="browser_video_hide_actions", capability="devtools", tool_type="readOnly", handler=_handle_hide_actions),
]
