"""Recent-mods config write failures surface a one-time UI warning (#197)."""

from __future__ import annotations

import copy

import pytest

from hoi4cm.mod import MOD
from hoi4cm.ui import mod_loading
from hoi4cm.ui.mod_loading import ModLoadingMixin


@pytest.fixture(autouse=True)
def isolate_mod():
    snapshot = copy.deepcopy(MOD.__dict__)
    MOD.loaded = False
    MOD.root = None
    yield
    MOD.__dict__.clear()
    MOD.__dict__.update(snapshot)


class _FakeApp(ModLoadingMixin):
    pass


def test_stale_recent_mod_removal_warns_once_on_failed_save(monkeypatch):
    warnings: list[tuple] = []
    monkeypatch.setattr(
        mod_loading.messagebox,
        "showwarning",
        lambda *args, **kwargs: warnings.append((args, kwargs)),
    )
    monkeypatch.setattr(mod_loading, "report_error", lambda *args, **kwargs: None)
    monkeypatch.setattr(MOD, "save_config", lambda *args, **kwargs: False)
    MOD._recent_mods = ["/gone-one", "/gone-two"]  # type: ignore[attr-defined]

    app = _FakeApp()
    app._load_mod_path("/gone-one")
    app._load_mod_path("/gone-two")

    assert MOD._recent_mods == []  # type: ignore[attr-defined]
    assert len(warnings) == 1
    assert "save settings" in warnings[0][0][1].lower()


def test_successful_recent_mod_save_shows_no_warning(monkeypatch):
    warnings: list[tuple] = []
    monkeypatch.setattr(
        mod_loading.messagebox,
        "showwarning",
        lambda *args, **kwargs: warnings.append((args, kwargs)),
    )
    monkeypatch.setattr(mod_loading, "report_error", lambda *args, **kwargs: None)
    monkeypatch.setattr(MOD, "save_config", lambda *args, **kwargs: True)
    MOD._recent_mods = ["/gone"]  # type: ignore[attr-defined]

    _FakeApp()._load_mod_path("/gone")

    assert warnings == []
