import copy
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest
from ui_fakes import AppFake

import hoi4_content_maker as app_module
from hoi4cm.core.undo import UndoStack
from hoi4cm.focus_tree.codec import apply_focus_code, render_focus_block
from hoi4cm.models import Focus
from hoi4cm.models.document import FocusDocument
from hoi4cm.ui.theme import XGRID, YGRID


def _as_app(app: AppFake) -> app_module.App:
    return cast(app_module.App, app)


def test_clear_all_pushes_full_snapshot_after_confirmation(monkeypatch):
    app = AppFake([Focus(id=33)])
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *args: True)

    app_module.App._clear_all(_as_app(app))

    app._push_undo.assert_called_once_with("clear all", tree_state=True)
    assert not app.focuses


def test_clear_all_cancel_keeps_document_without_undo(monkeypatch):
    focus = Focus(id=1)
    app = AppFake([focus])
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *args: False)

    app_module.App._clear_all(_as_app(app))

    app._push_undo.assert_not_called()
    assert app.focuses[focus.id] is focus


def test_clear_all_round_trips_through_real_undo_stack(monkeypatch):
    focus = Focus(id=2)
    app = AppFake([focus])
    app._undo_stack = UndoStack()

    def push_undo(label="action", touched_ids=None, *, tree_state=False):
        app_module.App._push_undo(
            _as_app(app), label, touched_ids, tree_state=tree_state
        )

    app._push_undo = push_undo
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *args: True)

    app_module.App._clear_all(_as_app(app))
    result = app._undo_stack.undo(app.focuses, Focus.from_dict)

    assert result is not None
    assert result[0] == "clear all"
    assert app.focuses[focus.id].name == focus.name


def test_undo_and_redo_refresh_selected_focus():
    focus = Focus(id=3)
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


def test_bulk_rename_ui_undo_redo_restores_anchor_only_child():
    root = Focus(id=40)
    root.name = "OLD_root"
    child = Focus(id=41)
    child.name = "OTHER_child"
    child.relative_position_id = root.name
    app = AppFake([root, child])
    app._undo_stack = UndoStack()
    touched_ids = app.focuses.prefix_rename_touched_ids("OLD_")
    app_module.App._push_undo(_as_app(app), "bulk_rename", touched_ids=touched_ids)
    app.focuses.rename_prefix("OLD_", "NEW_")

    assert app.focuses[root.id].name == "NEW_root"
    assert app.focuses[child.id].relative_position_id == "NEW_root"
    app_module.App._undo(_as_app(app))
    assert app.focuses[root.id].name == "OLD_root"
    assert app.focuses[child.id].relative_position_id == "OLD_root"

    app_module.App._redo(_as_app(app))
    assert app.focuses[root.id].name == "NEW_root"
    assert app.focuses[child.id].relative_position_id == "NEW_root"


def test_undo_clears_selected_focus_after_removal():
    app = AppFake()
    app._undo_stack = UndoStack()
    app_module.App._push_undo(_as_app(app), "add focus", touched_ids=())
    focus = Focus(id=4)
    app.focuses.add(focus)
    app.selected = focus

    app_module.App._undo(_as_app(app))

    assert app.selected is None
    app._hide_form.assert_called_once_with()
    app.cv.delete.assert_called_once_with(f"F{focus.id}")


def test_make_prereq_pushes_child_id():
    child = Focus(id=5)
    parent = Focus(id=6)
    app = AppFake([child, parent])

    app_module.App._make_prereq(_as_app(app), child, parent)

    app._push_undo.assert_called_once_with("add prerequisite", touched_ids=(child.id,))
    assert child.prereqs == [[parent.id]]


def test_duplicate_prereq_does_not_push_undo():
    child = Focus(id=7)
    parent = Focus(id=8)
    child.prereqs = [[parent.id]]
    app = AppFake([child, parent])

    app_module.App._make_prereq(_as_app(app), child, parent)

    app._push_undo.assert_not_called()
    assert child.prereqs == [[parent.id]]


def test_remove_prereq_without_selection_does_not_push_undo():
    app = AppFake([Focus(id=34)])

    app_module.App._rm_prereq(_as_app(app), 0)

    app._push_undo.assert_not_called()


def test_remove_prereq_group_pushes_child_id():
    child = Focus(id=9)
    parent = Focus(id=10)
    child.prereqs = [[parent.id]]
    app = AppFake([child, parent])
    app.selected = child

    app_module.App._rm_prereq(_as_app(app), 0)

    app._push_undo.assert_called_once_with(
        "remove prerequisite group", touched_ids=(child.id,)
    )
    assert child.prereqs == []


def test_remove_mutex_without_selection_does_not_push_undo():
    app = AppFake([Focus(id=35)])

    app_module.App._rm_mutex(_as_app(app), 0)

    app._push_undo.assert_not_called()


def test_make_mutex_pushes_both_focus_ids():
    first = Focus(id=11)
    second = Focus(id=12)
    app = AppFake([first, second])

    app_module.App._make_mutex(_as_app(app), first, second)

    app._push_undo.assert_called_once_with(
        "add mutex", touched_ids=(first.id, second.id)
    )
    assert first.mutex == [second.id]
    assert second.mutex == [first.id]


def test_remove_mutex_pushes_selected_and_partner_ids():
    selected = Focus(id=13)
    partner = Focus(id=14)
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
    focus = Focus(id=15)
    focus.effects = [{"type": "add_ideas", "fields": {}}]
    app = AppFake([focus])
    app.selected = focus

    app_module.App._rm_effect(_as_app(app), 0)

    app._push_undo.assert_called_once_with("remove effect", touched_ids=(focus.id,))
    assert focus.effects == []


def test_rm_effect_round_trip_through_real_undo_stack():
    focus = Focus(id=16)
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
    focus = Focus(id=17)
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
    focus = Focus(id=18)
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
    focus = Focus(id=19)
    focus.offsets = [{"x": 1, "y": 2, "trigger": ""}, {"x": 3, "y": 4, "trigger": ""}]
    app = AppFake([focus])
    app.selected = focus

    app_module.App._del_offset(_as_app(app), 0)

    app._push_undo.assert_called_once_with("remove offset", touched_ids=(focus.id,))
    assert focus.offsets == [{"x": 3, "y": 4, "trigger": ""}]


def test_del_offset_round_trip_through_real_undo_stack():
    focus = Focus(id=20)
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
    focus = Focus(id=21)
    app = AppFake([focus])
    app.zoom = 1.0
    app.mutex_mode = False

    app._foc_pr(focus.id, SimpleNamespace(x=0, y=0, state=0))
    app._foc_mv(focus.id, SimpleNamespace(x=3, y=3))

    app._push_undo.assert_not_called()
    assert (focus.x, focus.y) == (0, 0)


def test_drag_into_occupied_cell_does_not_push_undo():
    focus = Focus(id=22)
    occupied = Focus(id=23, x=1, y=1)
    app = AppFake([focus, occupied])
    app.zoom = 1.0
    app.mutex_mode = False

    app._foc_pr(focus.id, SimpleNamespace(x=0, y=0, state=0))
    app._foc_mv(focus.id, SimpleNamespace(x=XGRID, y=YGRID))

    app._push_undo.assert_not_called()
    assert (focus.x, focus.y) == (0, 0)


def test_drag_event_for_other_focus_does_not_push_undo():
    focus = Focus(id=24)
    other = Focus(id=25, x=1, y=1)
    app = AppFake([focus, other])
    app.zoom = 1.0
    app.mutex_mode = False

    app._foc_pr(focus.id, SimpleNamespace(x=0, y=0, state=0))
    app._foc_mv(other.id, SimpleNamespace(x=XGRID, y=YGRID))

    app._push_undo.assert_not_called()
    assert (focus.x, focus.y) == (0, 0)


def test_drag_in_mutex_mode_does_not_push_undo():
    focus = Focus(id=26)
    app = AppFake([focus])
    app.zoom = 1.0
    app.mutex_mode = False

    app._foc_pr(focus.id, SimpleNamespace(x=0, y=0, state=0))
    app.mutex_mode = True
    app._foc_mv(focus.id, SimpleNamespace(x=XGRID, y=YGRID))

    app._push_undo.assert_not_called()
    assert (focus.x, focus.y) == (0, 0)


def test_drag_move_pushes_once_with_moved_focus_id():
    focus = Focus(id=27)
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
    focus = Focus(id=28)
    other = Focus(id=29, x=3, y=4)
    app = AppFake([focus, other])
    app.zoom = 1.0
    app.mutex_mode = False

    app._foc_pr(focus.id, SimpleNamespace(x=0, y=0, state=0))

    assert app._drag["occupied"] == {(3, 4)}


def test_rmb_on_occupied_cell_does_not_place(monkeypatch: pytest.MonkeyPatch):
    focus = Focus(id=30, x=2, y=3)
    app = AppFake([focus])
    app._new_focus_at = Mock()
    monkeypatch.setattr(app, "c2w", lambda _x, _y: (2, 3))
    app.cv.find_overlapping.return_value = ()

    app._rmb(SimpleNamespace(x=10, y=10))

    app._new_focus_at.assert_not_called()


def test_rmb_on_free_cell_places(monkeypatch: pytest.MonkeyPatch):
    focus = Focus(id=31, x=2, y=3)
    app = AppFake([focus])
    app._new_focus_at = Mock()
    monkeypatch.setattr(app, "c2w", lambda _x, _y: (5, 5))
    app.cv.find_overlapping.return_value = ()

    app._rmb(SimpleNamespace(x=10, y=10))

    app._new_focus_at.assert_called_once_with(5, 5)


def _code_app(focus: Focus) -> AppFake:
    app = AppFake([focus])
    cast(Any, app).selected = focus
    app.zoom = 1.0
    app.offset = [0, 0]
    app._undo_stack = UndoStack()
    return app


def _code_of(app: AppFake, focus: Focus) -> str:
    return render_focus_block(
        focus, focus_lookup=app.focuses, focus_name_lookup=app.focuses.by_name
    )


def _normalized_focus() -> Focus:
    """A focus that already took one Code-tab round trip, which adds fields."""
    focus = Focus(id=1)
    doc = FocusDocument([focus])
    code = render_focus_block(focus, focus_lookup=doc, focus_name_lookup=doc.by_name)
    apply_focus_code(focus, code, focus_lookup=doc)
    return focus


@pytest.fixture
def reported(monkeypatch):
    errors: list[object] = []
    monkeypatch.setattr(
        app_module, "report_error", lambda message, ex, **_kw: errors.append(ex)
    )
    return errors


def test_apply_focus_code_pushes_one_entry_and_undo_restores_the_focus():
    focus = _normalized_focus()
    app = _code_app(focus)
    edited = _code_of(app, focus).replace("cost = 10", "cost = 12")

    assert app_module.App._apply_focus_code(_as_app(app), focus, edited) is True

    assert focus.cost == 12
    assert len(app._undo_stack) == 1
    assert app._undo_stack._stack[-1][0] == "edit focus code"

    app_module.App._undo(_as_app(app))

    assert app.focuses[focus.id].cost == 10


def test_apply_focus_code_without_changes_pushes_nothing_and_keeps_redo():
    focus = _normalized_focus()
    app = _code_app(focus)
    app._undo_stack.push("edit", app.focuses, (focus.id,))
    focus.desc = "later"
    app_module.App._undo(_as_app(app))
    current = app.focuses[focus.id]

    ok = app_module.App._apply_focus_code(_as_app(app), current, _code_of(app, current))

    assert ok is True
    assert len(app._undo_stack) == 0
    app_module.App._redo(_as_app(app))
    assert app.focuses[focus.id].desc == "later"


def test_apply_focus_code_unnormalized_first_round_trip_keeps_redo():
    focus = Focus(id=1)
    app = _code_app(focus)
    app._undo_stack.push("edit", app.focuses, (focus.id,))
    focus.desc = "later"
    app_module.App._undo(_as_app(app))
    current = app.focuses[focus.id]
    before = current.to_dict()

    ok = app_module.App._apply_focus_code(_as_app(app), current, _code_of(app, current))

    assert ok is True
    assert current.to_dict() == before
    assert len(app._undo_stack) == 0
    app_module.App._redo(_as_app(app))
    assert app.focuses[focus.id].desc == "later"


def test_apply_focus_code_parse_failure_leaves_no_entry_and_keeps_redo(reported):
    focus = _normalized_focus()
    app = _code_app(focus)
    app._undo_stack.push("edit", app.focuses, (focus.id,))
    focus.desc = "later"
    app_module.App._undo(_as_app(app))
    before = app.focuses[focus.id].to_dict()

    ok = app_module.App._apply_focus_code(
        _as_app(app), app.focuses[focus.id], "not a focus block"
    )

    assert ok is False
    assert len(reported) == 1
    assert len(app._undo_stack) == 0
    assert app.focuses[focus.id].to_dict() == before
    app_module.App._redo(_as_app(app))
    assert app.focuses[focus.id].desc == "later"


def test_apply_focus_code_keeps_the_entry_when_a_later_step_fails(reported):
    focus = _normalized_focus()
    app = _code_app(focus)
    app._invalidate_focus_list_structure = Mock(side_effect=RuntimeError("boom"))
    edited = _code_of(app, focus).replace("cost = 10", "cost = 12")

    assert app_module.App._apply_focus_code(_as_app(app), focus, edited) is False

    assert focus.cost == 12
    assert len(app._undo_stack) == 1
    app._undo_stack.undo(app.focuses, Focus.from_dict)
    assert app.focuses[focus.id].cost == 10


def test_add_focus_picks_first_free_cell_without_repairing_indexes():
    app = AppFake([Focus(id=36, x=0, y=0), Focus(id=37, x=2, y=0)])
    app._new_focus_at = Mock()
    app.focuses.validate_indexes = Mock()  # type: ignore[method-assign]
    app.focuses.rebuild_indexes = Mock()  # type: ignore[method-assign]

    app_module.App._add_focus(_as_app(app))

    app._new_focus_at.assert_called_once_with(4, 0)
    app.focuses.validate_indexes.assert_not_called()
    app.focuses.rebuild_indexes.assert_not_called()


def test_new_focus_at_keeps_indexes_exact_without_a_rebuild():
    existing = Focus(id=32, x=0, y=0)
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


class _TextFake:
    def __init__(self, text: str) -> None:
        self.text = text

    def get(self, _start: str, _end: str) -> str:
        return self.text


class _TraceVar:
    """A StringVar stand-in whose set() fires the write trace, as Tk does."""

    def __init__(self, value: str, on_write: Callable[[], None]) -> None:
        self._value = value
        self._on_write = on_write

    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = value
        self._on_write()


def _live_undo_app(focus: Focus, *others: Focus) -> AppFake:
    """A host that selects ``focus`` and pushes onto a real UndoStack."""
    app = AppFake([focus, *others])
    cast(Any, app).selected = focus
    app._undo_stack = UndoStack()
    app._push_undo = lambda *args, **kwargs: app_module.App._push_undo(
        _as_app(app), *args, **kwargs
    )
    return app


def _raw_focus(raw: str) -> Focus:
    focus = Focus(id=40)
    focus.effects = [{"type": "_raw_block", "fields": {"raw": raw}}]
    return focus


def _fields_of(app: AppFake, focus_id: int) -> dict[str, str]:
    return cast(dict[str, str], app.focuses[focus_id].effects[0]["fields"])


def _raw_of(app: AppFake) -> str:
    return _fields_of(app, 40)["raw"]


def test_raw_edit_pushes_before_writing_and_undo_restores_the_imported_text():
    imported = "add_political_power = 5  \n"
    app = _live_undo_app(_raw_focus(imported))
    revision = app.focuses.content_revision

    app._live_raw_block(0, _TextFake("add_political_power = 50\n"))

    assert _raw_of(app) == "add_political_power = 50"
    assert app.focuses.content_revision > revision
    assert len(app._undo_stack) == 1
    app_module.App._undo(_as_app(app))
    assert _raw_of(app) == imported


def test_raw_edit_typing_coalesces_into_one_entry():
    imported = "a = 1\n"
    app = _live_undo_app(_raw_focus(imported))

    for text in ("a = 1x", "a = 1xy", "a = 1xyz"):
        app._live_raw_block(0, _TextFake(text))

    assert _raw_of(app) == "a = 1xyz"
    assert len(app._undo_stack) == 1
    app_module.App._undo(_as_app(app))
    assert _raw_of(app) == imported


def test_raw_edit_bare_key_release_pushes_nothing_and_keeps_redo():
    app = _live_undo_app(_raw_focus("a = 1  \n"))
    app._live_raw_block(0, _TextFake("a = 2"))
    app_module.App._undo(_as_app(app))
    imported = _raw_of(app)

    app._live_raw_block(0, _TextFake(imported))

    assert imported == "a = 1  \n"
    assert _raw_of(app) == imported
    assert len(app._undo_stack) == 0
    app_module.App._redo(_as_app(app))
    assert _raw_of(app) == "a = 2"


def test_rename_effect_key_pushes_and_undo_restores_the_key():
    focus = Focus(id=41)
    focus.effects = [{"type": "mine", "fields": {"amount": "1", "tag": "GER"}}]
    app = _live_undo_app(focus)
    app._effects_sig = "built"
    revision = app.focuses.content_revision

    app._rename_effect_key(0, "amount", "value")

    assert _fields_of(app, 41) == {"value": "1", "tag": "GER"}
    assert app.focuses.content_revision > revision
    assert app._effects_sig is None
    assert len(app._undo_stack) == 1
    app_module.App._undo(_as_app(app))
    assert _fields_of(app, 41) == {"amount": "1", "tag": "GER"}


def test_rename_effect_key_onto_an_existing_key_is_undoable():
    focus = Focus(id=41)
    focus.effects = [{"type": "mine", "fields": {"amount": "1", "tag": "GER"}}]
    app = _live_undo_app(focus)

    app._rename_effect_key(0, "amount", "tag")

    assert _fields_of(app, 41) == {"tag": "1"}
    app_module.App._undo(_as_app(app))
    assert _fields_of(app, 41) == {"amount": "1", "tag": "GER"}


@pytest.mark.parametrize(
    ("old", "new"), [("amount", "amount"), ("missing", "value")], ids=["same", "gone"]
)
def test_rename_effect_key_without_a_change_pushes_nothing(old, new):
    focus = Focus(id=41)
    focus.effects = [{"type": "mine", "fields": {"amount": "1", "tag": "GER"}}]
    app = _live_undo_app(focus)
    app._effects_sig = "built"
    revision = app.focuses.content_revision

    app._rename_effect_key(0, old, new)

    assert list(_fields_of(app, 41).items()) == [("amount", "1"), ("tag", "GER")]
    assert app.focuses.content_revision == revision
    assert app._effects_sig == "built"
    assert len(app._undo_stack) == 0


@pytest.mark.parametrize(
    ("effect", "added"),
    [
        ({"type": "mine", "fields": {"a": "1"}}, {"a": "1", "key1": "value"}),
        ({"type": "mine"}, {"key0": "value"}),
    ],
    ids=["with-fields", "no-fields"],
)
def test_add_raw_field_pushes_and_undo_removes_it(effect, added):
    focus = Focus(id=42)
    focus.effects = [effect]
    before = copy.deepcopy(effect)
    app = _live_undo_app(focus)
    revision = app.focuses.content_revision

    app._add_raw_effect_field(0)

    assert _fields_of(app, 42) == added
    assert app.focuses.content_revision > revision
    assert len(app._undo_stack) == 1
    cast(Any, app)._refresh_effects.assert_called_once_with()
    app_module.App._undo(_as_app(app))
    assert app.focuses[42].effects == [before]


@pytest.mark.parametrize(
    ("selected", "index"), [(False, 0), (True, 3)], ids=["no-selection", "stale-index"]
)
def test_raw_effect_edits_ignore_a_missing_selection_or_stale_index(selected, index):
    focus = _raw_focus("a = 1")
    app = _live_undo_app(focus)
    if not selected:
        cast(Any, app).selected = None

    app._live_raw_block(index, _TextFake("b"))
    app._rename_effect_key(index, "raw", "other")
    app._add_raw_effect_field(index)

    assert focus.effects == [{"type": "_raw_block", "fields": {"raw": "a = 1"}}]
    assert len(app._undo_stack) == 0


def _icon_app(focus: Focus, *others: Focus) -> tuple[AppFake, _TraceVar]:
    """A host wired like the sidebar: the icon var's trace calls the handler."""
    app = _live_undo_app(focus, *others)
    host = cast(Any, app)
    host._redraw_now = Mock()
    icon_var = _TraceVar(
        focus.icon, lambda: app_module.App._on_icon_change(_as_app(app))
    )
    host._fv_icon = icon_var
    app._populate = Mock(side_effect=lambda f: icon_var.set(f.icon))
    return app, icon_var


def _icon_focus(focus_id: int, icon: str) -> Focus:
    focus = Focus(id=focus_id)
    focus.icon = icon
    return focus


def test_icon_change_pushes_before_writing_and_round_trips_through_undo_redo():
    focus = _icon_focus(43, "A")
    app, icon_var = _icon_app(focus)
    revision = app.focuses.content_revision

    icon_var.set("B")

    assert focus.icon == "B"
    assert app.focuses.content_revision > revision
    assert len(app._undo_stack) == 1
    cast(Any, app)._redraw_now.assert_called_once_with()
    app_module.App._undo(_as_app(app))
    assert app.focuses[43].icon == "A"
    assert len(app._undo_stack) == 0
    app_module.App._redo(_as_app(app))
    assert app.focuses[43].icon == "B"


def test_icon_repick_of_the_current_icon_pushes_nothing():
    focus = _icon_focus(43, "A")
    app, icon_var = _icon_app(focus)
    revision = app.focuses.content_revision

    icon_var.set("A")

    assert focus.icon == "A"
    assert app.focuses.content_revision == revision
    assert len(app._undo_stack) == 0
    cast(Any, app)._redraw_now.assert_not_called()


def test_icon_change_without_a_selected_focus_writes_nothing():
    focus = _icon_focus(43, "A")
    app, icon_var = _icon_app(focus)
    cast(Any, app).selected = None

    icon_var.set("B")

    assert focus.icon == "A"
    assert len(app._undo_stack) == 0


def test_select_populates_the_icon_without_pushing_or_writing_the_previous_focus():
    first = _icon_focus(44, "A")
    second = _icon_focus(45, "B")
    app, icon_var = _icon_app(first, second)
    host = cast(Any, app)
    host._autosave = Mock()
    host._show_form = Mock()
    host._update_focus_list_selection = Mock()

    app_module.App._select(_as_app(app), second)

    assert icon_var.get() == "B"
    assert (first.icon, second.icon) == ("A", "B")
    assert len(app._undo_stack) == 0
