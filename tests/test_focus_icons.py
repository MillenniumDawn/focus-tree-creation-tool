"""Structured MD icons survive editing, project recovery and every exporter."""

import json

import pytest

from hoi4cm.core.undo import _snapshot_focus
from hoi4cm.editor.project_codec import decode_project, encode_project
from hoi4cm.focus_tree.build import build_focuses
from hoi4cm.focus_tree.codec import apply_focus_code, render_focus_block
from hoi4cm.focus_tree.export import export_focus_tree, export_main_tree
from hoi4cm.focus_tree.parse import parse_focus_tree
from hoi4cm.models import EditorWorkspace, Focus


@pytest.mark.parametrize(
    "icons",
    [
        "icon = { FRA_udf_party = { NOT = { has_country_flag = FRA_LREM_CREATED } } "
        "FRA_larem_party = yes }",
        "icon = first icon = { second = { original_tag = KAZ } third = yes }",
    ],
)
def test_structured_icon_complete_round_trip(icons):
    source = (
        f"focus_tree = {{ id = TST focus = {{ id = TST_one {icons} x = 1 y = 2 }} }}"
    )
    parsed = parse_focus_tree(source, "test.txt")
    focus = build_focuses(parsed, 0)[0]
    original_icon = parsed.focuses_data[0]["icon"]
    assert isinstance(focus.gfx, str)
    hash(focus.gfx)  # GFX catalog keys must always be scalar.
    focus.cost = 12
    focus.gfx = focus.gfx  # Unchanged sidebar field must retain script.
    workspace = EditorWorkspace()
    workspace.focuses[focus.id] = focus
    restored = decode_project(json.loads(json.dumps(encode_project(workspace))))
    focus = restored.focuses[focus.id]
    focus = Focus.from_dict(_snapshot_focus(focus))
    lookup = {focus.id: focus}
    code = render_focus_block(
        focus, focus_lookup=lookup, focus_name_lookup={focus.name: focus}
    )
    apply_focus_code(focus, code, focus_lookup=lookup)
    for exporter, info in [
        (export_main_tree, {"tree_id": "TST"}),
        (export_focus_tree, {"tree_id": "TST", "had_wrapper": True}),
        (export_focus_tree, {"tree_id": "TST", "type": "shared"}),
        (export_focus_tree, {"tree_id": "TST", "type": "joint"}),
    ]:
        output = exporter([focus], info, focus_lookup=lookup)
        reparsed = parse_focus_tree(output, "test.txt")
        assert reparsed.focuses_data[0]["icon"] == original_icon
    preview = focus.gfx
    focus.gfx = "replacement"
    focus.gfx = preview
    assert not hasattr(focus, "_icon_script")


def test_old_project_structured_gfx_and_metadata_order():
    focus = Focus.from_dict({"gfx": {"first": "yes"}})
    assert focus.gfx == "first"
    snapshot = {"_icon_script": focus._icon_script, "gfx": focus.gfx}
    assert Focus.from_dict(snapshot)._icon_script == focus._icon_script


def test_malformed_semantic_icon_falls_back_to_scalar():
    focus = Focus.from_dict({"gfx": "first", "_icon_script": {"preview": "first"}})
    assert not hasattr(focus, "_icon_script")
