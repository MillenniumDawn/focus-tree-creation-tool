"""Vanilla Hearts of Iron IV trigger catalogue.

Entries use the same shape as :data:`hoi4cm.data.effects.EFFECT_DEFS`:
``label``, ``cat`` and a list of ``(name, widget, default, hint)`` fields.
The table is intentionally limited to frequently used vanilla script triggers;
mod-specific scripted triggers remain available through the raw text area.
"""

# ruff: noqa: E501

# fmt: off
TRIGGER_DEFS = {
    # ── Logic and script ───────────────────────────────────────────────────
    "always": {"label": "Always", "cat": "Logic", "fields": [], "_note": "Always true."},
    "never": {"label": "Never", "cat": "Logic", "fields": [], "_note": "Always false."},
    "AND": {"label": "All of (AND)", "cat": "Logic", "fields": [("conditions", "multiline", "always = yes", "Every condition in the block must be true.")], "_block": True},
    "OR": {"label": "Any of (OR)", "cat": "Logic", "fields": [("conditions", "multiline", "always = yes", "At least one condition in the block must be true.")], "_block": True},
    "NOR": {"label": "None of (NOR)", "cat": "Logic", "fields": [("conditions", "multiline", "always = yes", "Every condition in the block must be false.")], "_block": True},
    "NAND": {"label": "Not all of (NAND)", "cat": "Logic", "fields": [("conditions", "multiline", "always = yes", "The block must not have all conditions true.")], "_block": True},
    "NOT": {"label": "Not", "cat": "Logic", "fields": [("condition", "multiline", "always = yes", "The condition in the block must be false.")], "_block": True},
    "has_dlc": {"label": "Has DLC", "cat": "Logic", "fields": [("dlc", "entry", "Together for Victory", "DLC name or DLC identifier.")]},
    "has_game_rule": {"label": "Has Game Rule", "cat": "Logic", "fields": [("rule", "entry", "rule_id", "Game rule key."), ("value", "entry", "option", "Selected rule option.")]},
    "has_global_flag": {"label": "Has Global Flag", "cat": "Script", "fields": [("flag", "entry", "my_global_flag", "Global flag name.")]},
    "has_country_flag": {"label": "Has Country Flag", "cat": "Script", "fields": [("flag", "entry", "my_country_flag", "Country flag name.")]},
    "has_state_flag": {"label": "Has State Flag", "cat": "Script", "fields": [("flag", "entry", "my_state_flag", "State flag name.")]},
    "has_province_flag": {"label": "Has Province Flag", "cat": "Script", "fields": [("flag", "entry", "my_province_flag", "Province flag name.")]},
    "has_variable": {"label": "Has Variable", "cat": "Script", "fields": [("variable", "entry", "my_variable", "Saved script variable name.")]},
    "check_variable": {"label": "Check Variable", "cat": "Script", "fields": [("variable", "entry", "my_variable", "Variable name."), ("comparison", "entry", "> 0", "Comparison, for example > 5 or = 10.")]},
    "check_variable_in_range": {"label": "Variable In Range", "cat": "Script", "fields": [("variable", "entry", "my_variable", "Variable name."), ("range", "entry", "0..10", "Inclusive range.")]},
    "has_scripted_trigger": {"label": "Has Scripted Trigger", "cat": "Script", "fields": [("trigger", "entry", "my_scripted_trigger", "Scripted trigger name.")]},
    "has_completed_focus": {"label": "Has Completed Focus", "cat": "Focus", "fields": [("focus", "entry", "TAG_focus_id", "Focus ID, usually with the country tag.")]},
    "has_focus_tree": {"label": "Has Focus Tree", "cat": "Focus", "fields": [("tree", "entry", "focus_tree_id", "Focus tree name.")]},
    "has_completed_focus_on": {"label": "Country Has Completed Focus", "cat": "Focus", "fields": [("country", "entry", "GER", "Country tag."), ("focus", "entry", "GER_focus_id", "Focus ID.")]},
    "is_historical_focus_on": {"label": "Historical Focus Is On", "cat": "Focus", "fields": [("focus", "entry", "GER_focus_id", "Focus ID.")]},
    "has_war": {"label": "Has A War", "cat": "Diplomacy", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country is at war.")]},
    "has_war_with": {"label": "Has War With", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "has_offensive_war": {"label": "Has Offensive War", "cat": "Diplomacy", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country has an offensive war.")]},
    "has_defensive_war": {"label": "Has Defensive War", "cat": "Diplomacy", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country has a defensive war.")]},
    "has_annex_war": {"label": "Has Annex War", "cat": "Diplomacy", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country has an annexation war goal.")]},
    "has_capitulated": {"label": "Has Capitulated", "cat": "War", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country has capitulated.")]},
    "is_capitulated": {"label": "Is Capitulated", "cat": "War", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country is capitulated.")]},
    "is_in_faction": {"label": "Is In A Faction", "cat": "Diplomacy", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country belongs to a faction.")]},
    "is_faction_leader": {"label": "Is Faction Leader", "cat": "Diplomacy", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country leads its faction.")]},
    "faction_exists": {"label": "Faction Exists", "cat": "Diplomacy", "fields": [("faction", "entry", "faction_id", "Faction name or identifier.")]},
    "has_subject": {"label": "Has Subject", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Subject country tag, or a subject block.")]},
    "has_overlord": {"label": "Has Overlord", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Overlord country tag or scope.")]},
    "is_subject": {"label": "Is A Subject", "cat": "Diplomacy", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country is any kind of subject.")]},
    "is_subject_of": {"label": "Is Subject Of", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Overlord country tag or scope.")]},
    "is_puppet": {"label": "Is A Puppet", "cat": "Diplomacy", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country is a puppet.")]},
    "is_integrated_puppet": {"label": "Is An Integrated Puppet", "cat": "Diplomacy", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country is an integrated puppet.")]},
    "is_colony": {"label": "Is A Colony", "cat": "Diplomacy", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country is a colony.")]},
    "is_dominion": {"label": "Is A Dominion", "cat": "Diplomacy", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country is a dominion.")]},
    "is_overlord": {"label": "Is An Overlord", "cat": "Diplomacy", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country has a subject.")]},
    "has_guarantee": {"label": "Has A Guarantee", "cat": "Diplomacy", "fields": [("country", "entry", "POL", "Country tag being guaranteed.")]},
    "is_guaranteed_by": {"label": "Is Guaranteed By", "cat": "Diplomacy", "fields": [("country", "entry", "ENG", "Country tag providing the guarantee.")]},
    "is_guaranteeing": {"label": "Is Guaranteeing", "cat": "Diplomacy", "fields": [("country", "entry", "POL", "Country tag being guaranteed.")]},
    "is_neighbor_of": {"label": "Is Neighbor Of", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "is_in_faction_with": {"label": "Is In Faction With", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "is_ally_with": {"label": "Is Allied With", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "is_ally": {"label": "Is An Ally", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "is_enemy": {"label": "Is An Enemy", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "is_friend": {"label": "Is A Friend", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "has_truce": {"label": "Has A Truce", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "has_non_aggression_pact_with": {"label": "Has Non-Aggression Pact With", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "has_military_access_to": {"label": "Has Military Access To", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "has_military_access": {"label": "Has Military Access", "cat": "Diplomacy", "fields": [("value", "dropdown:yes,no", "yes", "Whether another country has access here.")]},
    "has_attache": {"label": "Has Attaché", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag with the attaché.")]},
    "has_send_volunteers": {"label": "Has Sent Volunteers", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag receiving volunteers.")]},
    "has_sent_volunteers": {"label": "Has Sent Volunteers (Alias)", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag receiving volunteers.")]},
    "has_license": {"label": "Has A License", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag that granted the license.")]},
    "has_opinion": {"label": "Has Opinion", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag or scope."), ("value", "entry", "> 50", "Opinion comparison.")]},
    "has_relation_modifier": {"label": "Has Relation Modifier", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Other country tag or scope."), ("modifier", "entry", "improved_relations", "Relation modifier name.")]},
    "can_declare_war_on": {"label": "Can Declare War On", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "has_war_together_with": {"label": "Has War Together With", "cat": "Diplomacy", "fields": [("country", "entry", "GER", "Country tag or scope.")]},

    # ── Politics and country ───────────────────────────────────────────────
    "has_government": {"label": "Has Government", "cat": "Politics", "fields": [("ideology", "dropdown:democratic,fascism,communism,neutrality", "democratic", "Ruling ideology group.")]},
    "has_ideology": {"label": "Has Ideology", "cat": "Politics", "fields": [("ideology", "entry", "democratic", "Ideology key.")]},
    "has_ideology_group": {"label": "Has Ideology Group", "cat": "Politics", "fields": [("ideology", "dropdown:democratic,fascism,communism,neutrality", "democratic", "Ideology group.")]},
    "has_political_power": {"label": "Has Political Power", "cat": "Politics", "fields": [("amount", "entry", "> 50", "Political power comparison.")]},
    "has_stability": {"label": "Has Stability", "cat": "Politics", "fields": [("amount", "entry", "> 0.5", "Stability comparison from 0 to 1.")]},
    "has_war_support": {"label": "Has War Support", "cat": "Politics", "fields": [("amount", "entry", "> 0.5", "War support comparison from 0 to 1.")]},
    "has_elections": {"label": "Has Elections", "cat": "Politics", "fields": [("value", "dropdown:yes,no", "yes", "Whether elections are active.")]},
    "elections_allowed": {"label": "Elections Allowed", "cat": "Politics", "fields": [("value", "dropdown:yes,no", "yes", "Whether elections are allowed.")]},
    "has_country_leader": {"label": "Has Country Leader", "cat": "Politics", "fields": [("leader", "entry", "character_id", "Leader character ID.")]},
    "has_character": {"label": "Has Character", "cat": "Politics", "fields": [("character", "entry", "character_id", "Character ID.")]},
    "has_trait": {"label": "Has Trait", "cat": "Politics", "fields": [("trait", "entry", "trait_id", "Character or country trait.")]},
    "has_legitimacy": {"label": "Has Legitimacy", "cat": "Politics", "fields": [("amount", "entry", "> 50", "Legitimacy comparison.")]},
    "has_party_popularity": {"label": "Has Party Popularity", "cat": "Politics", "fields": [("ideology", "entry", "democratic", "Ideology key."), ("amount", "entry", "> 0.5", "Popularity comparison from 0 to 1.")]},
    "has_country_modifier": {"label": "Has Country Modifier", "cat": "Politics", "fields": [("modifier", "entry", "my_modifier", "Country modifier name.")]},
    "has_dynamic_modifier": {"label": "Has Dynamic Modifier", "cat": "Politics", "fields": [("modifier", "entry", "my_modifier", "Dynamic modifier name.")]},
    "has_idea": {"label": "Has National Spirit", "cat": "Politics", "fields": [("idea", "entry", "my_spirit", "National spirit or idea ID.")]},
    "has_idea_with_trait": {"label": "Has Idea With Trait", "cat": "Politics", "fields": [("trait", "entry", "idea_trait", "Idea trait name.")]},
    "has_manpower": {"label": "Has Manpower", "cat": "Politics", "fields": [("amount", "entry", "> 10000", "Available manpower comparison.")]},
    "has_available_manpower": {"label": "Has Available Manpower", "cat": "Politics", "fields": [("amount", "entry", "> 10000", "Available manpower comparison.")]},
    "is_major": {"label": "Is A Major", "cat": "Politics", "fields": [("value", "dropdown:yes,no", "yes", "Whether this is a major country.")]},
    "is_ai": {"label": "Is AI Controlled", "cat": "Politics", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country is controlled by the AI.")]},
    "country_exists": {"label": "Country Exists", "cat": "Politics", "fields": [("country", "entry", "GER", "Country tag.")]},
    "tag": {"label": "Has Country Tag", "cat": "Politics", "fields": [("country", "entry", "GER", "Country tag to compare.")]},

    # ── Military and equipment ─────────────────────────────────────────────
    "has_army_experience": {"label": "Has Army Experience", "cat": "Military", "fields": [("amount", "entry", "> 10", "Army experience comparison.")]},
    "has_navy_experience": {"label": "Has Navy Experience", "cat": "Military", "fields": [("amount", "entry", "> 10", "Navy experience comparison.")]},
    "has_air_experience": {"label": "Has Air Experience", "cat": "Military", "fields": [("amount", "entry", "> 10", "Air experience comparison.")]},
    "has_army": {"label": "Has An Army", "cat": "Military", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country has an army.")]},
    "has_navy": {"label": "Has A Navy", "cat": "Military", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country has a navy.")]},
    "has_air_force": {"label": "Has An Air Force", "cat": "Military", "fields": [("value", "dropdown:yes,no", "yes", "Whether this country has an air force.")]},
    "has_equipment": {"label": "Has Equipment", "cat": "Military", "fields": [("equipment", "multiline", "type = infantry_equipment\namount > 100", "Equipment type and amount comparison." )], "_block": True},
    "has_equipment_ratio": {"label": "Has Equipment Ratio", "cat": "Military", "fields": [("equipment", "multiline", "type = infantry_equipment\nratio > 0.5", "Equipment type and ratio comparison." )], "_block": True},
    "has_equipment_production": {"label": "Has Equipment Production", "cat": "Military", "fields": [("equipment", "entry", "infantry_equipment", "Equipment type.")]},
    "has_stockpile": {"label": "Has Stockpile", "cat": "Military", "fields": [("equipment", "entry", "infantry_equipment", "Equipment type."), ("amount", "entry", "> 100", "Stockpile comparison.")]},
    "has_unit": {"label": "Has Unit", "cat": "Military", "fields": [("unit", "entry", "unit_id", "Unit or division identifier.")]},
    "has_unit_leader": {"label": "Has Unit Leader", "cat": "Military", "fields": [("leader", "entry", "character_id", "Unit leader character ID.")]},
    "has_unit_leader_trait": {"label": "Has Unit Leader Trait", "cat": "Military", "fields": [("trait", "entry", "trait_id", "Unit leader trait.")]},
    "has_division_template": {"label": "Has Division Template", "cat": "Military", "fields": [("template", "entry", "Infantry Division", "Division template name.")]},
    "has_template": {"label": "Has Template", "cat": "Military", "fields": [("template", "entry", "Infantry Division", "Division template name.")]},
    "num_of_divisions": {"label": "Number Of Divisions", "cat": "Military", "fields": [("amount", "entry", "> 10", "Division count comparison.")]},
    "num_of_controlled_states": {"label": "Number Of Controlled States", "cat": "Military", "fields": [("amount", "entry", "> 5", "Controlled state count comparison.")]},
    "num_of_owned_states": {"label": "Number Of Owned States", "cat": "Military", "fields": [("amount", "entry", "> 5", "Owned state count comparison.")]},
    "num_of_combat_units": {"label": "Number Of Combat Units", "cat": "Military", "fields": [("amount", "entry", "> 10", "Combat unit count comparison.")]},
    "army_strength": {"label": "Army Strength", "cat": "Military", "fields": [("amount", "entry", "> 0.5", "Army strength ratio comparison.")]},
    "navy_strength": {"label": "Navy Strength", "cat": "Military", "fields": [("amount", "entry", "> 0.5", "Navy strength ratio comparison.")]},
    "air_strength": {"label": "Air Strength", "cat": "Military", "fields": [("amount", "entry", "> 0.5", "Air strength ratio comparison.")]},
    "strength_ratio": {"label": "Strength Ratio", "cat": "Military", "fields": [("comparison", "multiline", "tag = GER\nratio > 0.5", "Country tag and relative strength comparison.")], "_block": True},
    "has_nukes": {"label": "Has Nuclear Weapons", "cat": "Military", "fields": [("amount", "entry", "> 0", "Number of nuclear weapons comparison.")]},
    "num_of_nukes": {"label": "Number Of Nuclear Weapons", "cat": "Military", "fields": [("amount", "entry", "> 0", "Nuclear weapon count comparison.")]},
    "has_tech": {"label": "Has Technology", "cat": "Research", "fields": [("technology", "entry", "infantry_weapons", "Technology ID.")]},
    "has_technology": {"label": "Has Technology (Alias)", "cat": "Research", "fields": [("technology", "entry", "infantry_weapons", "Technology ID.")]},
    "has_research_slot": {"label": "Has Research Slot", "cat": "Research", "fields": [("amount", "entry", "> 3", "Research slot count comparison.")]},
    "num_of_research_slots": {"label": "Number Of Research Slots", "cat": "Research", "fields": [("amount", "entry", "> 3", "Research slot count comparison.")]},

    # ── Economy and resources ──────────────────────────────────────────────
    "num_of_civilian_factories": {"label": "Number Of Civilian Factories", "cat": "Economy", "fields": [("amount", "entry", "> 10", "Civilian factory count comparison.")]},
    "num_of_military_factories": {"label": "Number Of Military Factories", "cat": "Economy", "fields": [("amount", "entry", "> 10", "Military factory count comparison.")]},
    "num_of_naval_factories": {"label": "Number Of Naval Factories", "cat": "Economy", "fields": [("amount", "entry", "> 5", "Dockyard count comparison.")]},
    "num_of_factories": {"label": "Number Of Factories", "cat": "Economy", "fields": [("amount", "entry", "> 10", "Factory count comparison.")]},
    "num_of_buildings": {"label": "Number Of Buildings", "cat": "Economy", "fields": [("comparison", "multiline", "type = industrial_complex\namount > 5", "Building type and count comparison.")], "_block": True},
    "has_civilian_factory": {"label": "Has Civilian Factory", "cat": "Economy", "fields": [("amount", "entry", "> 0", "Civilian factory count comparison.")]},
    "has_military_factory": {"label": "Has Military Factory", "cat": "Economy", "fields": [("amount", "entry", "> 0", "Military factory count comparison.")]},
    "has_naval_factory": {"label": "Has Naval Factory", "cat": "Economy", "fields": [("amount", "entry", "> 0", "Dockyard count comparison.")]},
    "has_resources": {"label": "Has Resources", "cat": "Economy", "fields": [("resources", "multiline", "steel > 10", "Resource amount comparison.")], "_block": True},
    "has_resource": {"label": "Has Resource", "cat": "Economy", "fields": [("resource", "multiline", "type = steel\namount > 10", "Resource type and amount comparison.")], "_block": True},
    "has_building": {"label": "Has Building", "cat": "Economy", "fields": [("building", "multiline", "type = industrial_complex\nlevel > 0", "Building type and level comparison.")], "_block": True},
    "has_available_building_slots": {"label": "Has Available Building Slots", "cat": "Economy", "fields": [("slots", "multiline", "building = industrial_complex\namount > 0", "Building type and available slot comparison.")], "_block": True},
    "has_market": {"label": "Has Access To Market", "cat": "Economy", "fields": [("country", "entry", "GER", "Market country tag or scope.")]},
    "has_trade_agreement_with": {"label": "Has Trade Agreement With", "cat": "Economy", "fields": [("country", "entry", "GER", "Country tag or scope.")]},

    # ── State, province and map ─────────────────────────────────────────────
    "owns_state": {"label": "Owns State", "cat": "State", "fields": [("state", "entry", "64", "State ID.")]},
    "controls_state": {"label": "Controls State", "cat": "State", "fields": [("state", "entry", "64", "State ID.")]},
    "is_core_of": {"label": "Is Core Of", "cat": "State", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "is_claimed_by": {"label": "Is Claimed By", "cat": "State", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "is_owned_by": {"label": "Is Owned By", "cat": "State", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "is_controlled_by": {"label": "Is Controlled By", "cat": "State", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "is_fully_owned_by": {"label": "Is Fully Owned By", "cat": "State", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "is_fully_controlled_by": {"label": "Is Fully Controlled By", "cat": "State", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "has_state_category": {"label": "Has State Category", "cat": "State", "fields": [("category", "entry", "large_city", "State category key.")]},
    "state_population": {"label": "State Population", "cat": "State", "fields": [("amount", "entry", "> 1000000", "Population comparison.")]},
    "free_building_slots": {"label": "Free Building Slots", "cat": "State", "fields": [("slots", "multiline", "building = industrial_complex\namount > 0", "Building type and free slot comparison.")], "_block": True},
    "has_building_level": {"label": "Has Building Level", "cat": "State", "fields": [("building", "multiline", "type = industrial_complex\nlevel > 2", "Building type and level comparison.")], "_block": True},
    "has_state_modifier": {"label": "Has State Modifier", "cat": "State", "fields": [("modifier", "entry", "my_state_modifier", "State modifier name.")]},
    "is_demilitarized": {"label": "Is Demilitarized", "cat": "State", "fields": [("value", "dropdown:yes,no", "yes", "Whether the state is demilitarized.")]},
    "is_border_state": {"label": "Is Border State", "cat": "State", "fields": [("value", "dropdown:yes,no", "yes", "Whether the state borders another country.")]},
    "is_coastal": {"label": "Is Coastal", "cat": "State", "fields": [("value", "dropdown:yes,no", "yes", "Whether the state has a coastline.")]},
    "has_port": {"label": "Has Port", "cat": "State", "fields": [("value", "dropdown:yes,no", "yes", "Whether the state has a port.")]},
    "has_naval_base": {"label": "Has Naval Base", "cat": "State", "fields": [("value", "dropdown:yes,no", "yes", "Whether the state has a naval base.")]},
    "terrain": {"label": "Has Terrain", "cat": "State", "fields": [("terrain", "entry", "plains", "Terrain key.")]},
    "is_in_home_area": {"label": "Is In Home Area", "cat": "State", "fields": [("value", "dropdown:yes,no", "yes", "Whether the state is in the current country's home area.")]},
    "is_on_continent": {"label": "Is On Continent", "cat": "State", "fields": [("continent", "entry", "europe", "Continent key.")]},
    "has_continent": {"label": "Has Continent", "cat": "State", "fields": [("continent", "entry", "europe", "Continent key.")]},
    "province_id": {"label": "Province ID", "cat": "Province", "fields": [("province", "entry", "1234", "Province ID.")]},
    "has_province_modifier": {"label": "Has Province Modifier", "cat": "Province", "fields": [("modifier", "entry", "my_province_modifier", "Province modifier name.")]},
    "is_in_state": {"label": "Is In State", "cat": "Province", "fields": [("state", "entry", "64", "State ID.")]},

    # ── Date, AI and scope iteration ───────────────────────────────────────
    "date": {"label": "Date", "cat": "Date", "fields": [("comparison", "entry", "> 1939.1.1", "Date comparison, for example < 1939.9.1.")]},
    "has_start_date": {"label": "Has Start Date", "cat": "Date", "fields": [("comparison", "entry", ">= 1936.1.1", "Start date comparison.")]},
    "days_since_last_war": {"label": "Days Since Last War", "cat": "Date", "fields": [("amount", "entry", "> 30", "Number of days comparison.")]},
    "has_active_mission": {"label": "Has Active Mission", "cat": "Date", "fields": [("mission", "entry", "mission_id", "Mission ID.")]},
    "ai_will_do": {"label": "AI Will Do", "cat": "AI", "fields": [("conditions", "multiline", "base = 1", "Modifier triggers used by an AI weight." )], "_block": True},
    "ai_strategy_plan": {"label": "AI Strategy Plan", "cat": "AI", "fields": [("plan", "entry", "plan_id", "AI strategy plan ID.")]},
    "is_in_home_area_of": {"label": "Is In Home Area Of", "cat": "AI", "fields": [("country", "entry", "GER", "Country tag or scope.")]},
    "any_owned_state": {"label": "Any Owned State", "cat": "Scope", "fields": [("conditions", "multiline", "is_coastal = yes", "A state trigger checked for each owned state.")], "_block": True},
    "all_owned_state": {"label": "All Owned States", "cat": "Scope", "fields": [("conditions", "multiline", "is_core_of = ROOT", "A state trigger checked for every owned state.")], "_block": True},
    "any_controlled_state": {"label": "Any Controlled State", "cat": "Scope", "fields": [("conditions", "multiline", "has_building = { industrial_complex > 0 }", "A state trigger checked for each controlled state.")], "_block": True},
    "all_controlled_state": {"label": "All Controlled States", "cat": "Scope", "fields": [("conditions", "multiline", "is_demilitarized = no", "A state trigger checked for every controlled state.")], "_block": True},
    "any_neighbor_country": {"label": "Any Neighbor Country", "cat": "Scope", "fields": [("conditions", "multiline", "has_war = yes", "A country trigger checked for each neighbor.")], "_block": True},
    "all_neighbor_country": {"label": "All Neighbor Countries", "cat": "Scope", "fields": [("conditions", "multiline", "has_war = no", "A country trigger checked for every neighbor.")], "_block": True},
    "any_country": {"label": "Any Country", "cat": "Scope", "fields": [("conditions", "multiline", "is_major = yes", "A country trigger checked for each country.")], "_block": True},
    "all_country": {"label": "All Countries", "cat": "Scope", "fields": [("conditions", "multiline", "is_ai = yes", "A country trigger checked for every country.")], "_block": True},
    "any_state": {"label": "Any State", "cat": "Scope", "fields": [("conditions", "multiline", "is_coastal = yes", "A state trigger checked for each state.")], "_block": True},
    "all_state": {"label": "All States", "cat": "Scope", "fields": [("conditions", "multiline", "has_state_category = rural", "A state trigger checked for every state.")], "_block": True},
}

TRIGGER_CATS = ["Logic", "Script", "Focus", "Diplomacy", "War", "Politics", "Military", "Research", "Economy", "State", "Province", "Date", "AI", "Scope"]
# fmt: on

_TRIGGERS_BY_CAT = None


def triggers_in_cat(cat):
    """Return ``[(key, label), ...]`` for every trigger in *cat*."""
    global _TRIGGERS_BY_CAT
    if _TRIGGERS_BY_CAT is None:
        index = {}
        for key, definition in TRIGGER_DEFS.items():
            index.setdefault(definition.get("cat"), []).append(
                (key, definition["label"])
            )
        _TRIGGERS_BY_CAT = index
    return list(_TRIGGERS_BY_CAT.get(cat, []))


__all__ = ["TRIGGER_DEFS", "TRIGGER_CATS", "triggers_in_cat"]
