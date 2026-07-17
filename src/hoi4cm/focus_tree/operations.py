from __future__ import annotations

from collections.abc import Iterable

from hoi4cm.models import Focus


def group_focuses_by_tree(focuses: Iterable[Focus]) -> dict[int, list[Focus]]:
    groups: dict[int, list[Focus]] = {}
    for focus in focuses:
        groups.setdefault(focus.tree_idx, []).append(focus)
    return groups


def build_focus_name_lookup(focuses: Iterable[Focus]) -> dict[str, Focus]:
    lookup = {}
    for focus in focuses:
        lookup.setdefault(focus.name, focus)
    return lookup
