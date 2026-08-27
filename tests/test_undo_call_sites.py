from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import hoi4_content_maker as app_module
from hoi4cm.core.undo import UndoStack
from hoi4cm.models import Focus
from hoi4cm.models.document import FocusDocument
from hoi4cm.ui.canvas import CanvasMixin
from hoi4cm.ui.theme import XGRID, YGRID


class _UndoCallSiteApp:
    selected: Focus | None
    zoom: float
    mutex_mode: bool
    _multisel_mode: bool
    _multi_sel: set[int]
    _select: Any
    _push_undo: Any
    _undo_stack: UndoStack
    _drag: dict[str, object]
    w2c: Any
    _fv_x: Any
    _fv_y: Any
    _hint: Any
    _draw_lines_throttled: Any

    def __init__(self, focuses=()):
        self.focuses = FocusDocument(focuses)
        self.selected = None
        self._multisel_mode = False
        self._multi_sel = set()
        self._select = Mock()
        self._push_undo = Mock()
        self._redraw = Mock()
        self._refresh_prereqs = Mock()
        self._refresh_mutex = Mock()
        self._refresh_effects = Mock()
        self._focus_list_cache = Mock()
        self._save_offsets_to_focus = Mock()
        self._refresh_offsets = Mock()
        self._populate = Mock()
        self._hint = Mock()
        self._draw_lines = Mock()
        self._begin_document_generation = Mock()
        self._hide_form = Mock()
        self._draw_grid = Mock()
        self._invalidate_focus_list_structure = Mock()
        self._invalidate_tree_badges = Mock()
        self._refresh_loaded_trees_panel = Mock()
        self._refresh_tree_meta_panel = Mock()
        self._reset_canvas_bounds = Mock()
        self.cv = Mock()
        self._focus_bundles = {}
        self._lines = []
        self._extra_trees = []
        self._shared_focuses = []
        self._joint_focuses = []
        self._grid_item = None
        self._grid_key = None
        self._grid_img = None


def _as_app(app: _UndoCallSiteApp) -> app_module.App:
    return cast(app_module.App, app)


def test_clear_all_pushes_full_snapshot_after_confirmation(monkeypatch):
    app = _UndoCallSiteApp([Focus()])
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *args: True)

    app_module.App._clear_all(_as_app(app))

    app._push_undo.assert_called_once_with("clear all")
    assert not app.focuses


def test_clear_all_cancel_keeps_document_without_undo(monkeypatch):
    focus = Focus()
    app = _UndoCallSiteApp([focus])
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *args: False)

    app_module.App._clear_all(_as_app(app))

    app._push_undo.assert_not_called()
    assert app.focuses[focus.id] is focus


def test_clear_all_round_trips_through_real_undo_stack(monkeypatch):
    focus = Focus()
    app = _UndoCallSiteApp([focus])
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
    app = _UndoCallSiteApp([focus])
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
    app = _UndoCallSiteApp()
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
    app = _UndoCallSiteApp([child, parent])

    app_module.App._make_prereq(_as_app(app), child, parent)

    app._push_undo.assert_called_once_with("add prerequisite", touched_ids=(child.id,))
    assert child.prereqs == [[parent.id]]


def test_duplicate_prereq_does_not_push_undo():
    child = Focus()
    parent = Focus()
    child.prereqs = [[parent.id]]
    app = _UndoCallSiteApp([child, parent])

    app_module.App._make_prereq(_as_app(app), child, parent)

    app._push_undo.assert_not_called()
    assert child.prereqs == [[parent.id]]


def test_remove_prereq_without_selection_does_not_push_undo():
    app = _UndoCallSiteApp([Focus()])

    app_module.App._rm_prereq(_as_app(app), 0)

    app._push_undo.assert_not_called()


def test_remove_prereq_group_pushes_child_id():
    child = Focus()
    parent = Focus()
    child.prereqs = [[parent.id]]
    app = _UndoCallSiteApp([child, parent])
    app.selected = child

    app_module.App._rm_prereq(_as_app(app), 0)

    app._push_undo.assert_called_once_with(
        "remove prerequisite group", touched_ids=(child.id,)
    )
    assert child.prereqs == []


def test_remove_mutex_without_selection_does_not_push_undo():
    app = _UndoCallSiteApp([Focus()])

    app_module.App._rm_mutex(_as_app(app), 0)

    app._push_undo.assert_not_called()


def test_make_mutex_pushes_both_focus_ids():
    first = Focus()
    second = Focus()
    app = _UndoCallSiteApp([first, second])

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
    app = _UndoCallSiteApp([selected, partner])
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
    app = _UndoCallSiteApp([focus])
    app.selected = focus

    app_module.App._rm_effect(_as_app(app), 0)

    app._push_undo.assert_called_once_with("remove effect", touched_ids=(focus.id,))
    assert focus.effects == []


def test_rm_effect_round_trip_through_real_undo_stack():
    focus = Focus()
    focus.effects = [{"type": "add_ideas", "fields": {}}]
    app = _UndoCallSiteApp([focus])
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
    app = _UndoCallSiteApp([focus])
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
    app = _UndoCallSiteApp([focus])
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
    app = _UndoCallSiteApp([focus])
    app.selected = focus

    app_module.App._del_offset(_as_app(app), 0)

    app._push_undo.assert_called_once_with("remove offset", touched_ids=(focus.id,))
    assert focus.offsets == [{"x": 3, "y": 4, "trigger": ""}]


def test_del_offset_round_trip_through_real_undo_stack():
    focus = Focus()
    focus.offsets = [{"x": 1, "y": 2, "trigger": ""}, {"x": 3, "y": 4, "trigger": ""}]
    app = _UndoCallSiteApp([focus])
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
    app = _UndoCallSiteApp([focus])
    app.zoom = 1.0
    app.mutex_mode = False

    CanvasMixin._foc_pr(
        cast(CanvasMixin, app), focus.id, SimpleNamespace(x=0, y=0, state=0)
    )
    CanvasMixin._foc_mv(cast(CanvasMixin, app), focus.id, SimpleNamespace(x=3, y=3))

    app._push_undo.assert_not_called()
    assert (focus.x, focus.y) == (0, 0)


def test_drag_into_occupied_cell_does_not_push_undo():
    focus = Focus()
    occupied = Focus(1, 1)
    app = _UndoCallSiteApp([focus, occupied])
    app.zoom = 1.0
    app.mutex_mode = False

    CanvasMixin._foc_pr(
        cast(CanvasMixin, app), focus.id, SimpleNamespace(x=0, y=0, state=0)
    )
    CanvasMixin._foc_mv(
        cast(CanvasMixin, app), focus.id, SimpleNamespace(x=XGRID, y=YGRID)
    )

    app._push_undo.assert_not_called()
    assert (focus.x, focus.y) == (0, 0)


def test_drag_event_for_other_focus_does_not_push_undo():
    focus = Focus()
    other = Focus(1, 1)
    app = _UndoCallSiteApp([focus, other])
    app.zoom = 1.0
    app.mutex_mode = False

    CanvasMixin._foc_pr(
        cast(CanvasMixin, app), focus.id, SimpleNamespace(x=0, y=0, state=0)
    )
    CanvasMixin._foc_mv(
        cast(CanvasMixin, app), other.id, SimpleNamespace(x=XGRID, y=YGRID)
    )

    app._push_undo.assert_not_called()
    assert (focus.x, focus.y) == (0, 0)


def test_drag_in_mutex_mode_does_not_push_undo():
    focus = Focus()
    app = _UndoCallSiteApp([focus])
    app.zoom = 1.0
    app.mutex_mode = False

    CanvasMixin._foc_pr(
        cast(CanvasMixin, app), focus.id, SimpleNamespace(x=0, y=0, state=0)
    )
    app.mutex_mode = True
    CanvasMixin._foc_mv(
        cast(CanvasMixin, app), focus.id, SimpleNamespace(x=XGRID, y=YGRID)
    )

    app._push_undo.assert_not_called()
    assert (focus.x, focus.y) == (0, 0)


def test_drag_move_pushes_once_with_moved_focus_id():
    focus = Focus()
    app = _UndoCallSiteApp([focus])
    app.zoom = 1.0
    app.mutex_mode = False
    app.w2c = lambda x, y: (x * XGRID, y * YGRID)
    app._fv_x = Mock()
    app._fv_y = Mock()
    app._hint = Mock()
    app._draw_lines_throttled = Mock()

    CanvasMixin._foc_pr(
        cast(CanvasMixin, app), focus.id, SimpleNamespace(x=0, y=0, state=0)
    )
    CanvasMixin._foc_mv(cast(CanvasMixin, app), focus.id, SimpleNamespace(x=3, y=3))
    app._push_undo.assert_not_called()

    CanvasMixin._foc_mv(
        cast(CanvasMixin, app), focus.id, SimpleNamespace(x=XGRID, y=YGRID)
    )
    CanvasMixin._foc_mv(
        cast(CanvasMixin, app), focus.id, SimpleNamespace(x=XGRID, y=YGRID)
    )
    CanvasMixin._foc_mv(
        cast(CanvasMixin, app),
        focus.id,
        SimpleNamespace(x=2 * XGRID, y=2 * YGRID),
    )

    app._push_undo.assert_called_once_with("move focus", touched_ids=(focus.id,))
    assert (focus.x, focus.y) == (2, 2)
