"""Tests for export_focus_tree (extra/shared and joint trees, tree_idx > 0)."""

import pytest

from hoi4cm.focus_tree.export import export_focus_tree
from hoi4cm.models import Focus


@pytest.fixture(autouse=True)
def reset_counter():
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


def _info(**overrides):
    info = {"tree_id": "TST_extra", "country_tag": "TST"}
    info.update(overrides)
    return info


def test_duplicate_of_extra_tree_focus_exports_at_new_canvas_position():
    """Regression test for #116: duplicate must not reuse the original's raw coords."""
    original = Focus(3, 5)
    original.name = "TST_original"
    original.tree_idx = 1
    original._raw_gx = 1
    original._raw_gy = 9

    duplicate = original.duplicate()
    duplicate.name = "TST_original_copy"
    duplicate.x = original.x + 1
    duplicate.y = original.y

    lookup = {duplicate.id: duplicate}
    text = export_focus_tree([duplicate], _info(), focus_lookup=lookup)
    lines = text.splitlines()

    assert "\tx = 4" in lines
    assert "\ty = 5" in lines
    assert "\tx = 1" not in lines
    assert "\ty = 9" not in lines

    # the original, exported on its own, still uses its raw file coords
    original_lookup = {original.id: original}
    original_text = export_focus_tree([original], _info(), focus_lookup=original_lookup)
    original_lines = original_text.splitlines()
    assert "\tx = 1" in original_lines
    assert "\ty = 9" in original_lines
