"""Focus-tree loading: parse script text, build focuses, serialize back.

Shared core behind the monolith's shared/joint tree loaders. The flow is
parse_focus_tree (text -> ParsedFocusTree) -> build_focuses (-> Focus objects)
-> export_focus_tree (Focus objects -> script text).
"""

from .batch_load import batch_load_trees, make_cancel_handle
from .build import BuildContext, build_focuses
from .codec import apply_focus_code, render_focus_block, render_focus_body
from .drawio import (
    EmptyDrawioGraphError,
    build_drawio_focuses,
    drawio_to_focus_data,
    parse_drawio_graph,
)
from .export import export_focus_tree, export_main_tree
from .export_plan import (
    ExportPlan,
    ExportResult,
    execute_export_plans,
    make_extra_export_plan,
    make_main_export_plan,
    render_export_plan,
)
from .loc import LOC_LANGUAGE_NAMES, LocTarget, build_loc_yml
from .operations import (
    build_focus_name_lookup,
    group_focuses_by_tree,
)
from .parse import EmptyFocusTreeError, ParsedFocusTree, parse_focus_tree
from .validate import (
    Issue,
    Severity,
    collect_loc_keys_from_text,
    validate_document,
    worst_severity_per_focus,
)

__all__ = [
    "batch_load_trees",
    "make_cancel_handle",
    "parse_focus_tree",
    "ParsedFocusTree",
    "EmptyFocusTreeError",
    "BuildContext",
    "apply_focus_code",
    "build_focuses",
    "build_focus_name_lookup",
    "export_focus_tree",
    "export_main_tree",
    "ExportPlan",
    "ExportResult",
    "execute_export_plans",
    "make_extra_export_plan",
    "make_main_export_plan",
    "render_export_plan",
    "group_focuses_by_tree",
    "render_focus_block",
    "render_focus_body",
    "build_loc_yml",
    "LOC_LANGUAGE_NAMES",
    "LocTarget",
    "EmptyDrawioGraphError",
    "parse_drawio_graph",
    "drawio_to_focus_data",
    "build_drawio_focuses",
    "Issue",
    "Severity",
    "collect_loc_keys_from_text",
    "validate_document",
    "worst_severity_per_focus",
]
