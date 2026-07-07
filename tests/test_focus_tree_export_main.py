"""Characterization + round-trip tests for export_main_tree (tree_idx == 0).

The golden text in test_full_focus_body_matches_hand_derived_text was derived
by hand-reading the monolith's pre-extraction ``_export`` (see
docs/dev/monolith-migration.md, phase 4) line by line, not by running the new
code and copying its output — it exists to catch porting mistakes, not to
freeze whatever export_main_tree happens to produce.
"""

import os

import pytest

from hoi4cm.core import read_file
from hoi4cm.focus_tree.build import build_focuses
from hoi4cm.focus_tree.export import export_main_tree
from hoi4cm.focus_tree.parse import parse_focus_tree
from hoi4cm.models import Focus

FIX_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "focus_trees")


@pytest.fixture(autouse=True)
def reset_counter():
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


def raw_block_renderer(eff):
    """Mirror the monolith's _raw_block effect rendering (3-tab base indent)."""
    if eff.get("type") != "_raw_block":
        return ""
    raw = eff.get("fields", {}).get("raw", "").strip()
    return "\n".join(f"\t\t\t{ln}" for ln in raw.splitlines()) if raw else ""


def _info(**overrides):
    info = {
        "tree_id": "TST_main_tree",
        "country_tag": "TST",
        "cfp_x": 20,
        "cfp_y": 300,
        "country_raw": "",
        "shared_focuses": [],
        "joint_focuses": [],
    }
    info.update(overrides)
    return info


def test_full_focus_body_matches_hand_derived_text():
    root = Focus(0, 0)
    root.name = "TST_root"

    child = Focus(2, 3)
    child.name = "TST_child"
    child.gfx = "GFX_goal_political_effort"
    child.text = "custom_loc_key"
    child.relative_position_id = "TST_root"
    child.offsets = [{"x": 5, "y": -2, "trigger": "original_tag = TST"}]
    child.cost = 8
    child.prereqs = [[root.id, 9999]]  # 9999 is an invalid id, must be filtered
    child.mutex = [root.id, 9999]
    child.search_filters = "FOCUS_FILTER_POLITICAL FOCUS_FILTER_MILITARY"
    child.allow_branch = "always = yes"
    child.available_cond = "has_flag = only_child"
    child.bypass_cond = "OR = {\n\thas_flag = a\n\thas_flag = b\n}"
    child.will_lead_to_war_with = "{ ENG FRA }"
    child.complete_tooltip = 'log = "test"'
    child.cancel_if_invalid = False
    child.continue_if_invalid = True
    child.available_if_capitulated = True
    child.effects = [
        {"type": "_raw_block", "fields": {"raw": "add_political_power = 50"}}
    ]
    child.bypass_effect = "some_effect = yes"
    child.ai_will_do_raw = "base = 10\n\tmodifier = {\n\t\tfactor = 2\n\t}"

    focuses = [root, child]
    lookup = {f.id: f for f in focuses}
    info = _info(shared_focuses=["OTHER_shared"], joint_focuses=["OTHER_joint"])

    text = export_main_tree(
        focuses, info, focus_lookup=lookup, effect_renderer=raw_block_renderer
    )

    expected = "\n".join(
        [
            "focus_tree = {",
            "\tid = TST_main_tree",
            "",
            "\tcountry = {",
            "\t\tbase = 0",
            "\t\tmodifier = {",
            "\t\t\tadd = 100",
            "\t\t\toriginal_tag = TST",
            "\t\t}",
            "\t}",
            "",
            "\tshared_focus = OTHER_shared",
            "\tjoint_focus = OTHER_joint",
            "",
            "\tcontinuous_focus_position = { x = 20 y = 300 }",
            "",
            "\tfocus = {",
            "\t\tid = TST_root",
            "\t\ticon = generic_political_pressure",
            "\t\tx = 0",
            "\t\ty = 0",
            "\t\tcost = 10",
            "\t\tsearch_filters = { FOCUS_FILTER_POLITICAL }",
            "",
            "\t\tcompletion_reward = {",
            '\t\t\tlog = "[GetDateText]: [Root.GetName]: Focus TST_root"',
            "\t\t\t# TODO: add effects",
            "\t\t}",
            "",
            "\t\tai_will_do = {",
            "\t\t\tbase = 1",
            "\t\t}",
            "\t}",
            "",
            "\tfocus = {",
            "\t\tid = TST_child",
            "\t\ticon = political_effort",
            "\t\ttext = custom_loc_key",
            "\t\tx = 2",
            "\t\ty = 3",
            "\t\trelative_position_id = TST_root",
            "\t\toffset = {",
            "\t\t\tx = 5",
            "\t\t\ty = -2",
            "\t\t\ttrigger = {",
            "\t\t\t\toriginal_tag = TST",
            "\t\t\t}",
            "\t\t}",
            "\t\tcost = 8",
            "\t\tprerequisite = { focus = TST_root }",
            "\t\tmutually_exclusive = { focus = TST_root }",
            "\t\tsearch_filters = { FOCUS_FILTER_POLITICAL FOCUS_FILTER_MILITARY }",
            "\t\tallow_branch = {",
            "\t\t\talways = yes",
            "\t\t}",
            "\t\tavailable = {",
            "\t\t\thas_flag = only_child",
            "\t\t}",
            "\t\tbypass = {",
            "\t\t\tOR = {",
            "\t\t\t\thas_flag = a",
            "\t\t\t\thas_flag = b",
            "\t\t\t}",
            "\t\t}",
            "\t\twill_lead_to_war_with = {",
            "\t\t\tENG FRA",
            "\t\t}",
            "\t\tcomplete_tooltip = {",
            '\t\t\tlog = "test"',
            "\t\t}",
            "\t\tcancel_if_invalid = no",
            "\t\tcontinue_if_invalid = yes",
            "\t\tavailable_if_capitulated = yes",
            "",
            "\t\tcompletion_reward = {",
            "\t\t\tadd_political_power = 50",
            "\t\t}",
            "\t\tbypass_effect = {",
            "\t\t\tsome_effect = yes",
            "\t\t}",
            "",
            "\t\tai_will_do = {",
            "\t\t\tbase = 10",
            "\t\t\tmodifier = {",
            "\t\t\tfactor = 2",
            "\t\t\t}",
            "\t\t}",
            "\t}",
            "",
            "}",
        ]
    )
    assert text == expected


def test_cfp_none_derives_from_focus_bounds():
    a = Focus(1, 2)
    a.name = "TST_a"
    b = Focus(3, 5)
    b.name = "TST_b"
    focuses = [a, b]
    lookup = {f.id: f for f in focuses}
    info = _info(cfp_x=None, cfp_y=None)
    text = export_main_tree(
        focuses, info, focus_lookup=lookup, effect_renderer=raw_block_renderer
    )
    # min(x)*100 = 100, max(y)*100 = 500
    assert "continuous_focus_position = { x = 100 y = 500 }" in text


def test_cfp_none_and_no_focuses_defaults_to_zero():
    info = _info(cfp_x=None, cfp_y=None)
    text = export_main_tree(
        [], info, focus_lookup={}, effect_renderer=raw_block_renderer
    )
    assert "continuous_focus_position = { x = 0 y = 0 }" in text


def test_relative_position_can_point_outside_main_tree():
    """relative_position_id may resolve against a focus in another tree."""
    other = Focus(10, 10)
    other.name = "SHR_anchor"
    other.tree_idx = 1

    child = Focus(11, 12)
    child.name = "TST_child"
    child.relative_position_id = "SHR_anchor"
    child._rel_dx = 1
    child._rel_dy = 2

    lookup = {other.id: other, child.id: child}
    text = export_main_tree(
        [child], _info(), focus_lookup=lookup, effect_renderer=raw_block_renderer
    )
    assert "relative_position_id = SHR_anchor" in text
    assert "x = 1" in text
    assert "y = 2" in text


def test_relative_position_first_match_wins_on_duplicate_names():
    first = Focus(1, 1)
    first.name = "DUP"
    second = Focus(9, 9)
    second.name = "DUP"
    child = Focus(2, 2)
    child.name = "TST_child"
    child.relative_position_id = "DUP"

    # dict preserves insertion order; "first" must win, matching next()'s
    # first-match semantics over self.focuses.values().
    lookup = {first.id: first, second.id: second, child.id: child}
    text = export_main_tree(
        [child], _info(), focus_lookup=lookup, effect_renderer=raw_block_renderer
    )
    assert "x = 1" in text
    assert "y = 1" in text


def test_country_raw_written_verbatim_with_nested_indent_preserved():
    root = Focus(0, 0)
    root.name = "TST_root"
    country_raw = (
        "factor    =   0\nmodifier = {\n\tadd = 20\n\toriginal_tag=TST\n}\n\n\t"
    )
    info = _info(country_raw=country_raw)
    text = export_main_tree(
        [root], info, focus_lookup={root.id: root}, effect_renderer=raw_block_renderer
    )
    expected_country_block = "\n".join(
        [
            "\tcountry = {",
            "\t\tfactor    =   0",
            "\t\tmodifier = {",
            "\t\t\tadd = 20",
            "\t\t\toriginal_tag=TST",
            "\t\t}",
            "\t}",
        ]
    )
    assert expected_country_block in text
    # The default block must not appear alongside the verbatim one.
    assert "base = 0" not in text


# ── Fixture round-trip (see tests/fixtures/focus_trees/wrapper_basic.txt) ──
#
# Full-text idempotence across repeated export->reparse->export cycles is NOT
# asserted here: unlike export_focus_tree (which always writes a canned
# country block, ignoring whatever was imported), export_main_tree writes
# country_raw back verbatim by prefixing every non-blank line with a flat two
# tabs, not by dedenting first. Re-parsing that output and exporting again
# changes the block's nested-line indentation (each round adds two tabs to
# interior lines) even though the leading line is always re-stripped flat.
# That's a property of "verbatim from the last import," not a per-focus field
# loss, so it's out of scope for the round-trip guarantee below, which checks
# focus data survival instead.


def _norm_gfx(gfx):
    # export_main_tree strips a leading "GFX_goal_" on write (main tree only,
    # unlike export_focus_tree's shared/joint path); reparsing takes the icon
    # field verbatim, so the prefix doesn't survive a round trip. Normalize
    # here so the comparison checks the same icon, not the same prefix.
    return gfx[len("GFX_goal_") :] if gfx.startswith("GFX_goal_") else gfx


def _summary(focuses):
    by_id = {f.id: f.name for f in focuses}
    return [
        (
            f.name,
            _norm_gfx(f.gfx),
            f.cost,
            f.x,
            f.y,
            getattr(f, "relative_position_id", None),
            tuple(tuple(by_id.get(i, i) for i in grp) for grp in f.prereqs),
            tuple(by_id.get(i, i) for i in f.mutex),
            tuple((o["x"], o["y"]) for o in f.offsets),
            f.ai_will_do,
            f.search_filters,
        )
        for f in focuses
    ]


def _main_info(parsed):
    return {
        "tree_id": parsed.tree_id,
        "country_tag": parsed.country_tag,
        "cfp_x": parsed.cfp_x,
        "cfp_y": parsed.cfp_y,
        "country_raw": parsed.country_raw,
        "shared_focuses": parsed.shared_refs,
        "joint_focuses": parsed.joint_refs,
    }


def _load_and_export_main(src, path="/tmp/x.txt"):
    parsed = parse_focus_tree(src, path)
    focuses = build_focuses(parsed, 0)
    lookup = {f.id: f for f in focuses}
    text = export_main_tree(
        focuses,
        _main_info(parsed),
        focus_lookup=lookup,
        effect_renderer=raw_block_renderer,
    )
    return focuses, text


def test_fixture_structural_fields_survive_round_trip():
    path = os.path.join(FIX_DIR, "wrapper_basic.txt")
    raw = read_file(path)
    f1, t1 = _load_and_export_main(raw, path)
    f2, _t2 = _load_and_export_main(t1)
    assert _summary(f1) == _summary(f2)


def test_fixture_country_raw_present_verbatim_on_first_export():
    path = os.path.join(FIX_DIR, "wrapper_basic.txt")
    raw = read_file(path)
    _f, text = _load_and_export_main(raw, path)
    assert "factor    =   0" in text
    assert "original_tag=TST" in text  # no space around '=', preserved verbatim


def test_fixture_content_present():
    path = os.path.join(FIX_DIR, "wrapper_basic.txt")
    raw = read_file(path)
    _f, text = _load_and_export_main(raw, path)
    for needle in (
        "focus_tree = {",
        "id = TST_main_tree",
        "id = TST_root",
        "id = TST_child_a",
        "relative_position_id = TST_root",
        "prerequisite = { focus = TST_root",
        "mutually_exclusive = { focus = TST_child_b }",
        "add_political_power = 50",
    ):
        assert needle in text, needle
