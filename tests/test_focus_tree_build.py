"""Tests for hoi4cm.focus_tree.build — parsed data -> Focus objects."""

import pytest
from test_focus_tree_parse import WRAPPED
from test_focus_tree_roundtrip import _info, raw_block_renderer

from hoi4cm.focus_tree.build import BuildContext, build_focuses
from hoi4cm.focus_tree.export import export_focus_tree
from hoi4cm.focus_tree.parse import parse_focus_tree
from hoi4cm.models import Focus


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
    fields = alpha.effects[0].get("fields")
    assert isinstance(fields, dict)
    raw = fields.get("raw")
    assert isinstance(raw, str) and raw.strip() == "add_political_power = 120"
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
    anchor = Focus(id=1, x=10, y=10)
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
    dup_first = Focus(id=2, x=1, y=1)
    dup_first.name = "DUP_name"
    dup_second = Focus(id=3, x=5, y=5)
    dup_second.name = "DUP_name"
    shared_existing = Focus(id=4, x=0, y=0)
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
    seed = Focus(id=41)
    context = BuildContext([seed])
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
    assert [focus.id for focus in first_batch] == [42, 43]
    assert second_batch[0].id == 44
    assert second_batch[0].prereqs == [[first_batch[-1].id]]
    assert second_batch[0].prereqs != [[second_batch[0].id]]


def test_build_preserves_unresolved_links_and_reconciles_later_tree():
    child_src = """focus_tree = {
        id = CHILD_tree
        focus = {
            id = CHILD_one
            x = 3
            y = 2
            relative_position_id = MID_anchor
            prerequisite = { focus = KNOWN focus = LATE }
            prerequisite = { focus = LATE }
            mutually_exclusive = { focus = LATE }
        }
        focus = { id = MID_anchor x = 2 y = 1 relative_position_id = LATE }
    }"""
    context = BuildContext()
    child = build_focuses(
        parse_focus_tree(child_src, "child.txt"), tree_idx=1, context=context
    )
    known = Focus(id=90)
    known.name = "KNOWN"
    context.add_focuses([known])

    # Missing anchors use their raw displacement until the target is adopted.
    assert (child[0].x, child[0].y) == (5, 3)
    assert child[0].prereqs == [[known.id], []]
    assert child[0]._unresolved_prereqs == [["LATE"], ["LATE"]]
    assert child[0]._unresolved_mutex == ["LATE"]

    late = Focus(id=91, x=10, y=20)
    late.name = "LATE"
    context.add_focuses([late])

    assert (child[1].x, child[1].y) == (12, 21)
    assert (child[0].x, child[0].y) == (15, 23)
    assert child[0].prereqs == [[known.id, late.id], [late.id]]
    assert child[0]._unresolved_prereqs == [[], []]
    assert child[0].mutex == [late.id]
    assert child[0]._unresolved_mutex == []


def test_build_batch_order_parity_with_multihop_anchors_and_cycles(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text(
        "focus_tree = { id = FIRST focus = { id = A x = 2 y = 1 "
        "relative_position_id = B } focus = { id = B x = 3 y = 4 "
        "relative_position_id = C } focus = { id = C x = 10 y = 20 } }",
        encoding="utf-8",
    )
    second.write_text(
        "focus_tree = { id = SECOND focus = { id = C x = 10 y = 20 } "
        "focus = { id = B x = 3 y = 4 relative_position_id = C } "
        "focus = { id = A x = 2 y = 1 relative_position_id = B } }",
        encoding="utf-8",
    )
    cycle = parse_focus_tree(
        "focus_tree = { id = CYCLE focus = { id = X x = 1 y = 2 "
        "relative_position_id = Y } focus = { id = Y x = 3 y = 4 "
        "relative_position_id = X } }",
        "cycle.txt",
    )

    ordered = build_focuses(parse_focus_tree(first.read_text(), str(first)), 1)
    reverse = build_focuses(parse_focus_tree(second.read_text(), str(second)), 1)
    ordered_positions = {focus.name: (focus.x, focus.y) for focus in ordered}
    reverse_positions = {focus.name: (focus.x, focus.y) for focus in reverse}
    assert ordered_positions == reverse_positions
    assert ordered_positions == {"A": (15, 25), "B": (13, 24), "C": (10, 20)}
    cyclic = build_focuses(cycle, 1)
    assert all(
        isinstance(focus.x, int) and isinstance(focus.y, int) for focus in cyclic
    )


def test_relative_pending_propagates_through_later_tree_anchor():
    context = BuildContext()
    first = parse_focus_tree(
        "focus_tree = { id = A focus = { id = A x = 1 y = 0 "
        "relative_position_id = M } }",
        "a.txt",
    )
    second = parse_focus_tree(
        "focus_tree = { id = B focus = { id = B x = 2 y = 0 "
        "relative_position_id = A } }",
        "b.txt",
    )
    target = Focus(id=100, x=10, y=0)
    target.name = "M"

    a = build_focuses(first, 1, context=context)
    b = build_focuses(second, 2, context=context)
    context.add_focuses([target])

    assert (a[0].x, b[0].x) == (11, 13)
    assert a[0]._relative_pending is False
    assert b[0]._relative_pending is False


def test_duplicate_reference_resolution_keeps_lookup_winner_policy():
    source = parse_focus_tree(
        "focus_tree = { id = C focus = { id = CHILD prerequisite = { "
        "focus = LATE } } }",
        "child.txt",
    )
    first = Focus(id=80)
    first.name = "LATE"
    last = Focus(id=81)
    last.name = "LATE"

    immediate_context = BuildContext()
    immediate = build_focuses(source, 1, context=immediate_context)[0]
    immediate_context.add_focuses([first])
    immediate_context.add_focuses([last])
    assert immediate.prereqs == [[first.id]]

    deferred_context = BuildContext(reconcile=False)
    deferred = build_focuses(
        source, 1, context=deferred_context, register_focuses=False
    )[0]
    deferred_context.add_focuses([deferred], reconcile=False)
    deferred_context.add_focuses([first, last])
    assert deferred.prereqs == [[last.id]]


def _tree_with_ai(ai_clause):
    return (
        "focus_tree = {\n"
        "\tid = AI_tree\n"
        "\tfocus = {\n"
        "\t\tid = TST_alpha\n"
        "\t\tx = 1\n"
        "\t\ty = 1\n"
        f"\t\t{ai_clause}\n"
        "\t}\n"
        "}\n"
    )


@pytest.mark.parametrize("literal", ["inf", "-inf", "1e999", "-1e999"])
@pytest.mark.parametrize("form", ["scalar", "factor", "base"])
def test_nonfinite_ai_will_do_falls_back_to_one(literal, form):
    if form == "scalar":
        ai_clause = f"ai_will_do = {literal}"
    elif form == "factor":
        ai_clause = f"ai_will_do = {{ factor = {literal} }}"
    else:
        ai_clause = f"ai_will_do = {{ base = {literal} }}"
    parsed = parse_focus_tree(_tree_with_ai(ai_clause), "/tmp/ai.txt")
    # Non-finite literals (±inf, ±1e999) must not abort an otherwise usable import.
    focuses = build_focuses(parsed, tree_idx=1)
    assert _by_name(focuses)["TST_alpha"].ai_will_do == 1


@pytest.mark.parametrize(
    "ai_clause,expected",
    [
        ("ai_will_do = -2", -2),
        ("ai_will_do = 1.75", 1),
        ("ai_will_do = { factor = 0.5 }", 0),
        ("ai_will_do = { base = -3.5 }", -3),
        ("ai_will_do = { base = 4 }", 4),
        ("ai_will_do = { factor = 2 base = 9 }", 2),
        ("ai_will_do = { modifier = { factor = 2 } }", 1),
    ],
)
def test_finite_ai_will_do_precedence_and_values(ai_clause, expected):
    parsed = parse_focus_tree(_tree_with_ai(ai_clause), "/tmp/ai.txt")
    focuses = build_focuses(parsed, tree_idx=1)
    assert _by_name(focuses)["TST_alpha"].ai_will_do == expected


def test_nonfinite_ai_will_do_raw_block_round_trips():
    src = (
        "focus_tree = {\n"
        "\tid = AI_tree\n"
        "\tfocus = {\n"
        "\t\tid = TST_alpha\n"
        "\t\tx = 1\n"
        "\t\ty = 1\n"
        "\t\tcompletion_reward = {\n"
        "\t\t\tadd_political_power = 120\n"
        "\t\t}\n"
        "\t\tai_will_do = { factor = 1e999 "
        "modifier = { factor = 2 has_war = yes } }\n"
        "\t}\n"
        "}\n"
    )
    parsed = parse_focus_tree(src, "/tmp/ai.txt")
    focuses = build_focuses(parsed, tree_idx=1)
    alpha = _by_name(focuses)["TST_alpha"]
    assert alpha.ai_will_do == 1
    assert "factor = 1e999" in alpha.ai_will_do_raw

    def _export(tree):
        lookup = {f.id: f for f in tree}
        return export_focus_tree(
            tree,
            _info(parsed, "shared"),
            focus_lookup=lookup,
            effect_renderer=raw_block_renderer,
        )

    t1 = _export(focuses)
    assert "factor = 1e999" in t1
    reparsed = parse_focus_tree(t1, "/tmp/ai.txt")
    assert (
        reparsed.focuses_data[0]["ai_will_do"] == parsed.focuses_data[0]["ai_will_do"]
    )
    rebuilt = build_focuses(reparsed, tree_idx=1)
    rebuilt_alpha = _by_name(rebuilt)["TST_alpha"]
    assert rebuilt_alpha.ai_will_do == 1
    assert "factor = 1e999" in rebuilt_alpha.ai_will_do_raw
    t2 = _export(rebuilt)
    assert t1 == t2
