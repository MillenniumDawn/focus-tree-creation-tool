"""Dirty tracking and autosave guard tests for issue #49."""

# pyright: reportAttributeAccessIssue=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import os

import hoi4_content_maker as m
from hoi4cm.models import (
    EditorWorkspace,
    Focus,
    FocusDocument,
    TreeDocument,
    TreeMetadata,
)


class _Var:
    def __init__(self, v=""):
        self._v = v

    def get(self):
        return self._v

    def set(self, v):
        self._v = v


def _fake_app(**overrides):
    """Minimal App-shaped object with real dirty helpers bound."""
    # Bind the real App methods as unbound functions, then attach to fake.
    fake = type("Fake", (), {})()
    for name in (
        "_workspace_fingerprint",
        "_is_dirty",
        "_mark_clean",
        "_confirm_discard",
        "_schedule_autosave",
        "_cancel_autosave",
        "_autosave_tick",
        "_maybe_offer_autosave_restore",
        "_update_title",
    ):
        setattr(fake, name, getattr(m.App, name).__get__(fake))
    # Required attributes for fingerprint
    fake._tree_id = _Var("TAG_focus_tree")
    fake._tree_country_tag = ""
    fake._tree_country_name = ""
    fake._tree_country_raw = ""
    fake._tree_focus_prefix = ""
    fake._tree_extras = {}
    fake._tree_had_wrapper = True
    fake._cfp_x = None
    fake._cfp_y = None
    fake._cfp_x_var = _Var("")
    fake._cfp_y_var = _Var("")
    fake._shared_focuses = []
    fake._joint_focuses = []
    fake._canvas_min = [0, 0]
    fake._canvas_max = [9, 9]
    fake._default_focus_prefix = ""
    fake._extra_trees = []
    fake.focuses = FocusDocument()
    fake._saved_revision = fake.focuses.revision
    fake._saved_fingerprint = fake._workspace_fingerprint()
    fake._autosave_job = None
    fake._autosave_interval_ms = 60000
    fake._last_project_path = None
    # Tk-ish stubs
    fake.after = lambda ms, cb: "job"
    fake.after_cancel = lambda j: None
    fake.title = lambda t: setattr(fake, "_title", t)
    fake._update_statusbar = lambda: None
    fake._capture_workspace = lambda: None
    fake.workspace = EditorWorkspace()
    fake._hint = lambda msg: setattr(fake, "_hint_msg", msg)
    # Provide minimal MOD edit_focus_file
    for k, v in overrides.items():
        setattr(fake, k, v)
    return fake


def test_is_dirty_initially_clean():
    app = _fake_app()
    assert app._is_dirty() is False


def test_is_dirty_after_focus_added():
    app = _fake_app()
    app.focuses.add(Focus(0, 0))
    assert app._is_dirty() is True


def test_is_dirty_after_fingerprint_change_tree_id():
    app = _fake_app()
    app._tree_id.set("OTHER_tree")
    assert app._is_dirty() is True


def test_is_dirty_after_cfp_change():
    app = _fake_app()
    app._cfp_x_var.set("5")
    assert app._is_dirty() is True


def test_is_dirty_after_extra_tree_append():
    app = _fake_app()
    app._extra_trees.append(
        {"type": "shared", "file_path": "a.txt", "tree_id": "t", "focus_ids": {1}}
    )
    assert app._is_dirty() is True


def test_is_dirty_after_canvas_change():
    app = _fake_app()
    app._canvas_max = [20, 20]
    assert app._is_dirty() is True


def test_is_dirty_after_tree_extras_change():
    app = _fake_app()
    app._tree_extras = {"custom": 1}
    assert app._is_dirty() is True


def test_is_dirty_after_edit_focus_file_change(monkeypatch):
    app = _fake_app()
    monkeypatch.setattr(m.MOD, "edit_focus_file", "new/path.txt", raising=False)
    assert app._is_dirty() is True


def test_mark_clean_resets_dirty():
    app = _fake_app()
    app.focuses.add(Focus(0, 0))
    assert app._is_dirty() is True
    app._mark_clean()
    assert app._is_dirty() is False
    assert app._saved_revision == app.focuses.revision


def test_workspace_fingerprint_changes_with_extra_tree_focus_ids_order():
    app = _fake_app()
    fp1 = app._workspace_fingerprint()
    app._extra_trees = [
        {
            "type": "shared",
            "file_path": "a.txt",
            "tree_id": "t",
            "focus_ids": {2, 1},
            "shared_focuses": [],
            "joint_focuses": [],
        }
    ]
    fp2 = app._workspace_fingerprint()
    assert fp1 != fp2
    # Order of focus_ids must not matter (sorted)
    app2 = _fake_app()
    app2._extra_trees = [
        {
            "type": "shared",
            "file_path": "a.txt",
            "tree_id": "t",
            "focus_ids": {1, 2},
            "shared_focuses": [],
            "joint_focuses": [],
        }
    ]
    assert fp2 == app2._workspace_fingerprint()


def test_confirm_discard_no_dirty_returns_true_without_prompt(monkeypatch):
    app = _fake_app()
    called = []
    monkeypatch.setattr(
        m.messagebox, "askyesnocancel", lambda *a, **kw: called.append(1) or True
    )
    assert app._confirm_discard("loading") is True
    assert called == []


def test_confirm_discard_dirty_cancel_returns_false(monkeypatch):
    app = _fake_app()
    app.focuses.add(Focus(0, 0))
    monkeypatch.setattr(m.messagebox, "askyesnocancel", lambda *a, **kw: None)
    assert app._confirm_discard("loading") is False


def test_confirm_discard_dirty_no_returns_true_without_save(monkeypatch):
    app = _fake_app()
    app.focuses.add(Focus(0, 0))
    monkeypatch.setattr(m.messagebox, "askyesnocancel", lambda *a, **kw: False)
    app._save = lambda: (_ for _ in ()).throw(AssertionError("should not save"))
    assert app._confirm_discard("loading") is True


def test_confirm_discard_dirty_yes_saves(monkeypatch):
    app = _fake_app()
    app.focuses.add(Focus(0, 0))
    monkeypatch.setattr(m.messagebox, "askyesnocancel", lambda *a, **kw: True)
    saved = []
    app._save = lambda: saved.append(1) or True
    assert app._confirm_discard("loading") is True
    assert saved == [1]


def test_confirm_discard_dirty_yes_save_fails_returns_false(monkeypatch):
    app = _fake_app()
    app.focuses.add(Focus(0, 0))
    monkeypatch.setattr(m.messagebox, "askyesnocancel", lambda *a, **kw: True)
    app._save = lambda: False
    assert app._confirm_discard("loading") is False


def test_autosave_tick_writes_when_dirty(monkeypatch, tmp_path):
    app = _fake_app()
    app.focuses.add(Focus(0, 0))
    writes = []
    monkeypatch.setattr(m, "write_project", lambda p, ws: writes.append(p))
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "autosave.json")
    )
    app._capture_workspace = lambda: None
    app.workspace = EditorWorkspace(focuses=app.focuses)
    app._schedule_autosave = lambda: None
    app._autosave_tick()
    assert len(writes) == 1
    assert writes[0].endswith("autosave.json")


def test_autosave_tick_no_write_when_clean(monkeypatch, tmp_path):
    app = _fake_app()
    writes = []
    monkeypatch.setattr(m, "write_project", lambda p, ws: writes.append(p))
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "autosave.json")
    )
    app._schedule_autosave = lambda: None
    app._autosave_tick()
    assert writes == []


def test_autosave_tick_writes_sibling_when_last_path(monkeypatch, tmp_path):
    app = _fake_app()
    app.focuses.add(Focus(0, 0))
    app._last_project_path = str(tmp_path / "project.json")
    writes = []
    monkeypatch.setattr(m, "write_project", lambda p, ws: writes.append(p))
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "autosave.json")
    )
    # sibling helper returns .autosave.json
    monkeypatch.setattr(
        m, "sibling_autosave_path", lambda p: p.replace(".json", ".autosave.json")
    )
    app._capture_workspace = lambda: None
    app.workspace = EditorWorkspace(focuses=app.focuses)
    app._schedule_autosave = lambda: None
    app._autosave_tick()
    assert len(writes) == 2
    assert any(".autosave.json" in p for p in writes)


def test_autosave_tick_swallows_write_error(monkeypatch, tmp_path):
    app = _fake_app()
    app.focuses.add(Focus(0, 0))
    monkeypatch.setattr(
        m, "write_project", lambda p, ws: (_ for _ in ()).throw(OSError("disk full"))
    )
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "autosave.json")
    )
    app._capture_workspace = lambda: None
    app.workspace = EditorWorkspace()
    app._schedule_autosave = lambda: setattr(app, "_scheduled", True)
    app._autosave_tick()
    assert getattr(app, "_scheduled", False) is True


def test_maybe_offer_restore_no_file_no_prompt(monkeypatch, tmp_path):
    app = _fake_app()
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "missing.json")
    )
    monkeypatch.setattr(os.path, "isfile", lambda p: False)
    called = []
    monkeypatch.setattr(
        m.messagebox, "askyesnocancel", lambda *a, **kw: called.append(1) or True
    )
    app._maybe_offer_autosave_restore()
    assert called == []


def test_maybe_offer_restore_when_dirty_no_prompt(monkeypatch, tmp_path):
    app = _fake_app()
    app.focuses.add(Focus(0, 0))
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "autosave.json")
    )
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    called = []
    monkeypatch.setattr(
        m.messagebox, "askyesnocancel", lambda *a, **kw: called.append(1) or True
    )
    app._maybe_offer_autosave_restore()
    assert called == []


def test_maybe_offer_restore_malformed_no_prompt(monkeypatch, tmp_path):
    app = _fake_app()
    path = tmp_path / "autosave.json"
    path.write_text("not json")
    monkeypatch.setattr(m, "workspace_autosave_path", lambda: str(path))
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(
        m, "read_project", lambda p: (_ for _ in ()).throw(ValueError("bad"))
    )
    called = []
    monkeypatch.setattr(
        m.messagebox, "askyesnocancel", lambda *a, **kw: called.append(1) or True
    )
    app._maybe_offer_autosave_restore()
    assert called == []


def test_maybe_offer_restore_empty_not_offered(monkeypatch, tmp_path):
    app = _fake_app()
    empty_ws = EditorWorkspace(
        main_tree=TreeDocument(metadata=TreeMetadata(tree_id="TAG_focus_tree"))
    )
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "autosave.json")
    )
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(m, "read_project", lambda p: empty_ws)
    called = []
    monkeypatch.setattr(
        m.messagebox, "askyesnocancel", lambda *a, **kw: called.append(1) or True
    )
    app._maybe_offer_autosave_restore()
    assert called == []


def test_maybe_offer_restore_yes_restores(monkeypatch, tmp_path):
    app = _fake_app()
    # needed attrs for restore path
    app.cv = type("CV", (), {"delete": lambda self, a: None})()
    app.selected = None
    app._lines = []
    app._grid_item = None
    app._grid_key = None
    app._grid_img = None
    app._install_workspace = lambda ws: setattr(app, "_installed", ws)
    app._detect_and_apply_tag = lambda: None
    app._refresh_tree_meta_panel = lambda: None
    app._refresh_loaded_trees_panel = lambda: None
    app._hide_form = lambda: None
    app._redraw = lambda: None
    app._invalidate_focus_list_structure = lambda: None

    ws = EditorWorkspace(
        focuses=FocusDocument([Focus(0, 0)]),
        main_tree=TreeDocument(metadata=TreeMetadata(tree_id="MY_tree")),
    )
    path = tmp_path / "autosave.json"
    path.write_text("x")
    monkeypatch.setattr(m, "workspace_autosave_path", lambda: str(path))
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(m, "read_project", lambda p: ws)
    monkeypatch.setattr(m.messagebox, "askyesnocancel", lambda *a, **kw: True)
    app._maybe_offer_autosave_restore()
    assert getattr(app, "_installed", None) is ws
    assert hasattr(app, "_hint_msg")


def test_maybe_offer_restore_no_clears_file(monkeypatch, tmp_path):
    app = _fake_app()
    ws = EditorWorkspace(
        focuses=FocusDocument([Focus(0, 0)]),
        main_tree=TreeDocument(metadata=TreeMetadata(tree_id="MY_tree")),
    )
    path = tmp_path / "autosave.json"
    path.write_text("x")
    monkeypatch.setattr(m, "workspace_autosave_path", lambda: str(path))
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(m, "read_project", lambda p: ws)
    monkeypatch.setattr(m.messagebox, "askyesnocancel", lambda *a, **kw: False)
    cleared = []
    monkeypatch.setattr(m, "clear_workspace_autosave", lambda p: cleared.append(p))
    app._maybe_offer_autosave_restore()
    assert cleared == [str(path)]


def test_maybe_offer_restore_cancel_keeps_file(monkeypatch, tmp_path):
    app = _fake_app()
    ws = EditorWorkspace(
        focuses=FocusDocument([Focus(0, 0)]),
        main_tree=TreeDocument(metadata=TreeMetadata(tree_id="MY_tree")),
    )
    path = tmp_path / "autosave.json"
    path.write_text("x")
    monkeypatch.setattr(m, "workspace_autosave_path", lambda: str(path))
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(m, "read_project", lambda p: ws)
    monkeypatch.setattr(m.messagebox, "askyesnocancel", lambda *a, **kw: None)
    cleared = []
    monkeypatch.setattr(m, "clear_workspace_autosave", lambda p: cleared.append(p))
    installed = []
    app._install_workspace = lambda ws: installed.append(ws)
    app._maybe_offer_autosave_restore()
    assert cleared == []
    assert installed == []
