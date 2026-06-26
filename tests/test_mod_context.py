"""Tests for hoi4cm.mod.context — the mod-asset scanner.

Each test builds a tiny mod tree under ``tmp_path`` with just the
subdirectories the scanner walks, then verifies the corresponding
``MOD.*`` field was populated correctly. Keeps each test fast and
side-effect-free.
"""

import textwrap

import pytest

from hoi4cm.mod import MOD
from hoi4cm.mod import context as ctx_mod


@pytest.fixture
def mod_tree(tmp_path):
    """Create a minimal but realistic mod directory tree."""

    def write(rel, content):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip("\n"))
        return path

    write(
        "common/national_focus/usa.txt",
        """
        focus_tree = {
            id = USA_focus_tree
            focus = { id = USA_first_focus }
            focus = { id = USA_second_focus }
        }
        """,
    )
    write(
        "common/ideas/usa_spirits.txt",
        """
        ideas = {
            USA = {
                USA_manifest_destiny = { picture = GFX_idea_usa_md }
                USA_great_depression = { picture = GFX_idea_usa_gd }
            }
        }
        """,
    )
    write(
        "common/decisions/USA.txt",
        """
        USA_intervention_in_china = {
            available = { has_war = no }
        }
        USA_destroy_hitler = {
            available = { threat > 0.5 }
        }
        """,
    )
    write(
        "common/decisions/categories/USA_decision_categories.txt",
        """
        USA_intervention_category = {
            icon = GFX_decision_category_usa_intervention
        }
        """,
    )
    write(
        "common/dynamic_modifiers/USA.txt",
        """
        USA_great_depression_modifier = {
            icon = GFX_idea_usa_great_depression
        }
        """,
    )
    write(
        "common/country_tags/00_countries.txt",
        """
        USA = "countries/United States.txt"
        GER = "countries/Germany.txt"
        SOV = "countries/Soviet Union.txt"
        """,
    )
    write(
        "events/USA_events.txt",
        """
        add_namespace = usa_events
        country_event = {
            id = usa_events.1
            title = usa_events.1.t
        }
        country_event = {
            id = usa_events.2
        }
        """,
    )
    write(
        "common/scripted_effects/00_money_system.txt",
        "## MD money system placeholder\n",
    )
    write(
        "common/scripted_localisation/money_scripted_localization.txt",
        "## MD sloc placeholder\n",
    )
    write(
        "localisation/english/MD_money_l_english.yml",
        "l_english:\n  x: y\n",
    )
    # A single focus goal .dds so the GFX scanner has something to index
    (tmp_path / "gfx" / "interface" / "goals").mkdir(parents=True, exist_ok=True)
    (tmp_path / "gfx" / "interface" / "goals" / "USA_first_focus.dds").write_bytes(b"")

    return tmp_path


def test_scan_loads_sprites(mod_tree):
    MOD.scan(str(mod_tree))
    assert "GFX_focus_USA_first_focus" in MOD.sprites


def test_scan_loads_focus_ids(mod_tree):
    MOD.scan(str(mod_tree))
    assert "USA_first_focus" in MOD.focus_ids
    assert "USA_second_focus" in MOD.focus_ids


def test_scan_loads_idea_ids(mod_tree):
    MOD.scan(str(mod_tree))
    assert "USA_manifest_destiny" in MOD.idea_ids
    assert "USA_great_depression" in MOD.idea_ids


def test_scan_loads_decision_ids_and_categories(mod_tree):
    MOD.scan(str(mod_tree))
    assert "USA_intervention_in_china" in MOD.decision_ids
    assert "USA_destroy_hitler" in MOD.decision_ids
    assert "USA_intervention_category" in MOD.decision_cats
    # Block-keyword false positives are filtered
    assert "category" not in MOD.decision_ids
    assert "available" not in MOD.decision_ids


def test_scan_loads_dyn_mods(mod_tree):
    MOD.scan(str(mod_tree))
    assert "USA_great_depression_modifier" in MOD.dyn_mod_ids


def test_scan_loads_country_tags(mod_tree):
    MOD.scan(str(mod_tree))
    assert MOD.country_tags[:3] == ["USA", "GER", "SOV"]


def test_scan_loads_event_ids(mod_tree):
    MOD.scan(str(mod_tree))
    assert MOD.event_ids.get("USA_events") == ["usa_events.1", "usa_events.2"]


def test_scan_discovers_md_money_files(mod_tree):
    MOD.scan(str(mod_tree))
    assert MOD.md_money_system_file.endswith("00_money_system.txt")
    assert "money_scripted_localization" in MOD.md_money_scripted_loc_file
    assert MOD.md_money_yml_file.endswith("MD_money_l_english.yml")


def test_md_detection_by_name(tmp_path, monkeypatch):
    """A mod named 'Millennium Dawn' is flagged by directory name alone."""
    # Don't let a real user config override our detection
    monkeypatch.setattr(ctx_mod, "cfg_load", lambda: {})
    md_root = tmp_path / "Millennium_Dawn"
    (md_root / "common").mkdir(parents=True)
    (md_root / "descriptor.mod").write_text('name = "Some Other Mod"')
    MOD.scan(str(md_root))
    assert MOD.is_md


def test_md_detection_false_for_normal_mod(mod_tree):
    MOD.scan(str(mod_tree))
    assert not MOD.is_md


def test_summary_includes_counts(mod_tree):
    MOD.scan(str(mod_tree))
    s = MOD.summary()
    # 3 focus IDs: USA_first_focus, USA_second_focus, USA_focus_tree (the tree's own id)
    assert "3 focus IDs" in s
    assert "2 ideas" in s
    assert "1 dyn modifiers" in s
    assert "3 tags" in s


def test_get_image_returns_none_when_pillow_unavailable(monkeypatch, mod_tree):
    """With Pillow disabled, get_image must return None, not crash."""
    monkeypatch.setattr(ctx_mod, "_PIL_OK", False)
    monkeypatch.setattr(ctx_mod, "_PILImage", None)
    monkeypatch.setattr(ctx_mod, "_PILImageTk", None)
    MOD.scan(str(mod_tree))
    assert MOD.get_image("GFX_focus_USA_first_focus") is None


def test_get_image_returns_none_for_unknown_gfx(mod_tree):
    MOD.scan(str(mod_tree))
    assert MOD.get_image("GFX_does_not_exist") is None
    assert any("NOT IN SPRITES" in e for e in MOD._img_errors)
