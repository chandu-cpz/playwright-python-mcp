from __future__ import annotations

from playwright_python_mcp.mcp.config import ServerConfig
from playwright_python_mcp.tools.registry import (
    CORE_TOOL_NAMES,
    NETWORK_TOOL_NAMES,
    PDF_TOOL_NAMES,
    TESTING_TOOL_NAMES,
    VISION_TOOL_NAMES,
)

from ..tool import Tool
from .common import common_tools
from .console import console_tools
from .evaluate import evaluate_tools
from .form import form_tools
from .keyboard import keyboard_tools
from .mouse import mouse_tools
from .navigate import navigate_tools
from .network import network_tools
from .snapshot import snapshot_tools


IMPLEMENTED_TOOLS = [
    *common_tools,
    *console_tools,
    *evaluate_tools,
    *form_tools,
    *keyboard_tools,
    *mouse_tools,
    *navigate_tools,
    *network_tools,
    *snapshot_tools,
]


def filtered_tools(config: ServerConfig) -> list[Tool]:
    visible_names = set(CORE_TOOL_NAMES)
    if config.caps and "pdf" in config.caps:
        visible_names.update(PDF_TOOL_NAMES)
    if config.caps and "vision" in config.caps:
        visible_names.update(VISION_TOOL_NAMES)
    if config.caps and "network" in config.caps:
        visible_names.update(NETWORK_TOOL_NAMES)
    if config.caps and "testing" in config.caps:
        visible_names.update(TESTING_TOOL_NAMES)

    implemented_by_name = {tool.name: tool for tool in IMPLEMENTED_TOOLS}
    result = [
        tool
        for tool in IMPLEMENTED_TOOLS
        if tool.name in visible_names and not tool.skill_only and (tool.capability.startswith("core") or tool.capability in (config.caps or []))
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
