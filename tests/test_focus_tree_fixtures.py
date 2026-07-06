"""Golden-fixture tests for the parse.py/build.py convergence work.

Each fixture under tests/fixtures/focus_trees/ hand-covers one importer
behavior (wrapper vs. bare focuses, bare shared_focus, country-tag-matching
offsets, the per-focus brace-walk fallback). parse_focus_tree + build_focuses
output is normalized (focuses keyed by name, prereqs/mutex remapped from id to
name) and compared against a committed golden JSON under
tests/fixtures/focus_trees/golden/. See docs/dev/testing.md for how these were
generated and how to regenerate them.
"""

import json
import os

import pytest

from hoi4cm.core import read_file
from hoi4cm.focus_tree import build_focuses, parse_focus_tree
from hoi4cm.models import Focus

FIX_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "focus_trees")
GOLDEN_DIR = os.path.join(FIX_DIR, "golden")

# fixture filename -> build_focuses kwargs
FIXTURES = {
    "wrapper_basic.txt": {},
    "bare_focus.txt": {},
    "bare_shared_focus.txt": {},
    "offset_original_tag.txt": {"country_tag": "OFS"},
    "brace_broken.txt": {},
}


@pytest.fixture(autouse=True)
def reset_counter():
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


def normalize(focus_list):
    """Key focuses by name; remap id-based prereqs/mutex to names."""
    by_id_name = {f.id: f.name for f in focus_list}
    out = {}
    for f in focus_list:
        d = f.to_dict()
        d.pop("id", None)
        d["prereqs"] = [
            [by_id_name.get(i, i) for i in grp] for grp in d.get("prereqs", [])
        ]
        d["mutex"] = [by_id_name.get(i, i) for i in d.get("mutex", [])]
        out[f.name] = d
    return out


def _parse_and_build(fname, kwargs):
    path = os.path.join(FIX_DIR, fname)
    raw = read_file(path)
    parsed = parse_focus_tree(raw, path)
    focuses = build_focuses(parsed, 0, **kwargs)
    meta = {
        "tree_id": parsed.tree_id,
        "cfp_x": parsed.cfp_x,
        "cfp_y": parsed.cfp_y,
        "country_tag": parsed.country_tag,
        "country_raw": parsed.country_raw,
        "shared_refs": parsed.shared_refs,
        "joint_refs": parsed.joint_refs,
        "had_wrapper": parsed.had_wrapper,
    }
    return meta, normalize(focuses)


def _load_golden(fname):
    name = os.path.splitext(fname)[0] + ".json"
    with open(os.path.join(GOLDEN_DIR, name), encoding="utf-8") as fp:
        return json.load(fp)


@pytest.mark.parametrize("fname,kwargs", FIXTURES.items())
def test_fixture_matches_golden(fname, kwargs):
    meta, focuses = _parse_and_build(fname, kwargs)
    golden = _load_golden(fname)
    assert meta == golden["meta"]
    assert focuses == golden["focuses"]


def test_wrapper_basic_country_raw_is_verbatim():
    # Distinctive formatting (irregular spacing, no space around one `=`,
    # trailing blank line) survives parse_focus_tree unchanged.
    meta, _ = _parse_and_build("wrapper_basic.txt", {})
    assert meta["country_raw"] == (
        "factor    =   0\nmodifier = {\n\tadd = 20\n\toriginal_tag=TST\n}\n\n\t"
    )


def test_wrapper_basic_prereq_groups_and_mutex():
    _, focuses = _parse_and_build("wrapper_basic.txt", {})
    needs_either = focuses["TST_needs_either"]
    # AND of two groups; first group is an OR of two focuses.
    assert needs_either["prereqs"] == [
        ["TST_child_a", "TST_child_b"],
        ["TST_root"],
    ]
    assert needs_either["mutex"] == ["TST_child_b"]


def test_wrapper_basic_nested_relative_position_chain():
    _, focuses = _parse_and_build("wrapper_basic.txt", {})
    # root(0,0) -> child_a(+1,+1) -> child_b(+1,+0) -> needs_either(+2,+2)
    assert (focuses["TST_root"]["x"], focuses["TST_root"]["y"]) == (0, 0)
    assert (focuses["TST_child_a"]["x"], focuses["TST_child_a"]["y"]) == (1, 1)
    assert (focuses["TST_child_b"]["x"], focuses["TST_child_b"]["y"]) == (2, 1)
    assert (focuses["TST_needs_either"]["x"], focuses["TST_needs_either"]["y"]) == (
        4,
        3,
    )


def test_bare_focus_no_wrapper_falls_back_to_filename():
    meta, focuses = _parse_and_build("bare_focus.txt", {})
    assert meta["had_wrapper"] is False
    assert meta["tree_id"] == "bare_focus"
    assert set(focuses) == {"BAR_alpha", "BAR_beta"}
    assert focuses["BAR_beta"]["prereqs"] == [["BAR_alpha"]]


def test_bare_shared_focus_no_wrapper():
    meta, focuses = _parse_and_build("bare_shared_focus.txt", {})
    assert meta["had_wrapper"] is False
    assert set(focuses) == {"SHR_one", "SHR_two"}
    assert (focuses["SHR_two"]["x"], focuses["SHR_two"]["y"]) == (1, 1)


def test_offset_applies_only_for_matching_tag():
    _, matching = _parse_and_build("offset_original_tag.txt", {"country_tag": "OFS"})
    _, other = _parse_and_build("offset_original_tag.txt", {"country_tag": "ZZZ"})
    _, none = _parse_and_build("offset_original_tag.txt", {})
    # anchor(10,10) + rel(1,1) = (11,11); offset (+5,-2) applies only for OFS.
    assert (matching["OFS_shifted"]["x"], matching["OFS_shifted"]["y"]) == (16, 9)
    assert (other["OFS_shifted"]["x"], other["OFS_shifted"]["y"]) == (11, 11)
    assert (none["OFS_shifted"]["x"], none["OFS_shifted"]["y"]) == (11, 11)


def test_brace_broken_recovers_all_focuses_via_fallback():
    meta, focuses = _parse_and_build("brace_broken.txt", {})
    assert set(focuses) == {"BRK_alpha", "BRK_beta", "BRK_gamma"}
    # The structured pass alone would have merged BRK_gamma into BRK_beta as a
    # nested value; the per-focus brace-walk recovers all three as siblings
    # with their basic scalar fields intact.
    for name, (x, y) in {
        "BRK_alpha": (0, 0),
        "BRK_beta": (1, 0),
        "BRK_gamma": (2, 0),
    }.items():
        assert (focuses[name]["x"], focuses[name]["y"]) == (x, y)
        assert focuses[name]["cost"] == 5
