"""Headless tests for the decision-wizard script/loc generators."""

from hoi4cm.wizards._generators import (
    generate_decision_block,
    generate_decision_categories_file,
    generate_decision_loc_yml,
    generate_decision_scripted_loc,
    generate_decisions_file,
)


def _cat(**overrides):
    base = dict(
        uid="cat-1",
        cat_id="TAG_cat",
        loc_name="My Cat",
        loc_desc="",
        icon="",
        picture="",
        allowed="",
        visible="",
        priority="1",
        visible_when_empty=False,
        on_map_area=False,
        map_state="123",
        map_name="my_map_area",
        map_zoom="850",
        map_trigger="",
        scripted_gui="",
        highlight_states="",
    )
    base.update(overrides)
    return base


def _dec(**overrides):
    base = dict(
        uid="dec-1",
        cat_uid="cat-1",
        dec_id="TAG_decision",
        loc_name="My Decision",
        loc_desc="",
        icon="",
        allowed="",
        visible="",
        available="",
        cost_type="pp",
        cost="25",
        custom_cost_trigger="",
        custom_cost_text="",
        ai_hint_pp_cost="",
        cost_var="",
        cost_amount="",
        days_remove="",
        days_re_enable="",
        fire_only_once=False,
        fixed_random_seed=True,
        is_mission=False,
        mission_timeout="100",
        selectable_mission=True,
        is_good=False,
        activation="",
        timeout_effect="",
        war_with_on_timeout="",
        targeted="none",
        targets="",
        targets_dynamic=False,
        target_non_existing=False,
        target_array="",
        target_trigger="",
        target_root_trigger="",
        state_target_scope="yes",
        on_map_mode="map_and_decisions_view",
        war_complete_tag="",
        war_remove_tag="",
        war_target_complete=False,
        war_target_remove=False,
        complete_effect="",
        remove_effect="",
        cancel_effect="",
        cancel_trigger="",
        cancel_if_not_visible=False,
        modifier="",
        remove_trigger="",
        ai_will_do="base = 0",
        priority="1",
        chain="",
        highlight_states="",
    )
    base.update(overrides)
    return base


def test_decision_block_minimum_open_and_close():
    out = generate_decision_block(_dec())
    assert out.startswith("\tTAG_decision = {")
    assert out.endswith("\t}")
    # complete_effect is always emitted with a log line.
    assert "complete_effect = {" in out
    assert 'log = "[GetDateText]: [Root.GetName]: Decision TAG_decision"' in out


def test_decision_block_emits_cost_only_for_pp():
    out = generate_decision_block(_dec(cost="50"))
    assert "\t\tcost = 50" in out


def test_decision_block_custom_cost_mode():
    out = generate_decision_block(
        _dec(
            custom_cost_trigger="has_war = yes",
            custom_cost_text="x",
            ai_hint_pp_cost="10",
        ),
        cost_type="custom",
    )
    assert "\t\tai_hint_pp_cost = 10" in out
    assert "\t\tcustom_cost_trigger = {" in out
    assert "\t\tcustom_cost_text = x" in out
    # cost is not emitted in custom mode even if set.
    assert "\t\tcost = " not in out


def test_decision_block_icon_prefixed_when_not_gfx():
    out = generate_decision_block(_dec(icon="my_icon"))
    assert "\t\ticon = GFX_decision_my_icon" in out

    out2 = generate_decision_block(_dec(icon="GFX_decision_real"))
    assert "\t\ticon = GFX_decision_real" in out2


def test_decision_block_state_targeted():
    out = generate_decision_block(
        _dec(targeted="state", targets="123 456", target_root_trigger="has_war = yes"),
        targeted="state",
    )
    assert "\t\tstate_target = yes" in out
    assert "\t\ttargets = { 123 456 }" in out
    assert "\t\ttarget_root_trigger = {" in out


def test_decision_block_country_targeted_with_array():
    out = generate_decision_block(
        _dec(
            targeted="country",
            target_array="TAG",
            on_map_mode="map_and_decisions_view",
        ),
        targeted="country",
    )
    assert "\t\ttarget_array = TAG" in out
    assert "\t\ton_map_mode = map_and_decisions_view" in out


def test_decision_block_mission_fields():
    out = generate_decision_block(
        _dec(
            is_mission=True,
            mission_timeout="50",
            selectable_mission=True,
            is_good=True,
        )
    )
    assert "\t\tdays_mission_timeout = 50" in out
    assert "\t\tselectable_mission = yes" in out
    assert "\t\tis_good = yes" in out


def test_decision_block_timer_flags():
    out = generate_decision_block(
        _dec(
            days_remove="10",
            days_re_enable="20",
            fire_only_once=True,
        )
    )
    assert "\t\tdays_remove = 10" in out
    assert "\t\tdays_re_enable = 20" in out
    assert "\t\tfire_only_once = yes" in out


def test_decision_block_cancel_if_not_visible():
    out = generate_decision_block(_dec(cancel_if_not_visible=True))
    assert "\t\tcancel_if_not_visible = yes" in out


def test_decision_block_fixed_random_seed_no():
    out = generate_decision_block(_dec(fixed_random_seed=False))
    assert "\t\tfixed_random_seed = no" in out

    out_default = generate_decision_block(_dec())
    assert "fixed_random_seed" not in out_default


def test_decision_block_war_warnings_country_tag():
    out = generate_decision_block(_dec(war_complete_tag="TAG", war_remove_tag="TAG2"))
    assert "\t\twar_with_on_complete = TAG" in out
    assert "\t\twar_with_on_remove = TAG2" in out


def test_decision_block_targeted_war_flags():
    out = generate_decision_block(
        _dec(targeted="state", war_target_complete=True, war_target_remove=True),
        targeted="state",
    )
    assert "\t\twar_with_target_on_complete = yes" in out
    assert "\t\twar_with_target_on_remove = yes" in out


def test_decision_block_complete_effect_injects_log():
    out = generate_decision_block(_dec(complete_effect="add_political_power = 50"))
    assert "\t\tcomplete_effect = {" in out
    assert '\t\t\tlog = "[GetDateText]: [Root.GetName]: Decision TAG_decision"' in out
    assert "\t\t\tadd_political_power = 50" in out


def test_decision_block_remove_effect_injects_log():
    out = generate_decision_block(_dec(remove_effect="add_stability = 0.1"))
    assert "\t\tremove_effect = {" in out
    assert 'log = "[GetDateText]: [Root.GetName]: Decision TAG_decision"' in out


def test_decision_block_modifier_and_ai():
    out = generate_decision_block(
        _dec(modifier="stability_factor = 0.1", ai_will_do="factor = 5")
    )
    assert "\t\tmodifier = {" in out
    assert "\t\tai_will_do = {" in out
    assert "factor = 5" in out


def test_generate_decision_loc_yml_emits_cat_and_dec_keys():
    cats = [_cat()]
    decs = [_dec()]
    out = generate_decision_loc_yml(cats, decs)
    assert out.startswith("l_english:")
    assert ' TAG_cat: "My Cat"' in out
    assert ' TAG_decision: "My Decision"' in out
    assert out.endswith("\n")


def test_generate_decision_loc_yml_includes_descriptions():
    cats = [_cat(loc_desc="Cat desc")]
    decs = [_dec(loc_desc="Dec desc")]
    out = generate_decision_loc_yml(cats, decs)
    assert ' TAG_cat_desc: "Cat desc"' in out
    assert ' TAG_decision_desc: "Dec desc"' in out


def test_generate_decision_scripted_loc_emits_name_and_desc_blocks():
    cats = [_cat()]
    decs = [_dec()]
    out = generate_decision_scripted_loc(cats, decs)
    assert "defined_text = {" in out
    assert "name = GET_TAG_cat_name" in out
    assert "localization_key = TAG_cat" in out
    assert "name = GET_TAG_decision_name" in out


def test_generate_decision_scripted_loc_skips_blank_cat_id():
    cats = [_cat(cat_id="   ")]
    decs = [_dec()]
    out = generate_decision_scripted_loc(cats, decs)
    assert "GET_" not in out


def test_generate_decision_categories_file_emits_block_fields():
    cats = [_cat(icon="cat_icon", visible="has_war = yes", allowed="always = yes")]
    out = generate_decision_categories_file(cats, [])
    assert "# FILE: common/decisions/categories/TAG_categories.txt" in out
    assert "TAG_cat = {" in out
    assert "\ticon = cat_icon" in out
    assert "\tvisible = {" in out
    assert "\tallowed = {" in out


def test_generate_decision_categories_file_on_map_area():
    cats = [_cat(on_map_area=True, map_state="5", map_name="area", map_zoom="500")]
    out = generate_decision_categories_file(cats, [])
    assert "\ton_map_area = {" in out
    assert "\t\tstate = 5" in out
    assert "\t\tname = area" in out
    assert "\t\tzoom = 500" in out


def test_generate_decisions_file_groups_by_cat():
    cats = [_cat(uid="c1", cat_id="CAT_ONE")]
    decs = [
        _dec(uid="d1", cat_uid="c1", dec_id="D1"),
        _dec(uid="d2", cat_uid="c1", dec_id="D2"),
    ]
    out = generate_decisions_file(cats, decs)
    assert "CAT_ONE = {" in out
    assert "D1 = {" in out
    assert "D2 = {" in out


def test_generate_decisions_file_skips_empty_cat():
    cats = [_cat(uid="c1", cat_id="CAT_ONE"), _cat(uid="c2", cat_id="CAT_EMPTY")]
    decs = [_dec(cat_uid="c1")]
    out = generate_decisions_file(cats, decs)
    assert "CAT_ONE = {" in out
    assert "CAT_EMPTY" not in out
