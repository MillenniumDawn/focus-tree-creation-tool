"""Keyboard controls and dialog dismissal bindings."""

from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import pytest

import hoi4_content_maker as m
from hoi4cm.models import Focus, FocusDocument


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
    return Focus(x, y)


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


def test_arrow_shortcuts_do_nothing_if_the_move_hits_an_unselected_focus():
    focus, blocker = _focus(1, 2), _focus(2, 2)
    app = _NudgeHarness([focus, blocker], selected=focus)

    app._nudge_selection(1, 0)

    assert (focus.x, focus.y) == (1, 2)
    assert app._undo_pushes.actions == []
    assert app._redraws == 0


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


@pytest.mark.visible_tk
def test_dialog_escape_binding_invokes_dialog_close(tk_root):
    dialog = tk.Toplevel(tk_root)
    closed = []
    m.App._bind_dialog_escape(dialog, lambda: closed.append(True))
    entry = tk.Entry(dialog)
    entry.pack()
    dialog.deiconify()
    dialog.update()
    assert entry.winfo_viewable()
    entry.focus_force()
    dialog.update()

    entry.event_generate("<Escape>")
    dialog.update()

    assert closed == [True]
    dialog.destroy()
