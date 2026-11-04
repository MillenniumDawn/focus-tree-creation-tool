"""Localisation file discovery for a mod root.

Scan results live on :class:`hoi4cm.mod.index.ModIndex`. User settings live on
:class:`hoi4cm.core.app_config.AppConfig`. PhotoImages live on the App.
"""

from __future__ import annotations

import os
import re


def find_loc_files(mod_root, *, language="english"):
    """Return configured-language localisation files below a mod root."""
    from hoi4cm.focus_tree.loc import LocTarget

    if not mod_root:
        return []
    loc_root = os.path.join(mod_root, "localisation")
    if not os.path.isdir(loc_root):
        return []

    target = LocTarget(language)
    target_dir = target.dirname().casefold()
    target_suffix = target.filename("").casefold()
    directory_matches = []
    suffix_matches = []
    try:
        for directory, dirnames, filenames in os.walk(loc_root):
            dirnames.sort(
                key=lambda name: (name.casefold() != target_dir, name.casefold())
            )
            relative_dir = os.path.relpath(directory, loc_root)
            first_part = relative_dir.split(os.sep, 1)[0].casefold()
            in_target_dir = relative_dir != "." and first_part == target_dir
            for filename in sorted(filenames, key=str.casefold):
                lower_name = filename.casefold()
                if not lower_name.endswith(".yml"):
                    continue
                path = os.path.join(directory, filename)
                if in_target_dir:
                    directory_matches.append(path)
                elif lower_name.endswith(target_suffix):
                    suffix_matches.append(path)
    except OSError:
        return []
    return directory_matches + suffix_matches


def detect_loc_file(mod_root, raw_text, *, language="english"):
    """Guess the localisation .yml matching an imported focus-tree file.

    Looks for a country tag in ``raw_text`` (the first ``TAG_something``
    identifier) and checks configured-language files recursively below
    ``mod_root/localisation/``. Returns the matched path, or ``""`` if no mod
    root, no tag, or no matching file was found.
    """
    from hoi4cm.focus_tree.loc import LocTarget

    if not mod_root:
        return ""
    tag_match = re.search(r"\b([A-Z]{2,4})_[A-Za-z]", raw_text)
    if not tag_match:
        return ""
    tag = tag_match.group(1)
    target = LocTarget(language)
    candidates = {
        target.filename(f"MD_focus_{tag}").casefold(),
        target.filename(f"{tag}_focus").casefold(),
        target.filename(f"{tag}_focuses").casefold(),
    }
    for path in find_loc_files(mod_root, language=target.language):
        if os.path.basename(path).casefold() in candidates:
            return path
    return ""


__all__ = ["detect_loc_file", "find_loc_files"]
