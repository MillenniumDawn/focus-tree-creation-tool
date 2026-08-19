"""Boundary tests for focus_tree build + drawio fallback paths."""

import pytest

from hoi4cm.focus_tree.build import build_focuses
from hoi4cm.focus_tree.drawio import _get_graph_root
from hoi4cm.focus_tree.parse import ParsedFocusTree
from hoi4cm.models import Focus


@pytest.fixture(autouse=True)
def reset_counter():
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


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
