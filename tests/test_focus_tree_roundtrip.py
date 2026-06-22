"""Round-trip guard for the focus-tree pipeline.

parse -> build -> export -> reparse must be stable (no fields dropped). The
exporter normalizes whitespace, so the durable guarantee is *text idempotence*:
the second export equals the first. We also check that the structural fields
survive and that key content actually made it into the exported text.
"""

import pytest
from test_focus_tree_parse import NO_WRAPPER, WRAPPED

from hoi4cm.focus_tree.build import build_focuses
from hoi4cm.focus_tree.export import export_focus_tree
from hoi4cm.focus_tree.parse import parse_focus_tree
from hoi4cm.models import Focus


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


def _info(parsed, tree_type):
    return {
        "type": tree_type,
        "file_path": "/tmp/x.txt",
        "tree_id": parsed.tree_id,
        "cfp_x": parsed.cfp_x,
        "cfp_y": parsed.cfp_y,
        "shared_focuses": parsed.shared_refs,
        "joint_focuses": parsed.joint_refs,
        "country_tag": parsed.country_tag,
        "had_wrapper": parsed.had_wrapper,
        "focus_ids": set(),
    }


def _load_and_export(src, tree_type, path="/tmp/x.txt"):
    parsed = parse_focus_tree(src, path)
    focuses = build_focuses(parsed, tree_idx=1)
    lookup = {f.id: f for f in focuses}
    text = export_focus_tree(
        focuses,
        _info(parsed, tree_type),
        focus_lookup=lookup,
        effect_renderer=raw_block_renderer,
    )
    return focuses, text


def _summary(focuses):
    by_id = {f.id: f.name for f in focuses}
    return [
        (
            f.name,
            f.gfx,
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


@pytest.mark.parametrize(
    "src,tree_type",
    [(WRAPPED, "shared"), (NO_WRAPPER, "joint")],
)
def test_export_is_idempotent(src, tree_type):
    _f1, t1 = _load_and_export(src, tree_type)
    _f2, t2 = _load_and_export(t1, tree_type)
    assert t1 == t2


@pytest.mark.parametrize(
    "src,tree_type",
    [(WRAPPED, "shared"), (NO_WRAPPER, "joint")],
)
def test_structural_fields_survive(src, tree_type):
    f1, t1 = _load_and_export(src, tree_type)
    f2, _t2 = _load_and_export(t1, tree_type)
    assert _summary(f1) == _summary(f2)


def test_wrapped_content_present():
    _f, t1 = _load_and_export(WRAPPED, "shared")
    for needle in (
        "focus_tree = {",
        "id = TST_shared_tree",
        "original_tag = TST",
        "continuous_focus_position = { x = 50 y = 1200 }",
        "shared_focus = OTHER_shared",
        "id = TST_alpha",
        "add_political_power = 120",
        "search_filters = { FOCUS_FILTER_POLITICAL }",
        "has_war = no",
        "relative_position_id = TST_alpha",
        "offset = {",
        "prerequisite = { focus = TST_alpha }",
        "mutually_exclusive = { focus = TST_alpha }",
        "factor = 3",
    ):
        assert needle in t1, needle


def test_joint_content_present():
    _f, t1 = _load_and_export(NO_WRAPPER, "joint")
    for needle in (
        "joint_focus = {",
        "id = JNT_one",
        "joint_trigger = {",
        "is_ai = no",
        "add_political_power = 50",
    ):
        assert needle in t1, needle
