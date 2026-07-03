from __future__ import annotations

from dataclasses import replace

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
from .find import find_tools
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

IMPLEMENTED_TOOLS = [
    *common_tools,
    *config_tools,
    *console_tools,
    *cookie_tools,
    *dialog_tools,
    *devtools_tools,
    *evaluate_tools,
    *file_tools,
    *find_tools,
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

_TAB_MODAL_BLOCKING_TOOLS = {
    "browser_resize",
    "browser_snapshot",
    "browser_click",
    "browser_select_option",
    "browser_hover",
    "browser_drag",
    "browser_generate_locator",
    "browser_check",
    "browser_uncheck",
    "browser_console_messages",
    "browser_console_clear",
    "browser_evaluate",
    "browser_drop",
    "browser_press_key",
    "browser_type",
    "browser_press_sequentially",
    "browser_keydown",
    "browser_keyup",
    "browser_mouse_move_xy",
    "browser_mouse_click_xy",
    "browser_mouse_down",
    "browser_mouse_up",
    "browser_mouse_wheel",
    "browser_mouse_drag_xy",
    "browser_navigate_back",
    "browser_navigate_forward",
    "browser_reload",
    "browser_network_requests",
    "browser_network_request",
    "browser_network_clear",
    "browser_pdf_save",
    "browser_find",
    "browser_run_code_unsafe",
    "browser_take_screenshot",
    "browser_wait_for",
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
    "browser_verify_element_visible",
    "browser_verify_text_visible",
    "browser_verify_list_visible",
    "browser_verify_value",
    "browser_highlight",
    "browser_hide_highlight",
}


def filtered_tools(config: ServerConfig) -> list[Tool]:
    caps = set(config.caps or [])
    if "tracing" in caps:
        caps.add("devtools")
    tools = [
        tool
        for tool in IMPLEMENTED_TOOLS
        if not tool.skill_only and (tool.capability.startswith("core") or tool.capability in caps)
    ]
    return [
        replace(tool, blocks_on_modal_state=True)
        if tool.name in _TAB_MODAL_BLOCKING_TOOLS and not tool.clears_modal_state
        else tool
        for tool in tools
    ]
