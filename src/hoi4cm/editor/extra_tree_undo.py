"""Small, App-owned side history for loaded extra-tree metadata."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hoi4cm.core.undo import UndoStack


@dataclass(frozen=True, slots=True)
class ExtraTreeState:
    """Shallow snapshot of the registry needed to describe extra trees."""

    trees: tuple[dict[str, Any], ...]
    shared_focuses: tuple[str, ...]
    joint_focuses: tuple[str, ...]

    @classmethod
    def capture(
        cls,
        trees: Sequence[Mapping[str, Any]],
        shared_focuses: Sequence[str],
        joint_focuses: Sequence[str],
    ) -> ExtraTreeState:
        records = []
        for tree in trees:
            record = dict(tree)
            record["focus_ids"] = set(tree.get("focus_ids", ()))
            record["shared_focuses"] = list(tree.get("shared_focuses", ()))
            record["joint_focuses"] = list(tree.get("joint_focuses", ()))
            records.append(record)
        return cls(tuple(records), tuple(shared_focuses), tuple(joint_focuses))


class ExtraTreeUndoHistory:
    """Metadata snapshots aligned with committed focus undo entries.

    Ordinary entries carry a ``None`` marker, so they incur no tree snapshot
    cost. The caller supplies the current state lazily when undoing or redoing
    a tree action. ``maxlen`` must match the corresponding focus undo stack.
    """

    def __init__(self, maxlen: int = 60) -> None:
        self._undo: deque[tuple[str, ExtraTreeState | None]] = deque(maxlen=maxlen)
        self._redo: deque[tuple[str, ExtraTreeState | None]] = deque(maxlen=maxlen)

    def __len__(self) -> int:
        return len(self._undo)

    def is_aligned(self, undo_depth: int) -> bool:
        return len(self._undo) == undo_depth

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def push(self, label: str, state: ExtraTreeState | None = None) -> None:
        self._undo.append((label, state))
        self._redo.clear()

    @contextmanager
    def track(
        self, stack: UndoStack, label: str, state: ExtraTreeState | None = None
    ) -> Iterator[None]:
        """Mirror one push/record, including commits made while unwinding errors.

        Every commit appends a new immutable entry tuple. Comparing its identity
        detects commits even at capacity, while dropped runs and no-op records
        leave both the metadata history and its redo trail alone.
        """
        if not self.is_aligned(len(stack)):
            self.clear()
        previous = stack._stack[-1] if stack else None
        try:
            yield
        finally:
            current = stack._stack[-1] if stack else None
            if current is not None and current is not previous:
                self.push(label, state)

    def undo(
        self,
        label: str,
        current_state: Callable[[], ExtraTreeState],
        *,
        aligned: bool,
    ) -> ExtraTreeState | None:
        if not aligned or not self._undo:
            self.clear()
            return None
        entry_label, state = self._undo.pop()
        if entry_label != label:
            self.clear()
            return None
        self._redo.append((label, current_state() if state is not None else None))
        return state

    def redo(
        self,
        label: str,
        current_state: Callable[[], ExtraTreeState],
        *,
        aligned: bool,
    ) -> ExtraTreeState | None:
        if not aligned or not self._redo:
            if not aligned:
                self.clear()
            return None
        entry_label, state = self._redo.pop()
        if entry_label != label:
            self.clear()
            return None
        self._undo.append((label, current_state() if state is not None else None))
        return state
