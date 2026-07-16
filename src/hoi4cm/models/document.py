from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Any

from .focus import Focus


@dataclass
class TreeMetadata:
    tree_id: str = "TAG_focus_tree"
    country_tag: str = ""
    country_name: str = ""
    country_raw: str = ""
    focus_prefix: str = ""
    cfp_x: int | None = None
    cfp_y: int | None = None
    shared_focuses: list[str] = field(default_factory=list)
    joint_focuses: list[str] = field(default_factory=list)


@dataclass
class TreeDocument:
    metadata: TreeMetadata = field(default_factory=TreeMetadata)
    tree_type: str = "main"
    file_path: str = ""
    had_wrapper: bool = True
    focus_ids: set[int] = field(default_factory=set)
    extras: dict[str, Any] = field(default_factory=dict)


class FocusDocument(MutableMapping[int, Focus]):
    """Focus ownership boundary with derived indexes and dict compatibility."""

    def __init__(self, focuses: Iterable[Focus] = ()) -> None:
        self._focuses: dict[int, Focus] = {}
        self.geometry_revision = 0
        self.names: dict[str, tuple[int, ...]] = {}
        self.first_by_name: dict[str, int] = {}
        self.last_by_name: dict[str, int] = {}
        self.tree_membership: dict[int, set[int]] = {}
        self.occupied_positions: dict[tuple[int, int], set[int]] = {}
        self.reverse_prerequisites: dict[int, set[int]] = {}
        self.reverse_mutex: dict[int, set[int]] = {}
        self.load(focuses)

    @property
    def revision(self) -> int:
        return self.geometry_revision

    @property
    def by_id(self) -> MutableMapping[int, Focus]:
        return self._focuses

    def __getitem__(self, focus_id: int) -> Focus:
        return self._focuses[focus_id]

    def __setitem__(self, focus_id: int, focus: Focus) -> None:
        if focus_id != focus.id:
            raise ValueError("mapping key must match focus.id")
        self.add(focus, replace=focus_id in self._focuses)

    def __delitem__(self, focus_id: int) -> None:
        self.delete_many((focus_id,), clean_references=False)

    def __iter__(self) -> Iterator[int]:
        return iter(self._focuses)

    def __len__(self) -> int:
        return len(self._focuses)

    def clear(self) -> None:
        if self._focuses:
            self._focuses.clear()
            self._changed()
        self.rebuild_indexes()

    def add(self, focus: Focus, *, replace: bool = False) -> Focus:
        if focus.id in self._focuses and not replace:
            raise KeyError(f"focus id already exists: {focus.id}")
        self._focuses[focus.id] = focus
        self._changed()
        self.rebuild_indexes()
        return focus

    def extend(self, focuses: Iterable[Focus], *, replace: bool = False) -> None:
        additions = list(focuses)
        addition_ids = [focus.id for focus in additions]
        if len(addition_ids) != len(set(addition_ids)):
            raise ValueError("focus batch contains duplicate ids")
        if not replace:
            existing = set(addition_ids) & self._focuses.keys()
            if existing:
                raise KeyError(f"focus id already exists: {min(existing)}")
        if not additions:
            return
        self._focuses.update((focus.id, focus) for focus in additions)
        self._changed()
        self.rebuild_indexes()

    def move(
        self, focus_id: int, x: int, y: int, *, allow_occupied: bool = False
    ) -> bool:
        focus = self._focuses[focus_id]
        occupants = self.occupied_positions.get((x, y), set()) - {focus_id}
        if occupants and not allow_occupied:
            return False
        if (focus.x, focus.y) == (x, y):
            return True
        focus.x, focus.y = x, y
        self._changed()
        self.rebuild_indexes()
        return True

    def link_prerequisite(
        self, child_id: int, parent_ids: Iterable[int], *, mode: str = "or"
    ) -> None:
        parents = list(parent_ids)
        if not parents:
            return
        child = self._focuses[child_id]
        if mode == "or":
            child.prereqs.append(parents)
        elif mode == "and":
            child.prereqs.extend([parent_id] for parent_id in parents)
        else:
            raise ValueError("mode must be 'or' or 'and'")
        self._changed()
        self.rebuild_indexes()

    def link(
        self,
        kind: str,
        source_id: int,
        target_ids: Iterable[int],
        *,
        mode: str = "or",
    ) -> None:
        targets = list(target_ids)
        if kind == "prerequisite":
            self.link_prerequisite(source_id, targets, mode=mode)
            return
        if kind == "mutex":
            for target_id in targets:
                self.link_mutex(source_id, target_id)
            return
        raise ValueError("kind must be 'prerequisite' or 'mutex'")

    def unlink_prerequisite_group(self, child_id: int, group_index: int) -> None:
        self._focuses[child_id].prereqs.pop(group_index)
        self._changed()
        self.rebuild_indexes()

    def link_mutex(self, left_id: int, right_id: int) -> None:
        left = self._focuses[left_id]
        right = self._focuses[right_id]
        if right_id not in left.mutex:
            left.mutex.append(right_id)
        if left_id not in right.mutex:
            right.mutex.append(left_id)
        self._changed()
        self.rebuild_indexes()

    def unlink_mutex(self, left_id: int, right_id: int) -> None:
        left = self._focuses[left_id]
        right = self._focuses.get(right_id)
        left.mutex = [focus_id for focus_id in left.mutex if focus_id != right_id]
        if right is not None:
            right.mutex = [focus_id for focus_id in right.mutex if focus_id != left_id]
        self._changed()
        self.rebuild_indexes()

    def delete_many(
        self, focus_ids: Iterable[int], *, clean_references: bool = True
    ) -> set[int]:
        deleted = set(focus_ids) & self._focuses.keys()
        if not deleted:
            return set()
        if clean_references:
            for focus in self._focuses.values():
                if focus.id in deleted:
                    continue
                focus.prereqs = [
                    [parent for parent in group if parent not in deleted]
                    for group in focus.prereqs
                ]
                focus.prereqs = [group for group in focus.prereqs if group]
                focus.mutex = [other for other in focus.mutex if other not in deleted]
        for focus_id in deleted:
            del self._focuses[focus_id]
        self._changed()
        self.rebuild_indexes()
        return deleted

    def replace(self, focus: Focus) -> Focus:
        return self.add(focus, replace=True)

    def load(self, focuses: Iterable[Focus] | Mapping[int, Focus]) -> None:
        if isinstance(focuses, Mapping):
            focuses = focuses.values()
        loaded = {focus.id: focus for focus in focuses}
        changed = loaded != self._focuses
        self._focuses = loaded
        if changed:
            self._changed()
        self.rebuild_indexes()

    def rename_prefix(self, old: str, new: str) -> int:
        if not old:
            raise ValueError("old prefix cannot be empty")
        renamed = 0
        for focus in self._focuses.values():
            if focus.name.startswith(old):
                focus.name = new + focus.name[len(old) :]
                renamed += 1
        if renamed:
            self.rebuild_indexes()
        return renamed

    def set_tree(self, focus_id: int, tree_idx: int) -> None:
        focus = self._focuses[focus_id]
        if getattr(focus, "tree_idx", 0) == tree_idx:
            return
        focus.tree_idx = tree_idx
        self._changed()
        self.rebuild_indexes()

    def set_trees(self, tree_by_focus_id: Mapping[int, int]) -> None:
        changed = False
        for focus_id, tree_idx in tree_by_focus_id.items():
            focus = self._focuses[focus_id]
            if getattr(focus, "tree_idx", 0) != tree_idx:
                focus.tree_idx = tree_idx
                changed = True
        if changed:
            self._changed()
            self.rebuild_indexes()

    def find_by_name(self, name: str, *, policy: str = "first") -> Focus | None:
        index = self.first_by_name if policy == "first" else self.last_by_name
        if policy not in {"first", "last"}:
            raise ValueError("policy must be 'first' or 'last'")
        focus_id = index.get(name)
        return self._focuses.get(focus_id) if focus_id is not None else None

    def validate_indexes(self, *, rebuild: bool = False) -> bool:
        expected = self._build_indexes()
        actual = self._index_tuple()
        valid = actual == expected
        if rebuild and not valid:
            self._assign_indexes(expected)
            self._changed()
        return valid

    def rebuild_indexes(self) -> None:
        self._assign_indexes(self._build_indexes())

    def touch(self) -> None:
        """Mark legacy direct field mutations and rebuild derived indexes."""
        self._changed()
        self.rebuild_indexes()

    def _build_indexes(self) -> tuple[dict[Any, Any], ...]:
        names: dict[str, list[int]] = defaultdict(list)
        trees: dict[int, set[int]] = defaultdict(set)
        positions: dict[tuple[int, int], set[int]] = defaultdict(set)
        reverse_prerequisites: dict[int, set[int]] = defaultdict(set)
        reverse_mutex: dict[int, set[int]] = defaultdict(set)
        for focus_id, focus in self._focuses.items():
            names[focus.name].append(focus_id)
            trees[getattr(focus, "tree_idx", 0)].add(focus_id)
            positions[(focus.x, focus.y)].add(focus_id)
            for group in focus.prereqs:
                for parent_id in group:
                    reverse_prerequisites[parent_id].add(focus_id)
            for other_id in focus.mutex:
                reverse_mutex[other_id].add(focus_id)
        frozen_names = {name: tuple(ids) for name, ids in names.items()}
        return (
            frozen_names,
            {name: ids[0] for name, ids in frozen_names.items()},
            {name: ids[-1] for name, ids in frozen_names.items()},
            dict(trees),
            dict(positions),
            dict(reverse_prerequisites),
            dict(reverse_mutex),
        )

    def _index_tuple(self) -> tuple[dict[Any, Any], ...]:
        return (
            self.names,
            self.first_by_name,
            self.last_by_name,
            self.tree_membership,
            self.occupied_positions,
            self.reverse_prerequisites,
            self.reverse_mutex,
        )

    def _assign_indexes(self, indexes: tuple[dict[Any, Any], ...]) -> None:
        (
            self.names,
            self.first_by_name,
            self.last_by_name,
            self.tree_membership,
            self.occupied_positions,
            self.reverse_prerequisites,
            self.reverse_mutex,
        ) = indexes

    def _changed(self) -> None:
        self.geometry_revision += 1


@dataclass
class EditorWorkspace:
    focuses: FocusDocument = field(default_factory=FocusDocument)
    main_tree: TreeDocument = field(default_factory=TreeDocument)
    extra_trees: list[TreeDocument] = field(default_factory=list)
    canvas_min: tuple[int, int] = (0, 0)
    canvas_max: tuple[int, int] = (9, 9)
    default_focus_prefix: str = ""
    workspace_extras: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)


__all__ = ["EditorWorkspace", "FocusDocument", "TreeDocument", "TreeMetadata"]
