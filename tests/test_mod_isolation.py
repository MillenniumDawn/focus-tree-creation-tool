"""The app's index, config, and image cache have separate ownership."""

import builtins
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

import pytest
from ui_fakes import AppFake

from hoi4cm.core.app_config import AppConfig
from hoi4cm.mod.index import ModIndex


def test_apps_do_not_share_index_settings_or_image_handles() -> None:
    first = AppFake()
    second = AppFake()
    image = object()
    first.images.images["sentinel"] = image
    first.index.event_ids["nested"] = ["nested.1"]
    first.index.failed_steps.append("Events")
    first.index.unparsable_files.append("bad.txt")
    first.index.graphics_catalog.last_metrics.gfx_reads += 1
    first.app_config.custom_gfx_dirs.append("custom")
    first.app_config.event_dim_profiles["test"] = {}
    first.edit_ideas_file = "first.txt"

    assert second.images.images.get("sentinel") is None
    assert second.index.event_ids == {}
    assert second.index.failed_steps == []
    assert second.index.unparsable_files == []
    assert second.index.graphics_catalog is not first.index.graphics_catalog
    assert second.index.graphics_catalog.last_metrics.gfx_reads == 0
    assert second.app_config.custom_gfx_dirs == []
    assert "test" not in second.app_config.event_dim_profiles
    assert second.edit_ideas_file == ""
    second.images.clear()
    assert first.images.images["sentinel"] is image


def test_scan_settings_are_a_detached_immutable_snapshot():
    config = AppConfig()
    config.custom_gfx_dirs.append("before")
    config.loc_language = "french"
    settings = config.scan_settings()
    candidate = ModIndex().new_scan_candidate(settings)
    config.custom_gfx_dirs.append("after")
    config.loc_language = "english"

    assert candidate._scan_settings().custom_gfx_dirs == ("before",)
    assert candidate._scan_settings().loc_language == "french"
    with pytest.raises(FrozenInstanceError):
        settings.__setattr__("loc_language", "german")
    assert not hasattr(candidate, "save_config")
    assert not hasattr(candidate, "get_image")
    assert not hasattr(candidate, "sprite_imgs")
    assert not hasattr(candidate, "edit_ideas_file")


def test_scan_candidate_has_no_ui_handles_or_pillow_imports(tmp_path, monkeypatch):
    app = AppFake()
    app.index.use_cache = False
    candidate = app.index.new_scan_candidate(
        app.app_config.scan_settings(use_cache=False)
    )
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith(("tkinter", "PIL")) or name == "hoi4cm.core.image":
            raise AssertionError(f"worker tried to import {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(candidate.scan, str(tmp_path)).result(timeout=5) is True
    assert candidate.loaded
    assert not app.index.loaded
    assert candidate.graphics_catalog is not app.index.graphics_catalog
    assert all(value is not app.images for value in vars(candidate).values())
    assert all(value is not app.app_config for value in vars(candidate).values())
