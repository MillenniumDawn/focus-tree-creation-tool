"""App-owned settings retain the existing config-file contract."""

from dataclasses import asdict
from types import SimpleNamespace
from typing import cast

import pytest

import hoi4_content_maker as main
from hoi4cm.core import config
from hoi4cm.core.app_config import AppConfig
from hoi4cm.mod.index import ModIndex


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(path))
    return path


def test_settings_round_trip_keeps_unknown_keys_and_falsy_values(config_path):
    assert config.cfg_save({"unknown_setting": {"keep": True}})
    settings = AppConfig(
        path_goals="",
        path_ideas_gfx="gfx/custom_ideas",
        path_event_pictures="gfx/custom_events",
        event_dim_profiles={"custom": {"country": [48, 24], "news": [96, 48]}},
        event_dim_active_profile="custom",
        custom_mod_path="mods/custom",
        custom_gfx_dirs=["gfx/extra"],
        country_tag_names={"TST": "Test"},
        loc_token_style="dot",
        loc_language="french",
        md_mode_override=False,
        sidebar_refresh_skip=False,
        window_geometry="900x600+10+20",
        recent_mods=["mods/one", "mods/two"],
    )

    assert settings.save(last_mod_path="mods/custom")
    assert asdict(AppConfig.load()) == asdict(settings)
    assert config.cfg_load()["unknown_setting"] == {"keep": True}
    assert config.cfg_load()["last_mod_path"] == "mods/custom"


def test_settings_save_preserves_geometry_until_explicitly_updated(config_path):
    settings = AppConfig(window_geometry="900x600+10+20")
    assert settings.save()
    settings.loc_language = "french"
    assert settings.save()
    assert AppConfig.load().window_geometry == "900x600+10+20"

    assert settings.save(window_geometry="1200x800+30+40")
    assert settings.window_geometry == "1200x800+30+40"
    assert AppConfig.load().window_geometry == "1200x800+30+40"


def test_app_save_config_does_not_persist_edit_targets(config_path, monkeypatch):
    settings = AppConfig()
    index = ModIndex()
    index.loaded = True
    index.root = "mods/custom"
    flushes = []
    monkeypatch.setattr(
        index.graphics_catalog, "flush_cache", lambda: flushes.append(True)
    )
    host = SimpleNamespace(
        app_config=settings,
        index=index,
        edit_focus_file="private/tree.txt",
        edit_loc_file="private/loc.yml",
    )

    assert main.App.save_user_config(cast(main.App, host), "900x600")
    payload = config.cfg_load()
    assert payload["last_mod_path"] == "mods/custom"
    assert payload["window_geometry"] == "900x600"
    assert "edit_focus_file" not in payload
    assert "edit_loc_file" not in payload
    assert flushes == [True]


def test_adoption_keeps_the_completed_scan_settings(tmp_path):
    settings = AppConfig(loc_language="french", md_mode_override=False).scan_settings(
        use_cache=False
    )
    index = ModIndex()
    candidate = index.new_scan_candidate(settings)
    assert candidate.scan(str(tmp_path)) is True

    index.adopt_scan(candidate)

    assert index._scan_settings() == settings
    assert index.use_cache is False
    assert index._cache is None
