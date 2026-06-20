"""Smoke tests for the extracted effects/modifier data tables."""

from hoi4cm.data import (
    EFFECT_CATS,
    EFFECT_DEFS,
    MD_RESOURCE_COST_PER_UNIT,
    MODIFIER_CATS,
    MODIFIER_DEFS,
    effects_in_cat,
    md_building_cost_hint,
    md_resource_cost_hint,
    modifiers_in_cat,
)


def test_effect_defs_not_empty():
    assert len(EFFECT_DEFS) > 100
    assert all("label" in v and "cat" in v for v in EFFECT_DEFS.values())


def test_effect_cats_covers_political():
    assert "Political" in EFFECT_CATS


def test_effects_in_cat_returns_tuples():
    items = effects_in_cat("Political")
    assert items
    assert all(isinstance(k, str) and isinstance(label, str) for k, label in items)
    assert "add_political_power" in [k for k, _ in items]


def test_modifier_defs_not_empty():
    assert len(MODIFIER_DEFS) > 100
    assert all("cat" in v and "desc" in v for v in MODIFIER_DEFS.values())


def test_modifier_cats_covers_ai():
    assert "AI" in MODIFIER_CATS


def test_modifiers_in_cat_sorted():
    items = modifiers_in_cat("AI")
    assert items
    keys = [k for k, _ in items]
    assert keys == sorted(keys)


def test_md_building_cost_hint_known_building():
    hint = md_building_cost_hint("industrial_complex", levels=2)
    assert hint is not None and "$15.00B" in hint
    assert hint is not None and "uses building slot" in hint


def test_md_building_cost_hint_unknown_building():
    assert md_building_cost_hint("not_a_building") == ""


def test_md_resource_cost_hint():
    hint = md_resource_cost_hint(8)
    expected = round(8 * MD_RESOURCE_COST_PER_UNIT, 3)
    assert f"${expected:.3f}B" in hint


def test_md_resource_cost_hint_invalid():
    assert md_resource_cost_hint("abc") == ""
