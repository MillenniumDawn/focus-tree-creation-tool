"""Decision import regressions through the dialog's record parser."""

import pytest

from hoi4cm.script.syntax import find_blocks, parse_script
from hoi4cm.wizards._generators import generate_decision_block
from hoi4cm.wizards.decision import import_decision_record, new_decision_record


def _import(body):
    return import_decision_record("TAG_example", body, "category", {})


def _round_trip(record):
    block = generate_decision_block(record)
    name, inner, _ = find_blocks(block)[0]
    return import_decision_record(name, inner, "category", {}), block


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("fire_only_once = yes", True),
        ("fire_only_once = no", False),
        ("", False),
        ("# fire_only_once = yes", False),
        ("available = { fire_only_once = yes }", False),
        ("fire_only_once = no # fire_only_once = yes", False),
    ],
)
def test_fire_only_once_import_and_export(source, expected):
    imported = _import(source)
    restored, output = _round_trip(imported)
    assert imported["fire_only_once"] is expected
    assert restored["fire_only_once"] is expected
    assert ("fire_only_once" in parse_script(find_blocks(output)[0][1])) is expected


def test_generated_mission_round_trip():
    original = new_decision_record("category")
    original.update(
        dec_id="TAG_example",
        is_mission=True,
        mission_timeout="30",
        selectable_mission=False,
        is_good=True,
        activation="always = yes",
        timeout_effect="add_political_power = -10",
    )
    imported, _ = _round_trip(original)
    restored, output = _round_trip(imported)
    assert imported["is_mission"] is True
    assert restored["mission_timeout"] == "30"
    assert restored["activation"] == "always = yes"
    assert restored["timeout_effect"] == "add_political_power = -10"
    assert restored["selectable_mission"] is False
    assert restored["is_good"] is True
    assert "days_mission_timeout = 30" in output


@pytest.mark.parametrize(
    "field",
    [
        "days_mission_timeout = 10",
        "selectable_mission = no",
        "is_good = no",
        "activation = { always = yes }",
        "timeout_effect = { add_stability = 0.1 }",
    ],
)
def test_each_top_level_mission_field_indicates_a_mission(field):
    assert _import(field)["is_mission"] is True


def test_nested_and_commented_mission_fields_do_not_indicate_mission():
    imported = _import(
        "# days_mission_timeout = 20\navailable = { activation = { always = yes } }"
    )
    assert imported["is_mission"] is False


def test_explicit_mission_values_are_preserved():
    imported = _import(
        "is_mission = yes\ndays_mission_timeout = 45\n"
        "selectable_mission = no\nis_good = no\n"
        "activation = { always = yes }\ntimeout_effect = { add_stability = 0.1 }"
    )
    assert imported["mission_timeout"] == "45"
    assert imported["selectable_mission"] is False
    assert imported["is_good"] is False
    assert imported["activation"] == "always = yes"
    assert imported["timeout_effect"] == "add_stability = 0.1"
