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


def test_offset_applies_only_for_matching_tag():
    _, matching = _parse_and_build("offset_original_tag.txt", {"country_tag": "OFS"})
    _, other = _parse_and_build("offset_original_tag.txt", {"country_tag": "ZZZ"})
    _, none = _parse_and_build("offset_original_tag.txt", {})
    # anchor(10,10) + rel(1,1) = (11,11); offset (+5,-2) applies only for OFS.
    assert (matching["OFS_shifted"]["x"], matching["OFS_shifted"]["y"]) == (16, 9)
    assert (other["OFS_shifted"]["x"], other["OFS_shifted"]["y"]) == (11, 11)
    assert (none["OFS_shifted"]["x"], none["OFS_shifted"]["y"]) == (11, 11)
