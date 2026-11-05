"""Explorer search and discovery must preserve the workspace and source files."""

import copy
from types import SimpleNamespace

from hoi4cm.models import EditorWorkspace, FocusDocument
from hoi4cm.ui.project_index import (
    ExplorerItem,
    discover_focus_files,
    discover_resources,
    filter_project,
    focus_file_items,
    project_items,
)


def test_project_uses_existing_ownership_and_searches_labels_ids_and_paths():
    document = FocusDocument()
    first = document.new_focus(0, 0)
    first.name, first.loc_name = "TAG_industry", "Industrial Expansion"
    second = document.new_focus(4, 0)
    second.tree_idx = 1
    document.extend((first, second))
    document.touch()
    workspace = EditorWorkspace(focuses=document)
    workspace.main_tree.file_path = "common/national_focus/ambiguous.txt"
    app = SimpleNamespace(
        focuses=document,
        workspace=workspace,
        _last_project_path="my-project.json",
        _tree_id=SimpleNamespace(get=lambda: "main_tree"),
        _extra_trees=[
            {
                "tree_id": "shared_registry",
                "file_path": "common/shared.txt",
                "type": "joint",
                "focus_ids": {second.id},
            }
        ],
    )
    mod = SimpleNamespace(root=None, edit_focus_file="", mod_name="")
    before = copy.deepcopy(([f.to_dict() for f in document.values()], app._extra_trees))
    items = project_items(app, mod)
    focuses = [item for item in items if item.kind == "focus"]
    assert len(focuses) == 2
    assert focuses[0].parent == "tree:0"
    assert focuses[1].parent == "tree:1"
    assert [item.kind for item in filter_project(items, "industrial")] == [
        "project",
        "tree_catalog",
        "tree",
        "focus",
    ]
    assert filter_project(items, "TAG_industry") == filter_project(items, "industrial")
    assert focuses[1] in filter_project(items, "common/shared.txt")
    assert not filter_project(items, "unfindable")
    assert filter_project(items, " ") is items
    assert before == ([f.to_dict() for f in document.values()], app._extra_trees)


def test_matching_group_keeps_children_and_ancestors():
    items = (
        ExplorerItem("root", "", "Project", "project"),
        ExplorerItem("tree", "root", "Joint tree", "tree"),
        ExplorerItem("focus", "tree", "Focus", "focus"),
    )
    assert filter_project(items, "joint") == items


def test_empty_project_does_not_invent_content():
    app = SimpleNamespace(
        focuses=FocusDocument(),
        workspace=EditorWorkspace(),
        _extra_trees=[],
        _last_project_path=None,
    )
    mod = SimpleNamespace(root=None, edit_focus_file="")
    assert project_items(app, mod) == ()


def test_explicit_empty_project_and_unloaded_mod_have_distinct_states():
    app = SimpleNamespace(
        focuses=FocusDocument(),
        workspace=EditorWorkspace(),
        _extra_trees=[],
        _last_project_path=None,
        _navigation_started=True,
        _navigation_source="",
        _tree_id=SimpleNamespace(get=lambda: "new_empty_tree"),
    )
    mod = SimpleNamespace(
        root=None, edit_focus_file="old_export_target.txt", mod_name=""
    )
    items = project_items(app, mod)
    assert next(item for item in items if item.kind == "tree").label == "new_empty_tree"
    assert any(item.key == "empty-tree:0" for item in items)
    assert all("old_export_target" not in item.path for item in items)
    app._navigation_started = False
    mod.root, mod.mod_name = "mod", "A loaded mod"
    items = project_items(app, mod)
    assert not any(item.kind == "tree" for item in items)
    assert any(item.kind == "tree_catalog" for item in items)


def test_resource_discovery_is_read_only_and_distinguishes_failure(
    tmp_path, monkeypatch
):
    source = tmp_path / "nested" / "original.txt"
    source.parent.mkdir()
    source.write_bytes(b"\xff\xfeexisting source")
    assert discover_resources(str(tmp_path)) == ((str(source),), ())
    assert source.read_bytes() == b"\xff\xfeexisting source"
    assert discover_resources(str(tmp_path / "missing")) == ((), ())

    def denied(_path):
        raise PermissionError("Unreadable source folder")

    monkeypatch.setattr("hoi4cm.ui.project_index.os.scandir", denied)
    paths, errors = discover_resources(str(tmp_path))
    assert not paths
    assert "Unreadable source folder" in errors[0]


def test_available_tree_files_are_searchable_and_do_not_duplicate_loaded_paths(
    tmp_path,
):
    root = tmp_path / "common" / "national_focus"
    root.mkdir(parents=True)
    loaded, other = root / "loaded.txt", root / "nested" / "other.TXT"
    items = (
        ExplorerItem("project", "", "Mod", "project"),
        ExplorerItem(
            "focus-trees", "project", "Focus Trees", "tree_catalog", str(root)
        ),
        ExplorerItem("tree:0", "focus-trees", "Loaded ID", "tree", str(loaded)),
    )
    available = focus_file_items(
        items, (str(loaded), str(other), str(root / "notes.md"))
    )
    assert [item.path for item in available] == [str(other)]
    assert available[0].kind == "tree_file"
    result = filter_project(items + available, "other.TXT")
    assert [item.key for item in result] == ["project", "focus-trees", available[0].key]
    adopted = items + (
        ExplorerItem("tree:1", "focus-trees", "Other ID", "tree", str(other)),
    )
    assert not focus_file_items(adopted, (str(loaded), str(other)))
    assert focus_file_items(items, None)[0].key == "trees:loading"
    failed = focus_file_items(items, (), ("access denied",))
    assert failed[0].detail == "access denied"


def test_tree_discovery_skips_utility_tables_comments_and_strings(tmp_path):
    tree = tmp_path / "country.txt"
    shared = tmp_path / "shared.txt"
    tree.write_text("focus_tree = { id = country }", encoding="utf-8")
    shared.write_bytes(b"# caf\xe9\nshared_focus = { id = actual }")
    (tmp_path / "styles.txt").write_text(
        '# focus_tree = {}\nstyle = { name = "focus = {" }', encoding="utf-8"
    )
    (tmp_path / "readme.md").write_text("focus_tree = {}", encoding="utf-8")
    files, errors = discover_focus_files(str(tmp_path))
    assert set(files) == {str(tree), str(shared)}
    assert not errors


def test_tree_discovery_reports_unreadable_sources(tmp_path, monkeypatch):
    source = tmp_path / "unreadable.txt"
    source.write_text("original", encoding="utf-8")
    monkeypatch.setattr(
        "hoi4cm.ui.project_index.read_file_with_encoding", lambda _path: (None, None)
    )
    files, errors = discover_focus_files(str(tmp_path))
    assert not files
    assert str(source) in errors[0]
    assert source.read_text(encoding="utf-8") == "original"
