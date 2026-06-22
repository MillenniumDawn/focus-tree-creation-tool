"""Focus-tree loading: parse script text, build focuses, serialize back.

Shared core behind the monolith's shared/joint tree loaders. The flow is
parse_focus_tree (text -> ParsedFocusTree) -> build_focuses (-> Focus objects)
-> export_focus_tree (Focus objects -> script text).
"""

from .build import build_focuses
from .export import export_focus_tree
from .parse import EmptyFocusTreeError, ParsedFocusTree, parse_focus_tree

__all__ = [
    "parse_focus_tree",
    "ParsedFocusTree",
    "EmptyFocusTreeError",
    "build_focuses",
    "export_focus_tree",
]
