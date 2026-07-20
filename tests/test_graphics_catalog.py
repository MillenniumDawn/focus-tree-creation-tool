import json
import os
import sqlite3

import pytest

from hoi4cm.core.paths import read_file
from hoi4cm.mod import scan_cache
from hoi4cm.mod.graphics_catalog import FileStamp, GraphicsCatalog, GraphicsScanConfig


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_cache, "STATE_DIR", str(tmp_path / "state"))


@pytest.fixture
def graphics_tree(tmp_path):
    interface = tmp_path / "interface"
    goals = tmp_path / "gfx" / "interface" / "goals"
    ideas = tmp_path / "gfx" / "interface" / "ideas"
    decisions = tmp_path / "gfx" / "decisions"
    interface.mkdir()
    goals.mkdir(parents=True)
    ideas.mkdir(parents=True)
    decisions.mkdir(parents=True)
    (interface / "assets.gfx").write_text(
        'spriteType = { name = "GFX_focus_declared" '
        'texturefile = "gfx/interface/goals/declared.dds" }\n'
    )
    (goals / "disk_focus.dds").write_bytes(b"focus")
    (ideas / "disk_idea.png").write_bytes(b"idea")
    (decisions / "disk_decision.tga").write_bytes(b"decision")
    return tmp_path


def _config(**overrides):
    values = {
        "path_goals": "gfx/interface/goals",
        "path_ideas_gfx": "gfx/interface/ideas",
        "custom_gfx_dirs": (),
    }
    values.update(overrides)
    return GraphicsScanConfig(**values)


def test_warm_catalog_load_restats_without_walking_or_reparsing(graphics_tree):
    first = GraphicsCatalog()
    cold_maps = first.refresh(str(graphics_tree), _config(), read_text=read_file)
    assert first.last_metrics.cache_status == "miss"
    assert first.last_metrics.directory_listings > 0
    assert first.last_metrics.image_stats == 3
    assert first.last_metrics.gfx_reads == 1

    second = GraphicsCatalog()
    warm_maps = second.refresh(str(graphics_tree), _config(), read_text=read_file)
    assert second.last_metrics.cache_status == "hit"
    assert second.last_metrics.directory_listings == 0
    # Warm loads restat the known images (cheap) so an in-place overwrite is
    # caught, but they never rewalk directories or reparse .gfx files.
    assert second.last_metrics.image_stats == 3
    assert second.last_metrics.gfx_reads == 0
    assert warm_maps == cold_maps


def test_event_pictures_dir_outside_gfx_is_catalogued(graphics_tree):
    events = graphics_tree / "event_pictures"
    events.mkdir()
    (events / "war_scene.dds").write_bytes(b"scene")

    catalog = GraphicsCatalog()
    catalog.refresh(
        str(graphics_tree),
        _config(path_event_pictures="event_pictures"),
        read_text=read_file,
    )

    found = [catalog.path_for(asset) for asset in catalog.query(under=str(events))]
    assert found == [str(events / "war_scene.dds")]


def test_in_place_image_overwrite_invalidates_cached_snapshot(graphics_tree):
    first = GraphicsCatalog()
    first.refresh(str(graphics_tree), _config(), read_text=read_file)
    before = first.resolve("GFX_focus_disk_focus")

    focus_image = graphics_tree / "gfx" / "interface" / "goals" / "disk_focus.dds"
    focus_image.write_bytes(b"focus-overwritten-with-more-bytes")

    second = GraphicsCatalog()
    second.refresh(str(graphics_tree), _config(), read_text=read_file)

    assert second.last_metrics.cache_status == "miss"
    after = second.resolve("GFX_focus_disk_focus")
    assert before is not None and after is not None
    assert after.stamp != before.stamp


def test_resolve_reports_the_current_image_stamp(graphics_tree):
    catalog = GraphicsCatalog()
    catalog.refresh(str(graphics_tree), _config(), read_text=read_file)
    focus_image = graphics_tree / "gfx" / "interface" / "goals" / "disk_focus.dds"
    stat = os.stat(focus_image)

    asset = catalog.resolve("GFX_focus_disk_focus")

    assert asset is not None
    assert asset.stamp == FileStamp(stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)


def test_declared_dds_uses_fallback_image_stamp(graphics_tree):
    fallback = graphics_tree / "gfx" / "interface" / "goals" / "declared.png"
    fallback.write_bytes(b"fallback")
    catalog = GraphicsCatalog()
    catalog.refresh(str(graphics_tree), _config(), read_text=read_file)

    asset = catalog.resolve("GFX_focus_declared")

    assert asset is not None
    stat = fallback.stat()
    assert asset.stamp == FileStamp(stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)

    fallback.write_bytes(b"new fallback with a different size")
    catalog.note_written(str(fallback), read_text=read_file)
    updated = catalog.resolve("GFX_focus_declared")

    assert updated is not None
    assert updated.stamp != asset.stamp


@pytest.mark.parametrize(
    ("setting", "source_id"),
    (
        ("path_goals", "goals"),
        ("path_ideas_gfx", "ideas"),
        ("path_event_pictures", "events"),
    ),
)
def test_incremental_changes_keep_in_mod_configured_source(
    graphics_tree, setting, source_id
):
    image_root = graphics_tree / "custom_assets" / source_id
    image_root.mkdir(parents=True)
    configured = str(image_root.relative_to(graphics_tree))
    catalog = GraphicsCatalog()
    catalog.refresh(
        str(graphics_tree), _config(**{setting: configured}), read_text=read_file
    )
    added = image_root / "added.dds"
    added.write_bytes(b"added")

    assert catalog.note_written(str(added), read_text=read_file) is not None
    assets = catalog.query(under=str(image_root))
    assert len(assets) == 1
    assert assets[0].source_id == source_id

    added.unlink()
    assert catalog.note_deleted(str(added)) is not None
    assert catalog.query(under=str(image_root)) == ()


@pytest.mark.parametrize(
    ("setting", "source_id"),
    (("path_goals", "goals"), ("path_ideas_gfx", "ideas")),
)
def test_incremental_changes_keep_external_configured_source(
    graphics_tree, tmp_path, setting, source_id
):
    image_root = tmp_path / f"external_{source_id}"
    image_root.mkdir()
    catalog = GraphicsCatalog()
    catalog.refresh(
        str(graphics_tree), _config(**{setting: str(image_root)}), read_text=read_file
    )
    added = image_root / "added.dds"
    added.write_bytes(b"added")

    assert catalog.note_written(str(added), read_text=read_file) is not None
    assets = catalog.query(under=str(image_root))
    assert len(assets) == 1
    assert assets[0].source_id == source_id

    added.unlink()
    assert catalog.note_deleted(str(added)) is not None
    assert catalog.query(under=str(image_root)) == ()


def test_cached_graphics_paths_are_relative(graphics_tree):
    catalog = GraphicsCatalog()
    catalog.refresh(str(graphics_tree), _config(), read_text=read_file)

    database = scan_cache.database_path(str(graphics_tree))
    with sqlite3.connect(database) as connection:
        encoded = connection.execute("SELECT data FROM graphics_snapshot").fetchone()[0]
    assert str(graphics_tree) not in encoded
    data = json.loads(encoded)
    assert all(
        not item["path"]["relative_path"].startswith("/") for item in data["images"]
    )


def test_catalog_query_uses_loaded_snapshot(graphics_tree, monkeypatch):
    catalog = GraphicsCatalog()
    catalog.refresh(str(graphics_tree), _config(), read_text=read_file)
    monkeypatch.setattr(
        "hoi4cm.mod.graphics_catalog.os.scandir",
        lambda _path: pytest.fail("query must not scan the filesystem"),
    )

    assets = catalog.query(
        under=str(graphics_tree / "gfx" / "interface"), search="disk_idea"
    )
    assert [catalog.path_for(asset) for asset in assets] == [
        str(graphics_tree / "gfx" / "interface" / "ideas" / "disk_idea.png")
    ]


def test_changed_graphics_path_uses_a_new_cache_entry(graphics_tree):
    alternate = graphics_tree / "gfx" / "alternate_ideas"
    alternate.mkdir()
    (alternate / "alternate.dds").write_bytes(b"")
    catalog = GraphicsCatalog()
    catalog.refresh(str(graphics_tree), _config(), read_text=read_file)

    maps = catalog.refresh(
        str(graphics_tree),
        _config(path_ideas_gfx="gfx/alternate_ideas"),
        read_text=read_file,
    )
    assert catalog.last_metrics.cache_status == "miss"
    assert "GFX_idea_alternate" in maps.idea_sprites
    assert "GFX_idea_disk_idea" not in maps.idea_sprites


def test_configured_goals_path_controls_focus_images(graphics_tree):
    alternate = graphics_tree / "gfx" / "alternate_goals"
    alternate.mkdir()
    (alternate / "alternate.dds").write_bytes(b"")

    catalog = GraphicsCatalog()
    maps = catalog.refresh(
        str(graphics_tree),
        _config(path_goals="gfx/alternate_goals"),
        read_text=read_file,
    )
    assert "GFX_focus_alternate" in maps.sprites
    assert "GFX_focus_disk_focus" not in maps.sprites


def test_uppercase_gfx_file_is_decision_only(graphics_tree):
    (graphics_tree / "interface" / "upper.GFX").write_text(
        'spriteType = { name = "GFX_idea_upper" '
        'texturefile = "gfx/interface/ideas/upper.dds" }\n'
    )
    catalog = GraphicsCatalog()
    maps = catalog.refresh(str(graphics_tree), _config(), read_text=read_file)
    assert "GFX_idea_upper" not in maps.idea_sprites
    assert maps.decision_sprites["GFX_idea_upper"].endswith(
        "gfx/interface/ideas/upper.dds"
    )


def test_corrupt_graphics_snapshot_degrades_to_rescan(graphics_tree):
    first = GraphicsCatalog()
    expected = first.refresh(str(graphics_tree), _config(), read_text=read_file)
    database = scan_cache.database_path(str(graphics_tree))
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE graphics_snapshot SET data = ?", ("{",))

    second = GraphicsCatalog()
    actual = second.refresh(str(graphics_tree), _config(), read_text=read_file)
    assert second.last_metrics.cache_status == "miss"
    assert second.last_metrics.directory_listings > 0
    assert actual == expected


def test_refresh_removes_legacy_sidecar_only_from_root(graphics_tree):
    sidecar = graphics_tree / ".hoi4cm_gfx_cache.json"
    sidecar.write_text("{}")
    nested = graphics_tree / "gfx" / ".hoi4cm_gfx_cache.json"
    nested.write_text("{}")

    GraphicsCatalog().refresh(str(graphics_tree), _config(), read_text=read_file)

    assert not sidecar.exists()
    assert nested.exists()  # only the exact file in the scanned root is removed


def test_absolute_texturefile_snapshot_is_not_cached(graphics_tree):
    abs_target = graphics_tree / "external" / "goals" / "abs_focus.dds"
    gfx_text = (
        'spriteType = { name = "GFX_focus_abs" ' f'texturefile = "{abs_target}" }}\n'
    )
    (graphics_tree / "interface" / "abs.gfx").write_text(gfx_text)

    catalog = GraphicsCatalog()
    maps = catalog.refresh(str(graphics_tree), _config(), read_text=read_file)
    assert catalog.last_metrics.cache_status == "miss"
    assert maps.sprites["GFX_focus_abs"] == str(abs_target)

    # The absolute texturefile makes the snapshot non-cacheable, so nothing is
    # stored and a fresh catalog is still a miss rather than a warm hit.
    second = GraphicsCatalog()
    second.refresh(str(graphics_tree), _config(), read_text=read_file)
    assert second.last_metrics.cache_status == "miss"


def test_note_deleted_removes_image_from_maps(graphics_tree):
    catalog = GraphicsCatalog()
    catalog.refresh(str(graphics_tree), _config(), read_text=read_file)
    idea_image = graphics_tree / "gfx" / "interface" / "ideas" / "disk_idea.png"
    idea_image.unlink()

    maps = catalog.note_deleted(str(idea_image))

    assert maps is not None
    assert "GFX_idea_disk_idea" not in maps.idea_sprites
    assert catalog.query(search="disk_idea.png") == ()


def test_image_under_decisions_dir_becomes_decision_sprites(graphics_tree):
    catalog = GraphicsCatalog()
    maps = catalog.refresh(str(graphics_tree), _config(), read_text=read_file)
    decision_image = str(graphics_tree / "gfx" / "decisions" / "disk_decision.tga")

    assert maps.decision_sprites["GFX_decision_disk_decision"] == decision_image
    assert (
        maps.decision_sprites["GFX_decision_category_disk_decision"] == decision_image
    )


def test_note_written_adds_image_without_rescanning(graphics_tree, monkeypatch):
    catalog = GraphicsCatalog()
    catalog.refresh(str(graphics_tree), _config(), read_text=read_file)
    added = graphics_tree / "gfx" / "interface" / "ideas" / "new.dds"
    added.write_bytes(b"new")
    monkeypatch.setattr(
        "hoi4cm.mod.graphics_catalog.os.scandir",
        lambda _path: pytest.fail("an app write must not rescan graphics roots"),
    )

    maps = catalog.note_written(str(added), read_text=read_file)

    assert maps is not None
    assert maps.idea_sprites["GFX_idea_new"] == str(added)
    assert [catalog.path_for(asset) for asset in catalog.query(search="new.dds")] == [
        str(added)
    ]


def test_note_written_reparses_only_changed_gfx_file(graphics_tree, monkeypatch):
    catalog = GraphicsCatalog()
    catalog.refresh(str(graphics_tree), _config(), read_text=read_file)
    gfx_file = graphics_tree / "interface" / "assets.gfx"
    gfx_file.write_text(
        'spriteType = { name = "GFX_focus_changed" '
        'texturefile = "gfx/interface/goals/changed.dds" }\n'
    )
    reads = []

    def tracked_read(path):
        reads.append(path)
        return read_file(path)

    monkeypatch.setattr(
        "hoi4cm.mod.graphics_catalog.os.scandir",
        lambda _path: pytest.fail("an app write must not rescan graphics roots"),
    )

    maps = catalog.note_written(str(gfx_file), read_text=tracked_read)

    assert maps is not None
    assert "GFX_focus_declared" not in maps.sprites
    assert maps.sprites["GFX_focus_changed"].endswith("goals/changed.dds")
    assert reads == [str(gfx_file)]
