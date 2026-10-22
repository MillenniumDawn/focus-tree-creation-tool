from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hoi4cm.models.document import FocusDocument
from hoi4cm.ui.canvas import CanvasMixin
from hoi4cm.ui.focus_actions import ACTIONS, FocusActions, action_positions


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
    app = SimpleNamespace(
        _drag={"id": 1, "moved": moved},
        mutex_mode=False,
        _redraw=Mock(),
        _focus_actions=Mock(),
    )
    CanvasMixin._foc_rl(app, 1)
    assert app._drag == {}
    if moved:
        app._focus_actions.show.assert_not_called()
        app._redraw.assert_called_once()
    else:
        app._focus_actions.show.assert_called_once_with(1)
        app._redraw.assert_not_called()


def test_canvas_without_matching_press_or_mutex_never_opens():
    app = SimpleNamespace(
        _drag={}, mutex_mode=False, _redraw=Mock(), _focus_actions=Mock()
    )
    CanvasMixin._foc_rl(app, 1)
    app._drag = {"id": 1, "moved": False}
    app.mutex_mode = True
    CanvasMixin._foc_rl(app, 1)
    app._focus_actions.show.assert_not_called()


@pytest.mark.parametrize(
    ("width", "height", "keyboard"),
    [(800, 600, False), (240, 400, False), (800, 600, True)],
)
def test_menu_positions_stay_inside_viewport(width, height, keyboard):
    positions = action_positions(width, height, 2000, -1000, 200, 44, keyboard=keyboard)
    assert len(positions) == len(ACTIONS)
    assert all(0 <= x <= width - 200 and 0 <= y <= height - 44 for x, y in positions)


@pytest.mark.parametrize(("width", "height"), [(1, 1), (240, 70), (800, 100)])
def test_tiny_canvas_uses_popup_instead_of_squeezing_buttons(width, height):
    assert action_positions(width, height, 0, 0, 200, 44) == []


def test_arrow_keys_traverse_buttons_and_wrap():
    actions, _, _ = make_actions()
    actions.buttons = [Mock() for _ in ACTIONS]
    assert actions._step(0, -1) == "break"
    actions.buttons[-1].focus_set.assert_called_once()
    assert actions._step(5, 1) == "break"
    actions.buttons[0].focus_set.assert_called_once()


def test_short_canvas_posts_readable_native_menu():
    actions, app, _ = make_actions()
    actions.keyboard = False
    actions.buttons = [Mock() for _ in ACTIONS]
    for button in actions.buttons:
        button.winfo_reqwidth.return_value = 200
        button.winfo_reqheight.return_value = 44
    app.cv.winfo_width = Mock(return_value=800)
    app.cv.winfo_height = Mock(return_value=70)
    app.w2c = Mock(return_value=(50, 50))
    actions._show_popup = Mock()
    actions.reflow()
    actions._show_popup.assert_called_once_with(50, 50)
    for button in actions.buttons:
        button.place_forget.assert_called_once()
        button.place.assert_not_called()


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
        setattr(app, name, getattr(maker.App, name).__get__(app))
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
