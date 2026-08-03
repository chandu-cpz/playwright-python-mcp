from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from playwright_python_mcp.backend.tab import (
    ResolvedTarget,
    StaleSnapshotError,
    Tab,
    _split_ref,
    _stale_snapshot_message,
    _version_refs,
)


def _bare_tab(**attrs: Any) -> Tab:
    tab = object.__new__(Tab)
    for name, value in attrs.items():
        setattr(tab, name, value)
    return tab


class RawAriaSnapshot:
    def __init__(self, text: str) -> None:
        self._text = text

    async def __call__(self, *, mode: str, depth: int | None, boxes: bool | None = None) -> str:
        return self._text


class FakeRefPage:
    def __init__(self) -> None:
        self.lookup_selectors: list[str] = []

    def locator(self, selector: str) -> "FakeLocator":
        self.lookup_selectors.append(selector)
        return FakeLocator()


class FakeLocator:
    async def normalize(self) -> "FakeNormalized":
        return FakeNormalized()

    def describe(self, element: str) -> "FakeLocator":
        return self


class FakeNormalized:
    _impl_obj = SimpleNamespace(_selector="aria-ref=e1")


def test_split_ref_parses_versioned_and_plain_refs() -> None:
    assert _split_ref("e1v7") == ("e1", 7)
    assert _split_ref("f1e2v7") == ("f1e2", 7)
    assert _split_ref("e1") == ("e1", None)
    assert _split_ref("f1e2") == ("f1e2", None)


def test_version_refs_stamps_element_and_frame_refs() -> None:
    text = '- button "Go" [ref=e1]\n  - textbox "Name" [ref=f1e2]'
    assert _version_refs(text, 5) == '- button "Go" [ref=e1v5]\n  - textbox "Name" [ref=f1e2v5]'


def test_version_refs_is_idempotent() -> None:
    assert _version_refs(_version_refs("[ref=e1]", 5), 5) == "[ref=e1v5]"


def test_stale_snapshot_message_is_deterministic() -> None:
    assert _stale_snapshot_message("e1v5", 5, 7) == (
        "STALE_SNAPSHOT: element reference e1v5 is from snapshot version "
        "5 but current version is 7; take a fresh snapshot before acting on this element"
    )


def test_consecutive_captures_yield_increasing_versions() -> None:
    async def run() -> None:
        tab = _bare_tab(
            _modal_states=[],
            _modal_event=asyncio.Event(),
            context=SimpleNamespace(track_task=lambda task: task),
            page=SimpleNamespace(aria_snapshot=RawAriaSnapshot('- button "Submit" [ref=e1]')),
            _snapshot_version=0,
        )

        first = await Tab._aria_snapshot_race(tab, target=None, root=None, depth=None, boxes=None)
        second = await Tab._aria_snapshot_race(tab, target=None, root=None, depth=None, boxes=None)

        assert tab.snapshot_version == 2
        assert first == '- button "Submit" [ref=e1v1]'
        assert second == '- button "Submit" [ref=e1v2]'

    asyncio.run(run())


def test_ref_from_current_version_resolves() -> None:
    async def run() -> None:
        page = FakeRefPage()
        tab = _bare_tab(_snapshot_version=7, page=page)

        resolved = await Tab.resolve_target(tab, target="e1v7")

        assert isinstance(resolved, ResolvedTarget)
        assert page.lookup_selectors == ["aria-ref=e1"]

    asyncio.run(run())


class MissingLocator:
    async def normalize(self) -> "FakeNormalized":
        raise Exception("element not found")

    def describe(self, element: str) -> "MissingLocator":
        return self


class MissingRefPage:
    def __init__(self) -> None:
        self.lookup_selectors: list[str] = []

    def locator(self, selector: str) -> MissingLocator:
        self.lookup_selectors.append(selector)
        return MissingLocator()


def test_stale_versioned_ref_still_resolves_live() -> None:
    async def run() -> None:
        page = FakeRefPage()
        tab = _bare_tab(_snapshot_version=7, page=page)

        resolved = await Tab.resolve_target(tab, target="e1v5")

        assert isinstance(resolved, ResolvedTarget)
        assert page.lookup_selectors == ["aria-ref=e1"]

    asyncio.run(run())


def test_absent_ref_errors_by_ref_kind() -> None:
    async def run() -> None:
        page = MissingRefPage()
        tab = _bare_tab(_snapshot_version=7, page=page)

        with pytest.raises(StaleSnapshotError) as excinfo:
            await Tab.resolve_target(tab, target="e9v5")
        assert excinfo.value.args[0] == (
            "STALE_SNAPSHOT: element reference e9v5 is from snapshot version "
            "5 but current version is 7; take a fresh snapshot before acting on this element"
        )
        assert page.lookup_selectors == ["aria-ref=e9"]

        page.lookup_selectors.clear()

        with pytest.raises(ValueError) as excinfo2:
            await Tab.resolve_target(tab, target="e9")
        assert excinfo2.value.args[0] == (
            "Ref e9 not found in the current page snapshot. Try capturing new snapshot."
        )
        assert page.lookup_selectors == ["aria-ref=e9"]

    asyncio.run(run())


def test_unversioned_ref_still_resolves_when_versions_enabled() -> None:
    async def run() -> None:
        page = FakeRefPage()
        tab = _bare_tab(_snapshot_version=7, page=page)

        resolved = await Tab.resolve_target(tab, target="e1")

        assert isinstance(resolved, ResolvedTarget)
        assert page.lookup_selectors == ["aria-ref=e1"]

    asyncio.run(run())
