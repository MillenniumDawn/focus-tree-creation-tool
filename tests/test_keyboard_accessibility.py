"""Keyboard controls and dialog dismissal bindings."""

from __future__ import annotations

import tkinter as tk
from itertools import count
from types import SimpleNamespace

import pytest

import hoi4_content_maker as m
from hoi4cm.core.undo import UndoStack
from hoi4cm.focus_tree.build import build_focuses
from hoi4cm.focus_tree.export import export_focus_tree
from hoi4cm.focus_tree.parse import parse_focus_tree
from hoi4cm.models import Focus, FocusDocument
from hoi4cm.ui.canvas import CanvasMixin


class _Variable:
    def __init__(self, value):
        self.value = value

    def set(self, value):
        self.value = value


class _UndoRecorder:
    def __init__(self):
        self.actions = []

    def __call__(self, label, *, touched_ids):
        self.actions.append((label, set(touched_ids)))


class _NudgeHarness:
    _nudge_selection = m.App._nudge_selection

    def __init__(self, focuses, selected=None, multi_sel=()):
        self.focuses = FocusDocument(focuses)
        self.selected = selected
        self._multi_sel = set(multi_sel)
        self._undo_pushes = _UndoRecorder()
        self._redraws = 0
        self._hints = []
        self._fv_x = _Variable(str(selected.x) if selected else "")
        self._fv_y = _Variable(str(selected.y) if selected else "")
        self._fv_name = ""

    def focus_get(self):
        return None

    def _push_undo(self, label, touched_ids):
        self._undo_pushes(label, touched_ids=touched_ids)

    def _redraw(self):
        self._redraws += 1

    def _hint(self, message):
        self._hints.append(message)


class _KeybindHarness:
    _build_keybinds = m.App._build_keybinds

    def __init__(self):
        self.bindings = {}
        self.nudges = []
        self.tutorial_calls = []
        self._tutorial = SimpleNamespace(start=self._start_tutorial)

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def _start_tutorial(self, **kwargs):
        self.tutorial_calls.append(kwargs)

    def _nudge_selection(self, dx, dy):
        self.nudges.append((dx, dy))

    def __getattr__(self, _name):
        # Other key commands are lazy callbacks and need no behavior here.
        return lambda *_args, **_kwargs: None


def _focus(x, y):
    return Focus(id=next(_focus_ids), x=x, y=y)


_focus_ids = count(1)


def test_arrow_shortcuts_nudge_single_selected_focus_and_record_undo():
    focus = _focus(3, 4)
    app = _NudgeHarness([focus], selected=focus)

    app._nudge_selection(1, 0)

    assert (focus.x, focus.y) == (4, 4)
    assert app._undo_pushes.actions == [("nudge focus", {focus.id})]
    assert app._redraws == 1
    assert (app._fv_x.value, app._fv_y.value) == ("4", "4")


def test_nudge_preserves_other_staged_sidebar_values():
    focus = _focus(3, 4)
    app = _NudgeHarness([focus], selected=focus)
    app._fv_name = "typed but not applied"

    app._nudge_selection(1, 0)

    assert (app._fv_x.value, app._fv_y.value) == ("4", "4")
    assert app._fv_name == "typed but not applied"


def test_arrow_shortcuts_move_multiselection_as_a_group():
    left, right = _focus(1, 2), _focus(2, 2)
    app = _NudgeHarness([left, right], multi_sel=(left.id, right.id))

    app._nudge_selection(0, -1)

    assert (left.x, left.y) == (1, 1)
    assert (right.x, right.y) == (2, 1)
    assert app._undo_pushes.actions == [("nudge focuses", {left.id, right.id})]


@pytest.mark.parametrize(("dx", "dy"), [(1, 0), (0, -1)])
def test_group_nudge_preserves_relative_offsets_through_export_undo_redo(dx, dy):
    parent = _focus(10, 20)
    parent.name = "TST_parent"
    parent._raw_gx, parent._raw_gy = 10, 20
    child = _focus(11, 22)
    child.name = "TST_child"
    child.relative_position_id = parent.name
    child._raw_gx, child._raw_gy = 1, 2
    child._rel_dx, child._rel_dy = 1, 2
    app = _NudgeHarness([parent, child], multi_sel=(parent.id, child.id))
    undo = UndoStack()
    app._push_undo = lambda label, touched_ids: undo.push(
        label, app.focuses, touched_ids=touched_ids
    )

    app._nudge_selection(dx, dy)

    assert (child._rel_dx, child._rel_dy) == (1, 2)
    info = {
        "tree_id": "TST_focus_tree",
        "country_tag": "TST",
        "type": "shared",
        "had_wrapper": False,
        "shared_focuses": [],
        "joint_focuses": [],
    }
    exported = export_focus_tree(
        [parent, child], info, focus_lookup=dict(app.focuses.items())
    )
    imported = build_focuses(
        parse_focus_tree(exported, "nudged.txt"), tree_idx=1
    )
    assert [(focus.x, focus.y) for focus in imported] == [
        (10 + dx, 20 + dy),
        (11 + dx, 22 + dy),
    ]
    assert (imported[1]._rel_dx, imported[1]._rel_dy) == (1, 2)

    undo.undo(app.focuses, Focus.from_dict)
    assert (app.focuses[parent.id].x, app.focuses[parent.id].y) == (10, 20)
    restored_child = app.focuses[child.id]
    assert (restored_child._rel_dx, restored_child._rel_dy) == (1, 2)
    undo.redo(app.focuses, Focus.from_dict)
    restored_child = app.focuses[child.id]
    assert (restored_child.x, restored_child.y) == (11 + dx, 22 + dy)
    assert (restored_child._rel_dx, restored_child._rel_dy) == (1, 2)


def test_arrow_shortcuts_do_nothing_if_the_move_hits_an_unselected_focus():
    focus, blocker = _focus(1, 2), _focus(2, 2)
    app = _NudgeHarness([focus, blocker], selected=focus)

    app._nudge_selection(1, 0)

    assert (focus.x, focus.y) == (1, 2)
    assert app._undo_pushes.actions == []
    assert app._redraws == 0


def test_arrow_shortcuts_leave_listbox_navigation_alone():
    focus = _focus(1, 2)
    app = _NudgeHarness([focus], selected=focus)
    app.focus_get = lambda: tk.Listbox.__new__(tk.Listbox)

    app._nudge_selection(0, 1)

    assert (focus.x, focus.y) == (1, 2)
    assert app._undo_pushes.actions == []
    assert app._redraws == 0


@pytest.mark.visible_tk
def test_canvas_click_moves_focus_from_sidebar_entry_before_arrow_nudge(tk_root):
    focus = _focus(1, 1)
    app = _NudgeHarness([focus], selected=focus)
    app.cv = tk.Canvas(tk_root, width=100, height=100)
    app.cv.pack()
    app.mutex_mode = False
    app._multisel_mode = False
    app._drag = None
    app.bind = tk_root.bind
    app.focus_get = tk_root.focus_get
    app._select = lambda selected: setattr(app, "selected", selected)
    app._foc_pr = CanvasMixin._foc_pr.__get__(app, type(app))

    entry = tk.Entry(tk_root)
    entry.pack()
    app.cv.bind("<ButtonPress-1>", lambda event: app._foc_pr(focus.id, event))
    tk_root.bind("<Right>", lambda _event: app._nudge_selection(1, 0))
    tk_root.update()

    entry.focus_force()
    tk_root.update()
    assert tk_root.focus_get() is entry

    app.cv.event_generate("<ButtonPress-1>", x=20, y=20)
    tk_root.update()
    assert tk_root.focus_get() is app.cv

    app.cv.event_generate("<Right>")
    tk_root.update()
    assert (focus.x, focus.y) == (2, 1)


@pytest.mark.visible_tk
def test_arrow_binding_preserves_listbox_down_navigation(tk_root):
    focus = _focus(1, 1)
    app = _NudgeHarness([focus], selected=focus)
    app.focus_get = tk_root.focus_get
    listing = tk.Listbox(tk_root, height=3)
    listing.insert("end", "one", "two", "three")
    listing.pack()
    tk_root.bind("<Down>", lambda _event: app._nudge_selection(0, 1))
    tk_root.update()

    listing.focus_force()
    listing.selection_set(0)
    listing.activate(0)
    tk_root.update()
    listing.event_generate("<Down>")
    tk_root.update()

    assert listing.curselection() == (1,)
    assert (focus.x, focus.y) == (1, 1)


def test_keybindings_include_arrows_and_f1_tutorial_shortcut():
    app = _KeybindHarness()
    app._build_keybinds()

    event = SimpleNamespace(widget=object())
    app.bindings["<Left>"](event)
    app.bindings["<Right>"](event)
    app.bindings["<Up>"](event)
    app.bindings["<Down>"](event)
    app.bindings["<F1>"](event)

    assert app.nudges == [(-1, 0), (1, 0), (0, -1), (0, 1)]
    assert app.tutorial_calls == [{"manual": True}]
