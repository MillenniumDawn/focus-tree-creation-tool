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

# focus_tree = { } wrappers holding only shared_focus/joint_focus blocks (or a
# mix), used to pin issue #123: had_wrapper must reflect that a wrapper was
# parsed, not just that a plain `focus` key was found.
WRAPPED_JOINT_ONLY = """\
focus_tree = {
\tid = TST_joint_tree
\tcountry = {
\t\tfactor = 0
\t\tmodifier = {
\t\t\tadd = 20
\t\t\toriginal_tag = TST
\t\t}
\t}
\tcontinuous_focus_position = { x = 0 y = 0 }
\tjoint_focus = {
\t\tid = TST_joint_one
\t\ticon = GFX_x
\t\tx = 0
\t\ty = 0
\t\tcost = 1
\t\tcompletion_reward = {
\t\t\tadd_political_power = 50
\t\t}
\t}
}
"""

WRAPPED_SHARED_ONLY = """\
focus_tree = {
\tid = TST_shared_only_tree
\tcountry = {
\t\tfactor = 0
\t\tmodifier = {
\t\t\tadd = 20
\t\t\toriginal_tag = TST
\t\t}
\t}
\tcontinuous_focus_position = { x = 0 y = 0 }
\tshared_focus = {
\t\tid = TST_shared_one
\t\ticon = GFX_x
\t\tx = 0
\t\ty = 0
\t\tcost = 1
\t\tcompletion_reward = {
\t\t\tadd_political_power = 50
\t\t}
\t}
}
"""

WRAPPED_MIXED = """\
focus_tree = {
\tid = TST_mixed_tree
\tcountry = {
\t\tfactor = 0
\t\tmodifier = {
\t\t\tadd = 20
\t\t\toriginal_tag = TST
\t\t}
\t}
\tcontinuous_focus_position = { x = 0 y = 0 }
\tfocus = {
\t\tid = TST_mixed_focus
\t\ticon = GFX_x
\t\tx = 0
\t\ty = 0
\t\tcost = 1
\t\tcompletion_reward = {
\t\t\tadd_political_power = 50
\t\t}
\t}
\tshared_focus = {
\t\tid = TST_mixed_shared
\t\ticon = GFX_x
\t\tx = 1
\t\ty = 1
\t\tcost = 1
\t\tcompletion_reward = {
\t\t\tadd_political_power = 25
\t\t}
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


def test_parse_tree_extras_empty_when_no_unknown_wrapper_keys():
    p = parse_focus_tree(WRAPPED, "/tmp/TST_shared_tree.txt")
    assert p.tree_extras == {}


def test_parse_tree_extras_captures_unknown_wrapper_keys():
    """default/reset_on_civilwar/initial_show_position aren't named fields on
    ParsedFocusTree — they must survive via tree_extras (issue #39)."""
    src = """\
focus_tree = {
\tid = TST_extras_tree
\tcountry = {
\t\tfactor = 0
\t}
\tdefault = yes
\treset_on_civilwar = no
\tinitial_show_position = yes
\tcontinuous_focus_position = { x = 0 y = 0 }
\tshared_focus = OTHER_shared
\tfocus = {
\t\tid = TST_only
\t\ticon = GFX_x
\t\tx = 0
\t\ty = 0
\t\tcost = 1
\t}
}
"""
    p = parse_focus_tree(src, "/tmp/x.txt")
    # Known wrapper fields (id, country, continuous_focus_position, focus,
    # shared_focus) must NOT leak into tree_extras — only genuinely unknown
    # keys belong there.
    assert p.tree_extras == {
        "default": "yes",
        "reset_on_civilwar": "no",
        "initial_show_position": "yes",
    }


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


def test_raw_key_scan_does_not_confuse_prefixed_and_suffixed_keys():
    """The single-pass raw-key scan must key each block to the right name.

    ``bypass`` is a prefix of ``bypass_effect`` and the alternation is
    deliberately unanchored, so this pins that ``bypass_effect = {`` is not
    also read as ``bypass``, and that a ``custom_``-prefixed key still counts
    (which is what the per-key ``re.search`` it replaced did).
    """
    source = """focus_tree = {
\tid = keys_tree
\tfocus = {
\t\tid = keys_focus
\t\tbypass_effect = { set_country_flag = from_bypass_effect }
\t\tcustom_available = { has_war = from_custom_available }
\t\tcancel = { has_war = from_cancel }
\t}
}"""

    rewards = parse_focus_tree(source, "/tmp/keys.txt").raw_rewards

    assert "from_bypass_effect" in rewards[("keys_focus", "bypass_effect")]
    assert ("keys_focus", "bypass") not in rewards
    assert "from_custom_available" in rewards[("keys_focus", "available")]
    assert "from_cancel" in rewards[("keys_focus", "cancel")]


def test_raw_key_scan_keeps_the_first_occurrence_of_a_repeated_key():
    source = """focus_tree = {
\tid = dup_tree
\tfocus = {
\t\tid = dup_focus
\t\tavailable = { has_war = first }
\t\tavailable = { has_war = second }
\t}
}"""

    rewards = parse_focus_tree(source, "/tmp/dup.txt").raw_rewards

    assert "first" in rewards[("dup_focus", "available")]
    assert "second" not in rewards[("dup_focus", "available")]


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


@pytest.mark.parametrize(
    "src,ids",
    [
        (WRAPPED_JOINT_ONLY, ["TST_joint_one"]),
        (WRAPPED_SHARED_ONLY, ["TST_shared_one"]),
        (WRAPPED_MIXED, ["TST_mixed_focus", "TST_mixed_shared"]),
    ],
)
def test_had_wrapper_true_for_shared_or_joint_only_wrapper(src, ids):
    """Issue #123: a wrapper holding only shared_focus/joint_focus blocks (or
    a mix) must still be recorded as wrapped, not just one with a plain
    `focus` key."""
    p = parse_focus_tree(src, "/tmp/x.txt")
    assert p.had_wrapper is True
    assert [f["id"] for f in p.focuses_data] == ids


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


def test_parse_quoted_hash_and_braces_without_losing_following_fields():
    source = """focus_tree = {
    id = quoted_tree
    focus = {
        id = quoted_focus
        custom_text = "value # with { braces } inside"
        x = 3 # real comment }
        y = 4
    }
}"""

    parsed = parse_focus_tree(source, "/tmp/quoted.txt")

    assert parsed.focuses_data[0]["custom_text"] == "value # with { braces } inside"
    assert parsed.focuses_data[0]["x"] == "3"
    assert parsed.focuses_data[0]["y"] == "4"
