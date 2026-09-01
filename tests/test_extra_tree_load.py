"""Single extra-tree load uses the same run_bg shape as _import_txt."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import hoi4_content_maker as m
from hoi4cm.focus_tree.parse import EmptyFocusTreeError
from hoi4cm.models import FocusDocument


def _shell():
    app = SimpleNamespace(
        _extra_trees=[],
        _shared_focuses=[],
        _joint_focuses=[],
        focuses=FocusDocument(),
        _tree_country_tag="",
        _invalidate_tree_badges=Mock(),
        _refresh_tree_meta_panel=Mock(),
        _refresh_loaded_trees_panel=Mock(),
        _redraw=Mock(),
        _invalidate_focus_list_structure=Mock(),
        _fit_all=Mock(),
    )
    app._install_extra_tree = m.App._install_extra_tree.__get__(app)
    return app


def _patch_run_bg(monkeypatch, calls: list[dict[str, Any]]):
    def run_background(_app, work, on_done, on_error=None, **kwargs):
        calls.append(kwargs)
        try:
            on_done(work())
        except EmptyFocusTreeError as exc:
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
