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
    EmptyFocusTreeError,
    ParsedFocusTree,
    build_focuses,
    export_focus_tree,
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
from .paths import default_hoi4_mod_dir, read_file

__all__ = [
    "log",
    "get_logger",
    "log_startup",
    "install_excepthook",
    "add_error",
    "get_error_entries",
    "clear_errors",
    "set_error_callback",
    "CONFIG_PATH",
    "cfg_load",
    "cfg_save",
    "default_hoi4_mod_dir",
    "read_file",
    "Focus",
    "parse_focus_tree",
    "ParsedFocusTree",
    "EmptyFocusTreeError",
    "build_focuses",
    "export_focus_tree",
    "dict_to_raw",
    "normalize_effect_fields",
    "append_scripted_loc",
    "show_splash",
    "EFFECT_DEFS",
    "EFFECT_CATS",
    "effects_in_cat",
    "MODIFIER_DEFS",
    "MODIFIER_CATS",
    "modifiers_in_cat",
    "MD_BUILDING_COSTS",
    "MD_RESOURCE_COST_PER_UNIT",
    "md_building_cost_hint",
    "md_resource_cost_hint",
]
