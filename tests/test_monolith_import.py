"""Integration tests for the monolith's focus-tree import shell."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import hoi4_content_maker as m
import hoi4cm.focus_tree.parse as parse_module
from hoi4cm.models import Focus, FocusDocument


def _shell():
    old_focus = Focus()
    old_focus.name = "OLD_focus"
    app = SimpleNamespace(
        cv=SimpleNamespace(delete=Mock()),
        focuses=FocusDocument([old_focus]),
        selected=old_focus,
        _lines=set(),
        _grid_item=None,
        _grid_key=None,
        _grid_img=None,
        _extra_trees=[],
        _tree_id=SimpleNamespace(set=Mock()),
        _cfp_x_var=SimpleNamespace(set=Mock()),
        _cfp_y_var=SimpleNamespace(set=Mock()),
        _default_focus_prefix="",
        _tree_country_tag="OLD",
        _begin_document_generation=Mock(),
        _reset_canvas_bounds=Mock(),
        _invalidate_tree_badges=Mock(),
        _refresh_loaded_trees_panel=Mock(),
        _hide_form=Mock(),
        _update_title=Mock(),
        _detect_and_apply_tag=Mock(),
        _refresh_tree_meta_panel=Mock(),
        _redraw=Mock(),
        _invalidate_focus_list_structure=Mock(),
        _fit_all=Mock(),
        _import_generation=0,
        _confirm_discard=Mock(return_value=True),
        _push_undo=Mock(),
    )
    return app, old_focus


def _patch_import_ui(monkeypatch, warnings, infos):
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_kwargs: "new.txt")
    monkeypatch.setattr(
        m,
        "progress_modal",
        lambda *_args, **_kwargs: SimpleNamespace(close=lambda: None),
    )
    monkeypatch.setattr(
        m.messagebox,
        "showwarning",
        lambda *args, **_kwargs: warnings.append(args),
    )
    monkeypatch.setattr(
        m.messagebox,
        "showinfo",
        lambda *args, **_kwargs: infos.append(args),
    )

    def run_background(_app, work, on_done, on_error=None, **_kwargs):
        try:
            result = work()
        except Exception as exc:  # noqa: BLE001
            if on_error is None:
                raise
            on_error(exc)
        else:
            on_done(result)

    monkeypatch.setattr(m, "run_bg", run_background)


def _write_tree(path):
    path.write_text(
        "focus_tree = {\n"
        "\tid = NEW_tree\n"
        "\tfocus = {\n"
        "\t\tid = TST_new_focus\n"
        "\t\tx = 0\n"
        "\t\ty = 0\n"
        "\t}\n"
        "}\n",
        encoding="utf-8",
    )


def _configure_mod(monkeypatch, tmp_path, old_focus, old_loc):
    focus_path = tmp_path / "new.txt"
    _write_tree(focus_path)
    loc_path = tmp_path / "localisation" / "english" / "MD_focus_TST_l_english.yml"
    loc_path.parent.mkdir(parents=True)
    loc_path.write_text("l_english:\n", encoding="utf-8")
    monkeypatch.setattr(m, "detect_loc_file", lambda *_args, **_kwargs: str(loc_path))
    monkeypatch.setattr(m.MOD, "loaded", True)
    monkeypatch.setattr(m.MOD, "root", str(tmp_path))
    monkeypatch.setattr(m.MOD, "loc_language", "english")
    monkeypatch.setattr(m.MOD, "edit_focus_file", str(old_focus))
    monkeypatch.setattr(m.MOD, "edit_loc_file", str(old_loc))
    return focus_path, loc_path


def test_import_budget_failure_preserves_targets_and_model(tmp_path, monkeypatch):
    old_focus = tmp_path / "old.txt"
    old_loc = tmp_path / "old.yml"
    app, old_model_focus = _shell()
    focus_path, _loc_path = _configure_mod(monkeypatch, tmp_path, old_focus, old_loc)
    warnings: list[tuple[Any, ...]] = []
    infos: list[tuple[Any, ...]] = []
    _patch_import_ui(monkeypatch, warnings, infos)
    monkeypatch.setattr(
        m.filedialog, "askopenfilename", lambda **_kwargs: str(focus_path)
    )
    monkeypatch.setattr(parse_module, "MAX_RAW_BLOCK_RESCANS", 0)

    m.App._import_txt(cast(m.App, app))

    assert m.MOD.edit_focus_file == str(old_focus)
    assert m.MOD.edit_loc_file == str(old_loc)
    assert list(app.focuses.values()) == [old_model_focus]
    assert warnings and "parse budget exhausted" in warnings[0][1]
    assert infos == []


def test_import_success_assigns_targets_after_build(tmp_path, monkeypatch):
    old_focus = tmp_path / "old.txt"
    old_loc = tmp_path / "old.yml"
    app, _old_model_focus = _shell()
    focus_path, loc_path = _configure_mod(monkeypatch, tmp_path, old_focus, old_loc)
    warnings: list[tuple[Any, ...]] = []
    infos: list[tuple[Any, ...]] = []
    _patch_import_ui(monkeypatch, warnings, infos)
    monkeypatch.setattr(
        m.filedialog, "askopenfilename", lambda **_kwargs: str(focus_path)
    )

    m.App._import_txt(cast(m.App, app))

    assert m.MOD.edit_focus_file == str(focus_path)
    assert m.MOD.edit_loc_file == str(loc_path)
    assert [focus.name for focus in app.focuses.values()] == ["TST_new_focus"]
    assert warnings == []
    assert infos
