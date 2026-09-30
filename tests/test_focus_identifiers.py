"""Lossless identifiers and rejected exports must preserve user data."""

import pytest

from hoi4cm.focus_tree.build import build_focuses
from hoi4cm.focus_tree.export import export_focus_tree, export_main_tree
from hoi4cm.focus_tree.export_plan import (
    execute_export_plans,
    make_extra_export_plan,
    make_main_export_plan,
)
from hoi4cm.focus_tree.identifiers import checked_focus_names
from hoi4cm.focus_tree.loc import build_loc_yml, hydrate_focus_localization
from hoi4cm.focus_tree.parse import parse_focus_tree
from hoi4cm.models import Focus


@pytest.fixture(autouse=True)
def reset_counter():
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


def _focus(name):
    focus = Focus(0, 0)
    focus.name = name
    return focus


def _info(**overrides):
    return {"tree_id": "TST_tree", "country_tag": "TST", **overrides}


@pytest.mark.parametrize("tree_type", ["main", "shared", "wrapped", "joint"])
def test_distinct_valid_ids_roundtrip_with_references_and_localisation(tree_type):
    parent, child = _focus("a-b"), _focus("a_b")
    child.x, child.y = 2, 3
    child.prereqs = [[parent.id]]
    child.mutex = [parent.id]
    child.relative_position_id = parent.name
    parent.loc_name, child.loc_name = "Hyphen", "Underscore"
    parent.desc, child.desc = "Parent description", "Child description"
    focuses = [parent, child]
    for focus in focuses:
        focus.effects = [
            {"type": "_raw_block", "fields": {"raw": "add_political_power = 5"}}
        ]
    lookup = {focus.id: focus for focus in focuses}
    exporter = export_main_tree if tree_type == "main" else export_focus_tree
    info = _info(type=tree_type, had_wrapper=tree_type == "wrapped")
    text = exporter(focuses, info, focus_lookup=lookup)
    loc, count = build_loc_yml(None, focuses, "TST")
    assert count == 4
    restored = build_focuses(parse_focus_tree(text, "test.txt"), 0)
    assert [focus.name for focus in restored] == ["a-b", "a_b"]
    assert restored[1].prereqs == [[restored[0].id]]
    assert restored[1].mutex == [restored[0].id]
    assert restored[1].relative_position_id == "a-b"
    assert restored[0].effects[0]["fields"]["raw"].strip() == "add_political_power = 5"
    hydrate_focus_localization(loc, restored)
    assert [focus.loc_name for focus in restored] == ["Hyphen", "Underscore"]
    assert [focus.desc for focus in restored] == [parent.desc, child.desc]
    assert build_loc_yml(loc, restored, "TST") == (None, 0)
    assert exporter(restored, info, focus_lookup={f.id: f for f in restored}) == text


@pytest.mark.parametrize("bad_name", ['a"b', "a\nb", "a: b", "a#b", ""])
@pytest.mark.parametrize("exporter", [export_main_tree, export_focus_tree])
def test_unsafe_parent_is_rejected_before_linked_export(exporter, bad_name):
    parent, child, other = _focus(bad_name), _focus("child"), _focus("a_b")
    child.prereqs = [[parent.id]]
    child.mutex = [parent.id]
    child.relative_position_id = parent.name
    focuses = [parent, child, other]
    snapshot = [focus.to_dict() for focus in focuses]
    with pytest.raises(ValueError, match="cannot be exported safely"):
        exporter(focuses, _info(), focus_lookup={f.id: f for f in focuses})
    with pytest.raises(ValueError, match="cannot be exported safely"):
        build_loc_yml(None, focuses, "TST")
    assert [focus.to_dict() for focus in focuses] == snapshot


@pytest.mark.parametrize("names", [("a_b", "a_b"), ("a", "a_desc")])
def test_duplicate_and_description_key_collisions_are_rejected(names):
    focuses = [_focus(name) for name in names]
    with pytest.raises(ValueError, match="collides"):
        checked_focus_names(focuses)
    with pytest.raises(ValueError, match="collides"):
        build_loc_yml(None, focuses, "TST")


@pytest.mark.parametrize("names", [('a"b', "a_b"), ("a_b", "a_b"), ("a", "a_desc")])
@pytest.mark.parametrize("tree_type", ["main", "extra"])
def test_failed_plan_never_calls_writer_or_changes_existing_pair(
    tmp_path, names, tree_type
):
    focuses = [_focus(name) for name in names]
    script_path, loc_path = tmp_path / "tree.txt", tmp_path / "loc.yml"
    script_path.write_text("original script", encoding="utf-8")
    loc_path.write_text("original loc", encoding="utf-8")
    plan_args = dict(
        label="Main",
        focus_path=str(script_path),
        focuses=focuses,
        tree_info=_info(),
        focus_lookup={f.id: f for f in focuses},
        focus_name_lookup={f.name: f for f in focuses},
    )
    if tree_type == "main":
        plan = make_main_export_plan(**plan_args, loc_path=str(loc_path))
    else:
        plan = make_extra_export_plan(**plan_args, extra_tree_idx=1)
    writes = []
    result = execute_export_plans([plan], lambda entries: writes.append(tuple(entries)))
    assert isinstance(result[0].error, ValueError)
    assert not writes
    assert script_path.read_text(encoding="utf-8") == "original script"
    assert loc_path.read_text(encoding="utf-8") == "original loc"


def test_localisation_hydrates_original_punctuation_keys():
    focuses = [_focus("a-b"), _focus("a_b"), _focus("a.b")]
    hydrate_focus_localization(
        'l_english:\n a-b:0 "Hyphen"\n a_b:0 "Underscore"\n a.b:0 "Dot"\n',
        focuses,
    )
    assert [f.loc_name for f in focuses] == ["Hyphen", "Underscore", "Dot"]


@pytest.mark.parametrize("link_type", ["prerequisite", "mutex", "relative"])
def test_unsafe_link_to_another_loaded_tree_is_rejected(link_type):
    parent, child = _focus('a"b'), _focus("child")
    if link_type == "prerequisite":
        child.prereqs = [[parent.id]]
    elif link_type == "mutex":
        child.mutex = [parent.id]
    else:
        child.relative_position_id = parent.name
    with pytest.raises(ValueError, match="cannot be exported safely"):
        export_main_tree(
            [child], _info(), focus_lookup={f.id: f for f in [parent, child]}
        )
