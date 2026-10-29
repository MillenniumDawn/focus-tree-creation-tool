"""Pending contextual drafts survive selection, close, save and undo boundaries."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from builders import make_focus

import hoi4_content_maker as main
from hoi4cm.core.undo import UndoStack
from hoi4cm.models import Focus, FocusDocument, FocusSidebarValues, apply_sidebar_values
from hoi4cm.ui.focus_editor import flush_pending_editor, reveal_search_result
from hoi4cm.ui.focus_list import FocusListItem


def host(**changes):
    focus = make_focus()
    focus.ai_will_do_raw = "base = 1"
    values = FocusSidebarValues(
        **{key: getattr(focus, key) for key in FocusSidebarValues.__dataclass_fields__}
    )
    values = replace(values, offsets=tuple(focus.offsets), **changes)
    document = FocusDocument([focus])
    undo = UndoStack()

    def commit():
        if changes:
            undo.push("edit focus", document, (focus.id,))
            apply_sidebar_values(focus, values)
            document.move(focus.id, values.x, values.y)

    app = SimpleNamespace(
        selected=focus,
        focuses=document,
        _read_sidebar_values=lambda: values,
        _autosave=Mock(side_effect=commit),
        _code_edit_mode=[False],
        _fv_cost=Mock(),
        _fv_x=Mock(),
        _fv_y=Mock(),
        _update_statusbar=Mock(),
        _code_edit_btn=Mock(),
        _undo_stack=undo,
    )
    app._fv_cost.get.return_value = str(values.cost)
    app._fv_x.get.return_value = str(values.x)
    app._fv_y.get.return_value = str(values.y)
    return app


def test_flush_commits_non_geometry_fields_with_one_undo():
    app = host(cost=35, desc="Keep this draft")
    revision = app.focuses.revision
    assert flush_pending_editor(app)
    assert app.selected.cost == 35
    assert app.selected.desc == "Keep this draft"
    assert app.focuses.revision > revision
    assert len(app._undo_stack) == 1
    result = app._undo_stack.undo(app.focuses, Focus.from_dict)
    assert result is not None
    assert app.focuses[app.selected.id].cost != 35


def overlapping_host(**changes):
    """A host whose selected focus shares its cell, as an imported tree can."""
    app = host(**changes)
    app.focuses.add(make_focus(id=2))
    return app


def test_unedited_focus_sharing_a_cell_flushes_without_warning(monkeypatch):
    app = overlapping_host()
    warning = Mock()
    monkeypatch.setattr("hoi4cm.ui.focus_editor.messagebox.showwarning", warning)
    assert flush_pending_editor(app)
    warning.assert_not_called()
    assert len(app._undo_stack) == 0


def test_moving_onto_an_occupied_cell_is_still_refused(monkeypatch):
    app = host(x=5)
    app.focuses.add(make_focus(id=2, x=5, y=0))
    warning = Mock()
    monkeypatch.setattr("hoi4cm.ui.focus_editor.messagebox.showwarning", warning)
    assert not flush_pending_editor(app)
    warning.assert_called_once()
    assert app.selected.x == 0


def test_overlapping_focus_does_not_block_select_save_or_close(monkeypatch):
    app = overlapping_host()
    other = app.focuses[2]

    def guard():
        return flush_pending_editor(app)

    app._focus_editor = SimpleNamespace(flush=guard, close=guard)
    for name in ("_redraw", "_show_form", "_populate", "_update_focus_list_selection"):
        setattr(app, name, Mock())

    assert main.App._select(app, other) is True
    assert app.selected is other

    chosen = Mock(return_value="")
    monkeypatch.setattr(main, "choose_project_save_path", chosen)
    assert main.App._save(app) is False
    chosen.assert_called_once()

    app._is_dirty = lambda: False
    app._lifecycle = Mock(begin_close=Mock(return_value=False))
    main.App._on_app_close(app)
    app._lifecycle.begin_close.assert_called_once()


def test_untouched_flush_does_not_create_undo_or_revision():
    app = host()
    revision = app.focuses.revision
    assert flush_pending_editor(app)
    assert len(app._undo_stack) == 0
    assert app.focuses.revision == revision


def test_invalid_code_prevents_leaving_and_preserves_draft():
    app = host()
    app._code_edit_mode[0] = True
    assert not flush_pending_editor(app)
    app._code_edit_btn.invoke.assert_called_once()
    assert app._code_edit_mode[0]


def test_timer_flush_does_not_lock_code_or_raise_typing_dialog(monkeypatch):
    app = host(desc="timer recovery")
    app._code_edit_mode[0] = True
    assert flush_pending_editor(app, autosave=True)
    assert app.selected.desc == "timer recovery"
    app._code_edit_btn.invoke.assert_not_called()
    warning = Mock()
    monkeypatch.setattr("hoi4cm.ui.focus_editor.messagebox.showwarning", warning)
    app._fv_cost.get.return_value = "-"
    assert not flush_pending_editor(app, autosave=True)
    warning.assert_not_called()


def test_selection_guard_keeps_invalid_draft_on_original_focus():
    app = host()
    original = app.selected
    app._focus_editor = SimpleNamespace(close=lambda: False)
    assert main.App._select(app, Focus(id=999)) is False
    assert app.selected is original


def test_reselecting_same_focus_never_repopulates_widgets():
    app = host()
    app._focus_editor = Mock()
    app._update_focus_list_selection = Mock()
    assert main.App._select(app, app.selected)
    app._focus_editor.close.assert_not_called()


def test_save_cancelled_when_editor_has_invalid_code():
    app = host()
    app._focus_editor = SimpleNamespace(flush=lambda: False)
    assert main.App._save(app) is False


def test_search_enter_reveals_first_matching_focus():
    app = SimpleNamespace(
        _focus_list_items=(
            FocusListItem(1, "AAA_focus"),
            FocusListItem(2, "BBB_focus"),
        ),
        _lp_search_var=Mock(),
        _select_focus_from_list=Mock(),
    )
    app._lp_search_var.get.return_value = "bbb"
    reveal_search_result(app)
    app._select_focus_from_list.assert_called_once_with(2)
