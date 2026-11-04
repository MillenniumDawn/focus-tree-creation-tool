"""Dirty tracking and autosave guard tests for issue #49."""

# pyright: reportAttributeAccessIssue=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import os
import tkinter as tk
from collections.abc import Callable
from unittest.mock import Mock

import pytest

import hoi4_content_maker as m
import hoi4cm.core.logger as logmod
import hoi4cm.editor.autosave_writer as aw
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

    def get(self, *_args):
        return self._v

    def set(self, v):
        self._v = v


class _ManualTimer:
    def __init__(self):
        self.job: tuple[str, Callable[[], None]] | None = None
        self.next_job = 0

    def after(self, _delay, callback):
        self.next_job += 1
        job = f"job-{self.next_job}"
        self.job = job, callback
        return job

    def after_cancel(self, _job):
        self.job = None

    def tick(self):
        assert self.job is not None
        _job, callback = self.job
        self.job = None
        callback()


@pytest.fixture
def errors(monkeypatch):
    """Isolate the shared error buffer from callbacks left by earlier Tk tests."""
    monkeypatch.setattr(logmod, "_error_callback", None)
    logmod.clear_errors()
    yield logmod.get_error_entries()
    logmod.clear_errors()


def _fake_app(**overrides):
    """Minimal App-shaped object with real dirty helpers bound."""
    # Bind the real App methods as unbound functions, then attach to fake.
    fake = type("Fake", (), {})()
    for name in (
        "_log_error",
        "_workspace_fingerprint",
        "_is_dirty",
        "_mark_clean",
        "_confirm_discard",
        "_schedule_autosave",
        "_cancel_autosave",
        "_autosave_tick",
        "_maybe_offer_autosave_restore",
        "_update_title",
        "_export",
    ):
        setattr(fake, name, getattr(m.App, name).__get__(fake))
    # Required attributes for fingerprint
    fake.edit_focus_file = ""
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
    fake._saved_revision = fake.focuses.content_revision
    fake._saved_fingerprint = fake._workspace_fingerprint()
    fake._autosave_job = None
    fake._autosave_interval_ms = 60000
    fake._last_project_path = None
    # Tk-ish stubs
    fake.after = lambda ms, cb: "job"
    fake.after_cancel = lambda j: None
    fake.winfo_exists = lambda: True
    fake.title = lambda t: setattr(fake, "_title", t)
    fake._update_statusbar = lambda: None
    fake._capture_workspace = lambda: None
    fake.workspace = EditorWorkspace()
    fake._hint = lambda msg: setattr(fake, "_hint_msg", msg)
    for k, v in overrides.items():
        setattr(fake, k, v)
    return fake


def test_is_dirty_initially_clean():
    app = _fake_app()
    assert app._is_dirty() is False


def test_is_dirty_after_focus_added():
    app = _fake_app()
    app.focuses.add(Focus(id=1, x=0, y=0))
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
    app.edit_focus_file = "new/path.txt"
    assert app._is_dirty() is True


def test_mark_clean_resets_dirty():
    app = _fake_app()
    app.focuses.add(Focus(id=2, x=0, y=0))
    assert app._is_dirty() is True
    app._mark_clean()
    assert app._is_dirty() is False
    assert app._saved_revision == app.focuses.content_revision


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


def test_confirm_discard_fingerprint_error_prompts(monkeypatch):
    app = _fake_app()
    app._workspace_fingerprint = lambda: (_ for _ in ()).throw(
        RuntimeError("fingerprint failed")
    )
    called = []
    monkeypatch.setattr(
        m.messagebox, "askyesnocancel", lambda *a, **kw: called.append(1) or False
    )
    assert app._is_dirty() is True
    assert app._confirm_discard("loading") is True
    assert called == [1]


def test_mark_clean_fingerprint_error_reports(monkeypatch):
    app = _fake_app()
    app._workspace_fingerprint = lambda: (_ for _ in ()).throw(
        RuntimeError("fingerprint failed")
    )
    errors = []
    monkeypatch.setattr(m, "add_error", errors.append)

    app._mark_clean()

    assert errors == ["Failed to update workspace fingerprint: fingerprint failed"]


def test_confirm_discard_dirty_cancel_returns_false(monkeypatch):
    app = _fake_app()
    app.focuses.add(Focus(id=3, x=0, y=0))
    monkeypatch.setattr(m.messagebox, "askyesnocancel", lambda *a, **kw: None)
    assert app._confirm_discard("loading") is False


def test_confirm_discard_dirty_no_returns_true_without_save(monkeypatch):
    app = _fake_app()
    app.focuses.add(Focus(id=4, x=0, y=0))
    monkeypatch.setattr(m.messagebox, "askyesnocancel", lambda *a, **kw: False)
    app._save = lambda: (_ for _ in ()).throw(AssertionError("should not save"))
    assert app._confirm_discard("loading") is True


def test_confirm_discard_dirty_yes_saves(monkeypatch):
    app = _fake_app()
    app.focuses.add(Focus(id=5, x=0, y=0))
    monkeypatch.setattr(m.messagebox, "askyesnocancel", lambda *a, **kw: True)
    saved = []
    app._save = lambda: saved.append(1) or True
    assert app._confirm_discard("loading") is True
    assert saved == [1]


def test_confirm_discard_dirty_yes_save_fails_returns_false(monkeypatch):
    app = _fake_app()
    app.focuses.add(Focus(id=6, x=0, y=0))
    monkeypatch.setattr(m.messagebox, "askyesnocancel", lambda *a, **kw: True)
    app._save = lambda: False
    assert app._confirm_discard("loading") is False


def test_autosave_tick_writes_when_dirty(monkeypatch, tmp_path):
    app = _fake_app()
    app.focuses.add(Focus(id=7, x=0, y=0))
    writes = []
    monkeypatch.setattr(aw, "write_project_text", lambda p, ws: writes.append(p))
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
    monkeypatch.setattr(aw, "write_project_text", lambda p, ws: writes.append(p))
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "autosave.json")
    )
    app._schedule_autosave = lambda: None
    app._autosave_tick()
    assert writes == []


def test_autosave_tick_writes_sibling_when_last_path(monkeypatch, tmp_path):
    app = _fake_app()
    app.focuses.add(Focus(id=8, x=0, y=0))
    app._last_project_path = str(tmp_path / "project.json")
    writes = []
    monkeypatch.setattr(aw, "write_project_text", lambda p, ws: writes.append(p))
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


@pytest.mark.parametrize("commit_path", ["apply", "select-away"])
def test_autosave_timer_persists_sidebar_cost_and_description_edits(
    monkeypatch, tmp_path, commit_path
):
    app = _fake_app()
    for name in (
        "_autosave",
        "_apply",
        "_select",
        "_read_sidebar_values",
        "_coerce_numeric",
        "_set_field_error",
        "_read_offsets_from_form",
    ):
        setattr(app, name, getattr(m.App, name).__get__(app))
    first = Focus(id=1, x=0, y=0)
    first.name = "focus_one"
    first.desc = "old description"
    second = Focus(id=2, x=2, y=0)
    second.name = "focus_two"
    app.focuses.add(first)
    app.focuses.add(second)
    app.selected = first
    app.workspace = EditorWorkspace(focuses=app.focuses)
    app._push_undo = lambda *_args, **_kwargs: None
    app._redraw = app._show_form = app._update_focus_list_selection = lambda: None
    app._invalidate_focus_list_structure = lambda: None
    app._populate = lambda focus: populate_sidebar(app, focus)
    app._offset_entries = []
    app._fv_name = _Var()
    app._fv_icon = _Var()
    app._fv_gfx = _Var()
    app._fv_cost = _Var()
    app._fv_ai_raw = _Var()
    app._fv_x = _Var()
    app._fv_y = _Var()
    app._fv_loc_name = _Var()
    app._fv_desc = _Var()
    app._fv_search = _Var()
    app._fv_avail = _Var()
    app._fv_bypass = _Var()
    app._fv_cancel2 = _Var()
    app._fv_cancel = _Var()
    app._fv_continue = _Var()
    app._fv_cap = _Var()
    app._set_field_error = lambda *_args: None
    app._populate(first)

    def commit_sidebar(target):
        if commit_path == "apply":
            app._apply()
        else:
            app._select(target)

    timer = _ManualTimer()
    app.after = timer.after
    app.after_cancel = timer.after_cancel
    app._last_project_path = str(tmp_path / "project.json")
    primary = tmp_path / "workspace.json"
    sibling = tmp_path / "project.autosave.json"
    monkeypatch.setattr(m, "workspace_autosave_path", lambda: str(primary))
    monkeypatch.setattr(m, "sibling_autosave_path", lambda _path: str(sibling))
    writes = []
    write = aw.write_project_text

    def record_write(path, text):
        writes.append(path)
        write(path, text)

    monkeypatch.setattr(aw, "write_project_text", record_write)

    app._schedule_autosave()
    timer.tick()
    assert [m.read_project(path).focuses[1].cost for path in (primary, sibling)] == [
        10,
        10,
    ]
    assert len(writes) == 2

    geometry_revision = app.focuses.revision
    content_revision = getattr(app.focuses, "content_revision", geometry_revision)
    name_index = app.focuses.names
    position_index = app.focuses.occupied_positions
    app._fv_cost.set("35")
    commit_sidebar(second)
    assert app.focuses[1].cost == 35
    assert app.focuses.revision == geometry_revision
    assert app._is_dirty()
    timer.tick()
    assert [m.read_project(path).focuses[1].cost for path in (primary, sibling)] == [
        35,
        35,
    ]
    assert app.focuses.content_revision > content_revision
    assert app.focuses.names is name_index
    assert app.focuses.occupied_positions is position_index
    assert len(writes) == 4
    assert primary.read_bytes() == sibling.read_bytes()
    timer.tick()
    assert len(writes) == 4

    # A normal project save can make the workspace clean between recovery
    # writes. The next sidebar edit must transition it back to dirty.
    app._mark_clean()
    assert not app._is_dirty()
    if commit_path == "select-away":
        app._select(first)
    content_revision = app.focuses.content_revision
    app._fv_desc.set("new description")
    commit_sidebar(second)
    assert app.focuses[1].desc == "new description"
    assert app.focuses.revision == geometry_revision
    assert app._is_dirty()
    timer.tick()
    recovery = [m.read_project(path).focuses[1] for path in (primary, sibling)]
    assert [(focus.cost, focus.desc) for focus in recovery] == [
        (35, "new description"),
        (35, "new description"),
    ]
    assert app.focuses.content_revision > content_revision
    assert app.focuses.names is name_index
    assert app.focuses.occupied_positions is position_index
    assert len(writes) == 6
    assert primary.read_bytes() == sibling.read_bytes()

    timer.tick()
    assert len(writes) == 6


def populate_sidebar(app, focus):
    values = {
        "_fv_name": focus.name,
        "_fv_icon": focus.icon,
        "_fv_gfx": focus.gfx,
        "_fv_cost": str(focus.cost),
        "_fv_ai_raw": focus.ai_will_do_raw or f"base = {focus.ai_will_do}",
        "_fv_x": str(focus.x),
        "_fv_y": str(focus.y),
        "_fv_loc_name": focus.loc_name,
        "_fv_desc": focus.desc,
        "_fv_search": focus.search_filters,
        "_fv_avail": focus.available_cond,
        "_fv_bypass": focus.bypass_cond,
        "_fv_cancel2": focus.cancel_cond,
        "_fv_cancel": focus.cancel_if_invalid,
        "_fv_continue": focus.continue_if_invalid,
        "_fv_cap": focus.available_if_capitulated,
    }
    for name, value in values.items():
        getattr(app, name).set(value)


def test_autosave_tick_swallows_write_error(monkeypatch, tmp_path, errors):
    app = _fake_app()
    app.focuses.add(Focus(id=9, x=0, y=0))
    monkeypatch.setattr(
        aw,
        "write_project_text",
        lambda p, ws: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "autosave.json")
    )
    app._capture_workspace = lambda: None
    app.workspace = EditorWorkspace()
    app._schedule_autosave = lambda: setattr(app, "_scheduled", True)
    app._autosave_tick()
    assert getattr(app, "_scheduled", False) is True
    assert len(errors) == 1
    assert "disk full" in errors[0][1]


def test_autosave_tick_records_one_entry_per_failure_streak(
    monkeypatch, tmp_path, errors
):
    app = _fake_app()
    app.focuses.add(app.focuses.new_focus(0, 0))
    outcomes = [OSError("disk full"), OSError("disk full"), None, OSError("again")]

    def write(_path, _workspace):
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome

    monkeypatch.setattr(aw, "write_project_text", write)
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "autosave.json")
    )
    app.workspace = EditorWorkspace()

    counts = []
    for _ in range(4):
        app._autosave_tick()
        counts.append(len(errors))

    assert counts == [1, 1, 1, 2]
    assert "again" in errors[1][1]
    assert app._autosave_job == "job"


def test_autosave_tick_sibling_failure_records_path_once(monkeypatch, tmp_path, errors):
    app = _fake_app()
    app.focuses.add(Focus(id=10, x=0, y=0))
    project = tmp_path / "project.json"
    sibling = tmp_path / "project.autosave.json"
    app._last_project_path = str(project)
    calls = []

    def write(path, _text):
        calls.append(path)
        if path == str(sibling):
            raise OSError("sibling disk full")

    monkeypatch.setattr(aw, "write_project_text", write)
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "workspace.json")
    )
    app.workspace = EditorWorkspace(focuses=app.focuses)

    app._autosave_tick()
    app._autosave_tick()

    assert len(errors) == 1
    assert str(sibling) in errors[0][1]
    assert "sibling disk full" in errors[0][1]
    assert calls[0].endswith("workspace.json")
    assert app._autosave_job == "job"
    assert not getattr(app, "_autosave_failing", False)


def test_autosave_tick_sibling_failure_streak_resets_after_success(
    monkeypatch, tmp_path, errors
):
    app = _fake_app()
    app.focuses.add(app.focuses.new_focus(0, 0))
    sibling = str(tmp_path / "project.autosave.json")
    app._last_project_path = str(tmp_path / "project.json")
    fail = True

    def write(path, _text):
        if fail and path == sibling:
            raise OSError("sibling disk full")

    monkeypatch.setattr(aw, "write_project_text", write)
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "workspace.json")
    )
    app.workspace = EditorWorkspace()

    app._autosave_tick()
    app._autosave_tick()
    assert len(errors) == 1

    fail = False
    app._autosave_tick()
    assert len(errors) == 1
    assert app._sibling_autosave_failing is None

    fail = True
    app._autosave_tick()
    assert len(errors) == 2
    assert "sibling disk full" in errors[1][1]


def test_clean_tick_ends_the_sibling_autosave_failure_streak(
    monkeypatch, tmp_path, errors
):
    app = _fake_app()
    app.focuses.add(app.focuses.new_focus(0, 0))
    sibling = str(tmp_path / "project.autosave.json")
    app._last_project_path = str(tmp_path / "project.json")

    def write(path, _text):
        if path == sibling:
            raise OSError("sibling disk full")

    monkeypatch.setattr(aw, "write_project_text", write)
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "workspace.json")
    )
    app.workspace = EditorWorkspace()

    app._autosave_tick()
    assert len(errors) == 1

    app._mark_clean()
    app._autosave_tick()
    app.focuses.add(app.focuses.new_focus(1, 1))
    app._autosave_tick()

    assert len(errors) == 2
    assert str(tmp_path / "project.autosave.json") in errors[1][1]


def test_real_sibling_write_failure_keeps_primary_recovery(
    monkeypatch, tmp_path, errors
):
    app = _fake_app()
    focus = app.focuses.new_focus(2, 3)
    focus.name = "TST_autosaved"
    app.focuses.add(focus)
    app.workspace = EditorWorkspace(focuses=app.focuses)
    app._last_project_path = str(tmp_path / "project.json")
    primary = tmp_path / "workspace.json"
    sibling = tmp_path / "project.autosave.json"
    sibling.mkdir()
    monkeypatch.setattr(m, "workspace_autosave_path", lambda: str(primary))

    app._autosave_tick()

    restored = m.read_project(primary)
    assert [(item.name, item.x, item.y) for item in restored.focuses.values()] == [
        ("TST_autosaved", 2, 3)
    ]
    assert sibling.is_dir()
    assert len(errors) == 1
    assert str(sibling) in errors[0][1]


def test_clean_tick_ends_the_autosave_failure_streak(monkeypatch, tmp_path, errors):
    app = _fake_app()
    app.focuses.add(app.focuses.new_focus(0, 0))
    monkeypatch.setattr(
        aw,
        "write_project_text",
        lambda p, ws: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(
        m, "workspace_autosave_path", lambda: str(tmp_path / "autosave.json")
    )
    app.workspace = EditorWorkspace()

    app._autosave_tick()
    assert len(errors) == 1

    app._mark_clean()
    app._autosave_tick()
    app.focuses.add(app.focuses.new_focus(1, 1))
    app._autosave_tick()

    assert len(errors) == 2


def test_schedule_autosave_failure_records_entry_and_retries_with_default(errors):
    app = _fake_app()
    app._autosave_interval_ms = -5
    delays = []

    def after(ms, _callback):
        delays.append(ms)
        if len(delays) == 1:
            raise RuntimeError("bad interval")
        return "retry-job"

    app.after = after
    app._schedule_autosave()

    assert delays == [-5, m._AUTOSAVE_INTERVAL_MS]
    assert app._autosave_job == "retry-job"
    assert app._autosave_interval_ms == m._AUTOSAVE_INTERVAL_MS
    assert len(errors) == 1
    assert "bad interval" in errors[0][1]


def test_schedule_autosave_records_when_retry_also_fails(errors):
    app = _fake_app()
    delays = []

    def after(ms, _callback):
        delays.append(ms)
        raise RuntimeError("timer broken")

    app.after = after
    app._schedule_autosave()

    assert delays == [m._AUTOSAVE_INTERVAL_MS, m._AUTOSAVE_INTERVAL_MS]
    assert app._autosave_job is None
    assert len(errors) == 2
    assert "off for this session" in errors[1][1]


def _gone():
    raise tk.TclError("application has been destroyed")


@pytest.mark.parametrize("winfo_exists", [lambda: 0, _gone])
def test_schedule_autosave_on_destroyed_root_stays_quiet(errors, winfo_exists):
    app = _fake_app()
    app.winfo_exists = winfo_exists
    delays = []

    def after(ms, _callback):
        delays.append(ms)
        raise tk.TclError("application has been destroyed")

    app.after = after
    app._schedule_autosave()

    assert len(delays) == 1
    assert app._autosave_job is None
    assert errors == []


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
    app.focuses.add(Focus(id=10, x=0, y=0))
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


def test_maybe_offer_restore_malformed_no_prompt(monkeypatch, tmp_path, errors):
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
    assert len(errors) == 1
    assert str(path) in errors[0][1]
    assert "bad" in errors[0][1]


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
        focuses=FocusDocument([Focus(id=11, x=0, y=0)]),
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
        focuses=FocusDocument([Focus(id=12, x=0, y=0)]),
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
        focuses=FocusDocument([Focus(id=13, x=0, y=0)]),
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


def test_export_records_failed_autosave_flush_and_proceeds(errors):
    make_plan = Mock(return_value=None)
    app = _fake_app(
        selected=Focus(id=1, x=0, y=0),
        _autosave=Mock(side_effect=RuntimeError("flush failed")),
        _make_main_export_plan=make_plan,
    )

    assert app._export(focuses_in_tree=[]) is None

    make_plan.assert_called_once()
    assert len(errors) == 1
    assert "flush failed" in errors[0][1]
