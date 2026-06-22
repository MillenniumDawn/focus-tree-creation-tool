"""Tests for hoi4cm.focus_tree.build — parsed data -> Focus objects."""

import pytest
from test_focus_tree_parse import WRAPPED

from hoi4cm.focus_tree.build import build_focuses
from hoi4cm.focus_tree.parse import parse_focus_tree
from hoi4cm.models import Focus


@pytest.fixture(autouse=True)
def reset_counter():
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


def _by_name(focuses):
    return {f.name: f for f in focuses}


def test_build_basic_fields():
    parsed = parse_focus_tree(WRAPPED, "/tmp/t.txt")
    focuses = build_focuses(parsed, tree_idx=1)
    by_name = _by_name(focuses)
    alpha = by_name["TST_alpha"]
    assert alpha.tree_idx == 1
    assert alpha.gfx == "GFX_goal_generic_demand_territory"
    assert alpha.cost == 7
    assert alpha.ai_will_do == 3
    assert alpha.search_filters == "FOCUS_FILTER_POLITICAL"
    assert "has_war = no" in alpha.available_cond
    # completion_reward is preserved verbatim as a single _raw_block effect.
    # extract_raw_block keeps trailing block indentation; the renderer strips it.
    assert len(alpha.effects) == 1
    assert alpha.effects[0]["type"] == "_raw_block"
    assert alpha.effects[0]["fields"]["raw"].strip() == "add_political_power = 120"
    assert alpha._raw_gx == 4 and alpha._raw_gy == 0


def test_build_resolves_relative_position():
    parsed = parse_focus_tree(WRAPPED, "/tmp/t.txt")
    focuses = build_focuses(parsed, tree_idx=1)
    by_name = _by_name(focuses)
    alpha, beta = by_name["TST_alpha"], by_name["TST_beta"]
    assert (alpha.x, alpha.y) == (4, 0)
    # beta is relative to alpha: (4,0) + (1,1)
    assert (beta.x, beta.y) == (5, 1)
    assert beta.relative_position_id == "TST_alpha"
    # export uses original file coords, not the resolved canvas coords
    assert beta._raw_gx == 1 and beta._raw_gy == 1
    assert beta._rel_dx == 1 and beta._rel_dy == 1


def test_build_links_prereqs_and_mutex():
    parsed = parse_focus_tree(WRAPPED, "/tmp/t.txt")
    focuses = build_focuses(parsed, tree_idx=1)
    by_name = _by_name(focuses)
    alpha, beta = by_name["TST_alpha"], by_name["TST_beta"]
    assert beta.prereqs == [[alpha.id]]
    assert beta.mutex == [alpha.id]


def test_build_applies_matching_country_offset():
    parsed = parse_focus_tree(WRAPPED, "/tmp/t.txt")
    # beta has offset { x=2 y=0 trigger { original_tag = TST } }
    focuses = build_focuses(parsed, tree_idx=1, country_tag="TST")
    beta = _by_name(focuses)["TST_beta"]
    # alpha(4,0) + rel(1,1) + offset(2,0)
    assert (beta.x, beta.y) == (7, 1)
    # raw export coords are untouched by the offset
    assert beta._raw_gx == 1


def test_build_ignores_nonmatching_country_offset():
    parsed = parse_focus_tree(WRAPPED, "/tmp/t.txt")
    focuses = build_focuses(parsed, tree_idx=1, country_tag="GER")
    beta = _by_name(focuses)["TST_beta"]
    assert (beta.x, beta.y) == (5, 1)


def test_build_cross_tree_relative_and_prereq():
    anchor = Focus(10, 10)
    anchor.name = "MAIN_anchor"
    src = (
        "focus_tree = {\n"
        "\tid = X_tree\n"
        "\tfocus = {\n"
        "\t\tid = X_child\n"
        "\t\tx = 3\n"
        "\t\ty = 2\n"
        "\t\trelative_position_id = MAIN_anchor\n"
        "\t\tprerequisite = { focus = MAIN_anchor }\n"
        '\t\tcompletion_reward = { log = "x" }\n'
        "\t}\n"
        "}\n"
    )
    parsed = parse_focus_tree(src, "/tmp/x.txt")
    focuses = build_focuses(parsed, tree_idx=2, existing_focuses=[anchor])
    child = focuses[0]
    # resolved against the cross-tree anchor: (10,10) + (3,2)
    assert (child.x, child.y) == (13, 12)
    assert child.prereqs == [[anchor.id]]
