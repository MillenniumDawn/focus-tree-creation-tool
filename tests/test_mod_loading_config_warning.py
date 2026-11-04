"""Recent-mods config write failures surface a one-time UI warning (#197)."""

from __future__ import annotations

from ui_fakes import AppFake

from hoi4cm.ui import mod_loading


def test_stale_recent_mod_removal_warns_once_on_failed_save(monkeypatch):
    warnings: list[tuple] = []
    monkeypatch.setattr(
        mod_loading.messagebox,
        "showwarning",
        lambda *args, **kwargs: warnings.append((args, kwargs)),
    )
    monkeypatch.setattr(mod_loading, "report_error", lambda *args, **kwargs: None)

    app = AppFake()
    app.app_config.recent_mods = ["/gone-one", "/gone-two"]
    monkeypatch.setattr(app, "save_user_config", lambda window_geometry="": False)
    app._load_mod_path("/gone-one")
    app._load_mod_path("/gone-two")

    assert app.app_config.recent_mods == []
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

    app = AppFake()
    app.app_config.recent_mods = ["/gone"]
    monkeypatch.setattr(app, "save_user_config", lambda window_geometry="": True)
    app._load_mod_path("/gone")

    assert warnings == []
