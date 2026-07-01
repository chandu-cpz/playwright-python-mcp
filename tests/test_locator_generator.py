from playwright_python_mcp.backend.codegen import python_invocation
from playwright_python_mcp.backend.locator_generator import as_python_locator


def test_generates_python_role_locator() -> None:
    locator = as_python_locator('internal:role=button[name="Submit"i]')

    assert locator == 'get_by_role("button", name="Submit")'


def test_generates_python_test_id_locator() -> None:
    locator = as_python_locator('internal:testid=[data-tid="submit"s]')

    assert locator == 'get_by_test_id("submit")'


def test_formats_python_locator_invocation() -> None:
    code = python_invocation(
        'get_by_role("button", name="Submit")',
        "click",
        [("modifiers", ["Shift", "Alt"])],
    )

    assert code == 'await page.get_by_role("button", name="Submit").click(modifiers=["Shift", "Alt"])'
