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


def test_from_dict_migrates_pixel_coords_when_legacy():
    f = Focus.from_dict({"id": 5, "x": 192, "y": 384}, legacy=True)
    assert f.x == 2
    assert f.y == 4


def test_from_dict_leaves_grid_coords_alone_by_default():
    f = Focus.from_dict({"id": 5, "x": 96, "y": 192})
    assert f.x == 96
    assert f.y == 192


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


def test_duplicate_assigns_id_from_counter():
    f = Focus()
    nf = f.duplicate()
    assert nf.id != f.id
    assert nf.id == Focus._next


def test_duplicate_after_load_stays_small_and_unique():
    base = Focus._next + 100
    Focus.from_dict({"id": base, "x": 0, "y": 0})
    f = Focus.from_dict({"id": base + 1, "x": 0, "y": 0})
    nf = f.duplicate()
    assert nf.id == base + 3
    assert nf.id != f.id


def test_duplicate_drops_raw_import_coords():
    f = Focus()
    f._raw_gx = 10
    f._raw_gy = 20
    f._rel_dx = 1
    f._rel_dy = 2
    nf = f.duplicate()
    assert not hasattr(nf, "_raw_gx")
    assert not hasattr(nf, "_raw_gy")
    assert not hasattr(nf, "_rel_dx")
    assert not hasattr(nf, "_rel_dy")
    # original is untouched
    assert f._raw_gx == 10 and f._raw_gy == 20


def test_duplicate_copies_public_fields():
    f = Focus(3, 4)
    f.name = "my_focus"
    f.cost = 5
    nf = f.duplicate()
    assert nf.name == f.name
    assert nf.x == f.x and nf.y == f.y
    assert nf.cost == f.cost
