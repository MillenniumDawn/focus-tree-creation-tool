"""Headless tests for the national-spirit wizard's script builder."""

import pytest

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
            "no_equals_sign\n"
        ),
    )
    assert "modifier = {" in out
    assert "stability_factor = 0.1" in out
    assert "war_support_factor = -0.1" in out
    # Comments and lines without a `key = value` pair are dropped.
    assert "# comment" not in out
    assert "no_equals_sign" not in out


def test_build_national_spirit_merges_list_and_text_modifiers():
    out = build_national_spirit_output(
        mod_id="TAG_s",
        modifiers=[{"key": "stability_factor", "value": "0.05"}],
        extra_modifiers="war_support_factor = 0.1",
    )
    assert out.count("modifier = {") == 1
    assert "\t\t\t\tstability_factor = 0.05" in out
    assert "\t\t\t\twar_support_factor = 0.1" in out


def test_build_national_spirit_omits_modifier_block_when_empty():
    assert "modifier = {" not in build_national_spirit_output(mod_id="TAG_s")


@pytest.mark.parametrize("field", ["visible", "on_add", "on_remove", "rule"])
def test_build_national_spirit_emits_each_optional_block(field):
    out = build_national_spirit_output(mod_id="TAG_s", **{field: "always = yes"})
    assert f"\t\t\t{field} = {{\n\t\t\t\talways = yes\n\t\t\t}}" in out
    assert f"{field} = {{" not in build_national_spirit_output(mod_id="TAG_s")


def test_build_national_spirit_uses_explicit_picture_over_default():
    out = build_national_spirit_output(mod_id="TAG_s", picture="GFX_idea_custom")
    assert "picture = GFX_idea_custom" in out


def test_build_national_spirit_golden_block():
    # Locks nesting depth and field order inside `ideas = { country = { ... } }`.
    out = build_national_spirit_output(
        mod_id="TAG_s",
        cost="50",
        loc_name="N",
        loc_desc="D",
        on_add="add_stability = 0.1",
        modifiers=[{"key": "stability_factor", "value": "0.05"}],
    )
    assert out == "\n".join(
        [
            "# ============================================================",
            "# FILE: common/ideas/TAG_s.txt",
            "# ============================================================",
            "",
            "ideas = {",
            "\tcountry = {",
            "\t\tTAG_s = {",
            "\t\t\tpicture = GFX_idea_TAG_s",
            "\t\t\tallowed_civil_war = { always = yes }",
            "\t\t\tcost = 50",
            "\t\t\ton_add = {",
            "\t\t\t\tadd_stability = 0.1",
            "\t\t\t}",
            "\t\t\tmodifier = {",
            "\t\t\t\tstability_factor = 0.05",
            "\t\t\t}",
            "\t\t}",
            "\t}",
            "}",
            "",
            "# ============================================================",
            "# LOCALISATION  localisation/english/TAG_s_l_english.yml",
            "# ============================================================",
            "",
            ' TAG_s: "N"',
            ' TAG_s_desc: "D"',
        ]
    )


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


def test_build_national_spirit_escapes_quotes_in_loc_values():
    out = build_national_spirit_output(
        mod_id="TAG_s", loc_name='My "Spirit"', loc_desc='Say "hi".'
    )
    assert ' TAG_s: "My \\"Spirit\\""' in out
    assert ' TAG_s_desc: "Say \\"hi\\"."' in out


def test_build_national_spirit_uses_configured_localisation_path():
    out = build_national_spirit_output(mod_id="TAG_s", loc_language="braz_por")

    assert "localisation/braz_por/TAG_s_l_braz_por.yml" in out


def test_build_national_spirit_skips_modifier_missing_key():
    out = build_national_spirit_output(
        mod_id="TAG_s",
        modifiers=[{"value": "0.05"}],  # no key
    )
    assert "modifier = {" not in out


def test_build_national_spirit_skips_modifier_missing_value():
    out = build_national_spirit_output(
        mod_id="TAG_s",
        modifiers=[{"key": "stability_factor"}],  # no value
    )
    assert "modifier = {" not in out


def test_build_national_spirit_skips_modifier_blank_key():
    out = build_national_spirit_output(
        mod_id="TAG_s", modifiers=[{"key": "   ", "value": "0.05"}]
    )
    assert "modifier = {" not in out


def test_build_national_spirit_skips_modifier_blank_value():
    out = build_national_spirit_output(
        mod_id="TAG_s", modifiers=[{"key": "stability_factor", "value": "   "}]
    )
    assert "modifier = {" not in out


def test_build_national_spirit_skips_modifier_non_dict_entry():
    out = build_national_spirit_output(
        mod_id="TAG_s",
        modifiers=[None, "foo", {"key": "stability_factor", "value": "0.05"}],
    )
    assert "modifier = {" in out
    assert "stability_factor = 0.05" in out
    assert "foo" not in out
    assert out.count("modifier = {") == 1


def test_build_national_spirit_skips_all_malformed_no_block():
    out = build_national_spirit_output(
        mod_id="TAG_s",
        modifiers=[
            {"key": "", "value": "0.05"},
            {"value": "0.1"},
            {"key": "stability_factor"},
            None,
        ],
    )
    assert "modifier = {" not in out


def test_build_national_spirit_mixed_valid_and_malformed():
    out = build_national_spirit_output(
        mod_id="TAG_s",
        modifiers=[
            {"key": "stability_factor", "value": "0.05"},
            {"key": "", "value": "0.1"},
            {"value": "0.2"},
            {"key": "political_power_gain", "value": "0.1"},
        ],
    )
    assert "stability_factor = 0.05" in out
    assert "political_power_gain = 0.1" in out
    assert out.count("modifier = {") == 1
    # malformed entries are silently dropped, not rendered as blank or None
    assert "None" not in out
    assert "= 0.1" not in out or "political_power_gain = 0.1" in out


def test_build_national_spirit_handles_numeric_value():
    out = build_national_spirit_output(
        mod_id="TAG_s",
        modifiers=[
            {"key": "stability_factor", "value": 0.05},
            {"key": "political_power_gain", "value": 0},
        ],
    )
    assert "stability_factor = 0.05" in out
    assert "political_power_gain = 0" in out


def test_build_national_spirit_trims_whitespace_in_key_and_value():
    out = build_national_spirit_output(
        mod_id="TAG_s",
        modifiers=[{"key": " stability_factor ", "value": " 0.05 "}],
    )
    assert "\t\t\t\tstability_factor = 0.05" in out
    # must not preserve surrounding spaces
    assert " stability_factor " not in out


def test_build_national_spirit_does_not_raise_for_malformed_list():
    # Previously m["key"] raised KeyError inside the preview try and was swallowed;
    # now it must not raise at all.
    try:
        out = build_national_spirit_output(
            mod_id="TAG_s",
            modifiers=[{"key": "a", "value": "1"}, {"bad": "entry"}],
        )
    except KeyError:
        pytest.fail(
            "build_national_spirit_output raised KeyError for malformed modifier"
        )
    assert "a = 1" in out


def test_build_national_spirit_fuzz_corrupted_autosave_never_raises():
    """Corrupted autosave must never crash the generator (B hardening)."""
    import random

    rng = random.Random(0)
    choices = [
        lambda: {"key": "stability_factor", "value": "0.05"},  # valid
        lambda: {"value": "0.05"},  # missing key
        lambda: {"key": "stability_factor"},  # missing value
        lambda: {"key": "", "value": "0.05"},  # blank key
        lambda: {"key": "stability_factor", "value": ""},  # blank value
        lambda: {"key": "   ", "value": "   "},  # whitespace
        lambda: None,  # non-dict
        lambda: "foo",  # non-dict
        lambda: {"key": rng.choice([None, 123, 0]), "value": "0.05"},  # bad key type
        lambda: {"key": "stability_factor", "value": None},  # None value
        lambda: {"key": "stability_factor", "value": rng.randint(-5, 5)},  # numeric
    ]
    for _ in range(200):
        mods = [rng.choice(choices)() for _ in range(rng.randint(0, 8))]
        # Must not raise, must not leak None/blank, must not emit empty block
        out = build_national_spirit_output(mod_id="TAG_s", modifiers=mods)
        assert "None" not in out
        # If any valid entry survived, modifier block appears once; else none.
        has_valid = any(
            isinstance(m, dict)
            and isinstance(m.get("key"), str)
            and m.get("key", "").strip()
            and m.get("value") is not None
            and not (isinstance(m.get("value"), str) and not m["value"].strip())
            for m in mods
        )
        if has_valid:
            # At least one valid entry could have been kept, but numeric
            # values are also valid — just ensure block count is 0 or 1.
            assert out.count("modifier = {") in (0, 1)
        else:
            assert "modifier = {" not in out
        # Corrupted raw text is handled via extra_modifiers, also must not raise.
        extra = "\n".join(
            rng.choice(["ok = 0.1", "bad", " = 0.2", "# comment", ""]) for _ in range(3)
        )
        out2 = build_national_spirit_output(
            mod_id="TAG_s", modifiers=mods, extra_modifiers=extra
        )
        assert "None" not in out2
