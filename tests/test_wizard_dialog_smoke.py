"""Tk smoke tests for the wizard collect_* helpers (issue #62, option C).

Uses a real ``tk.StringVar``/``tk.Text`` under Xvfb to prove the helpers
are wired to Tk correctly — the headless suite in ``test_wizard_collectors``
covers logic with fakes, this file covers the Tk contract.  All tests are
skipped when no display is available (``tests/conftest.py:tk_root``).
"""

import tkinter as tk

from hoi4cm.wizards._generators import generate_decision_block
from hoi4cm.wizards.additional_income import collect_additional_income_state
from hoi4cm.wizards.decision import collect_decision_state
from hoi4cm.wizards.dyn_mod import collect_dyn_mod_state
from hoi4cm.wizards.national_spirit import collect_national_spirit_state


def test_collect_decision_state_with_real_stringvar(tk_root):
    parent = tk.Frame(tk_root)
    v_targeted = tk.StringVar(parent, value="country")
    v_cost = tk.StringVar(parent, value="custom")
    state = collect_decision_state({"targeted": v_targeted, "cost_type": v_cost})
    assert state == {"targeted": "country", "cost_type": "custom"}
    v_targeted.set("none")
    assert collect_decision_state({"targeted": v_targeted})["targeted"] == "none"


def test_collect_decision_state_tk_mutation_changes_generator_output(tk_root):
    parent = tk.Frame(tk_root)
    v = tk.StringVar(parent, value="none")
    base = {
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
    untargeted = generate_decision_block(
        base, **collect_decision_state({"targeted": v})
    )
    assert "state_target" not in untargeted
    v.set("state")
    targeted = generate_decision_block(base, **collect_decision_state({"targeted": v}))
    assert "state_target = yes" in targeted


def test_collect_national_spirit_state_with_real_widgets(tk_root):
    v_id = tk.StringVar(tk_root, value="TAG_s")
    v_cost = tk.StringVar(tk_root, value="50")
    t_allowed = tk.Text(tk_root)
    t_allowed.insert("1.0", "has_war = yes")
    t_extra = tk.Text(tk_root)
    t_extra.insert("1.0", "stability_factor = 0.05")
    state = collect_national_spirit_state(
        {"mod_id": v_id, "cost": v_cost},
        {"allowed": t_allowed, "extra": t_extra},
        [],
    )
    assert state["mod_id"] == "TAG_s"
    assert state["cost"] == "50"
    assert state["allowed"] == "has_war = yes"
    assert state["extra_modifiers"] == "stability_factor = 0.05"


def test_collect_dyn_mod_state_with_real_widgets(tk_root):
    v_id = tk.StringVar(tk_root, value="TAG_dyn")
    v_scope = tk.StringVar(tk_root, value="state")
    t_enable = tk.Text(tk_root)
    t_enable.insert("1.0", "has_war = yes")
    t_mods = tk.Text(tk_root)
    t_mods.insert("1.0", "stability_factor = my_var")
    t_const = tk.Text(tk_root)
    state = collect_dyn_mod_state(
        {"mod_id": v_id, "scope": v_scope},
        {"enable": t_enable, "mods": t_mods, "const": t_const},
    )
    assert state["mod_id"] == "TAG_dyn"
    assert state["scope"] == "state"
    assert state["enable"] == "has_war = yes"
    assert state["mods_raw"] == "stability_factor = my_var"


def test_collect_additional_income_state_with_real_widgets(tk_root):
    vars_map = {
        "idea_id": tk.StringVar(tk_root, value=" HKG_bonus "),
        "country_tag": tk.StringVar(tk_root, value=" hkg "),
        "variable_name": tk.StringVar(tk_root, value=" HKG_gain "),
        "amount": tk.StringVar(tk_root, value=" 0.05 "),
        "tooltip_key": tk.StringVar(tk_root, value=" HKG_TT "),
        "spirit_name": tk.StringVar(tk_root, value=" Free Trade "),
        "mode": tk.StringVar(tk_root, value="also_spirit"),
        "formula_type": tk.StringVar(tk_root, value="gdp_pct"),
    }
    state = collect_additional_income_state(vars_map)
    assert state["idea_id"] == "HKG_bonus"
    assert state["country_tag"] == "HKG"
    assert state["variable_name"] == "HKG_gain"
    assert state["mode"] == "also_spirit"
    assert state["formula_type"] == "gdp_pct"
