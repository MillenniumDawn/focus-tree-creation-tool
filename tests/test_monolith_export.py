"""Tests for the monolith's export path — issue #46.

`_export` and `_export_extra_tree` overwrite the user's *tracked* mod files.
These bind the unbound App methods onto a stand-in `self` (same trick as
tests/test_sidebar_refresh.py) and check the two things the issue asked for:
the writes are atomic, and a failure surfaces as a dialog + an error-log
entry instead of a bare traceback.

No Tk widgets are built: the tk vars are stubs and every dialog is captured.
"""

from types import SimpleNamespace

import pytest

import hoi4_content_maker as m
import hoi4cm.core.logger as logmod
from hoi4cm.models import Focus


@pytest.fixture(autouse=True)
def reset_focus_counter():
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


@pytest.fixture
def dialogs(monkeypatch):
    """Capture every dialog the export path can raise, and isolate the log."""
    captured = SimpleNamespace(info=[], warning=[], error=[])
    monkeypatch.setattr(
        m.messagebox, "showinfo", lambda *a, **kw: captured.info.append(a)
    )
    monkeypatch.setattr(
        m.messagebox, "showwarning", lambda *a, **kw: captured.warning.append(a)
    )
    monkeypatch.setattr(
        m.messagebox, "showerror", lambda *a, **kw: captured.error.append(a)
    )
    # _export falls back to a save dialog when no edit target is set; a test
    # that hits it has mis-set up the mod, so make that loud.
    monkeypatch.setattr(
        m.filedialog,
        "asksaveasfilename",
        lambda **kw: pytest.fail("export must reuse the edit target, not prompt"),
    )
    logmod.clear_errors()
    yield captured
    logmod.clear_errors()


@pytest.fixture
def mod_files(tmp_path, monkeypatch):
    """A loaded-mod layout with an existing focus file and loc file."""
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
    """The slice of App state `_export` reads."""

    def __init__(self, focuses):
        self.selected = None
        self.focuses = {f.id: f for f in focuses}
        self._tree_id = SimpleNamespace(get=lambda: "TST_focus_tree")
        self._extra_trees = []


def _export(app, **kw):
    return m.App._export.__get__(app, _App)(**kw)


def _export_extra_tree(app, idx, **kw):
    return m.App._export_extra_tree.__get__(app, _App)(idx, **kw)


def _focus(name, x=0, y=0):
    focus = Focus(x, y)
    focus.name = name
    focus.tree_idx = 0
    return focus


def _fail_replace(monkeypatch, message="No space left on device"):
    monkeypatch.setattr(
        "hoi4cm.mod.workspace_files.os.replace",
        lambda *_args: (_ for _ in ()).throw(OSError(message)),
    )


# ── _export ──────────────────────────────────────────────────────────


def test_export_writes_both_tracked_files(dialogs, mod_files):
    app = _App([_focus("TST_root")])

    result = _export(app)

    assert result == str(mod_files.focus)
    tree_text = mod_files.focus.read_text(encoding="utf-8")
    assert "TST_root" in tree_text
    assert "focus_tree" in tree_text
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

    result = _export(app)

    # The whole point of the issue: the user's tree survives a failed write.
    assert result is None
    assert mod_files.focus.read_text(encoding="utf-8") == tree_before
    assert mod_files.loc.read_text(encoding="utf-8-sig") == loc_before
    assert list(mod_files.focus.parent.glob(".*.tmp")) == []
    assert list(mod_files.loc.parent.glob(".*.tmp")) == []


def test_failed_export_reports_instead_of_raising(dialogs, mod_files, monkeypatch):
    app = _App([_focus("TST_root")])
    _fail_replace(monkeypatch, "Permission denied")

    _export(app)

    assert len(dialogs.error) == 1
    assert "05_TST.txt" in dialogs.error[0][1]
    assert "Permission denied" in dialogs.error[0][1]
    # No success dialog claiming an export that never landed.
    assert dialogs.info == []
    # And it is recoverable from the in-app error log.
    assert len(logmod.get_error_entries()) == 1


def test_export_does_not_apply_half_the_pair(dialogs, mod_files, monkeypatch):
    """A .txt that lands followed by a .yml that fails must be rolled back."""
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


# ── _export_extra_tree ───────────────────────────────────────────────


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

    result = _export_extra_tree(app, 1)

    assert result is None
    assert shared.read_text(encoding="utf-8") == "shared_focus = { # real content }\n"
    assert len(dialogs.error) == 1
    assert "MD_shared_focuses.txt" in dialogs.error[0][1]
