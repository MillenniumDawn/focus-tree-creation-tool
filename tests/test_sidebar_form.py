"""Regression tests for the select-away sidebar dirty check.

A missed field in the match silently drops an edit when the user clicks
another focus. The apply path must touch indexes only when name changes.
"""

import pytest

from hoi4cm.focus_tree.codec import render_focus_block
from hoi4cm.focus_tree.operations import build_focus_name_lookup
from hoi4cm.models import (
    Focus,
    FocusDocument,
    FocusSidebarValues,
    apply_sidebar_values,
    sidebar_values_match_focus,
)


def _focus(**overrides):
    focus = Focus(0, 0)
    focus.id = 1
    focus.name = "keep"
    focus.icon = "⚔"
    focus.gfx = "GFX_goal_generic_political_pressure"
    focus.cost = 10
    focus.ai_will_do = 1
    focus.ai_will_do_raw = "base = 1"
    focus.desc = "desc"
    focus.search_filters = "FOCUS_FILTER_POLITICAL"
    focus.available_cond = ""
    focus.bypass_cond = ""
    focus.cancel_cond = ""
    focus.cancel_if_invalid = True
    focus.continue_if_invalid = False
    focus.available_if_capitulated = False
    focus.offsets = []
    for key, value in overrides.items():
        setattr(focus, key, value)
    return focus


def _values(focus=None, **overrides):
    focus = focus or _focus()
    base = FocusSidebarValues(
        name=focus.name,
        icon=focus.icon,
        gfx=focus.gfx,
        cost=focus.cost,
        ai_will_do=focus.ai_will_do,
        ai_will_do_raw=getattr(focus, "ai_will_do_raw", "").strip(),
        x=focus.x,
        y=focus.y,
        desc=focus.desc,
        search_filters=focus.search_filters,
        available_cond=focus.available_cond,
        bypass_cond=focus.bypass_cond,
        cancel_cond=focus.cancel_cond,
        cancel_if_invalid=focus.cancel_if_invalid,
        continue_if_invalid=focus.continue_if_invalid,
        available_if_capitulated=focus.available_if_capitulated,
        offsets=tuple(dict(offset) for offset in focus.offsets),
    )
    if not overrides:
        return base
    return FocusSidebarValues(**{**base.__dict__, **overrides})


def test_matching_form_is_noop():
    focus = _focus()
    assert sidebar_values_match_focus(focus, _values(focus)) is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "renamed"),
        ("icon", "★"),
        ("gfx", "GFX_other"),
        ("cost", 99),
        ("ai_will_do", 7),
        ("ai_will_do_raw", "base = 9"),
        ("x", 3),
        ("y", 4),
        ("desc", "changed"),
        ("search_filters", "FOCUS_FILTER_INDUSTRY"),
        ("available_cond", "always = yes"),
        ("bypass_cond", "always = yes"),
        ("cancel_cond", "always = yes"),
        ("cancel_if_invalid", False),
        ("continue_if_invalid", True),
        ("available_if_capitulated", True),
        ("offsets", ({"x": 1, "y": 2, "trigger": "tag = TST"},)),
    ],
)
def test_each_form_field_counts_as_a_change(field, value):
    focus = _focus()
    assert sidebar_values_match_focus(focus, _values(focus, **{field: value})) is False


def test_ai_will_do_raw_strips_focus_whitespace_for_match():
    focus = _focus(ai_will_do_raw="  base = 1\n")
    values = _values(focus, ai_will_do_raw="base = 1")
    assert sidebar_values_match_focus(focus, values) is True


def test_apply_name_change_returns_true_and_writes_fields():
    focus = _focus(desc="old")
    values = _values(focus, name="new_name", desc="new")
    document = FocusDocument((focus,))
    revision = document.revision

    assert apply_sidebar_values(focus, values) is True
    assert focus.name == "new_name"
    assert focus.desc == "new"
    assert document.revision == revision  # caller decides when to touch


def test_apply_non_name_change_returns_false():
    focus = _focus()
    values = _values(focus, desc="edited", cost=12)

    assert apply_sidebar_values(focus, values) is False
    assert focus.desc == "edited"
    assert focus.cost == 12
    assert focus.name == "keep"


def test_apply_copies_offsets_so_form_list_is_not_shared():
    focus = _focus()
    offset = {"x": 1, "y": 2, "trigger": ""}
    values = _values(focus, offsets=(offset,))

    apply_sidebar_values(focus, values)
    offset["x"] = 99

    assert focus.offsets == [{"x": 1, "y": 2, "trigger": ""}]


def test_name_change_needs_touch_position_change_uses_move_only():
    focus = _focus(name="old", x=0, y=0)
    document = FocusDocument((focus,))
    baseline = document.revision

    # Position-only edit: move patches indexes; no touch.
    pos_values = _values(focus, x=5, y=6)
    assert sidebar_values_match_focus(focus, pos_values) is False
    assert apply_sidebar_values(focus, pos_values) is False
    assert document.move(focus.id, pos_values.x, pos_values.y) is True
    assert document.revision == baseline + 1
    assert document.validate_indexes()
    assert document.first_by_name == {"old": 1}

    # Name edit: indexes stale until touch.
    name_values = _values(focus, name="new")
    assert apply_sidebar_values(focus, name_values) is True
    assert not document.validate_indexes()
    document.touch()
    assert document.first_by_name == {"new": 1}
    assert document.validate_indexes()


def test_by_name_matches_build_focus_name_lookup_first_wins():
    first = _focus(name="duplicate")
    first.id = 10
    second = _focus(name="duplicate")
    second.id = 20
    other = _focus(name="unique")
    other.id = 30
    document = FocusDocument((first, second, other))

    built = build_focus_name_lookup(document.values())
    view = document.by_name

    assert built.keys() == set(view)
    assert built["duplicate"] is view["duplicate"] is first
    assert built["unique"] is view["unique"] is other


def test_by_name_missing_key_raises_key_error():
    document = FocusDocument((_focus(),))

    with pytest.raises(KeyError):
        _ = document.by_name["missing"]


def test_render_focus_block_accepts_document_by_name():
    parent = Focus(0, 0)
    parent.id = 1
    parent.name = "PARENT"
    child = Focus(3, 4)
    child.id = 2
    child.name = "CHILD"
    child.relative_position_id = "PARENT"
    document = FocusDocument((parent, child))

    via_view = render_focus_block(
        child,
        focus_lookup=document,
        focus_name_lookup=document.by_name,
    )
    via_built = render_focus_block(
        child,
        focus_lookup=document,
        focus_name_lookup=build_focus_name_lookup(document.values()),
    )

    assert via_view == via_built
    assert "relative_position_id = PARENT" in via_view
    assert "x = 3" in via_view
    assert "y = 4" in via_view
