"""Tests for pure fragments in hoi4cm.ui.settings_dialog."""

from __future__ import annotations

import copy
import tkinter as tk
from unittest.mock import MagicMock

import pytest

import hoi4cm.ui.settings_dialog as settings_dialog
from hoi4cm.mod import MOD
from hoi4cm.mod import scan_cache as scan_cache_mod

# ── relativize_to_mod_root ───────────────────────────────────────────


def test_relativize_to_mod_root_strips_prefix_when_under_root():
    assert (
        settings_dialog.relativize_to_mod_root("/mods/mymod/gfx/goals", "/mods/mymod")
        == "gfx/goals"
    )


def test_relativize_to_mod_root_leaves_path_unchanged_outside_root():
    path = "/somewhere/else/gfx/goals"
    assert settings_dialog.relativize_to_mod_root(path, "/mods/mymod") == path


def test_relativize_to_mod_root_does_not_match_sibling_prefix():
    path = "/mods/mymod2/gfx/goals"
    assert settings_dialog.relativize_to_mod_root(path, "/mods/mymod") == path


def test_relativize_to_mod_root_leaves_path_unchanged_when_root_falsy():
    path = "/somewhere/gfx/goals"
    assert settings_dialog.relativize_to_mod_root(path, "") == path
    assert settings_dialog.relativize_to_mod_root(path, None) == path


# ── module-level data ────────────────────────────────────────────────


def test_vanilla_country_tags_are_three_letter_codes():
    assert settings_dialog.VANILLA_COUNTRY_TAGS["GER"] == "Germany"
    assert settings_dialog.VANILLA_COUNTRY_TAGS["SOV"] == "Soviet Union"
    for tag in settings_dialog.VANILLA_COUNTRY_TAGS:
        assert len(tag) == 3 and tag.isupper()


def test_gfx_path_presets_are_name_goals_ideas_triples():
    for name, goals, ideas in settings_dialog.GFX_PATH_PRESETS:
        assert isinstance(name, str) and name
        assert isinstance(goals, str) and goals
        assert isinstance(ideas, str) and ideas


# ── delete event-dim profile ─────────────────────────────────────────

_PROFILE = "custom_pack"
_PROFILE_DIMS = {"country": (420, 176), "news": (794, 330)}


@pytest.fixture
def isolate_mod(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_cache_mod, "STATE_DIR", str(tmp_path / "scan_cache"))
    monkeypatch.setattr(
        settings_dialog, "CONFIG_PATH", str(tmp_path / "hoi4_focus_maker.json")
    )
    snapshot = copy.deepcopy(MOD.__dict__)
    MOD.loaded = False
    MOD.root = None
    MOD.is_md = False
    yield
    MOD.__dict__.clear()
    MOD.__dict__.update(snapshot)


def _stub_mod_app(root: tk.Tk, monkeypatch: pytest.MonkeyPatch) -> tk.Tk:
    root._error_entries = []  # type: ignore[attr-defined]
    root._errlog_btn = MagicMock()  # type: ignore[attr-defined]
    root._show_error_log = lambda *a, **kw: None  # type: ignore[attr-defined]
    root._apply_md_visibility = lambda *a, **kw: None  # type: ignore[attr-defined]
    mb = settings_dialog.messagebox
    monkeypatch.setattr(mb, "showinfo", lambda *a, **kw: None)
    monkeypatch.setattr(mb, "showwarning", lambda *a, **kw: None)
    monkeypatch.setattr(mb, "showerror", lambda *a, **kw: None)
    return root


def _new_toplevels(before: set[tk.Misc], root: tk.Misc) -> list[tk.Toplevel]:
    return [
        w
        for w in root.winfo_children()  # type: ignore[union-attr]
        if w not in before and isinstance(w, tk.Toplevel)
    ]


def _destroy_toplevels(wins: list[tk.Toplevel], root: tk.Misc) -> None:
    for w in wins:
        try:
            w.grab_release()
        except Exception:
            pass
        try:
            w.destroy()
        except Exception:
            pass
    try:
        root.update()  # type: ignore[union-attr]
    except Exception:
        pass


def _find_profile_delete_button(win: tk.Misc, profile_name: str) -> tk.Button | None:
    stack: list[tk.Misc] = [win]
    while stack:
        cur = stack.pop()
        children = list(cur.winfo_children())  # type: ignore[union-attr]
        labels = [c for c in children if isinstance(c, tk.Label)]
        buttons = [c for c in children if isinstance(c, tk.Button)]
        if any(c.cget("text") == profile_name for c in labels) and any(
            c.cget("text") == "✕" for c in buttons
        ):
            return next(b for b in buttons if b.cget("text") == "✕")
        stack.extend(children)
    return None


def _open_settings_with_profile(tk_root, monkeypatch):
    _stub_mod_app(tk_root, monkeypatch)
    MOD.country_tag_names = {}
    MOD.event_dim_profiles = {
        "vanilla": {"country": (210, 176), "news": (397, 165)},
        _PROFILE: dict(_PROFILE_DIMS),
    }
    MOD.event_dim_active_profile = _PROFILE
    save_config = MagicMock()
    monkeypatch.setattr(MOD, "save_config", save_config)
    before: set[tk.Misc] = set(tk_root.winfo_children())
    settings_dialog.open_settings(tk_root)
    tk_root.update()
    wins = _new_toplevels(before, tk_root)
    assert wins, "open_settings did not create a Toplevel"
    save_config.reset_mock()
    return wins, save_config


def test_delete_event_dim_profile_cancel_leaves_profile_and_skips_save(
    tk_root, isolate_mod, monkeypatch
):
    asked: list[tuple] = []

    def _askyesno(*args, **kwargs):
        asked.append((args, kwargs))
        return False

    monkeypatch.setattr(settings_dialog.messagebox, "askyesno", _askyesno)
    wins, save_config = _open_settings_with_profile(tk_root, monkeypatch)
    win = wins[0]
    try:
        button = _find_profile_delete_button(win, _PROFILE)
        assert button is not None
        button.invoke()
        tk_root.update()
        assert asked
        assert _PROFILE in str(asked[0][0])
        assert asked[0][1].get("parent") is win
        assert _PROFILE in MOD.event_dim_profiles
        assert MOD.event_dim_active_profile == _PROFILE
        save_config.assert_not_called()
    finally:
        _destroy_toplevels(wins, tk_root)


def test_delete_event_dim_profile_confirm_removes_profile_and_saves(
    tk_root, isolate_mod, monkeypatch
):
    asked: list[tuple] = []

    def _askyesno(*args, **kwargs):
        asked.append((args, kwargs))
        return True

    monkeypatch.setattr(settings_dialog.messagebox, "askyesno", _askyesno)
    wins, save_config = _open_settings_with_profile(tk_root, monkeypatch)
    win = wins[0]
    try:
        button = _find_profile_delete_button(win, _PROFILE)
        assert button is not None
        button.invoke()
        tk_root.update()
        assert asked
        assert asked[0][1].get("parent") is win
        assert _PROFILE not in MOD.event_dim_profiles
        assert "vanilla" in MOD.event_dim_profiles
        assert MOD.event_dim_active_profile == "vanilla"
        save_config.assert_called_once_with()
    finally:
        _destroy_toplevels(wins, tk_root)
