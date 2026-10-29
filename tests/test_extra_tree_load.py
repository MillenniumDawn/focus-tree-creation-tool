"""Single extra-tree load uses the same run_bg shape as _import_txt."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import hoi4_content_maker as m
import hoi4cm.focus_tree.parse as parse_module
from hoi4cm.core.undo import UndoStack
from hoi4cm.editor.extra_tree_undo import ExtraTreeUndoHistory
from hoi4cm.focus_tree.parse import (
    EmptyFocusTreeError,
    FocusTreeParseBudgetExceeded,
)
from hoi4cm.models import Focus, FocusDocument


def _shell():
    app = SimpleNamespace(
        _extra_trees=[],
        _shared_focuses=[],
        _joint_focuses=[],
        _undo_stack=UndoStack(),
        _tree_undo_history=ExtraTreeUndoHistory(),
        focuses=FocusDocument(),
        _tree_country_tag="",
        _invalidate_tree_badges=Mock(),
        _refresh_tree_meta_panel=Mock(),
        _refresh_loaded_trees_panel=Mock(),
        _redraw=Mock(),
        _invalidate_focus_list_structure=Mock(),
        _fit_all=Mock(),
        _hide_form=Mock(),
        _hint=Mock(),
        cv=Mock(),
        selected=None,
    )
    app._install_extra_tree = m.App._install_extra_tree.__get__(app)
    app._push_undo = m.App._push_undo.__get__(app)
    app._snapshot_extra_tree_state = m.App._snapshot_extra_tree_state.__get__(app)
    app._restore_extra_tree_state = m.App._restore_extra_tree_state.__get__(app)
    app._undo = m.App._undo.__get__(app)
    app._redo = m.App._redo.__get__(app)
    app._load_extra_tree = m.App._load_extra_tree.__get__(app)
    return app


def _patch_run_bg(monkeypatch, calls: list[dict[str, Any]]):
    def run_background(_app, work, on_done, on_error=None, **kwargs):
        calls.append(kwargs)
        try:
            on_done(work())
        except (EmptyFocusTreeError, FocusTreeParseBudgetExceeded) as exc:
            if on_error is not None:
                on_error(exc)
            else:
                raise

    monkeypatch.setattr(m, "run_bg", run_background)


def test_load_extra_tree_parses_off_the_tk_thread(tmp_path, monkeypatch):
    tree = tmp_path / "shared.txt"
    tree.write_text(
        "focus_tree = {\n"
        "\tid = TST_shared\n"
        "\tfocus = {\n"
        "\t\tid = TST_alpha\n"
        "\t\tx = 0\n"
        "\t\ty = 0\n"
        "\t\tcost = 5\n"
        "\t}\n"
        "}\n",
        encoding="utf-8",
    )
    calls: list[dict[str, Any]] = []
    _patch_run_bg(monkeypatch, calls)
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_k: str(tree))
    monkeypatch.setattr(m.messagebox, "showinfo", lambda *_a, **_k: None)
    monkeypatch.setattr(
        m,
        "progress_modal",
        lambda *_a, **_k: SimpleNamespace(close=lambda: None),
    )
    monkeypatch.setattr(m.MOD, "loaded", False)
    monkeypatch.setattr(m.MOD, "root", None)
    app = _shell()

    m.App._load_extra_tree(cast(m.App, app), "shared")

    assert calls and calls[0]["scope"] == "document"
    assert len(app.focuses) == 1
    assert next(iter(app.focuses.values())).name == "TST_alpha"
    assert app._extra_trees[0]["tree_id"] == "TST_shared"
    assert app._shared_focuses == ["TST_shared"]
    app._fit_all.assert_called_once()

    app._undo()

    assert not app.focuses
    assert app._extra_trees == []
    assert app._shared_focuses == []

    app._redo()

    assert len(app.focuses) == 1
    assert app._extra_trees[0]["tree_id"] == "TST_shared"
    assert app._shared_focuses == ["TST_shared"]

    app._undo()
    m.App._load_extra_tree(cast(m.App, app), "shared")

    assert len(app.focuses) == 1
    assert app._extra_trees[0]["tree_id"] == "TST_shared"


def test_later_extra_tree_adoption_reconciles_live_indexes_and_undo_redo(
    tmp_path, monkeypatch
):
    target = tmp_path / "target.txt"
    target.write_text(
        "focus_tree = { id = TST_target focus = { id = TARGET x = 5 y = 7 } }",
        encoding="utf-8",
    )
    dependent = Focus(id=41, x=2, y=3)
    dependent.name = "DEPENDENT"
    dependent.tree_idx = 1
    dependent.relative_position_id = "TARGET"
    dependent._raw_gx = dependent._build_gx = 2
    dependent._raw_gy = dependent._build_gy = 3
    dependent._rel_dx = 2
    dependent._rel_dy = 3
    dependent._relative_pending = True
    dependent.prereqs = [[]]
    dependent._unresolved_prereqs = [["TARGET"]]
    dependent._unresolved_mutex = ["TARGET"]
    app = _shell()
    app.focuses.extend([dependent])
    calls: list[dict[str, Any]] = []
    _patch_run_bg(monkeypatch, calls)
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_k: str(target))
    monkeypatch.setattr(m.messagebox, "showinfo", lambda *_a, **_k: None)
    monkeypatch.setattr(
        m,
        "progress_modal",
        lambda *_a, **_k: SimpleNamespace(close=lambda: None),
    )
    monkeypatch.setattr(m.MOD, "loaded", False)
    monkeypatch.setattr(m.MOD, "root", None)

    m.App._load_extra_tree(cast(m.App, app), "shared")

    target_focus = app.focuses.find_by_name("TARGET")
    assert target_focus is not None
    live_dependent = app.focuses[dependent.id]
    assert (live_dependent.x, live_dependent.y) == (7, 10)
    assert live_dependent.prereqs == [[target_focus.id]]
    assert live_dependent.mutex == [target_focus.id]
    assert live_dependent._unresolved_prereqs == [[]]
    assert live_dependent._unresolved_mutex == []
    assert app.focuses.occupied_positions[(7, 10)] == {dependent.id}
    assert app.focuses.reverse_prerequisites == {target_focus.id: {dependent.id}}
    assert app.focuses.reverse_mutex == {target_focus.id: {dependent.id}}
    assert app.focuses.validate_indexes()

    app._undo()

    restored = app.focuses[dependent.id]
    assert (restored.x, restored.y) == (2, 3)
    assert restored.prereqs == [[]]
    assert restored._unresolved_prereqs == [["TARGET"]]
    assert restored._unresolved_mutex == ["TARGET"]
    assert app.focuses.occupied_positions[(2, 3)] == {dependent.id}
    assert app.focuses.reverse_prerequisites == {}
    assert app.focuses.reverse_mutex == {}
    assert app.focuses.validate_indexes()

    app._redo()

    redone = app.focuses[dependent.id]
    assert (redone.x, redone.y) == (7, 10)
    assert redone.prereqs == [[target_focus.id]]
    assert redone.mutex == [target_focus.id]
    assert app.focuses.validate_indexes()


def test_load_extra_tree_after_undo_does_not_reuse_redo_id(tmp_path, monkeypatch):
    tree = tmp_path / "shared.txt"
    tree.write_text(
        "focus_tree = {\n"
        "\tid = TST_shared\n"
        "\tfocus = {\n"
        "\t\tid = EXTRA_one\n"
        "\t\tx = 0\n"
        "\t\ty = 0\n"
        "\t}\n"
        "}\n",
        encoding="utf-8",
    )
    calls: list[dict[str, Any]] = []
    _patch_run_bg(monkeypatch, calls)
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_k: str(tree))
    monkeypatch.setattr(m.messagebox, "showinfo", lambda *_a, **_k: None)
    monkeypatch.setattr(
        m,
        "progress_modal",
        lambda *_a, **_k: SimpleNamespace(close=lambda: None),
    )
    monkeypatch.setattr(m.MOD, "loaded", False)
    monkeypatch.setattr(m.MOD, "root", None)
    app = _shell()
    app.focuses.add(Focus(id=1))
    app._undo_stack = UndoStack()
    app._undo_stack.push("add focus", app.focuses, touched_ids=())
    added = app.focuses.new_focus()
    added.name = "MAIN_added"
    app.focuses.add(added)

    assert added.id == 2
    assert app._undo_stack.undo(app.focuses, Focus.from_dict) is not None
    assert list(app.focuses) == [1]
    assert app.focuses.last_allocated_id == 2

    m.App._load_extra_tree(cast(m.App, app), "shared")

    imported = next(
        focus for focus in app.focuses.values() if focus.name == "EXTRA_one"
    )
    assert imported.id == 3
    # An undoable load starts a new branch, but must still reserve the old ID.
    assert app._undo_stack.redo(app.focuses, Focus.from_dict) is None
    app._undo()
    assert list(app.focuses) == [1]
    assert app._extra_trees == []
    app._redo()
    assert 2 not in app.focuses
    assert app.focuses[3].name == "EXTRA_one"
    assert len(app.focuses) == 2
    assert app.focuses.new_focus().id == 4


def test_import_tree_rejects_oversized_file(tmp_path, monkeypatch):
    tree = tmp_path / "oversized.txt"
    with tree.open("wb") as stream:
        stream.truncate(32 * 1024 * 1024 + 1)
    errors = []
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_k: str(tree))
    monkeypatch.setattr(m, "report_error", lambda *args, **_k: errors.append(args))
    monkeypatch.setattr(m.MOD, "loaded", False)
    monkeypatch.setattr(m.MOD, "root", None)
    app = SimpleNamespace(_confirm_discard=Mock(return_value=True))

    m.App._import_txt(cast(m.App, app))

    assert errors


def test_load_extra_tree_rejects_oversized_file(tmp_path, monkeypatch):
    tree = tmp_path / "oversized.txt"
    with tree.open("wb") as stream:
        stream.truncate(32 * 1024 * 1024 + 1)
    errors = []
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_k: str(tree))
    monkeypatch.setattr(m, "report_error", lambda *args, **_k: errors.append(args))
    monkeypatch.setattr(m.MOD, "loaded", False)
    monkeypatch.setattr(m.MOD, "root", None)
    app = _shell()

    m.App._load_extra_tree(cast(m.App, app), "joint")

    assert errors


def test_load_extra_tree_budget_failure_warns(tmp_path, monkeypatch):
    tree = tmp_path / "over_budget.txt"
    tree.write_text(
        "focus_tree = {\n\tid = over_budget\n\tfocus = { id = TST_focus }\n}\n",
        encoding="utf-8",
    )
    warnings: list[tuple] = []
    calls: list[dict[str, Any]] = []
    _patch_run_bg(monkeypatch, calls)
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_k: str(tree))
    monkeypatch.setattr(
        m.messagebox, "showwarning", lambda *args, **_k: warnings.append(args)
    )
    monkeypatch.setattr(
        m,
        "progress_modal",
        lambda *_a, **_k: SimpleNamespace(close=lambda: None),
    )
    monkeypatch.setattr(m.MOD, "loaded", False)
    monkeypatch.setattr(m.MOD, "root", None)
    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCANS", 0)
    app = _shell()

    m.App._load_extra_tree(cast(m.App, app), "shared")

    assert calls and calls[0]["scope"] == "document"
    assert warnings and "parse budget exhausted" in warnings[0][1]
    assert not app.focuses
    assert not app._extra_trees


def test_load_extra_tree_empty_file_warns(tmp_path, monkeypatch):
    tree = tmp_path / "empty.txt"
    tree.write_text("focus_tree = { id = empty }\n", encoding="utf-8")
    warnings: list[tuple] = []
    calls: list[dict[str, Any]] = []
    _patch_run_bg(monkeypatch, calls)
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_k: str(tree))
    monkeypatch.setattr(
        m.messagebox, "showwarning", lambda *args, **_k: warnings.append(args)
    )
    monkeypatch.setattr(
        m,
        "progress_modal",
        lambda *_a, **_k: SimpleNamespace(close=lambda: None),
    )
    monkeypatch.setattr(m.MOD, "loaded", False)
    monkeypatch.setattr(m.MOD, "root", None)
    app = _shell()

    m.App._load_extra_tree(cast(m.App, app), "shared")

    assert calls and calls[0]["scope"] == "document"
    assert warnings
    assert not app.focuses
    assert not app._extra_trees
