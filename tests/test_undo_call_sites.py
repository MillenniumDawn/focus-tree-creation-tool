from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import hoi4_content_maker as app_module
from hoi4cm.models import Focus
from hoi4cm.models.document import FocusDocument
from hoi4cm.ui.canvas import CanvasMixin
from hoi4cm.ui.theme import XGRID, YGRID


class _UndoCallSiteApp:
    selected: Focus | None
    zoom: float
    mutex_mode: bool
    _drag: dict[str, object]
    w2c: Any
    _fv_x: Any
    _fv_y: Any
    _hint: Any
    _draw_lines_throttled: Any

    def __init__(self, focuses=()):
        self.focuses = FocusDocument(focuses)
        self.selected = None
        self._push_undo = Mock()
        self._redraw = Mock()
        self._refresh_prereqs = Mock()
        self._refresh_mutex = Mock()
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


def test_make_prereq_pushes_child_id():
    child = Focus()
    parent = Focus()
    app = _UndoCallSiteApp([child, parent])

    app_module.App._make_prereq(_as_app(app), child, parent)

    app._push_undo.assert_called_once_with("add prerequisite", touched_ids=(child.id,))
    assert child.prereqs == [[parent.id]]


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


def test_drag_move_pushes_once_with_moved_focus_id():
    focus = Focus()
    app = _UndoCallSiteApp([focus])
    app.zoom = 1.0
    app.mutex_mode = False
    app._drag = {
        "id": focus.id,
        "sx": focus.x,
        "sy": focus.y,
        "cx": 0,
        "cy": 0,
        "moved": False,
        "undo_pushed": False,
        "last_snap": (focus.x, focus.y),
        "occupied": set(),
    }
    app.w2c = lambda x, y: (x * XGRID, y * YGRID)
    app._fv_x = Mock()
    app._fv_y = Mock()
    app._hint = Mock()
    app._draw_lines_throttled = Mock()

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
