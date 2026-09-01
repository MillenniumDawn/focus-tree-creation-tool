"""Tk wiring tests for App._autosave / _read_sidebar_values.

Mirrors the harness style in test_sidebar_refresh.py: bind monolith methods
onto a minimal widget shell so widget→snapshot→document stays covered.
"""

from __future__ import annotations

import tkinter as tk
from copy import deepcopy

import pytest

import hoi4_content_maker as m
import hoi4cm.core.logger as logmod
from hoi4cm.models import Focus, FocusDocument


@pytest.fixture
def log_state():
    """Isolate the shared error buffer around each autosave error path."""
    orig_cb = logmod._error_callback
    logmod.clear_errors()
    logmod.set_error_callback(None)
    yield logmod
    logmod._error_callback = orig_cb
    logmod.clear_errors()


class _AutosaveHarness:
    _read_offsets_from_form = m.App._read_offsets_from_form
    _read_sidebar_values = m.App._read_sidebar_values
    _autosave = m.App._autosave
    _apply = m.App._apply
    _log_error = m.App._log_error
    _coerce_numeric = m.App._coerce_numeric
    _set_field_error = m.App._set_field_error

    def __init__(self, root):
        self.selected: Focus | None = None
        self.focuses = FocusDocument()
        self._error_entries = logmod.get_error_entries()
        self._undo_pushes: list[tuple[str, object]] = []
        self._redraws = 0
        self._populates: list[int] = []
        self._list_invalidations = 0
        self._fv_name = tk.StringVar(master=root)
        self._fv_icon = tk.StringVar(master=root)
        self._fv_gfx = tk.StringVar(master=root)
        self._fv_cost = tk.StringVar(master=root)
        self._fv_x = tk.StringVar(master=root)
        self._fv_y = tk.StringVar(master=root)
        self._fv_loc_name = tk.StringVar(master=root)
        self._fv_search = tk.StringVar(master=root)
        self._fv_cancel = tk.BooleanVar(master=root)
        self._fv_continue = tk.BooleanVar(master=root)
        self._fv_cap = tk.BooleanVar(master=root)
        # Entry widgets for inline error indicators
        self._fv_cost_entry = None
        self._fv_x_entry = None
        self._fv_y_entry = None
        self._fv_ai_raw = tk.Text(root, height=2, width=20)
        self._fv_desc = tk.Text(root, height=2, width=20)
        self._fv_avail = tk.Text(root, height=2, width=20)
        self._fv_bypass = tk.Text(root, height=2, width=20)
        self._fv_cancel2 = tk.Text(root, height=2, width=20)
        self._offset_entries: list = []

    def _push_undo(self, label, touched_ids=()):
        self._undo_pushes.append((label, touched_ids))

    def _redraw(self):
        self._redraws += 1

    def _populate(self, focus):
        self._populates.append(focus.id)
        self.load_form(focus)

    def _invalidate_focus_list_structure(self):
        self._list_invalidations += 1

    def load_form(self, focus: Focus) -> None:
        self._fv_name.set(focus.name)
        self._fv_icon.set(focus.icon)
        self._fv_gfx.set(focus.gfx)
        self._fv_cost.set(str(focus.cost))
        self._fv_x.set(str(focus.x))
        self._fv_y.set(str(focus.y))
        self._fv_loc_name.set(getattr(focus, "loc_name", ""))
        self._fv_search.set(focus.search_filters)
        self._fv_cancel.set(focus.cancel_if_invalid)
        self._fv_continue.set(focus.continue_if_invalid)
        self._fv_cap.set(focus.available_if_capitulated)
        for widget, text in (
            (self._fv_ai_raw, focus.ai_will_do_raw),
            (self._fv_desc, focus.desc),
            (self._fv_avail, focus.available_cond),
            (self._fv_bypass, focus.bypass_cond),
            (self._fv_cancel2, focus.cancel_cond),
        ):
            widget.delete("1.0", "end")
            widget.insert("1.0", text)
        self._offset_entries = []
        for offset in focus.offsets:
            x_var = tk.StringVar(value=str(offset.get("x", 0)))
            y_var = tk.StringVar(value=str(offset.get("y", 0)))
            trig = tk.Text(self._fv_desc.master, height=1, width=10)
            trig.insert("1.0", offset.get("trigger", ""))
            self._offset_entries.append((x_var, y_var, trig))


def _focus(**overrides) -> Focus:
    focus = Focus(0, 0)
    focus.id = overrides.pop("id", 1)
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


def _harness_with(root, *focuses: Focus) -> _AutosaveHarness:
    selected = focuses[0]
    h = _AutosaveHarness(root)
    h.focuses = FocusDocument(focuses)
    h.selected = selected
    h.load_form(selected)
    return h


class _MessageBox:
    def __init__(self):
        self.errors: list[tuple] = []
        self.warnings: list[tuple] = []

    def showerror(self, *args, **kwargs):
        self.errors.append(args)

    def showwarning(self, *args, **kwargs):
        self.warnings.append(args)


def test_autosave_noop_when_form_matches_focus(tk_root, log_state):
    focus = _focus(desc="unchanged")
    h = _harness_with(tk_root, focus)
    baseline = h.focuses.revision
    before = deepcopy(focus.to_dict())

    h._autosave()

    assert focus.to_dict() == before
    assert h.focuses.revision == baseline
    assert log_state.get_error_entries() == []


def test_autosave_writes_desc_edit_without_touch(tk_root, log_state):
    focus = _focus(desc="old")
    h = _harness_with(tk_root, focus)
    baseline = h.focuses.revision
    h._fv_desc.delete("1.0", "end")
    h._fv_desc.insert("1.0", "edited from form")

    h._autosave()

    assert focus.desc == "edited from form"
    assert h.focuses.revision == baseline
    assert h.focuses.validate_indexes()
    assert log_state.get_error_entries() == []


def test_autosave_writes_localized_name_without_touch(tk_root, log_state):
    focus = _focus(loc_name="Old title")
    h = _harness_with(tk_root, focus)
    baseline = h.focuses.revision
    h._fv_loc_name.set("New title")

    h._autosave()

    assert focus.loc_name == "New title"
    assert h.focuses.revision == baseline
    assert log_state.get_error_entries() == []


def test_autosave_name_edit_touches_indexes(tk_root, log_state):
    focus = _focus(name="old_name")
    h = _harness_with(tk_root, focus)
    baseline = h.focuses.revision
    h._fv_name.set("new_name")

    h._autosave()

    assert focus.name == "new_name"
    assert h.focuses.revision == baseline + 1
    assert h.focuses.first_by_name == {"new_name": focus.id}
    assert h.focuses.validate_indexes()


def test_autosave_position_edit_uses_move_only(tk_root, log_state):
    focus = _focus(x=0, y=0)
    h = _harness_with(tk_root, focus)
    baseline = h.focuses.revision
    h._fv_x.set("4")
    h._fv_y.set("5")

    h._autosave()

    assert (focus.x, focus.y) == (4, 5)
    assert h.focuses.revision == baseline + 1
    assert h.focuses.occupied_positions == {(4, 5): {focus.id}}
    assert h.focuses.validate_indexes()


def test_autosave_empty_name_leaves_focus_untouched(tk_root, log_state):
    focus = _focus(name="keep", desc="stay")
    h = _harness_with(tk_root, focus)
    baseline = h.focuses.revision
    before = deepcopy(focus.to_dict())
    h._fv_name.set("   ")
    h._fv_desc.delete("1.0", "end")
    h._fv_desc.insert("1.0", "should not apply")

    h._autosave()

    assert focus.to_dict() == before
    assert h.focuses.revision == baseline
    assert log_state.get_error_entries() == []


def test_autosave_float_cost_matches_without_error(tk_root, log_state):
    """Imported non-integral costs must round-trip; int() used to raise."""
    focus = _focus(cost=7.5)
    h = _harness_with(tk_root, focus)
    baseline = h.focuses.revision
    before = deepcopy(focus.to_dict())

    h._autosave()

    assert focus.to_dict() == before
    assert focus.cost == 7.5
    assert h.focuses.revision == baseline
    assert log_state.get_error_entries() == []


def test_autosave_preserves_float_cost_when_other_field_edits(tk_root, log_state):
    focus = _focus(cost=7.5, desc="old")
    h = _harness_with(tk_root, focus)
    h._fv_desc.delete("1.0", "end")
    h._fv_desc.insert("1.0", "new")

    h._autosave()

    assert focus.cost == 7.5
    assert focus.desc == "new"
    assert log_state.get_error_entries() == []


def test_autosave_applies_valid_fields_when_cost_is_invalid(tk_root, log_state):
    """Invalid cost should not drop other valid edits."""
    focus = _focus(cost=10, desc="old")
    h = _harness_with(tk_root, focus)
    baseline = h.focuses.revision
    h._fv_cost.set("not-a-number")
    h._fv_desc.delete("1.0", "end")
    h._fv_desc.insert("1.0", "edited desc")

    h._autosave()

    # Cost falls back to current value; desc edit is applied.
    assert focus.cost == 10
    assert focus.desc == "edited desc"
    assert h.focuses.revision == baseline
    entries = log_state.get_error_entries()
    assert len(entries) == 1
    assert "not-a-number" in entries[0][1]


def test_autosave_applies_valid_fields_when_x_is_invalid(tk_root, log_state):
    """Invalid x should not drop other valid edits."""
    focus = _focus(x=0, y=0, desc="old")
    h = _harness_with(tk_root, focus)
    baseline = h.focuses.revision
    h._fv_x.set("not-a-number")
    h._fv_desc.delete("1.0", "end")
    h._fv_desc.insert("1.0", "edited desc")

    h._autosave()

    # X falls back to current value; desc edit is applied.
    assert focus.x == 0
    assert focus.desc == "edited desc"
    assert h.focuses.revision == baseline
    entries = log_state.get_error_entries()
    assert len(entries) == 1
    assert "not-a-number" in entries[0][1]


def test_autosave_applies_valid_fields_when_y_is_invalid(tk_root, log_state):
    """Invalid y should not drop other valid edits."""
    focus = _focus(x=0, y=0, desc="old")
    h = _harness_with(tk_root, focus)
    baseline = h.focuses.revision
    h._fv_y.set("not-a-number")
    h._fv_desc.delete("1.0", "end")
    h._fv_desc.insert("1.0", "edited desc")

    h._autosave()

    # Y falls back to current value; desc edit is applied.
    assert focus.y == 0
    assert focus.desc == "edited desc"
    assert h.focuses.revision == baseline
    entries = log_state.get_error_entries()
    assert len(entries) == 1
    assert "not-a-number" in entries[0][1]


def test_read_sidebar_values_returns_none_for_blank_name(tk_root):
    focus = _focus()
    h = _harness_with(tk_root, focus)
    h._fv_name.set("")

    assert h._read_sidebar_values() is None


def test_read_sidebar_values_sanitizes_name_and_reads_offsets(tk_root):
    focus = _focus(offsets=[{"x": 1, "y": 2, "trigger": "tag = A"}])
    h = _harness_with(tk_root, focus)
    h._fv_name.set("Bad Name!")
    h._offset_entries[0][0].set("9")

    values = h._read_sidebar_values()

    assert values is not None
    assert values.name == "Bad_Name_"
    assert values.offsets == ({"x": 9, "y": 2, "trigger": "tag = A"},)


def test_autosave_keeps_position_when_target_cell_occupied(tk_root, log_state):
    mover = _focus(id=1, name="mover", x=0, y=0, desc="old")
    blocker = _focus(id=2, name="blocker", x=3, y=4)
    h = _harness_with(tk_root, mover, blocker)
    h._fv_x.set("3")
    h._fv_y.set("4")
    h._fv_desc.delete("1.0", "end")
    h._fv_desc.insert("1.0", "moved desc")

    h._autosave()

    assert (mover.x, mover.y) == (0, 0)
    assert mover.desc == "moved desc"
    assert h.focuses.occupied_positions == {(0, 0): {1}, (3, 4): {2}}
    assert h.focuses.validate_indexes()
    assert log_state.get_error_entries() == []


def test_apply_bad_cost_applies_other_fields_uses_fallback(tk_root, monkeypatch):
    """Invalid cost should not block other valid field edits."""
    focus = _focus(name="keep", icon="⚔", gfx="GFX_goal_generic_political_pressure")
    h = _harness_with(tk_root, focus)
    h._fv_name.set("renamed")
    h._fv_icon.set("★")
    h._fv_cost.set("nope")

    h._apply()

    # Valid fields are applied; cost falls back to current value.
    assert focus.name == "renamed"
    assert focus.icon == "★"
    assert focus.cost == 10
    assert h._undo_pushes == [("edit focus", (focus.id,))]
    assert h.focuses.first_by_name == {"renamed": focus.id}
    assert h._list_invalidations == 1


def test_apply_empty_name_does_not_push_undo(tk_root, monkeypatch):
    focus = _focus(name="keep")
    h = _harness_with(tk_root, focus)
    before = deepcopy(focus.to_dict())
    boxes = _MessageBox()
    monkeypatch.setattr(m, "messagebox", boxes)
    h._fv_name.set("   ")

    h._apply()

    assert focus.to_dict() == before
    assert h._undo_pushes == []
    assert len(boxes.errors) == 1


def test_apply_occupied_position_refuses_all_changes(tk_root, monkeypatch):
    mover = _focus(id=1, name="mover", x=0, y=0, desc="old")
    blocker = _focus(id=2, name="blocker", x=5, y=5)
    h = _harness_with(tk_root, mover, blocker)
    before = deepcopy(mover.to_dict())
    boxes = _MessageBox()
    monkeypatch.setattr(m, "messagebox", boxes)
    h._fv_name.set("renamed")
    h._fv_desc.delete("1.0", "end")
    h._fv_desc.insert("1.0", "new desc")
    h._fv_x.set("5")
    h._fv_y.set("5")

    h._apply()

    assert mover.to_dict() == before
    assert h._undo_pushes == []
    assert len(boxes.warnings) == 1
    assert boxes.errors == []


def test_apply_writes_fields_and_moves_when_valid(tk_root, monkeypatch):
    focus = _focus(name="old", x=0, y=0, desc="old")
    h = _harness_with(tk_root, focus)
    boxes = _MessageBox()
    monkeypatch.setattr(m, "messagebox", boxes)
    h._fv_name.set("new_name")
    h._fv_desc.delete("1.0", "end")
    h._fv_desc.insert("1.0", "new desc")
    h._fv_x.set("2")
    h._fv_y.set("3")

    h._apply()

    assert focus.name == "new_name"
    assert focus.desc == "new desc"
    assert (focus.x, focus.y) == (2, 3)
    assert h._undo_pushes == [("edit focus", (focus.id,))]
    assert h.focuses.first_by_name == {"new_name": focus.id}
    assert h._list_invalidations == 1
    assert boxes.errors == []
    assert boxes.warnings == []
