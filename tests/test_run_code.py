from __future__ import annotations

import asyncio

import pytest

from playwright_python_mcp.backend.tools.run_code import _execute_python_code


def test_run_code_returns_value() -> None:
    result = asyncio.run(_execute_python_code('return {"message": "Hello"}', object()))

    assert result == {"message": "Hello"}


def test_run_code_supports_async_function() -> None:
    result = asyncio.run(_execute_python_code('async def run(page):\n    return "ok"', object()))

    assert result == "ok"


def test_run_code_blocks_import_by_default() -> None:
    with pytest.raises(ImportError, match="__import__"):
        asyncio.run(_execute_python_code("import os", object()))


def test_run_code_blocks_open_by_default() -> None:
    with pytest.raises(NameError, match="open"):
        asyncio.run(_execute_python_code('open("/tmp/blocked", "w")', object()))


def test_run_code_async_failure_is_reported() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(_execute_python_code('raise RuntimeError("boom")', object()))
