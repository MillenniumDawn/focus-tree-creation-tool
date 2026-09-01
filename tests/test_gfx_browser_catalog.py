import os
from pathlib import Path

from hoi4cm.mod.graphics_catalog import AssetRef, FileStamp
from hoi4cm.ui.gfx_browser import (
    _catalog_folder_groups,
    _catalog_image_paths,
    _pairs_from_paths,
    _uncatalogued_custom_groups,
)


class FakeCatalog:
    def __init__(self, paths):
        self._paths = tuple(paths)
        self.queries = []

    def query(self, *, under=None, search=""):
        self.queries.append((under, search))
        return tuple(
            AssetRef("fake", str(index), FileStamp(0, 0, 0), 1)
            for index, path in enumerate(self._paths)
            if (under is None or Path(path).is_relative_to(under))
            and search.casefold() in path.casefold()
        )

    def path_for(self, asset):
        return self._paths[int(asset.relative_path)]


def test_catalog_image_paths_uses_in_memory_query(tmp_path):
    root = tmp_path / "gfx"
    paths = (str(root / "a.dds"), str(root / "nested" / "b.png"))
    catalog = FakeCatalog(paths)

    result = _catalog_image_paths(catalog, under=str(root), search="b")

    assert result == (paths[1],)
    assert catalog.queries == [(str(root), "b")]


def test_catalog_folder_groups_include_event_pictures_when_scanned(tmp_path):
    # Folder list comes from catalog directory records, not a full image query.
    # A candidate with no catalogued directory under it is still dropped.
    gfx = tmp_path / "gfx"
    event_pics = tmp_path / "event_pictures"
    paths = (
        str(gfx / "ideas"),
        str(gfx / "ideas" / "nested"),
        str(event_pics),
    )
    candidates = (
        ("ideas", str(gfx / "ideas"), "GFX_idea_"),
        ("event pictures", str(event_pics), "GFX_event_"),
        ("empty", str(gfx / "empty"), "GFX_"),
    )

    groups = _catalog_folder_groups(candidates, paths)

    assert groups == [
        ("ideas", str(gfx / "ideas"), "GFX_idea_", True),
        ("  ideas/nested", str(gfx / "ideas" / "nested"), "GFX_idea_", True),
        ("event pictures", str(event_pics), "GFX_event_", True),
    ]


def test_pairs_from_paths_preserves_first_stem_after_sorting(tmp_path):
    paths = (
        str(tmp_path / "z" / "same.png"),
        str(tmp_path / "a" / "same.dds"),
        str(tmp_path / "a" / "other.tga"),
    )

    pairs = _pairs_from_paths(paths, "GFX_")

    assert pairs == [
        ("GFX_other", str(tmp_path / "a" / "other.tga")),
        ("GFX_same", str(tmp_path / "a" / "same.dds")),
    ]


def test_uncatalogued_custom_groups_survive_catalog_refresh(tmp_path):
    custom = tmp_path / "custom"
    custom.mkdir()
    catalogued = [("ideas", str(tmp_path / "ideas"), "GFX_idea_", True)]

    groups = _uncatalogued_custom_groups(
        catalogued, [str(custom), str(custom) + os.sep]
    )

    assert groups == [
        ("ideas", str(tmp_path / "ideas"), "GFX_idea_", True),
        ("custom (custom)", str(custom), "GFX_", False),
    ]
