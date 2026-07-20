from copy import deepcopy

import pytest

from hoi4cm.focus_tree.codec import apply_focus_code, render_focus_block
from hoi4cm.focus_tree.operations import build_focus_name_lookup
from hoi4cm.models import Focus


def test_code_block_apply_round_trips_all_editable_fields():
    prerequisite = Focus(1, 1)
    prerequisite.name = "TST_prerequisite"
    mutex = Focus(2, 2)
    mutex.name = "TST_mutex"
    focus = Focus(5, 6)
    focus.name = "TST_focus"
    focus.relative_position_id = prerequisite.name
    focus._rel_dx = 4
    focus._rel_dy = 5
    focus.gfx = "GFX_goal_test"
    focus.text = "TST_custom_text"
    focus.cost = 7.5
    focus.prereqs = [[prerequisite.id]]
    focus.mutex = [mutex.id]
    focus.allow_branch = "OR = {\n\thas_country_flag = one\n\thas_country_flag = two\n}"
    focus.available_cond = "has_country_flag = available"
    focus.bypass_cond = "has_country_flag = bypass"
    focus.cancel_cond = "has_country_flag = cancel"
    focus.will_lead_to_war_with = "ENG"
    focus.complete_tooltip = "custom_effect_tooltip = complete"
    focus.select_effect = "set_country_flag = selected"
    focus.bypass_effect = "set_country_flag = bypassed"
    focus.cancel_if_invalid = False
    focus.continue_if_invalid = True
    focus.available_if_capitulated = True
    focus.search_filters = "FOCUS_FILTER_POLITICAL FOCUS_FILTER_INDUSTRY"
    focus.effects = [{"type": "add_political_power", "fields": {"amount": "25"}}]
    focus.offsets = [
        {"x": 3, "y": -1, "trigger": "original_tag = TST"},
        {"x": -2, "y": 4, "trigger": ""},
    ]
    focus.ai_will_do_raw = "base = 3\nmodifier = {\n\tfactor = 2\n}"
    lookup = {candidate.id: candidate for candidate in (prerequisite, mutex, focus)}
    identity = id(focus)
    model_id = focus.id

    code = render_focus_block(
        focus,
        focus_lookup=lookup,
        focus_name_lookup=build_focus_name_lookup(lookup.values()),
    )
    apply_focus_code(focus, code, focus_lookup=lookup)

    assert id(focus) == identity
    assert focus.id == model_id
    assert lookup[model_id] is focus
    assert focus.name == "TST_focus"
    assert focus.gfx == "GFX_goal_test"
    assert focus.text == "TST_custom_text"
    assert (focus.x, focus.y, focus.cost) == (5, 6, 7.5)
    assert focus.relative_position_id == prerequisite.name
    assert focus.prereqs == [[prerequisite.id]]
    assert focus.mutex == [mutex.id]
    assert "has_country_flag = one" in focus.allow_branch
    assert focus.available_cond == "has_country_flag = available"
    assert focus.bypass_cond == "has_country_flag = bypass"
    assert focus.cancel_cond == "has_country_flag = cancel"
    assert focus.will_lead_to_war_with == "ENG"
    assert "custom_effect_tooltip = complete" in focus.complete_tooltip
    assert "set_country_flag = selected" in focus.select_effect
    assert "set_country_flag = bypassed" in focus.bypass_effect
    assert focus.cancel_if_invalid is False
    assert focus.continue_if_invalid is True
    assert focus.available_if_capitulated is True
    assert focus.search_filters == "FOCUS_FILTER_POLITICAL FOCUS_FILTER_INDUSTRY"
    assert "add_political_power = 25" in focus.effects[0]["fields"]["raw"]
    assert focus.offsets == [
        {"x": 3, "y": -1, "trigger": "original_tag = TST"},
        {"x": -2, "y": 4, "trigger": ""},
    ]
    assert "base = 3" in focus.ai_will_do_raw


def test_code_apply_failure_does_not_mutate_existing_focus():
    focus = Focus(5, 6)
    focus.name = "TST_unchanged"
    focus.effects = [{"type": "set_country_flag", "fields": {"flag": "safe"}}]
    before = deepcopy(focus.__dict__)

    with pytest.raises(ValueError):
        apply_focus_code(
            focus, "this is not a focus block", focus_lookup={focus.id: focus}
        )

    assert focus.__dict__ == before


def test_code_block_apply_preserves_joint_trigger():
    focus = Focus(1, 2)
    focus.name = "TST_joint"
    focus._joint_extra = 'joint_trigger = {\n\thas_dlc = "No Step Back"\n}'
    lookup = {focus.id: focus}

    apply_focus_code(
        focus,
        render_focus_block(
            focus,
            focus_lookup=lookup,
            focus_name_lookup=build_focus_name_lookup(lookup.values()),
        ),
        focus_lookup=lookup,
    )

    assert "has_dlc" in focus._joint_extra


def test_code_block_apply_keeps_moved_relative_focus_position():
    parent = Focus(0, 0)
    parent.name = "TST_parent"
    focus = Focus(5, 2)
    focus.name = "TST_child"
    focus.relative_position_id = parent.name
    focus._raw_gx = 1
    focus._raw_gy = 0
    focus._rel_dx = 1
    focus._rel_dy = 0
    lookup = {parent.id: parent, focus.id: focus}

    code = render_focus_block(
        focus,
        focus_lookup=lookup,
        focus_name_lookup=build_focus_name_lookup(lookup.values()),
    )
    apply_focus_code(focus, code, focus_lookup=lookup)

    assert (focus.x, focus.y) == (5, 2)
    assert (focus._rel_dx, focus._rel_dy) == (1, 0)


def test_code_block_apply_keeps_raw_coordinates_with_conditional_offset():
    focus = Focus(3, 0)
    focus.name = "TST_offset"
    focus._raw_gx = 1
    focus._raw_gy = 0
    focus.offsets = [{"x": 2, "y": 0, "trigger": "original_tag = TST"}]
    lookup = {focus.id: focus}

    code = render_focus_block(
        focus,
        focus_lookup=lookup,
        focus_name_lookup=build_focus_name_lookup(lookup.values()),
    )
    apply_focus_code(focus, code, focus_lookup=lookup)

    assert (focus.x, focus.y) == (3, 0)
    assert (focus._raw_gx, focus._raw_gy) == (1, 0)
