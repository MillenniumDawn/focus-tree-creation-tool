from __future__ import annotations

from collections.abc import Iterable, Set

from hoi4cm.models import Focus

ReferenceUpdate = tuple[list[list[int]], list[int]]


def plan_reference_cleanup(
    focuses: Iterable[Focus], deleted_ids: Set[int]
) -> dict[int, ReferenceUpdate]:
    updates = {}
    for focus in focuses:
        if focus.id in deleted_ids:
            continue
        prereqs = [
            [focus_id for focus_id in group if focus_id not in deleted_ids]
            for group in focus.prereqs
        ]
        prereqs = [group for group in prereqs if group]
        mutex = [focus_id for focus_id in focus.mutex if focus_id not in deleted_ids]
        if prereqs != focus.prereqs or mutex != focus.mutex:
            updates[focus.id] = (prereqs, mutex)
    return updates


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
