"""Pure rendering for structured focus effects."""

from __future__ import annotations

import re
from collections.abc import Mapping

from hoi4cm.data import EFFECT_DEFS

__all__ = ["render_effect"]


def render_effect(eff: Mapping[str, object]) -> str:
    """Render a single effect as HOI4 code (3-tab indent, in completion_reward)."""
    t = eff.get("type", "")
    if not isinstance(t, str):
        t = ""
    fields = eff.get("fields", {})
    f: Mapping[str, object] = fields if isinstance(fields, Mapping) else {}
    IND = "\t\t\t"

    def block(name, pairs):
        inner = "\n".join(f"{IND}\t{k} = {v}" for k, v in pairs)
        return f"{IND}{name} = {{\n{inner}\n{IND}}}"

    def g(key, default=""):
        return f.get(key, default)

    # ── Dispatch table: type → renderer ───────────────────────
    _DISPATCH = {
        "add_tech_bonus": lambda: block(
            "add_tech_bonus",
            [
                ("name", g("name", "bonus")),
                ("bonus", g("bonus", "0.5")),
                ("uses", g("uses", "1")),
                ("category", g("category", "infantry_weapons")),
            ],
        ),
        "add_popularity": lambda: (
            block(
                "add_popularity",
                [
                    ("ideology", g("ideology", "democratic")),
                    ("popularity", g("popularity", "0.05")),
                ],
            )
            + f"\n{IND}recalculate_party = yes"
        ),
        "set_politics": lambda: block(
            "set_politics",
            [
                ("ruling_party", g("ruling_party", "democratic")),
                ("elections_allowed", g("elections_allowed", "no")),
            ],
        ),
        "add_timed_idea": lambda: block(
            "add_timed_idea", [("idea", g("idea", "")), ("days", g("days", "180"))]
        ),
        "swap_ideas": lambda: block(
            "swap_ideas",
            [
                ("remove_idea", g("remove_idea", "old_spirit")),
                ("add_idea", g("add_idea", "new_spirit")),
            ],
        ),
        "declare_war_on": lambda: block(
            "declare_war_on",
            [
                ("target", g("target", "TAG")),
                ("type", g("type", "annex_everything")),
            ],
        ),
        "create_wargoal": lambda: block(
            "create_wargoal",
            [
                ("type", g("type", "annex_everything")),
                ("target", g("target", "TAG")),
            ],
        ),
        "annex_country": lambda: block(
            "annex_country",
            [
                ("target", g("target", "TAG")),
                ("transfer_troops", g("transfer_troops", "no")),
            ],
        ),
        "add_opinion_modifier": lambda: block(
            "add_opinion_modifier",
            [
                ("target", g("target", "TAG")),
                ("modifier", g("modifier", "my_opinion_mod")),
            ],
        ),
        "diplomatic_relation": lambda: block(
            "diplomatic_relation",
            [
                ("country", g("country", "TAG")),
                ("relation", g("relation", "guarantee")),
                ("active", g("active", "yes")),
            ],
        ),
        "add_ai_strategy": lambda: block(
            "add_ai_strategy",
            [
                ("type", g("type", "alliance")),
                ("id", g("id", "TAG")),
                ("value", g("value", "100")),
            ],
        ),
        "start_civil_war": lambda: block(
            "start_civil_war",
            [("ideology", g("ideology", "communism")), ("size", g("size", "0.5"))],
        ),
        "load_focus_tree": lambda: block(
            "load_focus_tree",
            [
                ("tree", g("tree", "TAG_focus_tree")),
                ("keep_completed", g("keep_completed", "yes")),
            ],
        ),
        "add_building_construction": lambda: block(
            "add_building_construction",
            [
                ("type", g("type", "industrial_complex")),
                ("level", g("level", "1")),
                ("instant_build", g("instant_build", "no")),
            ],
        ),
        "create_unit": lambda: (
            f"{IND}create_unit = {{\n"
            f'{IND}\tdivision = "name = \\"'
            f"{g('division_name', '1st Infantry Division')}"
            f'\\" '
            f'division_template = \\"'
            f"{g('division_template', 'Infantry Division')}"
            f'\\" '
            f'start_experience_factor = {g("start_experience_factor", "0.2")}"\n'
            f"{IND}\towner = {g('owner', 'ROOT')}\n"
            f"{IND}}}"
        ),
        "set_technology": lambda: (
            f"{IND}set_technology = {{ {g('tech_id', 'infantry_weapons1')} = "
            f"{'1' if g('researched', 'yes') == 'yes' else '0'} }}"
        ),
        "modify_timed_idea": lambda: block(
            "modify_timed_idea",
            [("idea", g("idea", "my_spirit")), ("days", g("days", "30"))],
        ),
        "build_railway": lambda: block(
            "build_railway",
            [("level", g("level", "1")), ("path", g("path", "{ 1 2 3 }"))],
        ),
        "division_template": lambda: (
            f"{IND}division_template = {{\n"
            f'{IND}\tname = "{g("name", "Infantry Division")}"\n'
            f"{IND}\tregiments = {{\n"
            + "\n".join(
                f"{IND}\t\t{ln.strip()}"
                for ln in g("regiments", "infantry = { x = 0 y = 0 }")
                .strip()
                .splitlines()
                if ln.strip()
            )
            + f"\n{IND}\t}}\n"
            f"{IND}}}"
        ),
        "load_oob": lambda: f'{IND}load_oob = "{g("file", "TAG_1936")}"',
        "set_oob": lambda: f'{IND}set_oob = "{g("file", "TAG_1936")}"',
        "log": lambda: f'{IND}log = "{g("text")}"',
        "set_variable": lambda: (
            f"{IND}set_variable = {{ {g('var', 'my_var')} = {g('value', '0')} }}"
        ),
        "force_update_dynamic_modifier": lambda: (
            f"{IND}force_update_dynamic_modifier = yes"
        ),
        "unlock_decision_category_tooltip": lambda: (
            f"{IND}unlock_decision_category_tooltip = {g('category', 'TAG_decisions')}"
        ),
        "unlock_decision_tooltip": lambda: (
            f"{IND}unlock_decision_tooltip = {g('decision', 'TAG_decision')}"
        ),
        "ingame_update_setup": lambda: f"{IND}ingame_update_setup = yes",
        # MD scripted effects
        "md_modify_treasury": lambda: (
            f"{IND}set_temp_variable = {{ "
            f"treasury_change = {g('amount', '-10.00')} }}\n"
            f"{IND}modify_treasury_effect = yes"
        ),
        "md_modify_debt": lambda: (
            f"{IND}set_temp_variable = {{ debt_change = {g('amount', '0.1')} }}\n"
            f"{IND}modify_debt_effect = yes"
        ),
        "md_modify_international_investment": lambda: (
            f"{IND}set_temp_variable = {{ "
            f"int_investment_change = {g('amount', '0.1')} }}\n"
            f"{IND}modify_international_investment_effect = yes"
        ),
        "md_modify_corporate_tax": lambda: (
            f"{IND}set_temp_variable = {{ corp_change = {g('amount', '2')} }}\n"
            f"{IND}modify_corporate_tax_rate_effect = yes"
        ),
        "md_modify_population_tax": lambda: (
            f"{IND}set_temp_variable = {{ pop_change = {g('amount', '2')} }}\n"
            f"{IND}modify_population_tax_rate_effect = yes"
        ),
        "md_flat_productivity": lambda: (
            f"{IND}set_temp_variable = {{ "
            f"temp_productivity_change = {g('amount', '0.025')} }}\n"
            f"{IND}flat_productivity_change_effect = yes"
        ),
        "md_economic_cycle": lambda: f"{IND}{g('cycle', 'stable_growth')} = yes",
        "md_gov_spending": lambda: (
            f"{IND}{g('action', 'increase_social_spending')} = yes"
        ),
        "md_build_random": lambda: (
            f"{IND}set_temp_variable = {{ "
            f"treasury_change = {g('treasury_change', '-7.50')} }}\n"
            f"{IND}modify_treasury_effect = yes\n"
            f"{IND}{g('effect', 'one_random_industrial_complex')} = yes"
        ),
        "md_enrichment_facility": lambda: (
            f"{IND}set_temp_variable = {{ temp_change = {g('count', '1')} }}\n"
            f"{IND}build_enrichment_facilities_effect = yes"
        ),
        "md_battery_park": lambda: (
            f"{IND}set_temp_variable = {{ temp_change = {g('count', '1')} }}\n"
            f"{IND}build_battery_park_effect = yes"
        ),
        "md_coalition_add": lambda: (
            f"{IND}set_temp_variable = {{ add_col_one = {g('party_index', '5')} }}\n"
            f"{IND}add_coalition_members_effect = yes"
        ),
        "md_coalition_remove": lambda: (
            f"{IND}set_temp_variable = {{ "
            f"remove_col_one = {g('party_index', '5')} }}\n"
            f"{IND}remove_coalition_members_effect = yes"
        ),
        "md_domestic_influence": lambda: (
            f"{IND}set_temp_variable = {{ percent_change = {g('percent', '10')} }}\n"
            f"{IND}change_domestic_influence_percentage = yes"
        ),
        "md_eurosceptic_all": lambda: (
            f"{IND}set_temp_variable = {{ "
            f"modify_eurosceptic = {g('amount', '-0.05')} }}\n"
            f"{IND}EU_eurosceptic_change = yes"
        ),
        # MD Budget — individual yes-call entries
        "increase_centralization": lambda: f"{IND}increase_centralization = yes",
        "decrease_centralization": lambda: f"{IND}decrease_centralization = yes",
        "increase_social_spending": lambda: f"{IND}increase_social_spending = yes",
        "decrease_social_spending": lambda: f"{IND}decrease_social_spending = yes",
        "increase_education_budget": lambda: f"{IND}increase_education_budget = yes",
        "decrease_education_budget": lambda: f"{IND}decrease_education_budget = yes",
        "increase_healthcare_budget": lambda: f"{IND}increase_healthcare_budget = yes",
        "decrease_healthcare_budget": lambda: f"{IND}decrease_healthcare_budget = yes",
        "increase_policing_budget": lambda: f"{IND}increase_policing_budget = yes",
        "decrease_policing_budget": lambda: f"{IND}decrease_policing_budget = yes",
        "increase_exports": lambda: f"{IND}increase_exports = yes",
        "decrease_exports": lambda: f"{IND}decrease_exports = yes",
        "increase_military_spending": lambda: f"{IND}increase_military_spending = yes",
        "decrease_military_spending": lambda: f"{IND}decrease_military_spending = yes",
        "increase_economic_growth": lambda: f"{IND}increase_economic_growth = yes",
        "decrease_economic_growth": lambda: f"{IND}decrease_economic_growth = yes",
        "increase_corruption": lambda: f"{IND}increase_corruption = yes",
        "decrease_corruption": lambda: f"{IND}decrease_corruption = yes",
        "increase_Free_Market_Economy": lambda: (
            f"{IND}increase_Free_Market_Economy = yes"
        ),
        "increase_Planned_Economy": lambda: f"{IND}increase_Planned_Economy = yes",
        "economic_boom": lambda: f"{IND}economic_boom = yes",
        "stable_growth": lambda: f"{IND}stable_growth = yes",
        "fast_growth": lambda: f"{IND}fast_growth = yes",
        "recession": lambda: f"{IND}recession = yes",
        "stagnation": lambda: f"{IND}stagnation = yes",
        "depression": lambda: f"{IND}depression = yes",
        # MD Politics
        "set_party_index_to_ruling_party": lambda: (
            f"{IND}set_party_index_to_ruling_party = yes"
        ),
        "recalculate_party": lambda: f"{IND}recalculate_party = yes",
        "add_own_ideology_drift": lambda: f"{IND}add_own_ideology_drift = yes",
        # MD Scripted
        "cyber_execute_operation": lambda: f"{IND}cyber_execute_operation = yes",
        "modify_reform_expectance_effect": lambda: (
            f"{IND}modify_reform_expectance_effect = yes"
        ),
    }

    if t in _DISPATCH:
        return _DISPATCH[t]()

    # ── Faction opinion individual renderers ────────────────────
    _FACTION_OPINIONS = {
        "change_small_medium_business_owners_opinion",
        "change_industrial_conglomerates_opinion",
        "change_fossil_fuel_industry_opinion",
        "change_defense_industry_opinion",
        "change_maritime_industry_opinion",
        "change_international_bankers_opinion",
        "change_oligarchs_opinion",
        "change_farmers_opinion",
        "change_landowners_opinion",
        "change_labour_unions_opinion",
        "change_communist_cadres_opinion",
        "change_the_clergy_opinion",
        "change_the_ulema_opinion",
        "change_the_priesthood_opinion",
        "change_the_wahabi_ulema_opinion",
        "change_the_military_opinion",
        "change_intelligence_community_opinion",
        "change_the_donju_opinion",
        "change_saudi_royal_family_opinion",
        "change_foreign_jihadis_opinion",
        "change_iranian_quds_force_opinion",
        "change_chaebols_opinion",
        "change_wall_street_opinion",
        "change_all_internal_faction_opinion",
    }
    if t in _FACTION_OPINIONS:
        return (
            f"{IND}set_temp_variable = {{ temp_opinion = {g('opinion', '5')} }}\n"
            f"{IND}{t} = yes"
        )

    # ── Multi-case handlers ────────────────────────────────────
    if t == "add_equipment_to_stockpile":
        pairs = [
            ("type", g("type", "infantry_equipment_1")),
            ("amount", g("amount", "500")),
        ]
        if g("producer", "").strip():
            pairs.append(("producer", g("producer")))
        return block("add_equipment_to_stockpile", pairs)

    if t in ("country_event", "news_event"):
        pairs = [("id", g("id", "my_event.1"))]
        d = g("days", "0").strip()
        if d and d != "0":
            pairs.append(("days", d))
        return block(t, pairs)

    if t in ("hidden_effect", "effect_tooltip"):
        raw = g("raw", "").strip()
        if not raw and "_list" in f:
            items = f["_list"]
            if isinstance(items, list):
                raw = "\n".join(
                    f"{IND}\t{ik} = {iv}"
                    for item in items
                    if isinstance(item, dict)
                    for ik, iv in item.items()
                    if not str(ik).startswith("_")
                )
        inner = "\n".join(f"{IND}\t{ln}" for ln in raw.splitlines())
        return f"{IND}{t} = {{\n{inner}\n{IND}}}"

    if t == "_raw_block":
        raw = g("raw", "").strip()
        return "\n".join(f"{IND}{ln}" for ln in raw.splitlines()) if raw else ""

    if t == "add_to_variable":
        vn = g("var", "AM_my_stat_var")
        val = g("value", "0.05")
        tt = g("tooltip", "").strip()
        base = f"{IND}add_to_variable = {{ {vn} = {val}"
        return base + (f" tooltip = {tt} }}" if tt else " }")

    # ── Variable math — all use { var = value } block form ──────────
    _VAR_TWO_FIELD = {
        "subtract_from_variable",
        "multiply_variable",
        "divide_variable",
        "modulo_variable",
        "add_to_temp_variable",
        "subtract_from_temp_variable",
        "multiply_temp_variable",
        "divide_temp_variable",
        "modulo_temp_variable",
    }
    if t in _VAR_TWO_FIELD:
        return f"{IND}{t} = {{ {g('var', 'my_var')} = {g('value', '1')} }}"

    if t == "set_temp_variable":
        return (
            f"{IND}set_temp_variable = {{ "
            f"{g('var', 'my_temp_var')} = {g('value', '1')} }}"
        )

    # single-arg variable ops (no block needed)
    if t in ("round_variable", "clear_variable"):
        return f"{IND}{t} = {g('var', 'my_var')}"
    if t in ("round_temp_variable",):
        return f"{IND}{t} = {g('var', 'my_temp_var')}"

    # clamp = { var = { min = X max = Y } }
    if t == "clamp_variable":
        return (
            f"{IND}clamp_variable = {{ {g('var', 'my_var')} = {{ "
            f"min = {g('min', '0')} max = {g('max', '100')} }} }}"
        )
    if t == "clamp_temp_variable":
        return (
            f"{IND}clamp_temp_variable = {{ {g('var', 'my_temp_var')} = {{ "
            f"min = {g('min', '0')} max = {g('max', '100')} }} }}"
        )

    # set_variable_to_random / randomize_variable = { var = { max = X } }
    if t in ("set_variable_to_random", "randomize_variable"):
        return f"{IND}{t} = {{ {g('var', 'my_var')} = {{ max = {g('max', '10')} }} }}"
    if t in ("set_temp_variable_to_random", "randomize_temp_variable"):
        return (
            f"{IND}{t} = {{ {g('var', 'my_temp_var')} = {{ max = {g('max', '10')} }} }}"
        )

    if t == "add_dynamic_modifier":
        out = [
            f"{IND}add_dynamic_modifier = {{",
            f"{IND}\tmodifier = {g('modifier', 'TAG_modifier')}",
        ]
        sc = g("scope", "").strip()
        dy = g("days", "").strip()
        if sc:
            out.append(f"{IND}\tscope = {sc}")
        if dy:
            out.append(f"{IND}\tdays = {dy}")
        out.append(f"{IND}}}")
        return "\n".join(out)

    if t == "add_dynamic_modifier_with_tt":
        # Generates add_dynamic_modifier + adds_dynamic_modifier_tt tooltip together
        # Per skill rules: use adds_ when the block contains add_dynamic_modifier
        mod = g("modifier", "TAG_modifier")
        sc = g("scope", "").strip()
        dy = g("days", "").strip()
        out = [f"{IND}add_dynamic_modifier = {{", f"{IND}\tmodifier = {mod}"]
        if sc:
            out.append(f"{IND}\tscope = {sc}")
        if dy:
            out.append(f"{IND}\tdays = {dy}")
        out.append(f"{IND}}}")
        out.append(f"{IND}custom_effect_tooltip = {{")
        out.append(f"{IND}\tlocalization_key = adds_dynamic_modifier_tt")
        out.append(f"{IND}\tMODIFIER = {mod}")
        out.append(f"{IND}}}")
        return "\n".join(out)

    if t == "remove_dynamic_modifier":
        return (
            f"{IND}remove_dynamic_modifier = {{\n"
            f"{IND}\tmodifier = {g('modifier', 'TAG_modifier')}\n"
            f"{IND}}}"
        )

    if t == "dynamic_modifier_tooltip":
        loc_key = g("localization_key", "modifies_dynamic_modifier_tt")
        mod = g("MODIFIER", "TAG_modifier")
        return (
            f"{IND}custom_effect_tooltip = {{\n"
            f"{IND}\tlocalization_key = {loc_key}\n"
            f"{IND}\tMODIFIER = {mod}\n"
            f"{IND}}}"
        )

    if t in ("custom_effect_tooltip", "custom_effect_tooltip_block"):
        if (
            f.get("_block_form")
            or "localization_key" in f
            or "MODIFIER" in f
            or t.endswith("_block")
        ):
            loc_key = g("localization_key", "modifies_dynamic_modifier_tt")
            # adds_dynamic_modifier_tt: block contains add_dynamic_modifier
            # modifies_dynamic_modifier_tt: block only changes variables
            # (no add_dynamic_modifier)
            return (
                f"{IND}custom_effect_tooltip = {{\n"
                f"{IND}\tlocalization_key = {loc_key}\n"
                f"{IND}\tMODIFIER = {g('MODIFIER', 'TAG_modifier')}\n"
                f"{IND}}}"
            )
        return f"{IND}custom_effect_tooltip = {g('tooltip', 'my_tooltip_key')}"

    if t in (
        "md_small_expenditure",
        "md_medium_expenditure",
        "md_large_expenditure",
    ):
        return f"{IND}{t.replace('md_', '')} = yes"

    if t == "md_build_state":
        effect = g("effect", "one_state_industrial_complex")
        state = g("state_id", "117")
        tchange = g("treasury_change", "-7.50")
        return (
            f"{IND}set_temp_variable = {{ treasury_change = {tchange} }}\n"
            f"{IND}modify_treasury_effect = yes\n"
            f"{IND}{state} = {{\n"
            f"{IND}\t{effect} = yes\n"
            f"{IND}}}"
        )

    if t == "md_add_resource":
        rtype = g("resource_type", "steel")
        amount = g("amount", "4")
        tchange = g("treasury_change", "-3.75")
        return (
            f"{IND}set_temp_variable = {{ treasury_change = {tchange} }}\n"
            f"{IND}modify_treasury_effect = yes\n"
            f"{IND}capital_scope = {{\n"
            f"{IND}\tadd_resource = {{\n"
            f"{IND}\t\ttype = {rtype}\n"
            f"{IND}\t\tamount = {amount}\n"
            f"{IND}\t}}\n"
            f"{IND}}}"
        )

    if t == "md_party_popularity":
        return (
            f"{IND}set_temp_variable = {{ party_index = {g('party_index', '2')} }}\n"
            f"{IND}set_temp_variable = {{ "
            f"party_popularity_increase = {g('amount', '0.10')} }}\n"
            f"{IND}add_relative_party_popularity = yes"
        )

    if t == "md_change_ruling_party":
        return (
            f"{IND}set_temp_variable = {{ "
            f"rul_party_temp = {g('rul_party_temp', '2')} }}\n"
            f"{IND}change_ruling_party_effect = yes\n"
            f"{IND}set_politics = {{\n"
            f"{IND}\truling_party = {g('ruling_party', 'western')}\n"
            f"{IND}\telections_allowed = {g('elections_allowed', 'no')}\n"
            f"{IND}}}"
        )

    if t == "md_ban_party":
        return (
            f"{IND}set_temp_variable = {{ party_index = {g('party_index', '1')} }}\n"
            f"{IND}ban_party_scripted_call = yes"
        )

    if t == "md_unban_party":
        return (
            f"{IND}set_temp_variable = {{ party_index = {g('party_index', '1')} }}\n"
            f"{IND}unban_party_scripted_call = yes"
        )

    if t == "md_pp_loss":
        return f"{IND}{g('duration', 'lose_pp_for_month')} = yes"

    if t == "md_faction_opinion":
        return (
            f"{IND}set_temp_variable = {{ temp_opinion = {g('opinion', '5')} }}\n"
            f"{IND}{g('faction', 'change_the_military_opinion')} = yes"
        )

    if t == "md_influence_country":
        return (
            f"{IND}set_temp_variable = {{ percent_change = {g('percent', '5')} }}\n"
            f"{IND}set_temp_variable = {{ tag_index = ROOT }}\n"
            f"{IND}set_temp_variable = {{ "
            f"influence_target = {g('target', 'GER')} }}\n"
            f"{IND}change_influence_percentage = yes"
        )

    if t == "md_eurosceptic_target":
        return (
            f"{IND}set_temp_variable = {{ "
            f"modify_eurosceptic = {g('amount', '0.05')} }}\n"
            f"{IND}set_temp_variable = {{ "
            f"modify_eurosceptic_target = {g('target', 'GER')} }}\n"
            f"{IND}eurosceptic_change = yes"
        )

    if t == "md_cart_strength":
        return (
            f"{IND}set_temp_variable = {{ "
            f"cart_strength_change = {g('strength', '2')} }}\n"
            f"{IND}set_temp_variable = {{ "
            f"cart_influence_change = {g('influence', '2')} }}\n"
            f"{IND}modify_cartel_variables_effect = yes"
        )

    if t == "md_relative_party_popularity":
        return (
            f"{IND}set_temp_variable = {{ party_index = {g('party_index', '1')} }}\n"
            f"{IND}set_temp_variable = {{ "
            f"party_popularity_increase = {g('amount', '0.02')} }}\n"
            f"{IND}set_temp_variable = {{ "
            f"temp_outlook_increase = {g('temp_outlook_increase', '0.02')} }}\n"
            f"{IND}add_relative_party_popularity = yes"
        )

    if t.startswith("md_modifier_"):
        return (
            f"{IND}# MD MODIFIER (place inside idea modifier block):\n"
            f"{IND}# {g('modifier', '')} = {g('value', '0.05')}"
        )

    # ── Scope / if / else blocks ───────────────────────────────
    _SCOPE_TYPES = {
        "if",
        "else_if",
        "else",
        "every_country",
        "every_state",
        "every_ally",
        "every_enemy_country",
        "every_faction_member",
        "every_subject_country",
        "every_neighbor_country",
        "every_allied_country",
        "every_other_country",
        "every_occupied_country",
        "every_possible_country",
        "every_controlled_state",
        "every_owned_state",
        "every_core_state",
        "every_neighbor_state",
        "every_army_leader",
        "every_navy_leader",
        "every_unit_leader",
        "every_character",
        "every_operative",
        "every_country_division",
        "every_state_division",
        "every_active_scientist",
        "every_scientist",
        "every_military_industrial_organization",
        "every_purchase_contract",
        "every_country_with_original_tag",
        "every_collection_element",
        "every_hostile_country",
        "global_every_army_leader",
        "random_country",
        "random_state",
        "random_ally",
        "random_neighbor_country",
        "random_owned_state",
        "random_controlled_state",
        "random_core_state",
        "random_owned_controlled_state",
        "random_neighbor_state",
        "random_allied_country",
        "random_other_country",
        "random_enemy_country",
        "random_occupied_country",
        "random_subject_country",
        "random_army_leader",
        "random_navy_leader",
        "random_unit_leader",
        "random_character",
        "random_operative",
        "random_active_scientist",
        "random_scientist",
        "random_military_industrial_organization",
        "random_purchase_contract",
        "random_country_division",
        "random_state_division",
        "random_country_with_original_tag",
        "random_scope_in_array",
        "random_hostile_country",
        "random_list",
        "random",
        "capital_scope",
        "overlord",
        "faction_leader",
        "party_leader",
        "while_loop_effect",
        "for_loop_effect",
        "for_each_loop",
        "for_each_scope_loop",
    }

    # ── Helper: coerce a Python value to a HOI4 scalar
    # (no True/False/list/dict leaks)
    def _hoi4_val(v):
        if isinstance(v, bool):
            return "yes" if v else "no"
        return str(v)

    # ── Helper: recursively render a dict/list value into HOI4 script lines
    def _hoi4_render_value(k, v, indent):
        """Render a single key->value pair at the given tab indent.

        Returns list of lines. Handles: scalars, bools → yes/no,
        lists → repeated keys, dicts → nested block.
        """
        T = indent
        if isinstance(v, bool):
            return [f"{T}{k} = {'yes' if v else 'no'}"]
        if isinstance(v, (int, float)):
            return [f"{T}{k} = {v}"]
        if isinstance(v, str):
            return [f"{T}{k} = {v}"]
        if isinstance(v, list):
            out_lines = []
            for item in v:
                if isinstance(item, dict):
                    out_lines.append(f"{T}{k} = {{")
                    for ik, iv in item.items():
                        if str(ik).startswith("_"):
                            continue
                        out_lines.extend(_hoi4_render_value(ik, iv, T + "\t"))
                    out_lines.append(f"{T}}}")
                else:
                    out_lines.append(f"{T}{k} = {_hoi4_val(item)}")
            return out_lines
        if isinstance(v, dict):
            out_lines = [f"{T}{k} = {{"]
            for ik, iv in v.items():
                if str(ik).startswith("_"):
                    continue
                out_lines.extend(_hoi4_render_value(ik, iv, T + "\t"))
            out_lines.append(f"{T}}}")
            return out_lines
        # fallback — coerce anything else to string (should not happen)
        return [f"{T}{k} = {v}"]

    if t in _SCOPE_TYPES:
        out = [f"{IND}{t} = {{"]
        limit_raw = str(g("limit", "")).strip()
        if limit_raw:
            out.append(f"{IND}\tlimit = {{")
            inner = limit_raw.strip("{}").replace("'", '"')
            for ln in inner.splitlines():
                ln = ln.strip().strip(",").strip()
                if ln:
                    out.append(f"{IND}\t\t{ln}")
            out.append(f"{IND}\t}}")
        effect_raw = str(g("effect", "")).strip()
        if effect_raw:
            inner = effect_raw.strip("{}[]").replace("'", '"')
            for ln in inner.splitlines():
                ln = ln.strip().strip(",")
                if ln:
                    out.append(f"{IND}\t{ln}")
        for k, v in f.items():
            if k in ("limit", "effect", "_list") or str(k).startswith("_"):
                continue
            # Use recursive renderer so lists/dicts/bools don't leak Python syntax
            if isinstance(v, (list, dict, bool)):
                out.extend(_hoi4_render_value(k, v, f"{IND}\t"))
                continue
            vs = str(v).strip()
            if not vs:
                continue
            if vs.startswith("{") and vs.endswith("}"):
                inner2 = vs[1:-1].replace("'", '"').strip()
                pairs = re.findall(r'"(\w+)"\s*[=:]\s*"([^"]*)"', inner2)
                if pairs:
                    out.append(f"{IND}\t{k} = {{")
                    for pk, pv in pairs:
                        out.append(f"{IND}\t\t{pk} = {pv}")
                    out.append(f"{IND}\t}}")
                else:
                    out.append(f"{IND}\t{k} = {vs}")
            else:
                out.append(f"{IND}\t{k} = {vs}")
        out.append(f"{IND}}}")
        return "\n".join(out)

    # ── Generic fallback ───────────────────────────────────────
    defn = EFFECT_DEFS.get(t, {})
    if not isinstance(defn, Mapping):
        defn = {}
    fl = defn.get("fields", [])
    fname = fl[0][0] if fl else None
    if fname and len(fl) == 1:
        val = g(fname, "")
        if isinstance(val, (list, dict, bool)):
            rendered = _hoi4_render_value(fname, val, IND)
            return "\n".join(rendered)
        val = str(val).strip()
        if val:
            return f"{IND}{t} = {val}"
    raw_val = str(g("raw", "")).strip()
    if raw_val:
        return f"{IND}{t} = {raw_val}"
    fields_clean = {
        k: v for k, v in f.items() if not str(k).startswith("_") and k != "raw"
    }
    if not fields_clean:
        return f"{IND}{t} = yes"
    if len(fields_clean) == 1:
        k0, v0 = list(fields_clean.items())[0]
        if isinstance(v0, (list, dict, bool)):
            rendered = _hoi4_render_value(k0, v0, IND)
            return "\n".join(rendered)
        if k0 in ("amount", "value", "flag", "tooltip", "category", "decision"):
            return f"{IND}{t} = {v0}"
        return f"{IND}{t} = {{ {k0} = {v0} }}"
    # Multi-field block — render each field recursively to handle nested structures
    inner_blocks = []
    for k, v in fields_clean.items():
        if isinstance(v, (list, dict, bool)):
            inner_blocks.extend(_hoi4_render_value(k, v, IND + "\t"))
        else:
            inner_blocks.append(f"{IND}\t{k} = {_hoi4_val(v)}")
    return f"{IND}{t} = {{\n" + "\n".join(inner_blocks) + f"\n{IND}}}"
