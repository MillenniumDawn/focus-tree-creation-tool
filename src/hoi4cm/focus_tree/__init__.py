"""Focus-tree loading: parse script text, build focuses, serialize back.

Shared core behind the monolith's shared/joint tree loaders. The flow is
parse_focus_tree (text -> ParsedFocusTree) -> build_focuses (-> Focus objects)
-> export_focus_tree (Focus objects -> script text).
"""

from .build import build_focuses
from .drawio import (
    EmptyDrawioGraphError,
    build_drawio_focuses,
    drawio_to_focus_data,
    parse_drawio_graph,
)
from .export import export_focus_tree, export_main_tree
from .loc import build_loc_yml
from .parse import EmptyFocusTreeError, ParsedFocusTree, parse_focus_tree

__all__ = [
    "parse_focus_tree",
    "ParsedFocusTree",
    "EmptyFocusTreeError",
    "build_focuses",
    "export_focus_tree",
    "export_main_tree",
    "build_loc_yml",
    "EmptyDrawioGraphError",
    "parse_drawio_graph",
    "drawio_to_focus_data",
    "build_drawio_focuses",
]
