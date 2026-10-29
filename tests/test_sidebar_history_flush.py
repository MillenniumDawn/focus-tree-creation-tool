"""Regression tests for sidebar pending edits across undo/redo.

Ctrl+Z / Ctrl+Y must flush pending sidebar edits into history instead of
letting the repopulated form silently drop them; an untouched form must not
clear the redo trail — including on freshly imported focuses whose ai_will_do
blocks hold duplicate, nested, or negative factors.
"""

from typing import Any
from unittest.mock import Mock

import pytest
from builders import make_focus

import hoi4_content_maker as m
from hoi4cm.core.undo import UndoStack
from hoi4cm.editor.extra_tree_undo import ExtraTreeUndoHistory
from hoi4cm.focus_tree.build import build_focuses
from hoi4cm.focus_tree.parse import parse_focus_tree
from hoi4cm.models import (
    Focus,
    FocusDocument,
    FocusSidebarValues,
    apply_sidebar_values,
    form_focus_id,
)

_REFRESH_MOCKS = ("_refresh_prereqs", "_refresh_mutex", "_refresh_effects")
_DEFAULT_GFX = "GFX_goal_generic_political_pressure"
_DEFAULT_SEARCH = "FOCUS_FILTER_POLITICAL"

# Three imported ai_will_do shapes: duplicated factor keys, a nested modifier
# factor alongside a top-level one, and a negative scalar.
_IMPORTED_TREE = """\
focus_tree = {
\tid = TST_tree
\tfocus = {
\t\tid = TST_dup
\t\tx = 0
\t\ty = 0
\t\tai_will_do = {
\t\t\tfactor = 2
\t\t\tfactor = 3
\t\t}
\t}
\tfocus = {
\t\tid = TST_nested
\t\tx = 1
\t\ty = 0
\t\tai_will_do = {
\t\t\tmodifier = { factor = 100 }
\t\t\tfactor = 4
\t\t}
\t}
\tfocus = {
\t\tid = TST_neg
\t\tx = 2
\t\ty = 0
\t\tai_will_do = -1
\t}
\tfocus = {
\t\tid = TST_cond
\t\tx = 3
\t\ty = 0
\t\tavailable = {
\t\t\thas_country_flag = foo
\t\t\tOR = {
\t\t\t\ttag = GER
\t\t\t\ttag = FRA
\t\t\t}
\t\t}
\t\tbypass = { has_war = yes }
\t\tcancel = {
\t\t\talways = no
\t\t}
\t\toffset = {
\t\t\tx = 1
\t\t\ty = -1
\t\t\ttrigger = {
\t\t\t\thas_dlc = "X"
\t\t\t}
\t\t}
\t}
}
"""


class _SidebarApp:
    """Headless app hosting the real sidebar autosave and undo plumbing."""

    selected: Focus
    _undo_stack: UndoStack
    _pending_values: FocusSidebarValues | None
    populate_calls: list[Focus]
    # Real App methods bound onto this app by ``_app``.
    _push_undo: Any
    _autosave: Any
    _undo: Any
    _redo: Any
    _refresh_prereqs: Mock
    _refresh_mutex: Mock
    _refresh_effects: Mock

    def __init__(self, focus: Focus) -> None:
        self.focuses = FocusDocument([focus])
        self.selected = focus
        self._undo_stack = UndoStack()
        self._tree_undo_history = ExtraTreeUndoHistory()
        self._snapshot_extra_tree_state = Mock(return_value=None)
        self._pending_values: FocusSidebarValues | None = None
        self.populate_calls: list[Focus] = []
        self.cv = Mock()
        self._hide_form = Mock()
        self._redraw = Mock()
        self._invalidate_focus_list_structure = Mock()
        self._hint = Mock()
        for refresh in _REFRESH_MOCKS:
            setattr(self, refresh, Mock())

    def _populate(self, focus: Focus) -> None:
        """Refresh the sidebar from ``focus``, clearing form edits like the app."""
        self.selected = focus
        self._pending_values = None
        self.populate_calls.append(focus)

    def _read_sidebar_values(self) -> FocusSidebarValues:
        if self._pending_values is not None:
            return self._pending_values
        return _untouched_sidebar_values(self.selected)


def _untouched_sidebar_values(focus: Focus) -> FocusSidebarValues:
    """Snapshot of the populated form for an untouched ``focus``.

    Mirrors ``App._read_sidebar_values``: text widgets read back stripped, an
    empty raw block displays as ``base = N`` (see ``App._populate``), and the
    name field holds the id verbatim, so ``form_focus_id`` keeps it as-is.
    """
    raw_ai = (getattr(focus, "ai_will_do_raw", "") or "").strip() or (
        f"base = {focus.ai_will_do}"
    )
    return FocusSidebarValues(
        name=form_focus_id(focus.name, focus.name),
        icon=focus.icon,
        gfx=focus.gfx.strip() or _DEFAULT_GFX,
        cost=focus.cost,
        ai_will_do=m.parse_ai_will_do(raw_ai),
        ai_will_do_raw=raw_ai,
        x=focus.x,
        y=focus.y,
        loc_name=getattr(focus, "loc_name", "").strip(),
        desc=focus.desc.strip(),
        search_filters=focus.search_filters.strip() or _DEFAULT_SEARCH,
        available_cond=focus.available_cond.strip(),
        bypass_cond=focus.bypass_cond.strip(),
        cancel_cond=focus.cancel_cond.strip(),
        cancel_if_invalid=focus.cancel_if_invalid,
        continue_if_invalid=focus.continue_if_invalid,
        available_if_capitulated=focus.available_if_capitulated,
        offsets=tuple(
            {**offset, "trigger": str(offset["trigger"]).strip()}
            for offset in focus.offsets
        ),
    )


def _imported_focus(name: str) -> Focus:
    parsed = parse_focus_tree(_IMPORTED_TREE, "/tmp/t343.txt")
    return {f.name: f for f in build_focuses(parsed, tree_idx=1)}[name]


def _app(focus: Focus) -> _SidebarApp:
    app = _SidebarApp(focus)
    for name in ("_push_undo", "_autosave", "_undo", "_redo"):
        setattr(app, name, getattr(m.App, name).__get__(app))
    return app


def _armed_with_desc(app: _SidebarApp, desc: str) -> None:
    matching = app._read_sidebar_values()
    app._pending_values = FocusSidebarValues(**{**matching.__dict__, "desc": desc})
    assert app.selected.desc != desc


def _seed_redo_step(app: _SidebarApp) -> None:
    before = app.selected.desc
    app._push_undo("edit focus", touched_ids=(app.selected.id,))
    app.selected.desc = "typed"
    app._undo()
    assert app.focuses[app.selected.id].desc == before
    assert len(app._undo_stack) == 0
    assert len(app._undo_stack._redo) == 1


def test_undo_flushes_pending_sidebar_edit_so_it_stays_undoable():
    focus = make_focus(desc="old")
    app = _app(focus)
    _armed_with_desc(app, "typed")

    app._undo()  # flushes the pending edit, then undoes that very push

    assert app.focuses[focus.id].desc == "old"
    assert app.populate_calls[0].desc == "old"  # form repopulated pre-edit
    assert len(app._undo_stack) == 0
    assert len(app._undo_stack._redo) == 1

    app._redo()

    # The cleared form cannot re-arm the pending edit, so "typed" can only
    # have come from the redo stack — and that stack is really consumed.
    assert app.focuses[focus.id].desc == "typed"
    assert len(app._undo_stack._redo) == 0
    assert len(app._undo_stack) == 1
    result = app._undo_stack.undo(app.focuses, Focus.from_dict)
    assert result is not None and result[0] == "edit focus"
    assert app.focuses[focus.id].desc == "old"


def test_redo_does_not_replay_stale_redo_across_a_fresh_pending_edit():
    focus = make_focus(desc="old")
    app = _app(focus)
    _seed_redo_step(app)

    _armed_with_desc(app, "typed")
    app._redo()

    # The flush push cleared the redo trail before redo looked at it: the
    # stale step never replays and the fresh edit is committed instead.
    assert app.focuses[focus.id].desc == "typed"
    assert len(app._undo_stack._redo) == 0
    assert len(app._undo_stack) == 1
    assert app._undo_stack._stack[-1][0] == "edit focus"
    app._hint.assert_any_call(m.tr("hint.nothing_to_redo", "Nothing to redo."))


def test_redo_flushes_pending_edit_so_it_stays_undoable():
    focus = make_focus(desc="old")
    app = _app(focus)
    _armed_with_desc(app, "typed")

    app._redo()  # flush commits the pending edit; there is nothing to redo

    assert app.focuses[focus.id].desc == "typed"
    assert len(app._undo_stack) == 1
    assert app._undo_stack._stack[-1][0] == "edit focus"
    assert len(app._undo_stack._redo) == 0

    app._undo()

    assert app.focuses[focus.id].desc == "old"
    assert len(app._undo_stack) == 0
    assert len(app._undo_stack._redo) == 1


def test_undo_with_untouched_form_preserves_the_redo_trail():
    focus = make_focus(desc="old")
    app = _app(focus)
    _seed_redo_step(app)

    app._undo()  # untouched form: flush is a no-op, redo must survive

    assert len(app._undo_stack._redo) == 1
    assert len(app._undo_stack) == 0

    app._redo()

    assert app.focuses[focus.id].desc == "typed"
    assert len(app._undo_stack._redo) == 0
    assert len(app._undo_stack) == 1


def test_history_navigation_with_untouched_form_pushes_no_undo_entry():
    focus = make_focus(desc="old")
    app = _app(focus)

    app._redo()  # untouched form: nothing to redo, and no flush push

    assert len(app._undo_stack) == 0
    assert apply_sidebar_values(focus, app._read_sidebar_values()) is False


@pytest.mark.parametrize(
    ("focus_name", "ai_will_do"),
    [
        ("TST_dup", 1),
        ("TST_nested", 4),
        ("TST_neg", -1),
        # Condition blocks and offset triggers import with surrounding
        # whitespace that the stripped form never shows back.
        ("TST_cond", 1),
    ],
)
def test_untouched_imported_blocks_do_not_disturb_history(
    focus_name: str, ai_will_do: int
):
    """Imported duplicate/nested/negative ai_will_do blocks and padded
    condition or offset blocks read back through the real sidebar autosave
    without adding history or clearing redo."""
    focus = _imported_focus(focus_name)
    assert focus.ai_will_do == ai_will_do
    app = _app(focus)
    _seed_redo_step(app)

    app._undo()  # untouched sidebar over the imported block

    assert len(app._undo_stack) == 0  # no flush push
    assert len(app._undo_stack._redo) == 1  # redo survives

    app._redo()

    assert app.focuses[focus.id].desc == "typed"
    assert len(app._undo_stack._redo) == 0


def test_undo_walks_real_history_over_a_padded_imported_focus():
    """A false-dirty flush would pop its own push and never reach these."""
    app = _app(_imported_focus("TST_cond"))
    for desc in ("one", "two"):
        app._push_undo("edit focus", touched_ids=(app.selected.id,))
        app.selected.desc = desc

    app._undo()
    assert app.selected.desc == "one"

    app._undo()
    assert app.selected.desc == ""
    assert len(app._undo_stack) == 0


def test_redo_redraws_when_the_flush_commits_a_pending_edit():
    app = _app(make_focus(desc="old"))
    _armed_with_desc(app, "typed")

    app._redo()  # nothing to redo, but the committed edit must reach the canvas

    app._redraw.assert_called_once()
    app._invalidate_focus_list_structure.assert_called_once()


def test_redo_with_untouched_form_does_not_redraw():
    app = _app(make_focus(desc="old"))

    app._redo()

    app._redraw.assert_not_called()
    app._invalidate_focus_list_structure.assert_not_called()
