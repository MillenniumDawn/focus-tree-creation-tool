"""Headless tests for the dynamic-modifier wizard's script builders."""

from hoi4cm.wizards._generators import (
    _parse_dyn_mod_line,
    build_dyn_mod_output,
    parse_dyn_mod_lines,
)


def test_parse_dyn_mod_line_two_field_form():
    modifier, var, tooltip = _parse_dyn_mod_line(
        "political_power_factor = AM_var_pp_factor_tt"
    )
    assert modifier == "political_power_factor"
    assert var == "AM_var_pp_factor_tt"
    assert tooltip == ""


def test_parse_dyn_mod_line_keeps_extra_equals_in_the_tooltip():
    modifier, var, tooltip = _parse_dyn_mod_line("a = b = c = d")
    assert (modifier, var, tooltip) == ("a", "b", "c = d")


def test_parse_dyn_mod_line_three_field_form_with_tooltip():
    modifier, var, tooltip = _parse_dyn_mod_line(
        "stability_factor = AM_var_stab = custom_modifier_tt"
    )
    assert modifier == "stability_factor"
    assert var == "AM_var_stab"
    assert tooltip == "custom_modifier_tt"


def test_parse_dyn_mod_lines_skips_blanks_and_comments():
    raw = (
        "# comment line\n"
        "\n"
        "stability_weekly = AM_var_stab_w\n"
        "political_power_factor = AM_pp_factor\n"
        "# another comment\n"
    )
    entries = parse_dyn_mod_lines(raw)
    assert entries == [
        ("stability_weekly", "AM_var_stab_w", ""),
        ("political_power_factor", "AM_pp_factor", ""),
    ]


def test_parse_dyn_mod_lines_drops_lines_missing_var():
    raw = "lone_modifier =\npolitical_power_factor = AM_pp\n"
    entries = parse_dyn_mod_lines(raw)
    assert entries == [("political_power_factor", "AM_pp", "")]


def test_build_dyn_mod_output_emits_three_file_sections():
    out = build_dyn_mod_output(mod_id="TAG_test")

    assert "# FILE: common/dynamic_modifiers/TAG_test.txt" in out
    assert "# FOCUS SNIPPET" in out
    assert "# LOCALISATION" in out
    assert out.count("TAG_test = {") == 1


def test_build_dyn_mod_output_emits_scope_and_icon_when_set():
    out = build_dyn_mod_output(mod_id="TAG_x", scope="state", icon="GFX_idea_x")
    assert "\tscope = state" in out
    assert "\ticon = GFX_idea_x" in out


def test_build_dyn_mod_output_omits_scope_when_country_default():
    out = build_dyn_mod_output(mod_id="TAG_x")
    assert "scope = country" not in out


def test_build_dyn_mod_output_emits_enable_block_indented():
    out = build_dyn_mod_output(mod_id="TAG_x", enable="has_war = yes\ndate > 1940.1.1")
    assert "\tenable = {" in out
    assert "\t\thas_war = yes" in out
    assert "\t\tdate > 1940.1.1" in out


def test_build_dyn_mod_output_emits_variable_modifier_lines():
    out = build_dyn_mod_output(
        mod_id="TAG_x",
        mods_raw="stability_factor = AM_stab\nwar_support_factor = AM_ws",
    )
    assert "\t# Variable modifiers \u2014 read daily from variables" in out
    assert "\tstability_factor = AM_stab" in out
    assert "\twar_support_factor = AM_ws" in out


def test_build_dyn_mod_output_emits_constant_modifier_block():
    out = build_dyn_mod_output(
        mod_id="TAG_x",
        const="consumer_goods_factor = 0.05\nproduction_speed_buildings_factor = 0.1",
    )
    assert "\t# Constant modifiers" in out
    assert "\tconsumer_goods_factor = 0.05" in out
    assert "\tproduction_speed_buildings_factor = 0.1" in out


def test_build_dyn_mod_output_emits_focus_snippet_with_add_to_variable():
    out = build_dyn_mod_output(
        mod_id="TAG_x",
        mods_raw="stability_factor = AM_stab = stab_change_tt",
    )
    assert "\t\tcompletion_reward = {" in out
    assert "MODIFIER = TAG_x" in out
    assert "\t\t\tadd_to_variable = { AM_stab = 0.05 tooltip = stab_change_tt }" in out


def test_build_dyn_mod_output_focus_snippet_uses_bare_form_without_tooltip():
    out = build_dyn_mod_output(mod_id="TAG_x", mods_raw="stability_factor = AM_stab")
    assert "\t\t\tadd_to_variable = { AM_stab = 0.05 }" in out


def test_build_dyn_mod_output_emits_loc_keys():
    out = build_dyn_mod_output(
        mod_id="TAG_x", loc_name="My Modifier", loc_desc="What it does."
    )
    assert ' TAG_x: "My Modifier"' in out
    assert ' TAG_x_desc: "What it does."' in out
    assert ' modifies_dynamic_modifier_tt: "Modifies $MODIFIER$"' in out
    assert ' adds_dynamic_modifier_tt: "Adds $MODIFIER$ which grants:"' in out


def test_build_dyn_mod_output_emits_placeholder_tooltip_keys():
    out = build_dyn_mod_output(
        mod_id="TAG_x",
        mods_raw="political_power_factor = AM_pp = pp_change_tt",
    )
    assert (
        ' pp_change_tt: "PLACEHOLDER \u2014 describe the political_power_factor change"'
        in out
    )


def test_build_dyn_mod_output_default_id_when_blank():
    out = build_dyn_mod_output(mod_id="")
    assert "TAG_my_dynamic_modifier" in out


def test_build_dyn_mod_output_empty_mods_omits_variable_section():
    out = build_dyn_mod_output(mod_id="TAG_x", mods_raw="")
    assert "Variable modifiers" not in out
    assert "Tooltip keys for each modifier stat" not in out


def test_build_dyn_mod_output_skips_commented_constant_lines():
    out = build_dyn_mod_output(
        mod_id="TAG_x", const="# skip me\nconsumer_goods_factor = 0.05"
    )
    assert "\tconsumer_goods_factor = 0.05" in out
    assert "skip me" not in out


def test_build_dyn_mod_output_golden_definition_block():
    # The definition block's order (scope, icon, enable, variables, consts)
    # is what a mod file needs; substring checks can't see it.
    out = build_dyn_mod_output(
        mod_id="TAG_x",
        icon="GFX_idea_x",
        enable="has_war = yes",
        mods_raw="stability_factor = AM_stab = stab_tt",
        const="consumer_goods_factor = 0.05",
    )
    definition = out.split("\n\n\n", maxsplit=1)[0]
    assert definition == "\n".join(
        [
            "# ============================================================",
            "# FILE: common/dynamic_modifiers/TAG_x.txt",
            "# ============================================================",
            "",
            "TAG_x = {",
            "\ticon = GFX_idea_x",
            "\tenable = {",
            "\t\thas_war = yes",
            "\t}",
            "",
            "\t# Variable modifiers — read daily from variables",
            "\tstability_factor = AM_stab",
            "",
            "\t# Constant modifiers",
            "\tconsumer_goods_factor = 0.05",
            "}",
        ]
    )
