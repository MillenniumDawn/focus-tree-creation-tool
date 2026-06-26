"""Module-level state shared between the wizard modules.

These were module-level globals in the monolith's tk-handling block.
Pulling them into one module keeps the wizard code free of cross-wizard
coupling and gives the App a single place to clear caches on mod reload.
"""

import re

# ── Image cache registry ──────────────────────────────────────────
# Wizards register their own caches here so the App can invalidate
# everything on mod reload without poking into each module.
_app_img_caches = []


# ── Per-wizard caches (event wizard) ───────────────────────────────
_ev_gfx_cache: dict = {}  # gfx_name -> file path
_ev_imgsize_cache: dict = {}  # file path -> (w, h)
_app_img_caches.extend([_ev_gfx_cache, _ev_imgsize_cache])


# ── Pre-compiled regex used by the additional-income wizard ────────
# Pulls the localisation-key token out of a quoted HOI4 string.
_LOC_KEY_RE = re.compile(r'\s+(\S+?)(?::\d+)?\s*"')

__all__ = [
    "_app_img_caches",
    "_ev_gfx_cache",
    "_ev_imgsize_cache",
    "_LOC_KEY_RE",
]
