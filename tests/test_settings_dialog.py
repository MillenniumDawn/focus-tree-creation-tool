"""Tests for hoi4cm.ui.settings_dialog — pure fragments plus an import smoke test."""

import pytest

import hoi4cm.ui.settings_dialog as settings_dialog


def test_settings_dialog_imports_without_tk_objects():
    """Import alone must not create any Tk objects (headless CI, no display).

    Collecting this module already exercises the import; this test just
    names the guarantee explicitly.
    """
    assert hasattr(settings_dialog, "open_settings")


# ── relativize_to_mod_root ───────────────────────────────────────────


def test_relativize_to_mod_root_strips_prefix_when_under_root():
    assert (
        settings_dialog.relativize_to_mod_root("/mods/mymod/gfx/goals", "/mods/mymod")
        == "gfx/goals"
    )


def test_relativize_to_mod_root_leaves_path_unchanged_outside_root():
    path = "/somewhere/else/gfx/goals"
    assert settings_dialog.relativize_to_mod_root(path, "/mods/mymod") == path


def test_relativize_to_mod_root_leaves_path_unchanged_when_root_falsy():
    path = "/somewhere/gfx/goals"
    assert settings_dialog.relativize_to_mod_root(path, "") == path
    assert settings_dialog.relativize_to_mod_root(path, None) == path


# ── loc_token_preview_text ───────────────────────────────────────────


def test_loc_token_preview_text_known_styles():
    assert "SOV:NameWithFlag" in settings_dialog.loc_token_preview_text("colon")
    assert "SOV.GetName" in settings_dialog.loc_token_preview_text("dot")
    assert "TAG:X" in settings_dialog.loc_token_preview_text("both")


def test_loc_token_preview_text_unknown_style_returns_empty():
    assert settings_dialog.loc_token_preview_text("nonsense") == ""


# ── parse_event_dim_profile ──────────────────────────────────────────


def test_parse_event_dim_profile_valid_ints():
    profile = settings_dialog.parse_event_dim_profile("420", "176", "794", "330")
    assert profile == {"country": (420, 176), "news": (794, 330)}


def test_parse_event_dim_profile_rejects_non_integer():
    with pytest.raises(ValueError):
        settings_dialog.parse_event_dim_profile("wide", "176", "794", "330")


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
