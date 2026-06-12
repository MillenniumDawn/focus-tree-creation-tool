"""Persistent user config for the HOI4 Content Maker.

Stored as a JSON dict at ``~/.hoi4_focus_maker.json``. The path is unchanged
from the original monolith so existing user configs keep loading.
"""
import json
import os

from .logger import get_logger

_log = get_logger("config")

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".hoi4_focus_maker.json")


def cfg_load():
    """Load saved config dict, return {} on any error."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def cfg_save(data):
    """Merge data into existing config and write to disk."""
    try:
        existing = cfg_load()
        existing.update(data)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        _log.error(f"save failed: {e}")
