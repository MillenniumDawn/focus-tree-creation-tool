"""Module-level state shared between the wizard modules.

These were module-level globals in the monolith's tk-handling block.
Pulling them into one module keeps the wizard code free of cross-wizard
coupling and gives the App a single place to clear caches on mod reload.
"""

import os
import re

from hoi4cm.mod import WorkspaceFiles


def notifying_workspace_files(mod, mod_root):
    """A ``WorkspaceFiles`` that tells the mod's catalog what it writes.

    The ``on_written`` callback fires only when the save target is inside the
    currently loaded mod, so writing into some other folder never pokes the
    live catalog. This is the seam that keeps newly written images / .gfx
    files visible without a full rescan.
    """
    on_written = None
    root = getattr(mod, "root", "") or ""
    if getattr(mod, "loaded", False) and root:
        same_mod = os.path.normcase(os.path.abspath(root)) == os.path.normcase(
            os.path.abspath(mod_root)
        )
        if same_mod:
            on_written = mod.note_file_written
    return WorkspaceFiles(on_written=on_written)


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
    "notifying_workspace_files",
]
