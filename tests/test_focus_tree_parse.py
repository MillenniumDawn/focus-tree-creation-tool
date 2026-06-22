"""Tests for hoi4cm.focus_tree.parse — text -> structured data, no field loss."""

import pytest

from hoi4cm.focus_tree.parse import (
    EmptyFocusTreeError,
    parse_focus_tree,
)

# Tab-indented like real HOI4 files (\t -> tab in this non-raw string).
WRAPPED = """\
focus_tree = {
\tid = TST_shared_tree
\tcountry = {
\t\tfactor = 0
\t\tmodifier = {
\t\t\tadd = 20
\t\t\toriginal_tag = TST
\t\t}
\t}
\tcontinuous_focus_position = { x = 50 y = 1200 }
\tshared_focus = OTHER_shared

\tfocus = {
\t\tid = TST_alpha
\t\ticon = GFX_goal_generic_demand_territory
\t\tx = 4
\t\ty = 0
\t\tcost = 7
\t\tsearch_filters = { FOCUS_FILTER_POLITICAL }
\t\tavailable = {
\t\t\thas_war = no
\t\t}
\t\tcompletion_reward = {
\t\t\tadd_political_power = 120
\t\t}
\t\tai_will_do = { factor = 3 }
\t}

\tfocus = {
\t\tid = TST_beta
\t\ticon = GFX_goal_generic_political_pressure
\t\tx = 1
\t\ty = 1
\t\trelative_position_id = TST_alpha
\t\toffset = {
\t\t\tx = 2
\t\t\ty = 0
\t\t\ttrigger = {
\t\t\t\toriginal_tag = TST
\t\t\t}
\t\t}
\t\tprerequisite = { focus = TST_alpha }
\t\tmutually_exclusive = { focus = TST_alpha }
\t\tcompletion_reward = {
\t\t\tadd_stability = 0.05
\t\t}
\t}
}
"""

NO_WRAPPER = """\
joint_focus = {
\tid = JNT_one
\ticon = GFX_goal_generic_political_pressure
\tx = 0
\ty = 0
\tcost = 10
\tjoint_trigger = {
\t\tis_ai = no
\t}
\tcompletion_reward = {
\t\tadd_political_power = 50
\t}
}
"""


def test_parse_tree_metadata():
    p = parse_focus_tree(WRAPPED, "/tmp/TST_shared_tree.txt")
    assert p.tree_id == "TST_shared_tree"
    assert p.cfp_x == 50
    assert p.cfp_y == 1200
    assert p.country_tag == "TST"
    assert p.shared_refs == ["OTHER_shared"]
    assert p.had_wrapper is True
    assert [f["id"] for f in p.focuses_data] == ["TST_alpha", "TST_beta"]


def test_parse_keeps_focus_fields():
    p = parse_focus_tree(WRAPPED, "/tmp/TST_shared_tree.txt")
    alpha, beta = p.focuses_data
    assert alpha["icon"] == "GFX_goal_generic_demand_territory"
    assert alpha["x"] == "4"
    assert alpha["cost"] == "7"
    assert alpha["ai_will_do"] == {"factor": "3"}
    assert beta["relative_position_id"] == "TST_alpha"
    assert beta["prerequisite"] == {"focus": "TST_alpha"}
    assert beta["mutually_exclusive"] == {"focus": "TST_alpha"}


def test_parse_raw_rewards_and_conditions():
    p = parse_focus_tree(WRAPPED, "/tmp/TST_shared_tree.txt")
    assert "add_political_power = 120" in p.raw_rewards["TST_alpha"]
    assert "has_war = no" in p.raw_rewards[("TST_alpha", "available")]
    assert "add_stability = 0.05" in p.raw_rewards["TST_beta"]


def test_parse_structured_offsets():
    p = parse_focus_tree(WRAPPED, "/tmp/TST_shared_tree.txt")
    offsets = p.raw_rewards[("TST_beta", "_offsets")]
    assert len(offsets) == 1
    assert offsets[0]["x"] == 2
    assert offsets[0]["y"] == 0
    assert "original_tag = TST" in offsets[0]["trigger"]


def test_parse_no_wrapper_fallback():
    p = parse_focus_tree(NO_WRAPPER, "/tmp/joint_file.txt")
    assert p.had_wrapper is False
    # No focus_tree wrapper -> tree name falls back to the filename.
    assert p.tree_id == "joint_file"
    assert [f["id"] for f in p.focuses_data] == ["JNT_one"]
    assert "joint_trigger" in p.raw_rewards[("JNT_one", "_joint_extra")]
    assert "is_ai = no" in p.raw_rewards[("JNT_one", "_joint_extra")]


def test_parse_strips_bom():
    p = parse_focus_tree("﻿" + NO_WRAPPER, "/tmp/joint_file.txt")
    assert [f["id"] for f in p.focuses_data] == ["JNT_one"]


def test_parse_empty_raises_with_block_diagnostic():
    # Has a focus_tree keyword but no valid focus IDs inside.
    src = "focus_tree = {\n\tid = X\n}\n"
    with pytest.raises(EmptyFocusTreeError) as exc:
        parse_focus_tree(src, "/tmp/bad.txt")
    msg = str(exc.value)
    assert "No focus data found in bad.txt" in msg
    assert "Blocks found: focus_tree" in msg


def test_parse_empty_no_blocks_diagnostic():
    with pytest.raises(EmptyFocusTreeError) as exc:
        parse_focus_tree("# only a comment\nfoo = bar\n", "/tmp/none.txt")
    assert "No recognized block types found." in str(exc.value)


def test_empty_focus_tree_error_is_value_error():
    assert issubclass(EmptyFocusTreeError, ValueError)
