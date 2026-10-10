from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

from ui_fakes import AppFake

import hoi4_content_maker as app_module
from hoi4cm.core.undo import UndoStack
from hoi4cm.models import Focus
from hoi4cm.ui.theme import XGRID, YGRID


def _as_app(app: AppFake) -> app_module.App:
    return cast(app_module.App, app)


def test_clear_all_pushes_full_snapshot_after_confirmation(monkeypatch):
    app = AppFake([Focus()])
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *args: True)

    app_module.App._clear_all(_as_app(app))

    app._push_undo.assert_called_once_with("clear all")
    assert not app.focuses


def test_clear_all_cancel_keeps_document_without_undo(monkeypatch):
    focus = Focus()
    app = AppFake([focus])
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *args: False)

    app_module.App._clear_all(_as_app(app))

    app._push_undo.assert_not_called()
    assert app.focuses[focus.id] is focus


def test_clear_all_round_trips_through_real_undo_stack(monkeypatch):
    focus = Focus()
    app = AppFake([focus])
    app._undo_stack = UndoStack()

    def push_undo(label="action", touched_ids=None):
        app_module.App._push_undo(_as_app(app), label, touched_ids)

    app._push_undo = push_undo
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *args: True)

    app_module.App._clear_all(_as_app(app))
    result = app._undo_stack.undo(app.focuses, Focus.from_dict)

    assert result is not None
    assert result[0] == "clear all"
    assert app.focuses[focus.id].name == focus.name


def test_undo_and_redo_refresh_selected_focus():
    focus = Focus()
    original_name = focus.name
    app = AppFake([focus])
    app.selected = focus
    app._undo_stack = UndoStack()

    app_module.App._push_undo(_as_app(app), "edit focus", touched_ids=(focus.id,))
    focus.name = "changed"
    app_module.App._undo(_as_app(app))

    assert app.selected is not focus
    assert app.selected.name == original_name
    app._populate.assert_called_once_with(app.selected)
    app._refresh_prereqs.assert_called_once_with()
    app._refresh_mutex.assert_called_once_with()
    app._refresh_effects.assert_called_once_with()

    app_module.App._redo(_as_app(app))

    assert app.selected.name == "changed"
    assert app._populate.call_count == 2
    assert app._refresh_prereqs.call_count == 2
    assert app._refresh_mutex.call_count == 2
    assert app._refresh_effects.call_count == 2


def test_undo_clears_selected_focus_after_removal():
    app = AppFake()
    app._undo_stack = UndoStack()
    app_module.App._push_undo(_as_app(app), "add focus", touched_ids=())
    focus = Focus()
    app.focuses.add(focus)
    app.selected = focus

    app_module.App._undo(_as_app(app))

    assert app.selected is None
    app._hide_form.assert_called_once_with()
    app.cv.delete.assert_called_once_with(f"F{focus.id}")


def test_make_prereq_pushes_child_id():
    child = Focus()
    parent = Focus()
    app = AppFake([child, parent])

    app_module.App._make_prereq(_as_app(app), child, parent)

    app._push_undo.assert_called_once_with("add prerequisite", touched_ids=(child.id,))
    assert child.prereqs == [[parent.id]]


def test_duplicate_prereq_does_not_push_undo():
    child = Focus()
    parent = Focus()
    child.prereqs = [[parent.id]]
    app = AppFake([child, parent])

    app_module.App._make_prereq(_as_app(app), child, parent)

    app._push_undo.assert_not_called()
    assert child.prereqs == [[parent.id]]


def test_remove_prereq_without_selection_does_not_push_undo():
    app = AppFake([Focus()])

    app_module.App._rm_prereq(_as_app(app), 0)

    app._push_undo.assert_not_called()


def test_remove_prereq_group_pushes_child_id():
    child = Focus()
    parent = Focus()
    child.prereqs = [[parent.id]]
    app = AppFake([child, parent])
    app.selected = child

    app_module.App._rm_prereq(_as_app(app), 0)

    app._push_undo.assert_called_once_with(
        "remove prerequisite group", touched_ids=(child.id,)
    )
    assert child.prereqs == []


def test_remove_mutex_without_selection_does_not_push_undo():
    app = AppFake([Focus()])

    app_module.App._rm_mutex(_as_app(app), 0)

    app._push_undo.assert_not_called()


def test_make_mutex_pushes_both_focus_ids():
    first = Focus()
    second = Focus()
    app = AppFake([first, second])

    app_module.App._make_mutex(_as_app(app), first, second)

    app._push_undo.assert_called_once_with(
        "add mutex", touched_ids=(first.id, second.id)
    )
    assert first.mutex == [second.id]
    assert second.mutex == [first.id]


def test_remove_mutex_pushes_selected_and_partner_ids():
    selected = Focus()
    partner = Focus()
    selected.mutex = [partner.id]
    partner.mutex = [selected.id]
    app = AppFake([selected, partner])
    app.selected = selected

    app_module.App._rm_mutex(_as_app(app), 0)

    app._push_undo.assert_called_once_with(
        "remove mutex", touched_ids=(selected.id, partner.id)
    )
    assert selected.mutex == []
    assert partner.mutex == []


def test_rm_effect_pushes_focus_id():
    focus = Focus()
    focus.effects = [{"type": "add_ideas", "fields": {}}]
    app = AppFake([focus])
    app.selected = focus

    app_module.App._rm_effect(_as_app(app), 0)

    app._push_undo.assert_called_once_with("remove effect", touched_ids=(focus.id,))
    assert focus.effects == []


def test_rm_effect_round_trip_through_real_undo_stack():
    focus = Focus()
    focus.effects = [{"type": "add_ideas", "fields": {}}]
    app = AppFake([focus])
    app.selected = focus
    app._undo_stack = UndoStack()

    def push_undo(label="action", touched_ids=None):
        app_module.App._push_undo(_as_app(app), label, touched_ids)

    app._push_undo = push_undo

    app_module.App._rm_effect(_as_app(app), 0)
    assert focus.effects == []

    app_module.App._undo(_as_app(app))

    assert app.selected.effects == [{"type": "add_ideas", "fields": {}}]


def test_add_offset_pushes_focus_id_and_appends_offset():
    focus = Focus()
    focus.offsets = [{"x": 1, "y": 2, "trigger": "has_war = yes"}]
    app = AppFake([focus])
    app.selected = focus

    app_module.App._add_offset(_as_app(app))

    app._push_undo.assert_called_once_with("add offset", touched_ids=(focus.id,))
    assert focus.offsets == [
        {"x": 1, "y": 2, "trigger": "has_war = yes"},
        {"x": 0, "y": 0, "trigger": ""},
    ]


def test_add_offset_round_trip_through_real_undo_stack():
    focus = Focus()
    focus.offsets = [{"x": 1, "y": 2, "trigger": ""}]
    app = AppFake([focus])
    app.selected = focus
    app._undo_stack = UndoStack()

    def push_undo(label="action", touched_ids=None):
        app_module.App._push_undo(_as_app(app), label, touched_ids)

    app._push_undo = push_undo

    app_module.App._add_offset(_as_app(app))
    assert len(focus.offsets) == 2

    app_module.App._undo(_as_app(app))

    assert app.selected.offsets == [{"x": 1, "y": 2, "trigger": ""}]


def test_del_offset_pushes_focus_id_and_removes_offset():
    focus = Focus()
    focus.offsets = [{"x": 1, "y": 2, "trigger": ""}, {"x": 3, "y": 4, "trigger": ""}]
    app = AppFake([focus])
    app.selected = focus

    app_module.App._del_offset(_as_app(app), 0)

    app._push_undo.assert_called_once_with("remove offset", touched_ids=(focus.id,))
    assert focus.offsets == [{"x": 3, "y": 4, "trigger": ""}]


def test_del_offset_round_trip_through_real_undo_stack():
    focus = Focus()
    focus.offsets = [{"x": 1, "y": 2, "trigger": ""}, {"x": 3, "y": 4, "trigger": ""}]
    app = AppFake([focus])
    app.selected = focus
    app._undo_stack = UndoStack()

    def push_undo(label="action", touched_ids=None):
        app_module.App._push_undo(_as_app(app), label, touched_ids)

    app._push_undo = push_undo

    app_module.App._del_offset(_as_app(app), 0)
    assert len(focus.offsets) == 1

    app_module.App._undo(_as_app(app))

    assert app.selected.offsets == [
        {"x": 1, "y": 2, "trigger": ""},
        {"x": 3, "y": 4, "trigger": ""},
    ]


def test_drag_click_without_grid_move_does_not_push_undo():
    focus = Focus()
    app = AppFake([focus])
    app.zoom = 1.0
    app.mutex_mode = False

    app._foc_pr(focus.id, SimpleNamespace(x=0, y=0, state=0))
    app._foc_mv(focus.id, SimpleNamespace(x=3, y=3))

    app._push_undo.assert_not_called()
    assert (focus.x, focus.y) == (0, 0)


def test_drag_into_occupied_cell_does_not_push_undo():
    focus = Focus()
    occupied = Focus(1, 1)
    app = AppFake([focus, occupied])
    app.zoom = 1.0
    app.mutex_mode = False

    app._foc_pr(focus.id, SimpleNamespace(x=0, y=0, state=0))
    app._foc_mv(focus.id, SimpleNamespace(x=XGRID, y=YGRID))

    app._push_undo.assert_not_called()
    assert (focus.x, focus.y) == (0, 0)


def test_drag_event_for_other_focus_does_not_push_undo():
    focus = Focus()
    other = Focus(1, 1)
    app = AppFake([focus, other])
    app.zoom = 1.0
    app.mutex_mode = False

    app._foc_pr(focus.id, SimpleNamespace(x=0, y=0, state=0))
    app._foc_mv(other.id, SimpleNamespace(x=XGRID, y=YGRID))

    app._push_undo.assert_not_called()
    assert (focus.x, focus.y) == (0, 0)


def test_drag_in_mutex_mode_does_not_push_undo():
    focus = Focus()
    app = AppFake([focus])
    app.zoom = 1.0
    app.mutex_mode = False

    app._foc_pr(focus.id, SimpleNamespace(x=0, y=0, state=0))
    app.mutex_mode = True
    app._foc_mv(focus.id, SimpleNamespace(x=XGRID, y=YGRID))

    app._push_undo.assert_not_called()
    assert (focus.x, focus.y) == (0, 0)


def test_drag_move_pushes_once_with_moved_focus_id():
    focus = Focus()
    app = AppFake([focus])
    app.zoom = 1.0
    app.mutex_mode = False
    app._fv_x = Mock()
    app._fv_y = Mock()
    app._hint = Mock()
    app._draw_lines_throttled = Mock()

    app._foc_pr(focus.id, SimpleNamespace(x=0, y=0, state=0))
    app._foc_mv(focus.id, SimpleNamespace(x=3, y=3))
    app._push_undo.assert_not_called()

    app._foc_mv(focus.id, SimpleNamespace(x=XGRID, y=YGRID))
    app._foc_mv(focus.id, SimpleNamespace(x=XGRID, y=YGRID))
    app._foc_mv(
        focus.id,
        SimpleNamespace(x=2 * XGRID, y=2 * YGRID),
    )

    app._push_undo.assert_called_once_with("move focus", touched_ids=(focus.id,))
    assert (focus.x, focus.y) == (2, 2)


def test_drag_start_snapshots_occupied_positions():
    focus = Focus()
    other = Focus(3, 4)
    app = AppFake([focus, other])
    app.zoom = 1.0
    app.mutex_mode = False

    app._foc_pr(focus.id, SimpleNamespace(x=0, y=0, state=0))

    assert app._drag["occupied"] == {(3, 4)}


def test_rmb_on_occupied_cell_does_not_place(monkeypatch):
    focus = Focus(2, 3)
    app = AppFake([focus])
    app._new_focus_at = Mock()
    monkeypatch.setattr(app, "c2w", lambda _x, _y: (2, 3))
    app.cv.find_overlapping.return_value = ()

    app._rmb(SimpleNamespace(x=10, y=10))

    app._new_focus_at.assert_not_called()


def test_rmb_on_free_cell_places(monkeypatch):
    focus = Focus(2, 3)
    app = AppFake([focus])
    app._new_focus_at = Mock()
    monkeypatch.setattr(app, "c2w", lambda _x, _y: (5, 5))
    app.cv.find_overlapping.return_value = ()

    app._rmb(SimpleNamespace(x=10, y=10))

    app._new_focus_at.assert_called_once_with(5, 5)


def test_add_focus_picks_first_free_cell_without_repairing_indexes():
    app = AppFake([Focus(0, 0), Focus(2, 0)])
    app._new_focus_at = Mock()
    app.focuses.validate_indexes = Mock()  # type: ignore[method-assign]
    app.focuses.rebuild_indexes = Mock()  # type: ignore[method-assign]

    app_module.App._add_focus(_as_app(app))

    app._new_focus_at.assert_called_once_with(4, 0)
    app.focuses.validate_indexes.assert_not_called()
    app.focuses.rebuild_indexes.assert_not_called()


def test_new_focus_at_keeps_indexes_exact_without_a_rebuild():
    existing = Focus(0, 0)
    app = AppFake([existing])
    app._default_focus_prefix = "tag_"
    app.focuses.rebuild_indexes = Mock()  # type: ignore[method-assign]

    app_module.App._new_focus_at(_as_app(app), 2, 0)

    created = app._select.call_args.args[0]
    assert created.name == f"tag_focus_{created.id}"
    assert app.focuses.occupied_positions[(2, 0)] == {created.id}
    assert app.focuses.first_by_name[created.name] == created.id
    app.focuses.rebuild_indexes.assert_not_called()
    assert app.focuses.validate_indexes()
