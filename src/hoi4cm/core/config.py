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
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        _log.debug("config load failed: %s", exc, exc_info=True)
        return {}


def cfg_save(data):
    """Merge data into existing config and write it atomically."""
    try:
        existing = cfg_load()
        existing.update(data)
        tmp = CONFIG_PATH + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, CONFIG_PATH)
        except OSError, ValueError, TypeError, RuntimeError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        _log.debug("save failed: %s", exc, exc_info=True)
