from __future__ import annotations

from types import SimpleNamespace

import pytest

from botwright.fixtures import session
from botwright.plugin import _uses_botwright_fixture, pytest_collection_modifyitems


class FakeFixtureDef:
    def __init__(self, func: object) -> None:
        self.func = func


class FakeItem:
    def __init__(
        self,
        name2fixturedefs: dict[str, object],
        marker: object | None = None,
    ) -> None:
        self._fixtureinfo = SimpleNamespace(name2fixturedefs=name2fixturedefs)
        self.marker = marker
        self.added_markers: list[object] = []

    def get_closest_marker(self, name: str) -> object | None:
        assert name == "asyncio"
        return self.marker

    def add_marker(self, marker: object, append: bool = True) -> None:
        del append
        self.added_markers.append(marker)


def test_uses_botwright_fixture_detects_botwright_session_fixture() -> None:
    item = FakeItem({"session": [FakeFixtureDef(session)]})

    assert _uses_botwright_fixture(item)


def test_uses_botwright_fixture_ignores_unrelated_session_fixture() -> None:
    def session() -> None:
        pass

    item = FakeItem({"session": [FakeFixtureDef(session)]})

    assert not _uses_botwright_fixture(item)


def test_collection_adds_session_loop_marker_when_missing() -> None:
    item = FakeItem({"session": [FakeFixtureDef(session)]})

    pytest_collection_modifyitems([item])  # type: ignore[list-item]

    assert item.added_markers


def test_collection_rejects_conflicting_asyncio_loop_scope() -> None:
    marker = SimpleNamespace(kwargs={"loop_scope": "function"})
    item = FakeItem({"session": [FakeFixtureDef(session)]}, marker=marker)

    with pytest.raises(pytest.UsageError, match="loop_scope='session'"):
        pytest_collection_modifyitems([item])  # type: ignore[list-item]
