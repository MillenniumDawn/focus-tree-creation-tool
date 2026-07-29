from pathlib import Path

from hoi4cm.mod.graphics_catalog import AssetRef, FileStamp
from hoi4cm.wizards._graphics import (
    browser_folders,
    collect_image_pairs,
    find_catalog_image,
)


class FakeCatalog:
    def __init__(self, paths):
        self.paths = tuple(paths)
        self.queries = []

    def query(self, *, under=None, search=""):
        self.queries.append((under, search))
        return tuple(
            AssetRef("fake", str(index), FileStamp(0, 0, 0), 1)
            for index, path in enumerate(self.paths)
            if under is None or Path(path).is_relative_to(under)
        )

    def path_for(self, asset):
        return self.paths[int(asset.relative_path)]


def test_collect_image_pairs_uses_catalog_and_filters_filename(tmp_path):
    root = tmp_path / "gfx" / "ideas"
    paths = (
        str(root / "alpha.dds"),
        str(root / "matching-folder" / "beta.png"),
        str(root / "nested" / "matching.tga"),
    )
    catalog = FakeCatalog(paths)

    pairs = collect_image_pairs(str(root), "GFX_idea_", search="MATCH", catalog=catalog)

    assert pairs == [("GFX_idea_matching", paths[2])]
    assert catalog.queries == [(str(root), "")]


def test_collect_image_pairs_falls_back_to_recursive_folder_scan(tmp_path):
    root = tmp_path / "selected"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (root / "root.dds").touch()
    (nested / "nested.PNG").touch()
    (nested / "ignored.jpg").touch()

    pairs = collect_image_pairs(str(root), "GFX_", catalog=None)

    assert pairs == [
        ("GFX_root", str(root / "root.dds")),
        ("GFX_nested", str(nested / "nested.PNG")),
    ]


def test_collect_image_pairs_falls_back_when_catalog_is_stale(tmp_path):
    root = tmp_path / "event_pictures"
    root.mkdir()
    image = root / "new.png"
    image.touch()

    pairs = collect_image_pairs(str(root), "GFX_event_", catalog=FakeCatalog(()))

    assert pairs == [("GFX_event_new", str(image))]


def test_browser_folders_uses_catalog_image_locations(tmp_path):
    root = tmp_path / "event_pictures"
    paths = (
        str(root / "root.dds"),
        str(root / "country" / "nested" / "one.png"),
        str(root / "news" / "two.tga"),
    )

    folders = browser_folders(str(root), "[event_pictures]", catalog=FakeCatalog(paths))

    assert folders == [
        ("[event_pictures]", str(root)),
        ("country", str(root / "country")),
        ("news", str(root / "news")),
    ]


def test_browser_folders_preserves_selected_folder_fallback(tmp_path):
    root = tmp_path / "selected"
    (root / "empty").mkdir(parents=True)
    (root / "icon.dds").touch()

    folders = browser_folders(str(root), "[selected folder]", catalog=None)

    assert folders == [
        ("[selected folder]", str(root)),
        ("empty", str(root / "empty")),
    ]


def test_browser_folders_falls_back_when_catalog_is_stale(tmp_path):
    root = tmp_path / "event_pictures"
    root.mkdir()
    (root / "new.dds").touch()

    folders = browser_folders(str(root), "[event_pictures]", catalog=FakeCatalog(()))

    assert folders == [("[event_pictures]", str(root))]


def test_find_catalog_image_prefers_flat_path_and_extension_order(tmp_path):
    root = tmp_path / "decisions"
    paths = (
        str(root / "nested" / "icon.dds"),
        str(root / "icon.png"),
        str(root / "icon.tga"),
    )

    result = find_catalog_image(FakeCatalog(paths), str(root), "ICON")

    assert result == str(root / "icon.tga")
