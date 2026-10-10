"""Regression tests: replacing the document must reset both undo stacks."""

from collections import deque
from typing import Any, cast
from unittest.mock import MagicMock, Mock

import hoi4_content_maker as app_module
from hoi4cm.core.undo import UndoStack
from hoi4cm.models import (
    EditorWorkspace,
    Focus,
    FocusDocument,
    TreeDocument,
    TreeMetadata,
)


class _Var:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value


class _DocumentApp:
    """Headless App double binding the real undo plumbing.

    Tk-facing collaborators are mocked out.
    """

    focuses: FocusDocument
    workspace: EditorWorkspace
    selected: Any
    cv: Mock
    _lines: list
    _grid_item: Any
    _grid_key: Any
    _grid_img: Any
    _extra_trees: list
    _shared_focuses: list
    _joint_focuses: list
    _tree_id: _Var
    _tree_country_tag: str
    _tree_country_name: str
    _tree_country_raw: str
    _tree_focus_prefix: str
    _tree_extras: dict
    _tree_had_wrapper: bool
    _cfp_x: Any
    _cfp_y: Any
    _cfp_x_var: _Var
    _cfp_y_var: _Var
    _canvas_min: list
    _canvas_max: list
    _default_focus_prefix: str
    _last_project_path: Any
    _import_generation: int
    _undo_stack: UndoStack
    _push_undo: Any
    _is_dirty: Mock
    _confirm_discard: Mock
    _begin_document_generation: Mock
    _hide_form: Mock
    _redraw: Mock
    _redraw_now: Mock
    _invalidate_focus_list_structure: Mock
    _invalidate_tree_badges: Mock
    _refresh_tree_meta_panel: Mock
    _refresh_loaded_trees_panel: Mock
    _refresh_prereqs: Mock
    _refresh_mutex: Mock
    _refresh_effects: Mock
    _populate: Mock
    _update_title: Mock
    _hint: Mock
    _detect_and_apply_tag: Mock
    _mark_clean: Mock

    def __init__(self, focuses=()):
        app = self
        self.focuses = FocusDocument(focuses)
        self.workspace = EditorWorkspace(focuses=self.focuses)
        self.selected = None
        self.cv = Mock()
        self._lines = []
        self._grid_item = None
        self._grid_key = None
        self._grid_img = None
        self._extra_trees = []
        self._shared_focuses = []
        self._joint_focuses = []
        self._tree_id = _Var("OLD_tree")
        self._tree_country_tag = "OLD"
        self._tree_country_name = ""
        self._tree_country_raw = ""
        self._tree_focus_prefix = "OLD_"
        self._tree_extras = {}
        self._tree_had_wrapper = True
        self._cfp_x = None
        self._cfp_y = None
        self._cfp_x_var = _Var("")
        self._cfp_y_var = _Var("")
        self._canvas_min = [0, 0]
        self._canvas_max = [9, 9]
        self._default_focus_prefix = "OLD_"
        self._last_project_path = None
        self._import_generation = 0
        self._undo_stack = UndoStack()
        self._push_undo = lambda *args, **kwargs: app_module.App._push_undo(
            cast(app_module.App, app), *args, **kwargs
        )
        self._install_workspace = lambda workspace: app_module.App._install_workspace(
            cast(app_module.App, app), workspace
        )
        self._is_dirty = Mock(return_value=False)
        self._confirm_discard = Mock(return_value=True)
        self._begin_document_generation = Mock()
        self._hide_form = Mock()
        self._redraw = Mock()
        self._redraw_now = Mock()
        self._invalidate_focus_list_structure = Mock()
        self._invalidate_tree_badges = Mock()
        self._refresh_tree_meta_panel = Mock()
        self._refresh_loaded_trees_panel = Mock()
        self._refresh_prereqs = Mock()
        self._refresh_mutex = Mock()
        self._refresh_effects = Mock()
        self._populate = Mock()
        self._update_title = Mock()
        self._hint = Mock()
        self._detect_and_apply_tag = Mock()
        self._mark_clean = Mock()


def _headless_app(monkeypatch, focuses=()):
    monkeypatch.setattr(app_module.MOD, "root", None)
    return _DocumentApp(focuses)


def _workspace(tree_id="NEW_tree", focuses=()):
    """A fresh workspace whose FocusDocument is a different object."""
    return EditorWorkspace(
        focuses=FocusDocument(focuses),
        main_tree=TreeDocument(
            metadata=TreeMetadata(
                tree_id=tree_id, country_tag="NEW", focus_prefix="NEW_"
            )
        ),
    )


def _seed_history(app, *, with_redo=False):
    """Push two sparse undo entries; ``with_redo`` moves one to the redo stack."""
    app_module.App._push_undo(cast(app_module.App, app), "add focus", touched_ids=())
    created = app.focuses.new_focus()
    created.name = "seed_created"
    app.focuses.add(created)
    app_module.App._push_undo(
        cast(app_module.App, app), "edit seed", touched_ids=(created.id,)
    )
    created.name = "seed_renamed"
    if with_redo:
        app_module.App._undo(cast(app_module.App, app))
    return created


def _assert_stacks_empty(app):
    assert len(app._undo_stack) == 0
    assert app._undo_stack.undo(app.focuses, Focus.from_dict) is None
    assert app._undo_stack.redo(app.focuses, Focus.from_dict) is None


def _assert_new_focus_survives_undo_and_redo(app, new_focus):
    app_module.App._undo(cast(app_module.App, app))
    assert app.focuses[new_focus.id] is new_focus
    app_module.App._redo(cast(app_module.App, app))
    assert app.focuses[new_focus.id] is new_focus


# ── _install_workspace (Load Project + autosave restore) ────────────


def test_install_workspace_clears_undo_and_redo_history(monkeypatch):
    old = Focus(id=1)
    old.name = "OLD_focus"
    app = _headless_app(monkeypatch, [old])
    _seed_history(app, with_redo=True)
    new_ws = _workspace(focuses=[Focus(id=1)])
    new_focus = next(iter(new_ws.focuses.values()))

    app_module.App._install_workspace(cast(app_module.App, app), new_ws)

    assert app.workspace is new_ws
    assert app.focuses is new_ws.focuses
    _assert_new_focus_survives_undo_and_redo(app, new_focus)
    _assert_stacks_empty(app)


def test_undo_tracks_edits_again_after_install(monkeypatch):
    app = _headless_app(monkeypatch)
    app_module.App._install_workspace(
        cast(app_module.App, app), _workspace(focuses=[Focus(id=1)])
    )
    new_focus = next(iter(app.focuses.values()))
    original_name = new_focus.name

    app_module.App._push_undo(
        cast(app_module.App, app), "edit new", touched_ids=(new_focus.id,)
    )
    new_focus.name = "renamed_after_install"
    app_module.App._undo(cast(app_module.App, app))
    assert app.focuses[new_focus.id].name == original_name

    app_module.App._redo(cast(app_module.App, app))
    assert app.focuses[new_focus.id].name == "renamed_after_install"


# ── Load Project (_load → _install_workspace) ───────────────────────


def _patch_load_infrastructure(monkeypatch):
    monkeypatch.setattr(app_module, "progress_modal", lambda *_a, **_kw: Mock())
    monkeypatch.setattr(app_module, "clear_workspace_autosave", Mock())
    monkeypatch.setattr(app_module.messagebox, "showwarning", Mock())


def run_bg_sync(_app, work, on_done, **_kw):
    on_done(work())


def run_bg_fails(_app, _work, _on_done, on_error, **_kw):
    on_error(ValueError("corrupt project"))


def test_successful_load_clears_undo_and_redo_history(monkeypatch):
    app = _headless_app(monkeypatch, [Focus(id=1)])
    _seed_history(app, with_redo=True)
    new_ws = _workspace(focuses=[Focus(id=1)])
    new_focus = next(iter(new_ws.focuses.values()))
    _patch_load_infrastructure(monkeypatch)
    monkeypatch.setattr(
        app_module.filedialog, "askopenfilename", Mock(return_value="/proj.json")
    )
    monkeypatch.setattr(app_module, "read_project", Mock(return_value=new_ws))
    monkeypatch.setattr(app_module, "run_bg", run_bg_sync)

    app_module.App._load(cast(app_module.App, app))

    assert app.workspace is new_ws
    assert app.focuses is new_ws.focuses
    _assert_new_focus_survives_undo_and_redo(app, new_focus)
    _assert_stacks_empty(app)


def test_cancelled_load_file_picker_preserves_history(monkeypatch):
    app = _headless_app(monkeypatch, [Focus(id=1)])
    created = _seed_history(app)
    ask_open = Mock(return_value="")
    monkeypatch.setattr(app_module.filedialog, "askopenfilename", ask_open)

    app_module.App._load(cast(app_module.App, app))

    ask_open.assert_called_once()
    app._begin_document_generation.assert_not_called()
    assert len(app._undo_stack) == 2
    assert app.focuses[created.id].name == "seed_renamed"
    # The surviving entry still applies to the unchanged old document.
    result = app._undo_stack.undo(app.focuses, Focus.from_dict)
    assert result is not None
    assert result[0] == "edit seed"
    assert app.focuses[created.id].name == "seed_created"


def test_declined_discard_preserves_history(monkeypatch):
    app = _headless_app(monkeypatch, [Focus(id=1)])
    _seed_history(app)
    app._confirm_discard = Mock(return_value=False)
    ask_open = Mock(side_effect=AssertionError("picker should not open"))
    monkeypatch.setattr(app_module.filedialog, "askopenfilename", ask_open)

    app_module.App._load(cast(app_module.App, app))

    app._confirm_discard.assert_called_once_with(action="loading")
    ask_open.assert_not_called()
    app._begin_document_generation.assert_not_called()
    assert len(app._undo_stack) == 2


def test_failed_load_preserves_history_and_old_document(monkeypatch):
    app = _headless_app(monkeypatch, [Focus(id=1)])
    original_ids = set(app.focuses)
    created = _seed_history(app)
    old_workspace = app.workspace
    _patch_load_infrastructure(monkeypatch)
    monkeypatch.setattr(
        app_module.filedialog, "askopenfilename", Mock(return_value="/proj.json")
    )
    monkeypatch.setattr(
        app_module, "read_project", Mock(side_effect=ValueError("corrupt project"))
    )
    monkeypatch.setattr(app_module, "run_bg", run_bg_fails)
    monkeypatch.setattr(app_module, "report_error", Mock())

    app_module.App._load(cast(app_module.App, app))

    assert app.workspace is old_workspace
    assert set(app.focuses) == original_ids | {created.id}
    assert app.focuses[created.id].name == "seed_renamed"
    assert len(app._undo_stack) == 2
    # The surviving entries still apply to the unchanged old document.
    app_module.App._undo(cast(app_module.App, app))
    assert app.focuses[created.id].name == "seed_created"


# ── Autosave restore (_maybe_offer_autosave_restore) ────────────────


def _patch_autosave_offer(monkeypatch, tmp_path, workspace, *, answer):
    """Patch the autosave offer for one ``answer``; returns ``(ask, cleared)``."""
    path = str(tmp_path / "autosave.json")
    monkeypatch.setattr(app_module, "workspace_autosave_path", lambda: path)
    monkeypatch.setattr(app_module.os.path, "isfile", Mock(return_value=True))
    monkeypatch.setattr(app_module, "read_project", Mock(return_value=workspace))
    ask = Mock(return_value=answer)
    monkeypatch.setattr(app_module.messagebox, "askyesnocancel", ask)
    cleared = []
    monkeypatch.setattr(
        app_module, "clear_workspace_autosave", lambda p: cleared.append(p)
    )
    return ask, cleared


def test_autosave_restore_clears_undo_and_redo_history(monkeypatch, tmp_path):
    app = _headless_app(monkeypatch, [Focus(id=1)])
    _seed_history(app, with_redo=True)
    saved_ws = _workspace(focuses=[Focus(id=1)])
    new_focus = next(iter(saved_ws.focuses.values()))
    _patch_autosave_offer(monkeypatch, tmp_path, saved_ws, answer=True)

    app_module.App._maybe_offer_autosave_restore(cast(app_module.App, app))

    assert app.workspace is saved_ws
    assert app.focuses is saved_ws.focuses
    _assert_new_focus_survives_undo_and_redo(app, new_focus)
    _assert_stacks_empty(app)


def test_autosave_restore_declined_preserves_history(monkeypatch, tmp_path):
    app = _headless_app(monkeypatch, [Focus(id=1)])
    _seed_history(app)
    old_workspace = app.workspace
    _patch_autosave_offer(monkeypatch, tmp_path, _workspace(), answer=False)

    app_module.App._maybe_offer_autosave_restore(cast(app_module.App, app))

    assert app.workspace is old_workspace
    app._begin_document_generation.assert_not_called()
    assert len(app._undo_stack) == 2


def test_autosave_restore_cancelled_preserves_history(monkeypatch, tmp_path):
    app = _headless_app(monkeypatch, [Focus(id=1)])
    _seed_history(app)
    old_workspace = app.workspace
    _patch_autosave_offer(monkeypatch, tmp_path, _workspace(), answer=None)

    app_module.App._maybe_offer_autosave_restore(cast(app_module.App, app))

    assert app.workspace is old_workspace
    app._begin_document_generation.assert_not_called()
    assert len(app._undo_stack) == 2


# ── New Tree dialog callback ────────────────────────────────────────


def _dialog_app(root, monkeypatch):
    """Tk root dressed as an App for the New Tree dialog callback."""
    app = cast(Any, root)
    old = Focus(id=1)
    old.name = "OLD_focus"
    app.focuses = FocusDocument([old])
    app.selected = None
    app.cv = MagicMock()
    app._lines = set()
    app._grid_item = None
    app._grid_key = None
    app._grid_img = None
    app._tree_id = app_module.tk.StringVar(master=root)
    app._default_focus_prefix = "OLD_"
    app._tree_country_tag = "OLD"
    app._undo_stack = UndoStack()
    app._push_undo = lambda *args, **kwargs: app_module.App._push_undo(
        cast(app_module.App, app), *args, **kwargs
    )
    app._is_dirty = MagicMock(return_value=False)
    for name in (
        "_begin_document_generation",
        "_hide_form",
        "_redraw",
        "_redraw_now",
        "_invalidate_focus_list_structure",
        "_update_title",
        "_hint",
    ):
        setattr(app, name, MagicMock())
    monkeypatch.setattr(app_module.messagebox, "askyesnocancel", lambda *a, **kw: True)
    monkeypatch.setattr(app_module.messagebox, "showinfo", Mock())
    monkeypatch.setattr(app_module.messagebox, "showwarning", Mock())
    return app


def _widgets_in_order(widget):
    """Yield the widget tree breadth-first (creation order per level)."""
    queue = deque([widget])
    while queue:
        current = queue.popleft()
        yield current
        queue.extend(current.winfo_children())


def _open_new_tree_dialog(app):
    app_module.App._new_tree_dialog(cast(app_module.App, app))
    return next(
        child
        for child in app.winfo_children()
        if isinstance(child, app_module.tk.Toplevel)
    )


def _click(window, text):
    for widget in _widgets_in_order(window):
        if isinstance(widget, app_module.tk.Button) and widget.cget("text") == text:
            widget.invoke()
            return
    raise AssertionError(f"button {text!r} not found in dialog")


def _type_tag(window):
    for widget in _widgets_in_order(window):
        if isinstance(widget, app_module.tk.Entry):
            widget.insert(0, "NEW")
            return
    raise AssertionError("no tag entry found in dialog")


def test_new_tree_cancel_preserves_history(tk_root, monkeypatch):
    app = _dialog_app(tk_root, monkeypatch)
    created = _seed_history(app)
    window = _open_new_tree_dialog(app)

    _click(window, "Cancel")

    assert app.focuses[created.id].name == "seed_renamed"
    assert len(app._undo_stack) == 2
    # The surviving entries still apply to the unchanged old document.
    app_module.App._undo(cast(app_module.App, app))
    assert app.focuses[created.id].name == "seed_created"


def test_new_tree_missing_tag_preserves_history(tk_root, monkeypatch):
    app = _dialog_app(tk_root, monkeypatch)
    original_ids = set(app.focuses)
    created = _seed_history(app)
    warning = Mock()
    monkeypatch.setattr(app_module.messagebox, "showwarning", warning)
    window = _open_new_tree_dialog(app)

    _click(window, "Create Tree")

    warning.assert_called_once()
    assert len(app._undo_stack) == 2
    assert set(app.focuses) == original_ids | {created.id}


def test_new_tree_cancelled_unsaved_changes_preserves_history(tk_root, monkeypatch):
    app = _dialog_app(tk_root, monkeypatch)
    original_ids = set(app.focuses)
    created = _seed_history(app, with_redo=True)
    ask = Mock(return_value=None)
    monkeypatch.setattr(app_module.messagebox, "askyesnocancel", ask)
    app._is_dirty = MagicMock(return_value=True)
    window = _open_new_tree_dialog(app)
    _type_tag(window)

    _click(window, "Create Tree")

    ask.assert_called_once()
    app._begin_document_generation.assert_not_called()
    assert set(app.focuses) == original_ids | {created.id}
    # Both stacks are intact and still apply to the unchanged old document.
    assert len(app._undo_stack) == 1
    result = app._undo_stack.redo(app.focuses, Focus.from_dict)
    assert result is not None
    assert result[0] == "edit seed"
    assert app.focuses[created.id].name == "seed_renamed"
    app_module.App._undo(cast(app_module.App, app))
    assert app.focuses[created.id].name == "seed_created"


def test_new_tree_failed_save_preserves_history(tk_root, monkeypatch):
    app = _dialog_app(tk_root, monkeypatch)
    original_ids = set(app.focuses)
    created = _seed_history(app, with_redo=True)
    ask = Mock(return_value=True)
    monkeypatch.setattr(app_module.messagebox, "askyesnocancel", ask)
    app._is_dirty = MagicMock(return_value=True)
    app._save = Mock(return_value=False)
    window = _open_new_tree_dialog(app)
    _type_tag(window)

    _click(window, "Create Tree")

    ask.assert_called_once()
    app._save.assert_called_once_with()
    app._begin_document_generation.assert_not_called()
    assert set(app.focuses) == original_ids | {created.id}
    # Both stacks are intact and still apply to the unchanged old document.
    assert len(app._undo_stack) == 1
    result = app._undo_stack.redo(app.focuses, Focus.from_dict)
    assert result is not None
    assert result[0] == "edit seed"
    assert app.focuses[created.id].name == "seed_renamed"
    app_module.App._undo(cast(app_module.App, app))
    assert app.focuses[created.id].name == "seed_created"


def test_new_tree_create_clears_undo_and_redo_history(tk_root, monkeypatch):
    app = _dialog_app(tk_root, monkeypatch)
    _seed_history(app, with_redo=True)
    window = _open_new_tree_dialog(app)
    _type_tag(window)

    _click(window, "Create Tree")

    assert len(app.focuses) == 0
    _assert_stacks_empty(app)
    app_module.App._undo(cast(app_module.App, app))
    assert len(app.focuses) == 0
    app_module.App._redo(cast(app_module.App, app))
    assert len(app.focuses) == 0


def test_new_tree_create_clears_history_even_without_document_clear(
    tk_root, monkeypatch
):
    # Skips the whole-document clear block: seeded stacks, empty clean document.
    app = _dialog_app(tk_root, monkeypatch)
    _seed_history(app, with_redo=True)
    app.focuses.clear()

    window = _open_new_tree_dialog(app)
    _type_tag(window)

    assert len(app.focuses) == 0
    assert not app._is_dirty()
    _click(window, "Create Tree")

    assert len(app.focuses) == 0
    _assert_stacks_empty(app)
    app_module.App._undo(cast(app_module.App, app))
    app_module.App._redo(cast(app_module.App, app))
    assert len(app.focuses) == 0
