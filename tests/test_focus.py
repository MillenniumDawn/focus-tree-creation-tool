"""Tests for hoi4cm.models.focus."""

import pytest

from hoi4cm.models import Focus


@pytest.fixture(autouse=True)
def reset_counter():
    """Isolate the module-level auto-increment counter."""
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


def test_new_focus_has_defaults():
    f = Focus(2, 3)
    assert f.id == 1
    assert f.x == 2
    assert f.y == 3
    assert f.name == "focus_1"
    assert f.gfx == "GFX_goal_generic_political_pressure"
    assert f.effects == []
    assert f.prereqs == []
    assert f.mutex == []


def test_counter_increments():
    a = Focus()
    b = Focus()
    assert a.id == 1
    assert b.id == 2


def test_to_dict_roundtrips():
    f = Focus(1, 2)
    f.name = "my_focus"
    f.gfx = "GFX_goal_test"
    f.effects = [{"type": "add_political_power", "fields": {"amount": "100"}}]
    d = f.to_dict()
    restored = Focus.from_dict(d)

    assert restored.to_dict() == d
    assert restored.id == f.id


def test_from_dict_migrates_pixel_coords():
    f = Focus.from_dict({"id": 5, "x": 192, "y": 384})
    assert f.x == 2
    assert f.y == 4


def test_from_dict_applies_defaults_for_missing_attrs():
    f = Focus.from_dict({"id": 1, "x": 0, "y": 0})
    assert f.gfx == "GFX_goal_generic_political_pressure"
    assert f.search_filters == "FOCUS_FILTER_POLITICAL"
    assert f.offsets == []
    assert f.ai_will_do_raw == ""
    assert f.tree_idx == 0


def test_from_dict_bumps_counter():
    Focus._next = 0
    Focus.from_dict({"id": 42, "x": 0, "y": 0})
    assert Focus._next == 43


def test_to_dict_excludes_dynamic_private_attrs():
    f = Focus()
    f._items = ["a"]
    f._draw_key = "key"  # type: ignore[assignment]
    restored = Focus.from_dict(f.to_dict())
    assert not hasattr(restored, "_items")
    assert not hasattr(restored, "_draw_key")
