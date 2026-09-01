from importlib import import_module

import pytest

_gfx_writer = import_module("hoi4cm.mod.gfx_writer")
DEFAULT_FOCUS_ICON = _gfx_writer.DEFAULT_FOCUS_ICON
append_sprite_types = _gfx_writer.append_sprite_types
build_focus_sprite_entries = _gfx_writer.build_focus_sprite_entries
build_sprite_type = _gfx_writer.build_sprite_type
resolve_focus_image_paths = _gfx_writer.resolve_focus_image_paths
resolve_mod_texture_path = _gfx_writer.resolve_mod_texture_path


class _Catalog:
    def __init__(self, paths):
        self.paths = paths

    def resolve(self, _name):
        return None

    def query(self, *, under):
        return [path for path in self.paths if str(path).startswith(under)]

    def path_for(self, path):
        return str(path)


def test_append_sprite_types_creates_wrapper_and_deduplicates_requests():
    text, added = append_sprite_types(
        None,
        [
            ("GFX_focus_custom", "gfx/interface/goals/custom.dds"),
            ("GFX_focus_custom", "gfx/interface/goals/other.dds"),
        ],
    )

    assert added == 1
    assert text == (
        "spriteTypes = {\n\n"
        "\tspriteType = {\n"
        '\t\tname = "GFX_focus_custom"\n'
        '\t\ttexturefile = "gfx/interface/goals/custom.dds"\n'
        "\t}\n\n}\n"
    )


def test_append_sprite_types_preserves_existing_wrapper_and_declarations():
    existing = (
        '# spriteTypes = { name = "GFX_focus_new" }\n'
        "spriteTypes = {\n"
        "\t# Keep this note.\n"
        '\tspriteType = { name = "GFX_focus_existing" '
        'texturefile = "gfx/interface/goals/existing.dds" }\n'
        "}\n"
        "# Keep this suffix.\n"
    )

    text, added = append_sprite_types(
        existing,
        [
            ("GFX_focus_existing", "gfx/interface/goals/replacement.dds"),
            ("GFX_focus_new", "gfx/interface/goals/new.dds"),
        ],
    )

    assert added == 1
    assert text.startswith(existing[: existing.index("}\n")])
    assert "# Keep this note." in text
    assert text.count('name = "GFX_focus_new"') == 2
    assert "# Keep this suffix." in text
    assert text.count('name = "GFX_focus_existing"') == 1


def test_append_sprite_types_preserves_unwrapped_content():
    existing = "# User content\n"

    text, added = append_sprite_types(
        existing, [("GFX_focus_new", "gfx/interface/goals/new.dds")]
    )

    assert added == 1
    assert text.startswith(existing)
    assert 'name = "GFX_focus_new"' in text


def test_append_sprite_types_skips_existing_names_without_rewriting():
    existing = (
        'spriteType = { name = "GFX_focus_existing" '
        'texturefile = "gfx/interface/goals/existing.dds" }\n'
    )

    text, added = append_sprite_types(
        existing, [("GFX_focus_existing", "gfx/interface/goals/new.dds")]
    )

    assert text == existing
    assert added == 0


@pytest.mark.parametrize(
    ("name", "texture_path"),
    [
        ('GFX_focus_bad"name', "gfx/interface/goals/custom.dds"),
        ("GFX_focus_bad\nname", "gfx/interface/goals/custom.dds"),
        ("GFX_focus_custom", 'gfx/interface/goals/bad"path.dds'),
        ("GFX_focus_custom", "gfx/interface/goals/bad\npath.dds"),
    ],
)
def test_build_sprite_type_rejects_unsafe_quoted_values(name, texture_path):
    with pytest.raises(ValueError):
        build_sprite_type(name, texture_path)


def test_build_focus_sprite_entries_filters_default_declared_and_unresolved(tmp_path):
    image = tmp_path / "gfx" / "interface" / "goals" / "custom.dds"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")

    entries, unresolved = build_focus_sprite_entries(
        [
            DEFAULT_FOCUS_ICON,
            "GFX_focus_custom",
            "GFX_focus_custom",
            "GFX_focus_missing",
        ],
        declared_names={"GFX_focus_declared"},
        image_paths={"GFX_focus_custom": str(image)},
        mod_root=str(tmp_path),
    )

    assert entries == (("GFX_focus_custom", "gfx/interface/goals/custom.dds"),)
    assert unresolved == ("GFX_focus_missing",)


def test_build_focus_sprite_entries_reports_unsafe_name_as_unresolved(tmp_path):
    image = tmp_path / "gfx" / "interface" / "goals" / "custom.dds"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")

    entries, unresolved = build_focus_sprite_entries(
        ['GFX_focus_bad"name'],
        declared_names=set(),
        image_paths={'GFX_focus_bad"name': str(image)},
        mod_root=str(tmp_path),
    )

    assert entries == ()
    assert unresolved == ('GFX_focus_bad"name',)


def test_resolve_focus_image_paths_uses_catalog_stem_fallback(tmp_path):
    image = tmp_path / "gfx" / "interface" / "goals" / "custom.dds"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")

    paths = resolve_focus_image_paths(
        ["GFX_focus_custom"],
        catalog=_Catalog([image]),
        mod_root=str(tmp_path),
        goals_path="gfx/interface/goals",
    )

    assert paths == {"GFX_focus_custom": str(image)}


def test_resolve_mod_texture_path_rejects_outside_and_missing_paths(tmp_path):
    image = tmp_path / "inside.dds"
    image.write_bytes(b"image")
    outside = tmp_path.parent / "outside.dds"
    outside.write_bytes(b"image")

    assert resolve_mod_texture_path(str(tmp_path), image) == "inside.dds"
    assert resolve_mod_texture_path(str(tmp_path), outside) is None
    assert resolve_mod_texture_path(str(tmp_path), "missing.dds") is None
