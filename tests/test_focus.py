"""Tests for hoi4cm.models.focus and document-scoped ID allocation."""

import pytest

from hoi4cm.models import Focus, FocusDocument


def test_new_focus_has_explicit_id_and_defaults():
    f = Focus(id=1, x=2, y=3)
    assert f.id == 1
    assert f.x == 2
    assert f.y == 3
    assert f.name == "focus_1"
    assert f.loc_name == ""
    assert f.gfx == "GFX_goal_generic_political_pressure"
    assert f.effects == []
    assert f.prereqs == []
    assert f.mutex == []


def test_documents_allocate_independent_ids():
    left, right = FocusDocument(), FocusDocument()
    assert left.new_focus().id == right.new_focus().id == 1
    assert left.new_focus().id == 2
    assert right.new_focus().id == 2


def test_explicit_focus_ids_advance_only_the_owning_document():
    left, right = FocusDocument(), FocusDocument()
    left.add(Focus(id=42))
    assert left.new_focus().id == 43
    assert right.new_focus().id == 1


def test_document_allocation_accounts_for_loaded_ids_and_exhaustion():
    document = FocusDocument([Focus(id=MAX_ID)])
    with pytest.raises(ValueError, match="allocator exhausted"):
        document.allocate_id()


def test_to_dict_roundtrips():
    f = Focus(id=7, x=1, y=2)
    f.name = "my_focus"
    f.loc_name = "My Focus"
    f.gfx = "GFX_goal_test"
    f.effects = [{"type": "add_political_power", "fields": {"amount": "100"}}]
    d = f.to_dict()
    restored = Focus.from_dict(d)
    assert restored.to_dict() == d
    assert restored.id == f.id


def test_from_dict_migrates_pixel_coords_when_legacy():
    f = Focus.from_dict({"id": 5, "x": 192, "y": 384}, legacy=True)
    assert (f.x, f.y) == (2, 4)


def test_from_dict_leaves_grid_coords_alone_by_default():
    f = Focus.from_dict({"id": 5, "x": 96, "y": 192})
    assert (f.x, f.y) == (96, 192)


def test_from_dict_applies_defaults_and_filters_unknown_fields():
    f = Focus.from_dict({"__dict__": 1, "id": 7, "evil": "x"})
    assert f.loc_name == ""
    assert f.gfx == "GFX_goal_generic_political_pressure"
    assert f.search_filters == "FOCUS_FILTER_POLITICAL"
    assert f.offsets == []
    assert f.ai_will_do_raw == ""
    assert f.tree_idx == 0
    assert "__dict__" not in f.__dict__
    assert not hasattr(f, "evil")


@pytest.mark.parametrize("focus_id", [-1, 1_000_001, 10**18])
def test_from_dict_rejects_out_of_range_id(focus_id):
    with pytest.raises(ValueError, match="focus id must be between"):
        Focus.from_dict({"id": focus_id})


def test_from_dict_coerces_known_field_types():
    f = Focus.from_dict(
        {
            "id": "7",
            "x": "192",
            "y": 3.0,
            "cost": "7.5",
            "cancel_if_invalid": "no",
            "mutex": ["4", 5],
            "unknown": {"ignored": True},
        }
    )
    assert (f.id, f.x, f.y, f.cost) == (7, 192, 3, 7.5)
    assert f.cancel_if_invalid is False
    assert f.mutex == [4, 5]
    assert "unknown" not in f.to_dict()


def test_to_dict_excludes_dynamic_private_attrs():
    f = Focus(id=1)
    f.__dict__.update(_items=["a"])
    f._draw_key = "key"  # type: ignore[assignment]
    restored = Focus.from_dict(f.to_dict())
    assert not hasattr(restored, "_items")
    assert not hasattr(restored, "_draw_key")


def test_duplicate_requires_an_explicit_document_id_and_drops_raw_coords():
    f = Focus(id=1)
    f._raw_gx = 10
    f._raw_gy = 20
    f._rel_dx = 1
    f._rel_dy = 2
    duplicate = f.duplicate(2)
    assert duplicate.id == 2
    assert not hasattr(duplicate, "_raw_gx")
    assert not hasattr(duplicate, "_raw_gy")
    assert not hasattr(duplicate, "_rel_dx")
    assert not hasattr(duplicate, "_rel_dy")
    assert f._raw_gx == 10 and f._raw_gy == 20


def test_duplicate_copies_public_fields():
    f = Focus(id=1, x=3, y=4)
    f.name = "my_focus"
    f.cost = 5
    duplicate = f.duplicate(2)
    assert duplicate.name == f.name
    assert (duplicate.x, duplicate.y) == (f.x, f.y)
    assert duplicate.cost == f.cost


MAX_ID = 1_000_000
