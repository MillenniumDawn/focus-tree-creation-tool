import pytest

from hoi4cm.editor.project_codec import decode_project, encode_project
from hoi4cm.models import (
    EditorWorkspace,
    Focus,
    FocusDocument,
    TreeDocument,
    TreeMetadata,
)


def test_legacy_two_field_project_loads_without_changing_focus_data():
    legacy = {
        "tree_name": "legacy_tree",
        "focuses": [
            {
                "id": 91,
                "name": "duplicate",
                "x": 3,
                "y": 4,
                "cost": 7,
                "effects": [],
                "prereqs": [],
                "unknown_focus_field": {"kept": True},
            },
            {
                "id": 92,
                "name": "duplicate",
                "x": 5,
                "y": 6,
                "effects": [],
                "prereqs": [],
            },
        ],
    }

    workspace = decode_project(legacy)
    encoded = encode_project(workspace)
    restored = decode_project(encoded)

    assert workspace.main_tree.metadata.tree_id == "legacy_tree"
    assert list(restored.focuses) == [91, 92]
    assert restored.focuses[91].unknown_focus_field == {"kept": True}
    assert restored.focuses.names["duplicate"] == (91, 92)


def test_legacy_decode_yields_empty_file_path():
    # The app must not treat this empty file_path as "clear the export target"
    # -- loading an old project keeps whatever export file the user had chosen.
    workspace = decode_project({"tree_name": "legacy_tree", "focuses": []})

    assert workspace.main_tree.file_path == ""


def test_v2_roundtrip_preserves_workspace_and_tree_metadata():
    main = Focus(1, 2)
    main.id = 12345678901234567890
    main.name = "same_name"
    extra = Focus(8, 9)
    extra.id = 7
    extra.name = "same_name"
    extra.tree_idx = 1
    workspace = EditorWorkspace(
        focuses=FocusDocument((main, extra)),
        main_tree=TreeDocument(
            metadata=TreeMetadata(
                tree_id="main_tree",
                country_tag="ABC",
                country_name="Example",
                country_raw="factor = 0",
                focus_prefix="ABC_",
                cfp_x=11,
                cfp_y=12,
                shared_focuses=["shared_tree"],
                joint_focuses=["joint_tree"],
            ),
            focus_ids={main.id},
            metadata_extras={"future_metadata_field": {"kept": True}},
        ),
        extra_trees=[
            TreeDocument(
                metadata=TreeMetadata(tree_id="shared_tree", country_tag="ABC"),
                tree_type="shared",
                file_path="common/national_focus/shared.txt",
                had_wrapper=False,
                focus_ids={extra.id},
                extras={"future_tree_field": 42},
            )
        ],
        canvas_min=(-4, -5),
        canvas_max=(40, 50),
        canvas_extras={"future_canvas_field": [1, 2, 3]},
        default_focus_prefix="ABC_",
        workspace_extras={"future_workspace_field": {"enabled": True}},
        extras={"future_root_field": [1, 2, 3]},
    )

    restored = decode_project(encode_project(workspace))

    assert restored.main_tree.metadata == workspace.main_tree.metadata
    assert restored.extra_trees == workspace.extra_trees
    assert restored.canvas_min == (-4, -5)
    assert restored.canvas_max == (40, 50)
    assert restored.canvas_extras == {"future_canvas_field": [1, 2, 3]}
    assert restored.default_focus_prefix == "ABC_"
    assert restored.workspace_extras == {"future_workspace_field": {"enabled": True}}
    assert restored.extras == {"future_root_field": [1, 2, 3]}
    assert list(restored.focuses) == [main.id, extra.id]
    assert restored.focuses.names["same_name"] == (main.id, extra.id)


def test_future_project_version_is_rejected_without_legacy_fallback():
    project = {
        "format": "hoi4cm-project",
        "version": 3,
        "workspace": {"focuses": [{"id": 1, "name": "kept"}]},
    }

    with pytest.raises(ValueError, match="unsupported project version"):
        decode_project(project)
