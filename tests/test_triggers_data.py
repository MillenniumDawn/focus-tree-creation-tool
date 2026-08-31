"""Regression tests for the vanilla trigger catalogue."""

from hoi4cm.data import TRIGGER_CATS, TRIGGER_DEFS, triggers_in_cat


def test_trigger_defs_cover_vanilla_catalogue_shape():
    assert len(TRIGGER_DEFS) >= 100
    assert {"always", "has_country_flag", "has_idea", "owns_state"} <= set(TRIGGER_DEFS)
    for definition in TRIGGER_DEFS.values():
        assert isinstance(definition["label"], str)
        assert definition["cat"] in TRIGGER_CATS
        assert isinstance(definition["fields"], list)
        for field in definition["fields"]:
            assert len(field) == 4
            assert all(isinstance(value, str) for value in field)


def test_triggers_in_cat_matches_catalogue_and_is_copy():
    for category in TRIGGER_CATS:
        expected = [
            (key, definition["label"])
            for key, definition in TRIGGER_DEFS.items()
            if definition["cat"] == category
        ]
        assert triggers_in_cat(category) == expected

    items = triggers_in_cat("Politics")
    items.clear()
    assert triggers_in_cat("Politics")
    assert triggers_in_cat("missing") == []


def test_trigger_fields_include_hints_for_common_conditions():
    for key in ("has_country_flag", "has_idea", "has_completed_focus", "owns_state"):
        fields = TRIGGER_DEFS[key]["fields"]
        assert fields
        assert all(field[3] for field in fields)
