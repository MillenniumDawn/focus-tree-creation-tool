"""UI i18n — load ``locales/<lang>.json`` and resolve translation keys.

Source code uses stable keys plus English fallbacks::

    text = tr("common.cancel", "Cancel")

The default language is taken from the ``HOI4CM_LANG`` env var, falling back
to the user's saved config (``language`` key), falling back to ``en``.
Locale JSON files live in ``./locales/<lang>.json`` and may be edited without
touching code.

This module is intentionally a stateful singleton (the i18n strings are
loaded once into a module-level dict and re-read on ``set_language``) because
Tk code reads ``tr(...)`` at call time, not at import time.
"""

import json
import os
import sys

from hoi4cm.core.config import cfg_load, cfg_save
from hoi4cm.core.logger import get_logger

_log = get_logger("i18n")

# Public state
I18N_LANGS = {
    "en": "English",
    "zh_CN": "简体中文",
}
I18N_LANG = None
I18N_STRINGS: dict[str, str] = {}


def _project_root():
    """Absolute path to the project root (parent of ``src/``).

    In a PyInstaller bundle, ``_MEIPASS`` is the bundle root which already
    holds ``locales/`` directly. In source, the project root is four
    parents up from this file (``src/hoi4cm/core/i18n.py``).
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        return meipass
    here = os.path.abspath(__file__)
    # here ends in src/hoi4cm/core/i18n.py — go up 4 segments.
    return here.rsplit(os.sep, 4)[0]


def _locale_path(lang):
    return os.path.join(_project_root(), "locales", f"{lang}.json")


def _load_i18n(lang=None):
    """Load UI translations with safe fallback to English."""
    global I18N_LANG, I18N_STRINGS
    cfg = cfg_load()
    chosen = lang or os.environ.get("HOI4CM_LANG") or cfg.get("language") or "en"
    if chosen not in I18N_LANGS:
        chosen = "en"
    path = _locale_path(chosen)
    try:
        with open(path, encoding="utf-8") as f:
            I18N_STRINGS = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        _log.warning("locale load failed for %s: %s", chosen, exc)
        I18N_STRINGS = {}
    I18N_LANG = chosen


def set_language(lang):
    """Persist and switch the active language."""
    if lang not in I18N_LANGS:
        lang = "en"
    cfg_save({"language": lang})
    _load_i18n(lang)


def get_language():
    """Return the currently active language code.

    Use this instead of importing the I18N_LANG name directly: the global is
    reassigned by set_language(), so an imported name would go stale.
    """
    return I18N_LANG


def tr(key: str, default: str | None = None, **kwargs: object) -> str:
    """Resolve a translation key. Falls back to *default* then the key itself."""
    text = I18N_STRINGS.get(key, default if default is not None else key)
    try:
        return text.format(**kwargs)
    except KeyError, ValueError, IndexError, AttributeError, TypeError:
        return text


# Auto-load on import so tr() works the moment any module that depends on
# this one is imported.
_load_i18n()


__all__ = [
    "I18N_LANGS",
    "I18N_LANG",
    "I18N_STRINGS",
    "get_language",
    "set_language",
    "tr",
]
