from __future__ import annotations

from playwright_python_mcp.mcp.config import ServerConfig

from ..tool import Tool
from .common import common_tools
from .config import config_tools
from .console import console_tools
from .cookies import cookie_tools
from .dialogs import dialog_tools
from .devtools import devtools_tools
from .evaluate import evaluate_tools
from .files import file_tools
from .form import form_tools
from .keyboard import keyboard_tools
from .mouse import mouse_tools
from .navigate import navigate_tools
from .network import network_tools
from .pdf import pdf_tools
from .run_code import run_code_tools
from .route import route_tools
from .screenshot import screenshot_tools
from .snapshot import snapshot_tools
from .storage import storage_tools
from .tabs import tabs_tools
from .tracing import tracing_tools
from .video import video_tools
from .verify import verify_tools
from .webstorage import webstorage_tools
from .wait import wait_tools


CORE_TOOL_NAMES = [
    "browser_click",
    "browser_console_messages",
    "browser_drag",
    "browser_drop",
    "browser_evaluate",
    "browser_file_upload",
    "browser_fill_form",
    "browser_handle_dialog",
    "browser_hover",
    "browser_select_option",
    "browser_type",
    "browser_close",
    "browser_navigate_back",
    "browser_navigate",
    "browser_network_request",
    "browser_network_requests",
    "browser_press_key",
    "browser_resize",
    "browser_run_code_unsafe",
    "browser_snapshot",
    "browser_tabs",
    "browser_take_screenshot",
    "browser_wait_for",
]

PDF_TOOL_NAMES = [
    "browser_pdf_save",
]

VISION_TOOL_NAMES = [
    "browser_mouse_move_xy",
    "browser_mouse_click_xy",
    "browser_mouse_drag_xy",
    "browser_mouse_down",
    "browser_mouse_up",
    "browser_mouse_wheel",
]

TESTING_TOOL_NAMES = [
    "browser_generate_locator",
    "browser_verify_element_visible",
    "browser_verify_text_visible",
    "browser_verify_list_visible",
    "browser_verify_value",
]

NETWORK_TOOL_NAMES = [
    "browser_network_state_set",
    "browser_route",
    "browser_route_list",
    "browser_unroute",
]

TRACING_TOOL_NAMES = [
    "browser_start_tracing",
    "browser_stop_tracing",
]

DEVTOOLS_TOOL_NAMES = [
    "browser_resume",
    "browser_highlight",
    "browser_hide_highlight",
    "browser_start_video",
    "browser_stop_video",
    "browser_video_chapter",
    "browser_video_show_actions",
    "browser_video_hide_actions",
]

CONFIG_TOOL_NAMES = [
    "browser_get_config",
]

STORAGE_TOOL_NAMES = [
    "browser_cookie_list",
    "browser_cookie_get",
    "browser_cookie_set",
    "browser_cookie_delete",
    "browser_cookie_clear",
    "browser_storage_state",
    "browser_set_storage_state",
    "browser_localstorage_list",
    "browser_localstorage_get",
    "browser_localstorage_set",
    "browser_localstorage_delete",
    "browser_localstorage_clear",
    "browser_sessionstorage_list",
    "browser_sessionstorage_get",
    "browser_sessionstorage_set",
    "browser_sessionstorage_delete",
    "browser_sessionstorage_clear",
]


IMPLEMENTED_TOOLS = [
    *common_tools,
    *config_tools,
    *console_tools,
    *cookie_tools,
    *dialog_tools,
    *devtools_tools,
    *evaluate_tools,
    *file_tools,
    *form_tools,
    *keyboard_tools,
    *mouse_tools,
    *navigate_tools,
    *network_tools,
    *pdf_tools,
    *run_code_tools,
    *route_tools,
    *screenshot_tools,
    *snapshot_tools,
    *storage_tools,
    *tabs_tools,
    *tracing_tools,
    *video_tools,
    *verify_tools,
    *webstorage_tools,
    *wait_tools,
]


def filtered_tools(config: ServerConfig) -> list[Tool]:
    visible_names = set(CORE_TOOL_NAMES)
    if config.caps and "pdf" in config.caps:
        visible_names.update(PDF_TOOL_NAMES)
    if config.caps and "vision" in config.caps:
        visible_names.update(VISION_TOOL_NAMES)
    if config.caps and "network" in config.caps:
        visible_names.update(NETWORK_TOOL_NAMES)
    if config.caps and "tracing" in config.caps:
        visible_names.update(TRACING_TOOL_NAMES)
    if config.caps and "devtools" in config.caps:
        visible_names.update(DEVTOOLS_TOOL_NAMES)
    if config.caps and "storage" in config.caps:
        visible_names.update(STORAGE_TOOL_NAMES)
    if config.caps and "testing" in config.caps:
        visible_names.update(TESTING_TOOL_NAMES)
    if config.caps and "config" in config.caps:
        visible_names.update(CONFIG_TOOL_NAMES)

    implemented_by_name = {tool.name: tool for tool in IMPLEMENTED_TOOLS}
    result = [
        tool
        for tool in IMPLEMENTED_TOOLS
        if tool.name in visible_names
        and not tool.skill_only
        and (tool.capability.startswith("core") or tool.capability in (config.caps or []))
    ]
    result.extend(
        Tool(name=name, capability="placeholder", handler=_placeholder_handler(name))
        for name in visible_names
        if name not in implemented_by_name
    )
    return result


def _placeholder_handler(name: str):
    async def handler(_context, _params, response):
        response.add_error(f'Tool "{name}" is not implemented yet.')

    return handler
