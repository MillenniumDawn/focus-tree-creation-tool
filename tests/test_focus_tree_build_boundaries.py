"""Boundary tests for focus_tree build + drawio fallback paths."""

import pytest

from hoi4cm.focus_tree.build import build_focuses
from hoi4cm.focus_tree.drawio import _get_graph_root
from hoi4cm.focus_tree.parse import ParsedFocusTree, parse_focus_tree


def _parsed_with_focus(fields: dict) -> ParsedFocusTree:
    return ParsedFocusTree(
        tree_id="TEST",
        cfp_x=None,
        cfp_y=None,
        country_tag="TAG",
        shared_refs=[],
        joint_refs=[],
        had_wrapper=True,
        focuses_data=[fields],
        raw_rewards={},
    )


def test_build_with_bad_cost_uses_fallback_10():
    parsed = _parsed_with_focus(
        {"id": "BAD_cost", "x": "0", "y": "0", "cost": "not_a_number"}
    )
    focuses = build_focuses(parsed, tree_idx=1)
    assert focuses[0].cost == 10


def test_build_with_bad_x_uses_0():
    parsed = _parsed_with_focus({"id": "BAD_x", "x": "oops", "y": "oops"})
    focuses = build_focuses(parsed, tree_idx=1)
    assert focuses[0].x == 0
    assert focuses[0].y == 0


def test_build_with_bad_ai_will_do_uses_1():
    parsed = _parsed_with_focus(
        {"id": "BAD_ai", "x": "0", "y": "0", "ai_will_do": {"factor": "bad"}}
    )
    focuses = build_focuses(parsed, tree_idx=1)
    assert focuses[0].ai_will_do == 1


def test_drawio_decompress_corrupt_returns_root():
    xml = "<mxfile><diagram>!!!not-base64!!!</diagram></mxfile>"
    root = _get_graph_root(xml)
    assert root.tag == "mxfile"


def _tree_with_cost(cost_clause: str) -> str:
    return (
        "focus_tree = {\n"
        "\tid = COST_tree\n"
        "\tfocus = {\n"
        "\t\tid = TST_alpha\n"
        "\t\tx = 1\n"
        "\t\ty = 1\n"
        f"\t\t{cost_clause}\n"
        "\t}\n"
        "}\n"
    )


@pytest.mark.parametrize("literal", ["inf", "-inf", "1e999", "-1e999"])
def test_nonfinite_or_overflow_cost_falls_back_to_ten(literal):
    parsed = parse_focus_tree(_tree_with_cost(f"cost = {literal}"), "/tmp/cost.txt")
    focuses = build_focuses(parsed, tree_idx=1)
    assert len(focuses) == 1
    assert focuses[0].cost == 10


@pytest.mark.parametrize(
    "literal,expected",
    [
        ("10", 10),
        ("7", 7),
        ("7.5", 7.5),
        ("0", 0),
        ("1e308", int(1e308)),
    ],
)
def test_finite_cost_values_are_kept(literal, expected):
    parsed = parse_focus_tree(_tree_with_cost(f"cost = {literal}"), "/tmp/cost.txt")
    focuses = build_focuses(parsed, tree_idx=1)
    assert focuses[0].cost == expected
