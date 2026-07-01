from __future__ import annotations

import json
from typing import Any

from .codegen import python_literal
from .selector_parser import ParsedAttributeSelector, ParsedSelectorPart, parse_attribute_selector, parse_selector


def as_python_locator(selector: str) -> str:
    """Port of upstream `asLocator('python', selector)` for MCP snippets.

    Upstream source:
    - packages/isomorphic/locatorGenerators.ts
    - PythonLocatorFactory

    This only formats the response snippet. Runtime execution still uses real
    Playwright Python locators in `BrowserSession`.
    """
    try:
        parts = parse_selector(selector)
        return ".".join(_locator_for_part(part) for part in parts)
    except (ValueError, json.JSONDecodeError):
        return _default_locator(selector)


def _locator_for_part(part: ParsedSelectorPart) -> str:
    if part.name == "internal:role":
        return _role_locator(parse_attribute_selector(part.body))
    if part.name == "internal:testid":
        attr_selector = parse_attribute_selector(part.body)
        if not attr_selector.attributes:
            raise ValueError("internal:testid selector has no attributes")
        return f"get_by_test_id({python_literal(attr_selector.attributes[0].value)})"
    if part.name == "internal:text":
        exact, text = _detect_exact(part.body)
        if exact:
            return f"get_by_text({python_literal(text)}, exact=True)"
        return f"get_by_text({python_literal(text)})"
    if part.name == "internal:label":
        exact, text = _detect_exact(part.body)
        if exact:
            return f"get_by_label({python_literal(text)}, exact=True)"
        return f"get_by_label({python_literal(text)})"
    if part.name == "nth":
        if part.body == "0":
            return "first"
        if part.body == "-1":
            return "last"
        return f"nth({part.body})"
    return _default_locator(_stringify_selector_part(part))


def _role_locator(attr_selector: ParsedAttributeSelector) -> str:
    attrs: list[tuple[str, Any]] = []
    exact = False

    for attr in attr_selector.attributes:
        if attr.name == "name":
            attrs.append(("name", attr.value))
            exact = attr.case_sensitive
        elif attr.name == "description":
            attrs.append(("description", attr.value))
            exact = attr.case_sensitive
        elif attr.name == "include-hidden":
            attrs.append(("include_hidden", attr.value))
        else:
            attrs.append((_to_snake_case(attr.name), attr.value))

    if exact and any(name in {"name", "description"} for name, _ in attrs):
        attrs.append(("exact", True))

    options = "".join(f", {name}={python_literal(value)}" for name, value in attrs)
    return f"get_by_role({python_literal(attr_selector.name)}{options})"


def _detect_exact(text: str) -> tuple[bool, str]:
    if text.endswith('"s'):
        return True, json.loads(text[:-1])
    if text.endswith('"i'):
        return False, json.loads(text[:-1])
    if text.endswith('"'):
        return True, json.loads(text)
    return False, text


def _stringify_selector_part(part: ParsedSelectorPart) -> str:
    if part.name == "css":
        return part.source
    if part.name == "xpath" and (part.source.startswith("//") or part.source.startswith("..")):
        return part.source
    return f"{part.name}={part.source}"


def _default_locator(selector: str) -> str:
    return f"locator({python_literal(selector)})"


def _to_snake_case(value: str) -> str:
    result: list[str] = []
    for char in value:
        if char == "-":
            result.append("_")
        elif char.isupper():
            if result:
                result.append("_")
            result.append(char.lower())
        else:
            result.append(char)
    return "".join(result)
