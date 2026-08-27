"""Tests for the sidebar's virtualized Loaded Trees panel (issue #114).

_refresh_loaded_trees_panel used to destroy and rebuild a Frame + several
Labels/Buttons per extra tree on every call. These tests pin the pooled
replacement: building rows for thousands of extra trees must not scale
widget construction with the tree count, and the shared/joint reference
lists in the Tree Meta panel must stay capped rather than growing one Label
per reference.
"""

import tkinter as tk
from unittest.mock import Mock

import hoi4_content_maker as app_module
from hoi4cm.ui.loaded_trees import VirtualLoadedTreesList


def _tree(i: int) -> dict:
    return {
        "type": "shared",
        "tree_id": f"TREE_{i:04d}",
        "file_path": f"/mods/tree_{i:04d}.txt",
        "focus_ids": {f"f{i}_0", f"f{i}_1"},
    }


def _count_widgets(widget) -> int:
    return 1 + sum(_count_widgets(w) for w in widget.winfo_children())


class _LoadedTreesHost:
    """Bare host exposing just what _refresh_loaded_trees_panel touches."""

    _get_tree_badge = app_module.App._get_tree_badge

    def __init__(self, master, on_export, on_unload):
        self._loaded_trees_empty = tk.Label(master)
        self._loaded_trees_box = tk.Frame(master, height=150)
        self._loaded_trees_box.pack_propagate(False)
        self._loaded_trees_inner = VirtualLoadedTreesList(
            self._loaded_trees_box, on_export=on_export, on_unload=on_unload
        )
        self._loaded_trees_inner.pack(fill="both", expand=True)
        self._loaded_trees_border = tk.Frame(master, height=1)
        self._loaded_trees_border.pack(fill="x")
        self._extra_trees: list = []


def test_refresh_loaded_trees_panel_pools_rows_for_thousands_of_trees(tk_root):
    """The issue's blowup: N extra trees must not construct N*k widgets."""
    tk_root.geometry("340x200")
    host = _LoadedTreesHost(tk_root, Mock(), Mock())
    host._extra_trees = [_tree(i) for i in range(3_000)]

    app_module.App._refresh_loaded_trees_panel(host)
    tk_root.update()
    host._loaded_trees_inner.refresh()

    panel = host._loaded_trees_inner
    assert panel.filtered_count == 3_000
    assert panel.pool_size < 30
    assert _count_widgets(panel) < 250


def test_refresh_loaded_trees_panel_renders_row_content_and_wires_buttons(tk_root):
    tk_root.geometry("340x200")
    on_export, on_unload = Mock(), Mock()
    host = _LoadedTreesHost(tk_root, on_export, on_unload)
    host._extra_trees = [_tree(0), _tree(1)]

    app_module.App._refresh_loaded_trees_panel(host)
    tk_root.update()
    host._loaded_trees_inner.refresh()

    row0 = host._loaded_trees_inner._rows[0]
    assert row0.tree_idx == 1
    assert row0.badge.cget("text") == " [S]"
    assert row0.id_label.cget("text") == "TREE_0000"
    assert "2 focuses" in row0.summary_label.cget("text")

    row0.save_btn.invoke()
    on_export.assert_called_once_with(1)
    row0.unload_btn.invoke()
    on_unload.assert_called_once_with(1)


def test_refresh_loaded_trees_panel_toggles_empty_placeholder(tk_root):
    host = _LoadedTreesHost(tk_root, Mock(), Mock())

    app_module.App._refresh_loaded_trees_panel(host)
    assert host._loaded_trees_empty.winfo_manager() == "pack"
    assert host._loaded_trees_box.winfo_manager() == ""

    host._extra_trees = [_tree(0)]
    app_module.App._refresh_loaded_trees_panel(host)
    assert host._loaded_trees_empty.winfo_manager() == ""
    assert host._loaded_trees_box.winfo_manager() == "pack"

    host._extra_trees = []
    app_module.App._refresh_loaded_trees_panel(host)
    assert host._loaded_trees_empty.winfo_manager() == "pack"
    assert host._loaded_trees_box.winfo_manager() == ""


class _CapHost:
    TREE_META_REF_CAP = app_module.App.TREE_META_REF_CAP


def test_fill_tree_meta_box_caps_long_ref_lists(tk_root):
    box = tk.Frame(tk_root)
    refs = [f"SF_{i}" for i in range(500)]

    app_module.App._fill_tree_meta_box(_CapHost(), box, refs, "#86efac")

    cap = app_module.App.TREE_META_REF_CAP
    children = box.winfo_children()
    assert len(children) == cap + 1  # capped refs + one "+N more" label
    assert children[0].cget("text") == "  SF_0"
    assert children[-1].cget("text") == f"  +{500 - cap} more"


def test_fill_tree_meta_box_empty_shows_none(tk_root):
    box = tk.Frame(tk_root)

    app_module.App._fill_tree_meta_box(_CapHost(), box, [], "#86efac")

    children = box.winfo_children()
    assert len(children) == 1
    assert children[0].cget("text") == "  (none)"


def test_refresh_tree_meta_panel_rebuilds_without_accumulating_widgets(tk_root):
    class _MetaHost:
        _fill_tree_meta_box = app_module.App._fill_tree_meta_box
        TREE_META_REF_CAP = app_module.App.TREE_META_REF_CAP

        def __init__(self):
            self._tree_meta_sf_box = tk.Frame(tk_root)
            self._tree_meta_jf_box = tk.Frame(tk_root)
            self._shared_focuses = ["MD_shared"]
            self._joint_focuses = ["MD_joint"]

    host = _MetaHost()
    app_module.App._refresh_tree_meta_panel(host)
    assert host._tree_meta_sf_box.winfo_children()[0].cget("text") == "  MD_shared"
    assert host._tree_meta_jf_box.winfo_children()[0].cget("text") == "  MD_joint"

    host._shared_focuses = ["MD_other"]
    app_module.App._refresh_tree_meta_panel(host)
    assert len(host._tree_meta_sf_box.winfo_children()) == 1
    assert host._tree_meta_sf_box.winfo_children()[0].cget("text") == "  MD_other"
