"""Regression tests for guarded .txt imports (issue #169)."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import hoi4_content_maker as m
from hoi4cm.core.undo import UndoStack
from hoi4cm.models import Focus, FocusDocument


class _Var:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value


def test_import_txt_cancel_stops_before_file_dialog(monkeypatch):
    app = SimpleNamespace(_confirm_discard=Mock(return_value=False))
    askopenfilename = Mock(side_effect=AssertionError("file dialog should not open"))
    monkeypatch.setattr(m.filedialog, "askopenfilename", askopenfilename)

    m.App._import_txt(cast(m.App, app))

    app._confirm_discard.assert_called_once_with(action="importing")
    askopenfilename.assert_not_called()


def test_import_txt_pushes_undo_before_replacing_document(monkeypatch, tmp_path):
    source = tmp_path / "tree.txt"
    source.write_text("focus_tree = { id = imported }")
    old_focus = Focus()
    old_focus.name = "existing_focus"
    new_focus = Focus()
    new_focus.name = "imported_focus"
    app = SimpleNamespace(
        _confirm_discard=Mock(return_value=True),
        _begin_document_generation=Mock(),
        _import_generation=0,
        focuses=FocusDocument([old_focus]),
        _undo_stack=UndoStack(),
        _extra_trees=[{"tree_id": "existing_shared"}],
        cv=Mock(),
        _reset_canvas_bounds=Mock(),
        selected=None,
        _lines=set(),
        _grid_item=None,
        _grid_key=None,
        _grid_img=None,
        _invalidate_tree_badges=Mock(),
        _refresh_loaded_trees_panel=Mock(),
        _hide_form=Mock(),
        _tree_id=_Var("existing_tree"),
        _update_title=Mock(),
        _cfp_x=None,
        _cfp_y=None,
        _cfp_x_var=_Var(),
        _cfp_y_var=_Var(),
        _tree_country_tag="",
        _tree_country_raw="",
        _tree_extras={},
        _tree_had_wrapper=True,
        _shared_focuses=[],
        _joint_focuses=[],
        _default_focus_prefix="",
        _detect_and_apply_tag=Mock(),
        _refresh_tree_meta_panel=Mock(),
        _redraw=Mock(),
        _invalidate_focus_list_structure=Mock(),
        _fit_all=Mock(),
    )
    app._push_undo = lambda label="action", touched_ids=None: m.App._push_undo(
        cast(m.App, app), label, touched_ids
    )
    parsed = SimpleNamespace(
        tree_id="imported_tree",
        cfp_x=None,
        cfp_y=None,
        country_raw="",
        tree_extras={},
        had_wrapper=True,
        shared_refs=[],
        joint_refs=[],
        country_tag="",
    )
    calls: list[dict[str, Any]] = []

    def run_background(_app, work, on_done, **kwargs):
        calls.append(kwargs)
        on_done(work())

    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_kwargs: str(source))
    monkeypatch.setattr(m, "parse_focus_tree", lambda _raw, _path: parsed)
    monkeypatch.setattr(m, "build_focuses", lambda _parsed, _tree_idx: [new_focus])
    monkeypatch.setattr(m, "run_bg", run_background)
    monkeypatch.setattr(
        m,
        "progress_modal",
        lambda *_args, **_kwargs: SimpleNamespace(close=Mock()),
    )
    monkeypatch.setattr(m.messagebox, "showinfo", Mock())
    monkeypatch.setattr(m.MOD, "loaded", False)
    monkeypatch.setattr(m.MOD, "root", None)
    monkeypatch.setattr(m.MOD, "edit_focus_file", "", raising=False)

    m.App._import_txt(cast(m.App, app))

    assert calls and calls[0]["scope"] == "document"
    assert list(app.focuses.values()) == [new_focus]
    assert app._extra_trees == []

    result = app._undo_stack.undo(app.focuses, Focus.from_dict)

    assert result is not None
    assert result[0] == "import tree"
    assert list(app.focuses.values())[0].name == "existing_focus"
    assert list(app.focuses.values())[0].id == old_focus.id
