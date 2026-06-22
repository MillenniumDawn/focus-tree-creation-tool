"""Static data tables used across the app."""

from .effects import (
    EFFECT_CATS,
    EFFECT_DEFS,
    MD_BUILDING_COSTS,
    MD_RESOURCE_COST_PER_UNIT,
    MODIFIER_CATS,
    MODIFIER_DEFS,
    effects_in_cat,
    md_building_cost_hint,
    md_resource_cost_hint,
    modifiers_in_cat,
)

__all__ = [
    "EFFECT_DEFS",
    "EFFECT_CATS",
    "effects_in_cat",
    "MODIFIER_DEFS",
    "MODIFIER_CATS",
    "modifiers_in_cat",
    "MD_BUILDING_COSTS",
    "MD_RESOURCE_COST_PER_UNIT",
    "md_building_cost_hint",
    "md_resource_cost_hint",
]
