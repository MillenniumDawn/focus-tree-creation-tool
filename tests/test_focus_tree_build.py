"""Tests for hoi4cm.focus_tree.build — parsed data -> Focus objects."""

import pytest
from test_focus_tree_parse import WRAPPED

from hoi4cm.focus_tree.build import BuildContext, build_focuses
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


def test_build_name_collision_semantics():
    # Two existing focuses share a name at different coords — resolve_abs's
    # cross-tree fallback must use the FIRST one in list order (setdefault
    # semantics), matching the old linear scan.
    dup_first = Focus(1, 1)
    dup_first.name = "DUP_name"
    dup_second = Focus(5, 5)
    dup_second.name = "DUP_name"
    shared_existing = Focus(0, 0)
    shared_existing.name = "SHARED_name"
    src = (
        "focus_tree = {\n"
        "\tid = Y_tree\n"
        "\tfocus = {\n"
        "\t\tid = Y_new_rel\n"
        "\t\tx = 2\n"
        "\t\ty = 2\n"
        "\t\trelative_position_id = DUP_name\n"
        '\t\tcompletion_reward = { log = "a" }\n'
        "\t}\n"
        "\tfocus = {\n"
        "\t\tid = SHARED_name\n"
        "\t\tx = 0\n"
        "\t\ty = 0\n"
        '\t\tcompletion_reward = { log = "b" }\n'
        "\t}\n"
        "\tfocus = {\n"
        "\t\tid = Y_dependent\n"
        "\t\tx = 1\n"
        "\t\ty = 0\n"
        "\t\tprerequisite = { focus = SHARED_name }\n"
        '\t\tcompletion_reward = { log = "c" }\n'
        "\t}\n"
        "}\n"
    )
    parsed = parse_focus_tree(src, "/tmp/y.txt")
    focuses = build_focuses(
        parsed,
        tree_idx=3,
        existing_focuses=[dup_first, dup_second, shared_existing],
    )
    by_name = _by_name(focuses)

    # Cross-tree position resolution: first DUP_name in list order wins.
    new_rel = by_name["Y_new_rel"]
    assert (new_rel.x, new_rel.y) == (3, 3)

    # Pass 2 name collision: the NEW "SHARED_name" focus wins over the
    # existing one of the same name (current, pre-existing behavior).
    new_shared = by_name["SHARED_name"]
    dependent = by_name["Y_dependent"]
    assert dependent.prereqs == [[new_shared.id]]
    assert new_shared.id != shared_existing.id


def test_build_resolves_long_relative_chain_iteratively():
    focus_blocks = [
        "\tfocus = { id = CHAIN_0 x = 0 y = 0 }",
        *[
            "\tfocus = { "
            f"id = CHAIN_{index} x = 1 y = 1 "
            f"relative_position_id = CHAIN_{index - 1} "
            "}"
            for index in range(1, 1_101)
        ],
    ]
    source = "focus_tree = {\n\tid = CHAIN_tree\n" + "\n".join(focus_blocks) + "\n}"

    focuses = build_focuses(parse_focus_tree(source, "/tmp/chain.txt"), tree_idx=1)

    assert (focuses[-1].x, focuses[-1].y) == (1_100, 1_100)


def test_build_context_updates_first_position_and_last_link_indexes():
    first_source = (
        "focus_tree = {\n"
        "\tid = FIRST_tree\n"
        "\tfocus = { id = DUP_name x = 1 y = 1 }\n"
        "\tfocus = { id = DUP_name x = 5 y = 5 }\n"
        "}\n"
    )
    second_source = (
        "focus_tree = {\n"
        "\tid = SECOND_tree\n"
        "\tfocus = {\n"
        "\t\tid = SECOND_child\n"
        "\t\tx = 2\n"
        "\t\ty = 3\n"
        "\t\trelative_position_id = DUP_name\n"
        "\t\tprerequisite = { focus = DUP_name }\n"
        "\t}\n"
        "}\n"
    )
    context = BuildContext()
    first_batch = build_focuses(
        parse_focus_tree(first_source, "/tmp/first.txt"),
        tree_idx=1,
        context=context,
    )

    second_batch = build_focuses(
        parse_focus_tree(second_source, "/tmp/second.txt"),
        tree_idx=2,
        context=context,
    )

    assert (second_batch[0].x, second_batch[0].y) == (3, 4)
    assert second_batch[0].prereqs == [[first_batch[-1].id]]
