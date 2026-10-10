"""Record builders shared by tests that need a fully populated sample."""

from __future__ import annotations

from typing import Any

from hoi4cm.models import Focus


def make_focus(**overrides: Any) -> Focus:
    focus = Focus(id=overrides.pop("id", 1), x=0, y=0)
    focus.name = "keep"
    focus.icon = "⚔"
    focus.gfx = "GFX_goal_generic_political_pressure"
    focus.cost = 10
    focus.ai_will_do = 1
    focus.ai_will_do_raw = "base = 1"
    focus.desc = "desc"
    focus.search_filters = "FOCUS_FILTER_POLITICAL"
    focus.available_cond = ""
    focus.bypass_cond = ""
    focus.cancel_cond = ""
    focus.cancel_if_invalid = True
    focus.continue_if_invalid = False
    focus.available_if_capitulated = False
    focus.offsets = []
    for key, value in overrides.items():
        setattr(focus, key, value)
    return focus


def default_decision(**overrides: Any) -> dict[str, Any]:
    decision: dict[str, Any] = {
        "uid": "dec-1",
        "cat_uid": "cat-1",
        "dec_id": "TAG_decision",
        "loc_name": "My Decision",
        "loc_desc": "",
        "icon": "",
        "allowed": "",
        "visible": "",
        "available": "",
        "cost_type": "pp",
        "cost": "25",
        "custom_cost_trigger": "",
        "custom_cost_text": "",
        "ai_hint_pp_cost": "",
        "cost_var": "",
        "cost_amount": "",
        "days_remove": "",
        "days_re_enable": "",
        "fire_only_once": False,
        "fixed_random_seed": True,
        "is_mission": False,
        "mission_timeout": "100",
        "selectable_mission": False,
        "is_good": False,
        "activation": "",
        "highlight_states": "",
        "on_map_mode": "map_and_decisions_view",
        "state_target_scope": "any",
        "target_root_trigger": "",
        "target_trigger": "",
        "targets": "",
        "targets_dynamic": False,
        "target_non_existing": False,
        "target_array": "",
        "modifier": "",
        "complete_effect": "",
        "timeout_effect": "",
        "remove_effect": "",
        "cancel_trigger": "",
        "cancel_effect": "",
        "cancel_if_not_visible": False,
        "remove_trigger": "",
        "ai_will_do": "",
        "priority": "1",
        "war_target_complete": False,
        "war_target_remove": False,
        "war_complete_tag": "",
        "war_remove_tag": "",
    }
    decision.update(overrides)
    return decision
