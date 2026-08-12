"""Tests for the monolith's Tk shells around the export-plan pipeline."""

from types import SimpleNamespace

import pytest

import hoi4_content_maker as m
import hoi4cm.core.logger as logmod
from hoi4cm.focus_tree.export_plan import execute_export_plans
from hoi4cm.mod.workspace_files import WorkspaceFiles
from hoi4cm.models import Focus


@pytest.fixture(autouse=True)
def reset_focus_counter():
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


@pytest.fixture
def dialogs(monkeypatch):
    captured = SimpleNamespace(info=[], warning=[], error=[])
    monkeypatch.setattr(
        m.messagebox, "showinfo", lambda *args, **_kwargs: captured.info.append(args)
    )
    monkeypatch.setattr(
        m.messagebox,
        "showwarning",
        lambda *args, **_kwargs: captured.warning.append(args),
    )
    monkeypatch.setattr(
        m.messagebox, "showerror", lambda *args, **_kwargs: captured.error.append(args)
    )
    monkeypatch.setattr(
        m.filedialog,
        "asksaveasfilename",
        lambda **_kwargs: pytest.fail("export must reuse the edit target, not prompt"),
    )
    logmod.clear_errors()
    yield captured
    logmod.clear_errors()


@pytest.fixture
def mod_files(tmp_path, monkeypatch):
    focus_file = tmp_path / "common" / "national_focus" / "05_TST.txt"
    loc_file = tmp_path / "localisation" / "english" / "MD_focus_TST_l_english.yml"
    focus_file.parent.mkdir(parents=True)
    loc_file.parent.mkdir(parents=True)
    focus_file.write_text("focus_tree = { # the user's real tree }\n", encoding="utf-8")
    loc_file.write_text("l_english:\n", encoding="utf-8-sig")
    monkeypatch.setattr(m.MOD, "root", str(tmp_path))
    monkeypatch.setattr(m.MOD, "loaded", False)
    monkeypatch.setattr(m.MOD, "edit_focus_file", str(focus_file))
    monkeypatch.setattr(m.MOD, "edit_loc_file", str(loc_file))
    return SimpleNamespace(root=tmp_path, focus=focus_file, loc=loc_file)


class _App:
    def _begin_document_generation(self):
        pass

    def __init__(self, focuses):
        self.selected = None
        self.focuses = {focus.id: focus for focus in focuses}
        self._tree_id = SimpleNamespace(get=lambda: "TST_focus_tree")
        self._extra_trees = []


def _focus(name, x=0, y=0):
    focus = Focus(x, y)
    focus.name = name
    focus.tree_idx = 0
    return focus


def _bind_export_shells(app):
    app._make_main_export_plan = m.App._make_main_export_plan.__get__(app, _App)
    app._make_extra_export_plan = m.App._make_extra_export_plan.__get__(app, _App)
    app._apply_export_results = m.App._apply_export_results.__get__(app, _App)

    def run_export_plans(plans, on_done, *, title):
        results = execute_export_plans(plans, WorkspaceFiles().write_texts)
        on_done(results)
        return results

    app._run_export_plans = run_export_plans
    app._autosave = lambda: None


def _export(app, **kwargs):
    _bind_export_shells(app)
    return m.App._export.__get__(app, _App)(**kwargs)


def _export_extra_tree(app, index, **kwargs):
    _bind_export_shells(app)
    return m.App._export_extra_tree.__get__(app, _App)(index, **kwargs)


def _fail_replace(monkeypatch, message="No space left on device"):
    monkeypatch.setattr(
        "hoi4cm.mod.workspace_files.os.replace",
        lambda *_args: (_ for _ in ()).throw(OSError(message)),
    )


def test_export_writes_both_tracked_files(dialogs, mod_files):
    _export(_App([_focus("TST_root")]))

    assert "TST_root" in mod_files.focus.read_text(encoding="utf-8")
    assert "TST_root" in mod_files.loc.read_text(encoding="utf-8-sig")
    assert len(dialogs.info) == 1
    assert dialogs.error == []


def test_failed_export_leaves_the_tracked_files_untouched(
    dialogs, mod_files, monkeypatch
):
    app = _App([_focus("TST_root")])
    tree_before = mod_files.focus.read_text(encoding="utf-8")
    loc_before = mod_files.loc.read_text(encoding="utf-8-sig")
    _fail_replace(monkeypatch)

    _export(app)

    assert mod_files.focus.read_text(encoding="utf-8") == tree_before
    assert mod_files.loc.read_text(encoding="utf-8-sig") == loc_before
    assert list(mod_files.focus.parent.glob(".*.tmp")) == []
    assert list(mod_files.loc.parent.glob(".*.tmp")) == []


def test_failed_export_reports_instead_of_raising(dialogs, mod_files, monkeypatch):
    _fail_replace(monkeypatch, "Permission denied")

    _export(_App([_focus("TST_root")]))

    assert len(dialogs.error) == 1
    assert "05_TST.txt" in dialogs.error[0][1]
    assert "Permission denied" in dialogs.error[0][1]
    assert dialogs.info == []
    assert len(logmod.get_error_entries()) == 1


def test_export_does_not_apply_half_the_pair(dialogs, mod_files, monkeypatch):
    app = _App([_focus("TST_root")])
    tree_before = mod_files.focus.read_text(encoding="utf-8")
    real_replace = m.os.replace
    calls = []

    def failing_replace(source, target):
        calls.append(target)
        if len(calls) == 1:
            return real_replace(source, target)
        raise OSError("disk full")

    monkeypatch.setattr("hoi4cm.mod.workspace_files.os.replace", failing_replace)

    _export(app)

    assert len(calls) == 2, "both files must be attempted as one group"
    assert mod_files.focus.read_text(encoding="utf-8") == tree_before
    assert len(dialogs.error) == 1


def test_failed_extra_tree_export_keeps_the_source_file(dialogs, tmp_path, monkeypatch):
    shared = tmp_path / "MD_shared_focuses.txt"
    shared.write_text("shared_focus = { # real content }\n", encoding="utf-8")
    focus = _focus("TST_shared")
    focus.tree_idx = 1
    app = _App([focus])
    app._extra_trees = [
        {
            "type": "shared",
            "file_path": str(shared),
            "tree_id": "",
            "country_tag": "TST",
            "country_raw": "",
            "cfp_x": None,
            "cfp_y": None,
            "had_wrapper": False,
        }
    ]
    monkeypatch.setattr(m.MOD, "loaded", False)
    _fail_replace(monkeypatch)

    _export_extra_tree(app, 1)

    assert shared.read_text(encoding="utf-8") == "shared_focus = { # real content }\n"
    assert len(dialogs.error) == 1
    assert "MD_shared_focuses.txt" in dialogs.error[0][1]


def test_run_export_plans_uses_document_scope_and_closes_modal(monkeypatch, mod_files):
    app = _App([_focus("TST_root")])
    plan = m.App._make_main_export_plan.__get__(app, _App)(
        list(app.focuses.values()),
        dict(app.focuses),
        {"TST_root": next(iter(app.focuses.values()))},
        show_dialog=False,
    )
    modal = SimpleNamespace(closed=False)
    calls = []

    monkeypatch.setattr(
        m,
        "progress_modal",
        lambda _app, _title: SimpleNamespace(
            set_text=lambda _text: None,
            set_fraction=lambda _fraction: None,
            close=lambda: setattr(modal, "closed", True),
        ),
    )
    monkeypatch.setattr(m, "make_progress", lambda _app, callback, **_kwargs: callback)

    def run_background(_app, work, on_done, **kwargs):
        calls.append(kwargs)
        on_done(work())

    monkeypatch.setattr(m, "run_bg", run_background)

    results = []
    m.App._run_export_plans.__get__(app, _App)(
        [plan],
        results.extend,
        title="Export",
    )

    assert results[0].ok
    assert modal.closed
    assert len(calls) == 1
    assert calls[0]["scope"] == "document"
    assert callable(calls[0]["on_error"])


def test_save_all_uses_one_plan_per_loaded_tree(dialogs, mod_files, tmp_path):
    shared = tmp_path / "MD_shared_focuses.txt"
    shared.write_text("shared_focus = { }\n", encoding="utf-8")
    main = _focus("TST_main")
    extra = _focus("TST_shared")
    extra.tree_idx = 1
    app = _App([main, extra])
    app._extra_trees = [
        {
            "type": "shared",
            "file_path": str(shared),
            "tree_id": "TST_shared_focuses",
            "country_tag": "TST",
            "country_raw": "",
            "cfp_x": None,
            "cfp_y": None,
            "had_wrapper": False,
        }
    ]
    _bind_export_shells(app)

    m.App._save_all_trees.__get__(app, _App)()

    assert "TST_main" in mod_files.focus.read_text(encoding="utf-8")
    assert "TST_shared" in shared.read_text(encoding="utf-8")
    assert len(dialogs.info) == 1
