from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pytest
from ui_fakes import AppFake

from hoi4cm.models.document import FocusDocument
from hoi4cm.ui.canvas import CanvasMixin
from hoi4cm.ui.focus_actions import ACTIONS, FocusActions
from hoi4cm.ui.focus_spotlight import spotlight_layout


def make_actions():
    document = FocusDocument()
    parent = document.new_focus(3, 4)
    parent.tree_idx = 2
    document.add(parent)
    app = SimpleNamespace(
        focuses=document,
        selected=parent,
        mutex_mode=False,
        cv=SimpleNamespace(focus_set=Mock()),
        _default_focus_prefix="TAG_",
        _focus_editor=SimpleNamespace(open=Mock(), flush=Mock(return_value=True)),
        _push_undo=Mock(),
        _redraw=Mock(),
        _invalidate_focus_list_structure=Mock(),
        _pick_prereq=Mock(),
        _duplicate_focus=Mock(),
        _delete_focus=Mock(),
    )
    app._select = Mock(side_effect=lambda focus: setattr(app, "selected", focus))
    actions = object.__new__(FocusActions)
    actions.app = app
    actions.focus_id = parent.id
    actions.buttons = []
    actions.images = []
    actions.popup = None
    return actions, app, parent


@pytest.mark.parametrize(
    ("action", "method", "tab"),
    [
        ("edit_focus", "open", "Properties"),
        ("add_effect", "open", "Effects"),
        ("add_prerequisite", "_pick_prereq", None),
        ("duplicate", "_duplicate_focus", None),
        ("delete", "_delete_focus", None),
    ],
)
def test_dispatch_captures_target_even_if_selection_changes(action, method, tab):
    actions, app, target = make_actions()
    other = app.focuses.new_focus(0, 0)
    app.focuses.add(other)
    app.selected = other
    actions.invoke(action)
    assert app.selected is target
    if tab:
        app._focus_editor.open.assert_called_once_with(tab=tab)
    else:
        getattr(app, method).assert_called_once_with()
    app._push_undo.assert_not_called()


def test_add_child_uses_free_cell_same_tree_and_one_undo():
    actions, app, parent = make_actions()
    app.focuses.add(app.focuses.new_focus(3, 5))
    actions.invoke("add_child")
    child = app.selected
    assert (child.x, child.y, child.tree_idx) == (3, 6, 2)
    assert child.prereqs == [[parent.id]]
    assert child.name == f"TAG_focus_{child.id}"
    app._push_undo.assert_called_once_with("add child", touched_ids=())
    app._invalidate_focus_list_structure.assert_called_once()


def test_dismiss_and_stale_target_do_not_mutate():
    actions, app, target = make_actions()
    actions.dismiss()
    assert actions.focus_id is None
    app._push_undo.assert_not_called()
    app.cv.focus_set.assert_called_once()
    actions.focus_id = target.id
    app.focuses.delete_many((target.id,))
    actions.invoke("delete")
    app._delete_focus.assert_not_called()
    app._select.assert_not_called()


def test_invalid_pending_editor_draft_prevents_action():
    actions, app, _ = make_actions()
    app._focus_editor.flush.return_value = False
    actions.invoke("duplicate")
    app._duplicate_focus.assert_not_called()
    app._push_undo.assert_not_called()


@pytest.mark.parametrize("moved", [True, False])
def test_canvas_opens_only_after_click_release(moved):
    app = AppFake()
    app._drag = {"id": 1, "moved": moved}
    app._focus_actions = Mock()
    redraw = Mock()
    app.__dict__["_redraw"] = redraw
    CanvasMixin._foc_rl(app, 1)
    assert app._drag == {}
    if moved:
        app._focus_actions.show.assert_not_called()
        redraw.assert_called_once()
    else:
        app._focus_actions.show.assert_called_once_with(1)
        redraw.assert_not_called()


def test_canvas_without_matching_press_or_mutex_never_opens():
    app = AppFake()
    app._focus_actions = Mock()
    CanvasMixin._foc_rl(app, 1)
    app._drag = {"id": 1, "moved": False}
    app.mutex_mode = True
    CanvasMixin._foc_rl(app, 1)
    app._focus_actions.show.assert_not_called()


@pytest.mark.parametrize(
    "width,scale", [(1200, 1), (500, 1), (280, 1), (1800, 1.5), (800, 2)]
)
def test_spotlight_layout_keeps_every_action_clear_of_preview(width, scale):
    bw, bh = round(200 * scale), round(48 * scale)
    layout = spotlight_layout(width, bw, bh, scale)
    assert len(layout.buttons) == len(ACTIONS)
    cx, cy, cw, ch = layout.preview
    assert cw >= 220 * scale - 1
    for i, (x, y) in enumerate(layout.buttons):
        assert 0 <= x and x + bw <= layout.width
        assert 0 <= y and y + bh <= layout.height
        assert x + bw <= cx or x >= cx + cw or y + bh <= cy or y >= cy + ch
        for x2, y2 in layout.buttons[:i]:
            assert x + bw <= x2 or x >= x2 + bw or y + bh <= y2 or y >= y2 + bh


def test_desktop_spotlight_places_actions_radially():
    layout = spotlight_layout(1200, 200, 48)
    cx, cy, cw, ch = layout.preview
    edit, prerequisite, effect, child, duplicate, delete = layout.buttons
    assert edit[0] + 100 == delete[0] + 100 == cx + cw / 2
    assert edit[1] + 48 < cy
    assert delete[1] > cy + ch
    assert prerequisite[0] + 200 < cx and effect[0] > cx + cw
    assert duplicate[0] + 200 < cx and child[0] > cx + cw
    assert prerequisite[1] < duplicate[1] and effect[1] < child[1]


def test_dismiss_restores_the_original_keyboard_widget():
    actions, app, _ = make_actions()
    previous = Mock()
    previous.winfo_exists.return_value = True
    actions._keyboard_focus = previous
    actions.dismiss()
    previous.focus_force.assert_called_once()
    app.cv.focus_set.assert_not_called()


def test_spotlight_open_error_reports_and_releases_input(monkeypatch):
    import tkinter as tk

    actions, app, target = make_actions()
    app.zoom, app.offset = 1.0, [0, 0]
    app.focus_get = Mock(return_value=None)
    actions.spotlight = Mock()
    actions.spotlight.open.side_effect = tk.TclError("unknown -transparentcolor")
    report = Mock()
    monkeypatch.setattr("hoi4cm.ui.focus_actions.report_error", report)
    actions.show(target.id)
    assert not actions.blocks_canvas
    assert actions._view_state is None
    actions.spotlight.close.assert_called()
    assert report.call_args.args[0] == (
        "Focus Spotlight could not open. Tk reported: unknown -transparentcolor"
    )


def test_dismiss_restores_exact_view_without_data_or_undo():
    actions, app, target = make_actions()
    app.zoom = 2.2
    app.offset = [45, 200]
    actions._view_state = (0.35, (-12.75, 99.25))
    actions.spotlight = Mock()
    before = target.to_dict()
    actions.dismiss()
    assert app.zoom == 0.35 and app.offset == [-12.75, 99.25]
    assert target.to_dict() == before
    app._push_undo.assert_not_called()
    actions.spotlight.close.assert_called_once()


@pytest.mark.parametrize(
    "method,args",
    [
        ("_lmb_dn", (SimpleNamespace(),)),
        ("_pan_pr", (SimpleNamespace(),)),
        ("_pan_mv", (SimpleNamespace(),)),
        ("_pan_rl", (SimpleNamespace(),)),
        ("_scroll", (SimpleNamespace(),)),
        ("_rmb", (SimpleNamespace(),)),
        ("_foc_pr", (1, SimpleNamespace())),
        ("_foc_mv", (1, SimpleNamespace())),
    ],
)
def test_spotlight_blocks_canvas_input(method, args):
    app = SimpleNamespace(_focus_actions=SimpleNamespace(blocks_canvas=True))
    assert getattr(CanvasMixin, method)(app, *args) == "break"


def test_extra_tree_child_registry_is_included_in_undo_and_redo():
    import hoi4_content_maker as maker
    from hoi4cm.core.undo import UndoStack
    from hoi4cm.editor.extra_tree_undo import ExtraTreeUndoHistory

    actions, app, parent = make_actions()
    app._extra_trees = [{"focus_ids": set()}, {"focus_ids": {parent.id}}]
    app._shared_focuses = []
    app._joint_focuses = []
    app._undo_stack = UndoStack()
    app._tree_undo_history = ExtraTreeUndoHistory()
    for name in (
        "_push_undo",
        "_snapshot_extra_tree_state",
        "_restore_extra_tree_state",
        "_undo",
        "_redo",
    ):
        setattr(app, name, MethodType(getattr(maker.App, name), app))
    for name in (
        "_refresh_loaded_trees_panel",
        "_refresh_tree_meta_panel",
        "_invalidate_tree_badges",
        "_hide_form",
        "_hint",
    ):
        setattr(app, name, Mock())
    app.cv.delete = Mock()
    actions.invoke("add_child")
    child = app.selected
    assert len(app._undo_stack) == 1
    assert app._extra_trees[1]["focus_ids"] == {parent.id, child.id}
    assert app.focuses.tree_membership[2] == {parent.id, child.id}
    app._undo()
    assert child.id not in app.focuses
    assert app._extra_trees[1]["focus_ids"] == {parent.id}
    app._redo()
    assert child.id in app.focuses
    assert app._extra_trees[1]["focus_ids"] == {parent.id, child.id}
