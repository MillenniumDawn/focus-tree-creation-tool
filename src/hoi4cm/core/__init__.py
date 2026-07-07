"""Base module: logging + foundational utilities for the HOI4 Content Maker."""

from hoi4cm.data import (
    EFFECT_CATS,
    EFFECT_DEFS,
    MD_BUILDING_COSTS,
    MD_RESOURCE_COST_PER_UNIT,
    MODIFIER_CATS,
    MODIFIER_DEFS,
    effects_in_cat,
    md_building_cost_hint,
    md_resource_cost_hint,
    modifiers_in_cat,
)
from hoi4cm.focus_tree import (
    EmptyDrawioGraphError,
    EmptyFocusTreeError,
    ParsedFocusTree,
    build_drawio_focuses,
    build_focuses,
    build_loc_yml,
    drawio_to_focus_data,
    export_focus_tree,
    export_main_tree,
    parse_drawio_graph,
    parse_focus_tree,
)
from hoi4cm.models import Focus
from hoi4cm.script import (
    append_scripted_loc,
    dict_to_raw,
    normalize_effect_fields,
)
from hoi4cm.ui import show_splash

from .config import CONFIG_PATH, cfg_load, cfg_save
from .i18n import (
    I18N_LANG,
    I18N_LANGS,
    I18N_STRINGS,
    get_language,
    set_language,
    tr,
)
from .logger import (
    add_error,
    clear_errors,
    get_error_entries,
    get_logger,
    install_excepthook,
    log,
    log_startup,
    set_error_callback,
)
from .paths import autosave_path, default_hoi4_mod_dir, read_file
from .safe_path import safe_join, sanitize_component
from .safe_xml import bounded_inflate, safe_fromstring
from .undo import UndoStack

__all__ = [
    "CONFIG_PATH",
    "EFFECT_CATS",
    "EFFECT_DEFS",
    "EmptyDrawioGraphError",
    "EmptyFocusTreeError",
    "Focus",
    "I18N_LANG",
    "I18N_LANGS",
    "I18N_STRINGS",
    "get_language",
    "MD_BUILDING_COSTS",
    "MD_RESOURCE_COST_PER_UNIT",
    "MODIFIER_CATS",
    "MODIFIER_DEFS",
    "ParsedFocusTree",
    "UndoStack",
    "add_error",
    "append_scripted_loc",
    "autosave_path",
    "bounded_inflate",
    "build_drawio_focuses",
    "build_focuses",
    "build_loc_yml",
    "cfg_load",
    "cfg_save",
    "clear_errors",
    "default_hoi4_mod_dir",
    "dict_to_raw",
    "drawio_to_focus_data",
    "effects_in_cat",
    "export_focus_tree",
    "export_main_tree",
    "get_error_entries",
    "get_logger",
    "install_excepthook",
    "log",
    "log_startup",
    "md_building_cost_hint",
    "md_resource_cost_hint",
    "modifiers_in_cat",
    "normalize_effect_fields",
    "parse_drawio_graph",
    "parse_focus_tree",
    "read_file",
    "safe_join",
    "safe_fromstring",
    "sanitize_component",
    "set_error_callback",
    "set_language",
    "show_splash",
    "tr",
]
