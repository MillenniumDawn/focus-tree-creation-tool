"""Lossless focus identifiers shared by script and localisation exports."""

import re
from collections.abc import Iterable

from hoi4cm.models import Focus

__all__ = ["checked_focus_names", "focus_identifier"]

# Preserve punctuation and Unicode; raw user script may also refer to an ID.
_IDENTIFIER = re.compile(r'[^\s"#:=\{\}\x00-\x1f\x7f]+')


def focus_identifier(name: str) -> str:
    """Return an unchanged exportable ID, or reject it without losing data."""
    if not _IDENTIFIER.fullmatch(name):
        raise ValueError(
            f"Focus ID {name!r} cannot be exported safely; rename it first"
        )
    return name


def checked_focus_names(focuses: Iterable[Focus]) -> dict[str, str]:
    """Build an identity mapping, checking both title and description keys."""
    names = {}
    keys: set[str] = set()
    for focus in focuses:
        name = focus_identifier(focus.name)
        for key in (name, f"{name}_desc"):
            if key in keys:
                raise ValueError(
                    f"Focus localisation key {key!r} collides; rename it first"
                )
            keys.add(key)
        names[name] = name
    return names
