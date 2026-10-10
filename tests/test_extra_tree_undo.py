"""Undo coverage for loading and unloading extra focus trees."""

from threading import Event
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import hoi4_content_maker as m
from hoi4cm.core.undo import UndoStack
from hoi4cm.editor.extra_tree_undo import ExtraTreeUndoHistory
from hoi4cm.models import Focus, FocusDocument


def _app(focuses=()):
    app = SimpleNamespace(
        _extra_trees=[],
        _shared_focuses=[],
        _joint_focuses=[],
        _undo_stack=UndoStack(),
        _tree_undo_history=ExtraTreeUndoHistory(),
        focuses=FocusDocument(focuses),
        selected=None,
        _lines=[],
        _lines_used=0,
        cv=Mock(),
        _invalidate_tree_badges=Mock(),
        _refresh_tree_meta_panel=Mock(),
        _refresh_loaded_trees_panel=Mock(),
        _redraw=Mock(),
        _invalidate_focus_list_structure=Mock(),
        _hide_form=Mock(),
        _hint=Mock(),
        _fit_all=Mock(),
        _begin_document_generation=Mock(),
        _tree_country_tag="",
        _autosave=Mock(),
        _tree_id=SimpleNamespace(get=lambda: "TAG_focus_tree"),
        _tree_country_name="",
        _tree_country_raw="",
        _tree_focus_prefix="",
        _tree_extras={},
        _tree_had_wrapper=True,
        _cfp_x=None,
        _cfp_y=None,
        _cfp_x_var=SimpleNamespace(get=lambda: ""),
        _cfp_y_var=SimpleNamespace(get=lambda: ""),
        _canvas_min=[0, 0],
        _canvas_max=[9, 9],
        _default_focus_prefix="",
    )
    app._push_undo = m.App._push_undo.__get__(app)
    app._snapshot_extra_tree_state = m.App._snapshot_extra_tree_state.__get__(app)
    app._restore_extra_tree_state = m.App._restore_extra_tree_state.__get__(app)
    app._undo = m.App._undo.__get__(app)
    app._redo = m.App._redo.__get__(app)
    app._workspace_fingerprint = m.App._workspace_fingerprint.__get__(app)
    app._is_dirty = m.App._is_dirty.__get__(app)
    app._saved_revision = app.focuses.revision
    app._saved_fingerprint = app._workspace_fingerprint()
    return app


def test_unload_extra_tree_prompts_and_undo_restores_canvas(monkeypatch):
    focus = Focus()
    focus.tree_idx = 1
    app = _app([focus])
    app._extra_trees = [
        {"tree_id": "shared_tree", "type": "shared", "focus_ids": {focus.id}}
    ]
    app._shared_focuses = ["shared_tree"]
    confirm = Mock(return_value=True)
    monkeypatch.setattr(m.messagebox, "askyesno", confirm)

    m.App._unload_extra_tree(cast(m.App, app), 1)

    confirm.assert_called_once()
    assert "shared_tree" in confirm.call_args.args[1]
    assert not app.focuses
    assert len(app._undo_stack) == 1

    app._undo()

    assert focus.id in app.focuses
    assert app.focuses[focus.id].tree_idx == 1
    assert app._extra_trees[0]["tree_id"] == "shared_tree"
    assert app._shared_focuses == ["shared_tree"]
    assert app._redraw.call_count == 2  # unload and undo each redraw the canvas

    app._redo()

    assert not app.focuses
    assert app._extra_trees == []
    assert app._shared_focuses == []


def test_unload_extra_tree_cancel_does_not_change_state_or_push_undo(monkeypatch):
    focus = Focus()
    focus.tree_idx = 1
    app = _app([focus])
    app._extra_trees = [
        {"tree_id": "shared_tree", "type": "shared", "focus_ids": {focus.id}}
    ]
    monkeypatch.setattr(m.messagebox, "askyesno", Mock(return_value=False))

    m.App._unload_extra_tree(cast(m.App, app), 1)

    assert app.focuses[focus.id] is focus
    assert len(app._undo_stack) == 0
    assert app._extra_trees[0]["tree_id"] == "shared_tree"


def test_clear_all_undo_restores_extra_tree_registry_and_focuses(monkeypatch):
    focus = Focus()
    focus.tree_idx = 1
    app = _app([focus])
    app._extra_trees = [
        {
            "tree_id": "shared_tree",
            "type": "shared",
            "focus_ids": {focus.id},
        }
    ]
    app._shared_focuses = ["shared_tree"]
    app._focus_bundles = {}
    app._reset_canvas_bounds = Mock()
    app._draw_grid = Mock()
    monkeypatch.setattr(m.messagebox, "askyesno", Mock(return_value=True))

    m.App._clear_all(cast(m.App, app))
    assert not app.focuses
    assert app._extra_trees == []
    assert app._shared_focuses == []

    app._undo()

    assert focus.id in app.focuses
    assert app.focuses[focus.id].tree_idx == 1
    assert app._extra_trees[0]["tree_id"] == "shared_tree"
    assert app._extra_trees[0]["focus_ids"] == {focus.id}
    assert app._shared_focuses == ["shared_tree"]


def test_unload_first_of_two_restores_save_all_tree_assignments(monkeypatch):
    shared_focus = Focus()
    shared_focus.tree_idx = 1
    joint_focus = Focus()
    joint_focus.tree_idx = 2
    app = _app([shared_focus, joint_focus])
    app._extra_trees = [
        {
            "tree_id": "shared_tree",
            "type": "shared",
            "file_path": "shared.txt",
            "focus_ids": {shared_focus.id},
            "shared_focuses": ["SHARED_ref"],
            "joint_focuses": [],
        },
        {
            "tree_id": "joint_tree",
            "type": "joint",
            "file_path": "joint.txt",
            "focus_ids": {joint_focus.id},
            "shared_focuses": [],
            "joint_focuses": ["JOINT_ref"],
        },
    ]
    app._shared_focuses = ["SHARED_ref"]
    app._joint_focuses = ["JOINT_ref"]
    monkeypatch.setattr(m.messagebox, "askyesno", Mock(return_value=True))
    m.App._unload_extra_tree(cast(m.App, app), 1)

    assert app._extra_trees[0]["tree_id"] == "joint_tree"
    assert app.focuses[joint_focus.id].tree_idx == 1
    app._undo()

    assert [tree["file_path"] for tree in app._extra_trees] == [
        "shared.txt",
        "joint.txt",
    ]
    assert app.focuses[shared_focus.id].tree_idx == 1
    assert app.focuses[joint_focus.id].tree_idx == 2
    assert app._shared_focuses == ["SHARED_ref"]
    assert app._joint_focuses == ["JOINT_ref"]

    def save_all_plans():
        plans = []
        app._autosave()
        app._make_main_export_plan = lambda *_a, **_k: None

        def make_extra_plan(tree_idx, tree_focuses, *_args, **_kwargs):
            plans.append(
                (
                    app._extra_trees[tree_idx - 1]["file_path"],
                    {focus.id for focus in tree_focuses},
                )
            )
            return (app._extra_trees[tree_idx - 1]["file_path"],)

        app._make_extra_export_plan = make_extra_plan
        app._run_export_plans = lambda *_a, **_k: None
        m.App._save_all_trees(cast(m.App, app))
        return plans

    assert save_all_plans() == [
        ("shared.txt", {shared_focus.id}),
        ("joint.txt", {joint_focus.id}),
    ]

    app._redo()
    assert len(app._extra_trees) == 1
    assert app._extra_trees[0]["file_path"] == "joint.txt"
    assert app.focuses[joint_focus.id].tree_idx == 1


def test_extra_tree_metadata_history_tracks_dirty_fingerprint(monkeypatch):
    focus = Focus()
    focus.tree_idx = 1
    app = _app([focus])
    app._extra_trees = [
        {
            "tree_id": "shared_tree",
            "type": "shared",
            "file_path": "shared.txt",
            "focus_ids": {focus.id},
        }
    ]
    app._shared_focuses = ["shared_tree"]
    baseline = app._workspace_fingerprint()
    monkeypatch.setattr(m.messagebox, "askyesno", Mock(return_value=True))

    m.App._unload_extra_tree(cast(m.App, app), 1)

    assert app._is_dirty() is True
    app._undo()
    assert app._workspace_fingerprint() == baseline
    app._redo()
    assert app._workspace_fingerprint() != baseline


def test_sidecar_stays_aligned_across_eviction_clear_and_redo_branch():
    app = _app()
    app._undo_stack = UndoStack(maxlen=2)
    app._tree_undo_history = ExtraTreeUndoHistory(maxlen=2)
    app._push_undo("load tree", touched_ids=(), tree_state=True)
    app._extra_trees.append({"tree_id": "tree", "type": "shared", "focus_ids": set()})
    app._push_undo("ordinary edit", touched_ids=())
    app._push_undo("another edit", touched_ids=())

    assert app._tree_undo_history.is_aligned(len(app._undo_stack))
    assert len(app._undo_stack) == 2

    app._undo()
    app._push_undo("new branch", touched_ids=())
    app._redo()

    assert app._hint.call_args.args == ("Nothing to redo.",)
    assert app._extra_trees[0]["tree_id"] == "tree"
    assert app._tree_undo_history.is_aligned(len(app._undo_stack))


def test_sidecar_discards_stale_history_after_undo_stack_clear():
    app = _app()
    app._push_undo("load tree", touched_ids=(), tree_state=True)
    app._extra_trees.append({"tree_id": "tree", "type": "shared", "focus_ids": set()})
    app._undo_stack.clear()

    app._push_undo("new document action", touched_ids=())
    app._undo()

    assert app._extra_trees[0]["tree_id"] == "tree"
    assert app._tree_undo_history.is_aligned(len(app._undo_stack))


def test_sidecar_label_guard_ignores_untracked_stack_entries():
    app = _app()
    app._push_undo("load tree", touched_ids=(), tree_state=True)
    app._extra_trees.append({"tree_id": "tree", "type": "shared", "focus_ids": set()})
    app._undo_stack.clear()
    app._undo_stack.push("untracked test entry", app.focuses, touched_ids=())

    app._undo()

    assert app._extra_trees[0]["tree_id"] == "tree"
    assert len(app._tree_undo_history) == 0


def test_batch_load_is_one_undo_redo_action(monkeypatch, tmp_path):
    class Widget:
        def __init__(self, *args, **kwargs):
            self.command = kwargs.get("command")

        def __getattr__(self, _name):
            return lambda *args, **kwargs: None

    class Variable:
        def __init__(self, value=""):
            self.value = value

        def get(self):
            return self.value

    buttons = []

    def button(*args, **kwargs):
        widget = Widget(*args, **kwargs)
        buttons.append(widget)
        return widget

    for name in ("Toplevel", "Label", "Frame"):
        monkeypatch.setattr(m.tk, name, Widget)
    monkeypatch.setattr(m.tk, "Button", button)
    monkeypatch.setattr(m.tk, "BooleanVar", lambda value=False: Variable(value))
    monkeypatch.setattr(m.tk, "StringVar", lambda value="": Variable(value))
    monkeypatch.setattr(m, "VirtualChecklist", Widget)
    loadable_calls = []

    def is_loadable(item):
        loadable_calls.append((item.key, item.checked.get(), item.type_var.get()))
        return True

    monkeypatch.setattr(
        m,
        "is_loadable",
        is_loadable,
    )
    monkeypatch.setattr(m.filedialog, "askdirectory", lambda **_kwargs: str(tmp_path))
    monkeypatch.setattr(
        m.os,
        "walk",
        lambda _path: [(str(tmp_path), [], ["shared.txt", "joint.txt"])],
    )
    monkeypatch.setattr(m.messagebox, "showinfo", Mock())
    monkeypatch.setattr(m.messagebox, "showwarning", Mock())

    shared_focus = Focus()
    joint_focus = Focus()
    shared_focus.tree_idx = 1
    joint_focus.tree_idx = 2

    def parsed(tree_id):
        return SimpleNamespace(
            tree_id=tree_id,
            cfp_x=None,
            cfp_y=None,
            shared_refs=[],
            joint_refs=[],
            country_tag="",
            country_raw="",
            tree_extras={},
            had_wrapper=True,
        )

    payload = (
        [
            {
                "path": "shared.txt",
                "ok": True,
                "type": "shared",
                "parsed": parsed("shared_tree"),
                "new_focuses": [shared_focus],
            },
            {
                "path": "joint.txt",
                "ok": True,
                "type": "joint",
                "parsed": parsed("joint_tree"),
                "new_focuses": [joint_focus],
            },
        ],
        False,
    )
    monkeypatch.setattr(m, "make_progress", lambda *_a, **_k: lambda *_a, **_k: None)
    monkeypatch.setattr(
        m,
        "progress_modal",
        lambda *_a, **_k: SimpleNamespace(
            cancelled=Event(),
            close=lambda: None,
            set_text=lambda *_a: None,
            set_fraction=lambda *_a: None,
        ),
    )
    monkeypatch.setattr(m, "run_bg", lambda _app, work, done, **_k: done(work()))
    monkeypatch.setattr(m.MOD, "loaded", False)
    monkeypatch.setattr(m.MOD, "root", None)
    app = _app()
    app._batch_load_trees_worker = lambda *_a, **_k: payload

    m.App._load_all_trees(cast(m.App, app))
    buttons[-2].command()

    assert loadable_calls
    assert len(app.focuses) == 2
    assert len(app._extra_trees) == 2
    assert len(app._undo_stack) == 1
    app._undo()
    assert not app.focuses
    assert app._extra_trees == []
    app._redo()
    assert len(app.focuses) == 2
    assert [tree["tree_id"] for tree in app._extra_trees] == [
        "shared_tree",
        "joint_tree",
    ]
