"""Regression tests for sidebar pending edits across undo/redo.

Ctrl+Z / Ctrl+Y must flush pending sidebar edits into history instead of
letting the repopulated form silently drop them, and an untouched form must
not clear the redo trail while navigating history.
"""

from typing import Any
from unittest.mock import Mock

from builders import make_focus

import hoi4_content_maker as m
from hoi4cm.core.undo import UndoStack
from hoi4cm.models import (
    Focus,
    FocusDocument,
    FocusSidebarValues,
    apply_sidebar_values,
)

_UNDO_REFRESHES = (
    "_populate",
    "_refresh_prereqs",
    "_refresh_mutex",
    "_refresh_effects",
)


class _SidebarApp:
    """Headless App double hosting the real sidebar autosave and history.

    ``_read_sidebar_values`` returns the pending values when one is armed
    (a dirty form) and a matching snapshot otherwise (an untouched form), so
    the real ``_autosave`` dirty check, undo push, and apply all run.
    """

    selected: Focus
    _undo_stack: UndoStack
    _pending_values: FocusSidebarValues | None
    # Real App methods bound onto this double by ``_app``.
    _push_undo: Any
    _autosave: Any
    _undo: Any
    _redo: Any
    _populate: Mock
    _refresh_prereqs: Mock
    _refresh_mutex: Mock
    _refresh_effects: Mock

    def __init__(self, focus: Focus) -> None:
        self.focuses = FocusDocument([focus])
        self.selected = focus
        self._undo_stack = UndoStack()
        self._pending_values: FocusSidebarValues | None = None
        self.cv = Mock()
        self._hide_form = Mock()
        self._redraw = Mock()
        self._invalidate_focus_list_structure = Mock()
        self._hint = Mock()
        for refresh in _UNDO_REFRESHES:
            setattr(self, refresh, Mock())

    def _read_sidebar_values(self) -> FocusSidebarValues:
        focus = self.selected
        if self._pending_values is not None:
            return self._pending_values
        return FocusSidebarValues(
            name=focus.name,
            icon=focus.icon,
            gfx=focus.gfx,
            cost=focus.cost,
            ai_will_do=focus.ai_will_do,
            ai_will_do_raw=getattr(focus, "ai_will_do_raw", "").strip(),
            x=focus.x,
            y=focus.y,
            loc_name=getattr(focus, "loc_name", ""),
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


def _app(focus: Focus) -> _SidebarApp:
    app = _SidebarApp(focus)
    for name in ("_push_undo", "_autosave", "_undo", "_redo"):
        setattr(app, name, getattr(m.App, name).__get__(app))
    return app


def _armed_with_desc(app: _SidebarApp, desc: str) -> None:
    matching = app._read_sidebar_values()
    app._pending_values = FocusSidebarValues(**{**matching.__dict__, "desc": desc})
    assert app.selected.desc != desc  # the armed snapshot really is a change


def test_undo_flushes_pending_sidebar_edit_so_it_stays_undoable():
    focus = make_focus(desc="old")
    app = _app(focus)
    _armed_with_desc(app, "typed")

    app._undo()  # flushes the pending edit, then undoes that very push

    assert app.focuses[focus.id].desc == "old"
    app._populate.assert_called_once_with(app.selected)
    assert len(app._undo_stack) == 0

    app._redo()

    assert app.focuses[focus.id].desc == "typed"
    assert app._undo_stack.undo(app.focuses, Focus.from_dict) is not None


def test_redo_does_not_replay_stale_redo_across_a_fresh_pending_edit():
    focus = make_focus(desc="old")
    app = _app(focus)
    app._push_undo("edit focus", touched_ids=(focus.id,))
    focus.desc = "previous step"
    app._undo()
    assert len(app._undo_stack._redo) == 1  # a stale redo step is waiting

    _armed_with_desc(app, "typed")
    app._redo()

    # The flush push cleared the redo trail: the stale step never replays,
    # and the fresh pending edit is committed instead of clobbered.
    assert app.focuses[focus.id].desc == "typed"
    assert len(app._undo_stack._redo) == 0
    app._hint.assert_any_call(m.tr("hint.nothing_to_redo", "Nothing to redo."))


def test_redo_flushes_pending_edit_so_it_stays_undoable():
    focus = make_focus(desc="old")
    app = _app(focus)
    _armed_with_desc(app, "typed")

    app._redo()  # flush commits the pending edit; there is nothing to redo

    assert app.focuses[focus.id].desc == "typed"
    assert len(app._undo_stack) == 1

    app._undo()

    assert app.focuses[focus.id].desc == "old"


def test_undo_with_untouched_form_preserves_the_redo_trail():
    focus = make_focus(desc="old")
    app = _app(focus)
    app._push_undo("edit focus", touched_ids=(focus.id,))
    focus.desc = "typed"
    app._undo()
    assert len(app._undo_stack._redo) == 1

    app._undo()  # untouched form: flush is a no-op, redo must survive

    assert len(app._undo_stack._redo) == 1
    assert len(app._undo_stack) == 0

    app._redo()

    assert app.focuses[focus.id].desc == "typed"


def test_history_navigation_with_untouched_form_pushes_no_undo_entry():
    focus = make_focus(desc="old")
    app = _app(focus)

    app._redo()  # untouched form: nothing to redo, and no flush push

    assert len(app._undo_stack) == 0
    assert apply_sidebar_values(focus, app._read_sidebar_values()) is False
