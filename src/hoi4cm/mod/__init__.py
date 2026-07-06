"""Mod context — the discovered-mod assets singleton the whole app reads.

The :class:`~hoi4cm.mod.context.ModContext` instance lives at module level as
``MOD`` for back-compat with the rest of the codebase. Wizard code reads
``MOD.sprites``, ``MOD.idea_ids``, etc. just like it did in the monolith.
"""

from hoi4cm.mod.context import ModContext, detect_loc_file

# Module-level singleton. Lazily constructed on first import so any code that
# does ``from hoi4cm.mod import MOD`` gets the same instance.
MOD = ModContext()


__all__ = ["ModContext", "MOD", "detect_loc_file"]
