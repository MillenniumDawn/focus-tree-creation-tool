"""Base module: logging + foundational utilities for the HOI4 Content Maker."""
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
]
