"""Headless tests for the national-spirit wizard's script builder."""

from hoi4cm.wizards._generators import build_national_spirit_output


def test_build_national_spirit_minimum_fields():
    out = build_national_spirit_output(mod_id="TAG_my_spirit")

    assert "# FILE: common/ideas/TAG_my_spirit.txt" in out
    assert "ideas = {" in out
    assert "country = {" in out
    assert "TAG_my_spirit = {" in out
    assert "picture = GFX_idea_TAG_my_spirit" in out
    assert "allowed_civil_war = { always = yes }" in out
    assert 'TAG_my_spirit: ""' in out
    assert out.rstrip().endswith('TAG_my_spirit_desc: ""')


def test_build_national_spirit_default_id_when_blank():
    out = build_national_spirit_output(mod_id="")
    assert "TAG_my_spirit" in out
    assert "# FILE: common/ideas/TAG_my_spirit.txt" in out


def test_build_national_spirit_emits_name_key_only_when_distinct():
    out = build_national_spirit_output(mod_id="TAG_spirit", name_key="TAG_spirit_alt")
    assert "name = TAG_spirit_alt" in out

    out2 = build_national_spirit_output(mod_id="TAG_spirit")
    # When name_key defaults to sid, no `name = ...` line is emitted.
    assert "name = TAG_spirit" not in out2


def test_build_national_spirit_omits_country_block_when_other_slot():
    out = build_national_spirit_output(mod_id="TAG_spirit", slot="hidden")
    # Other slots do NOT get allowed_civil_war.
    assert "allowed_civil_war" not in out
    assert "hidden = {" in out


def test_build_national_spirit_emits_trigger_blocks_indented():
    out = build_national_spirit_output(
        mod_id="TAG_s",
        allowed="has_war = yes",
        available="threat > 0.5",
        cancel="has_war = no",
    )
    assert "allowed = {" in out
    assert "has_war = yes" in out
    assert "available = {" in out
    assert "cancel = {" in out


def test_build_national_spirit_collects_modifiers_from_list():
    out = build_national_spirit_output(
        mod_id="TAG_s",
        modifiers=[
            {"key": "stability_factor", "value": "0.05"},
            {"key": "political_power_gain", "value": "0.1"},
        ],
    )
    assert "modifier = {" in out
    assert "stability_factor = 0.05" in out
    assert "political_power_gain = 0.1" in out
    assert out.count("modifier = {") == 1


def test_build_national_spirit_parses_extra_modifier_lines():
    out = build_national_spirit_output(
        mod_id="TAG_s",
        extra_modifiers=(
            "# comment\n"
            "stability_factor = 0.1\n"
            "war_support_factor = -0.1\n"
            "blank_line_below\n"
        ),
    )
    assert "modifier = {" in out
    assert "stability_factor = 0.1" in out
    assert "war_support_factor = -0.1" in out


def test_build_national_spirit_emits_cost_and_removal():
    out = build_national_spirit_output(mod_id="TAG_s", cost="50", removal_cost="30")
    assert "cost = 50" in out
    assert "removal_cost = 30" in out


def test_build_national_spirit_emits_ai_will_do_when_nonzero():
    out = build_national_spirit_output(mod_id="TAG_s", ai_factor="5")
    assert "ai_will_do = { factor = 5 }" in out

    out_zero = build_national_spirit_output(mod_id="TAG_s", ai_factor="0")
    assert "ai_will_do" not in out_zero


def test_build_national_spirit_emits_loc_block():
    out = build_national_spirit_output(
        mod_id="TAG_s", loc_name="My Spirit", loc_desc="What it does."
    )
    assert "# LOCALISATION" in out
    assert ' TAG_s: "My Spirit"' in out
    assert ' TAG_s_desc: "What it does."' in out
