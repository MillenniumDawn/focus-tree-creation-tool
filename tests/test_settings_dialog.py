"""Tests for pure fragments in hoi4cm.ui.settings_dialog."""

import hoi4cm.ui.settings_dialog as settings_dialog

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
