from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from math import floor

from hoi4cm.models.focus import Focus

# ``ensure`` trusts ``FocusDocument.revision``: every mutation path on the
# document bumps it, either through a mutating method or through an explicit
# ``touch()``. Re-deriving ``signature()`` to double-check costs a nested tuple
# per focus per frame, which is the whole document's worth of allocation on a
# frame where nothing changed — so it is opt-in. Set the env var to have the
# canvas cross-check every frame and rebuild on a mismatch; that is how a new
# mutation path that forgot to bump the revision gets caught.
DEBUG_VALIDATE = bool(os.environ.get("HOI4CM_SCENE_INDEX_VALIDATE"))


@dataclass(frozen=True)
class SceneEdge:
    kind: str
    source_id: int
    target_id: int
    cross_tree: bool = False


class SceneIndex:
    def __init__(self, cell_size: int = 8) -> None:
        if cell_size < 1:
            raise ValueError("cell_size must be positive")
        self.cell_size = cell_size
        self.revision = 0
        self._document_revision: int | None = None
        self._signature: tuple[object, ...] = ()
        self._focus_cells: dict[tuple[int, int], list[int]] = {}
        self._edge_cells: dict[tuple[int, int], list[int]] = {}
        self._wide_edges: set[int] = set()
        self._focus_order: dict[int, int] = {}
        self._positions: dict[int, tuple[float, float]] = {}
        self._edges: tuple[SceneEdge, ...] = ()
        self._edge_bounds: list[tuple[float, float, float, float]] = []
        self._edges_by_focus: dict[int, list[int]] = {}

    def rebuild(self, focuses: Mapping[int, Focus]) -> None:
        focus_cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        focus_order: dict[int, int] = {}
        positions: dict[int, tuple[float, float]] = {}
        edges: list[SceneEdge] = []

        for order, (focus_id, focus) in enumerate(focuses.items()):
            focus_order[focus_id] = order
            positions[focus_id] = (focus.x, focus.y)
            focus_cells[self._cell(focus.x, focus.y)].append(focus_id)
            tree_idx = getattr(focus, "tree_idx", 0)
            for group in focus.prereqs:
                for parent_id in group:
                    parent = focuses.get(parent_id)
                    if parent is not None:
                        edges.append(
                            SceneEdge(
                                "arr",
                                parent_id,
                                focus_id,
                                tree_idx != getattr(parent, "tree_idx", 0),
                            )
                        )
            for mutex_id in focus.mutex:
                if mutex_id in focuses and mutex_id > focus_id:
                    edges.append(SceneEdge("mut", focus_id, mutex_id))

        self._focus_cells = dict(focus_cells)
        self._focus_order = focus_order
        self._positions = positions
        self._edges = tuple(edges)
        self._edge_bounds = [(0.0, 0.0, 0.0, 0.0)] * len(edges)
        self._edge_cells = {}
        self._wide_edges = set()
        edges_by_focus: dict[int, list[int]] = defaultdict(list)
        for index, edge in enumerate(edges):
            edges_by_focus[edge.source_id].append(index)
            edges_by_focus[edge.target_id].append(index)
            self._place_edge(index, edge, focuses)
        self._edges_by_focus = dict(edges_by_focus)
        self._signature = self.signature(focuses)
        self._document_revision = getattr(focuses, "revision", None)
        self.revision += 1

    def _place_edge(
        self, index: int, edge: SceneEdge, focuses: Mapping[int, Focus]
    ) -> None:
        source = focuses[edge.source_id]
        target = focuses[edge.target_id]
        self._edge_bounds[index] = (
            min(source.x, target.x),
            min(source.y, target.y),
            max(source.x, target.x),
            max(source.y, target.y),
        )
        cell_x0, cell_y0, cell_x1, cell_y1 = self._cell_span(
            source.x, source.y, target.x, target.y
        )
        cell_count = (cell_x1 - cell_x0 + 1) * (cell_y1 - cell_y0 + 1)
        if cell_count > 256:
            self._wide_edges.add(index)
            return
        for cell_x in range(cell_x0, cell_x1 + 1):
            for cell_y in range(cell_y0, cell_y1 + 1):
                self._edge_cells.setdefault((cell_x, cell_y), []).append(index)

    def _unplace_edge(self, index: int) -> None:
        if index in self._wide_edges:
            self._wide_edges.discard(index)
            return
        min_x, min_y, max_x, max_y = self._edge_bounds[index]
        cell_x0, cell_y0, cell_x1, cell_y1 = self._cell_span(min_x, min_y, max_x, max_y)
        for cell_x in range(cell_x0, cell_x1 + 1):
            for cell_y in range(cell_y0, cell_y1 + 1):
                bucket = self._edge_cells.get((cell_x, cell_y))
                if not bucket:
                    continue
                remaining = [i for i in bucket if i != index]
                if remaining:
                    self._edge_cells[(cell_x, cell_y)] = remaining
                else:
                    del self._edge_cells[(cell_x, cell_y)]

    def ensure(self, focuses: Mapping[int, Focus], *, validate: bool = False) -> bool:
        document_revision = getattr(focuses, "revision", None)
        changed = document_revision != self._document_revision
        if validate and not changed:
            changed = self.signature(focuses) != self._signature
        if not self.revision or changed:
            self.rebuild(focuses)
            return True
        return False

    def update_focus(self, focuses: Mapping[int, Focus], focus_id: int) -> None:
        """Apply a single focus's geometry move without a full rebuild.

        Caller contract: only *focus_id*'s x/y changed since the last rebuild
        (the drag hot path). Anything structural (add/remove/link, another
        focus moving) must go back through ``rebuild``/``ensure``.
        """
        if (
            not self.revision
            or focus_id not in focuses
            or focus_id not in self._positions
        ):
            self.rebuild(focuses)
            return
        focus = focuses[focus_id]
        new_pos = (focus.x, focus.y)
        old_pos = self._positions[focus_id]
        if old_pos != new_pos:
            old_cell = self._cell(*old_pos)
            new_cell = self._cell(*new_pos)
            if old_cell != new_cell:
                bucket = self._focus_cells.get(old_cell)
                if bucket is not None:
                    remaining = [fid for fid in bucket if fid != focus_id]
                    if remaining:
                        self._focus_cells[old_cell] = remaining
                    else:
                        del self._focus_cells[old_cell]
                self._focus_cells.setdefault(new_cell, []).append(focus_id)
            self._positions[focus_id] = new_pos
            for index in self._edges_by_focus.get(focus_id, ()):
                self._unplace_edge(index)
                self._place_edge(index, self._edges[index], focuses)
        # The stale _signature is left as-is: a later validate=True ensure()
        # will rebuild once and refresh it, which is harmless.
        self._document_revision = getattr(focuses, "revision", None)
        self.revision += 1

    def query_focus_ids(self, rect: tuple[float, float, float, float]) -> list[int]:
        ids: set[int] = set()
        for cell in self._cells_for_rect(*rect):
            ids.update(self._focus_cells.get(cell, ()))
        x0, y0, x1, y1 = rect
        return sorted(
            (
                focus_id
                for focus_id in ids
                if x0 <= self._positions[focus_id][0] <= x1
                and y0 <= self._positions[focus_id][1] <= y1
            ),
            key=self._focus_order.__getitem__,
        )

    def query_edges(self, rect: tuple[float, float, float, float]) -> list[SceneEdge]:
        indexes = set(self._wide_edges)
        for cell in self._cells_for_rect(*rect):
            indexes.update(self._edge_cells.get(cell, ()))
        x0, y0, x1, y1 = rect
        return [
            self._edges[index]
            for index in sorted(indexes)
            if self._edge_bounds[index][0] <= x1
            and self._edge_bounds[index][2] >= x0
            and self._edge_bounds[index][1] <= y1
            and self._edge_bounds[index][3] >= y0
        ]

    def all_edges(self) -> tuple[SceneEdge, ...]:
        return self._edges

    @staticmethod
    def signature(focuses: Mapping[int, Focus]) -> tuple[object, ...]:
        """Full geometry/topology fingerprint — O(F), for ``DEBUG_VALIDATE``.

        Not on the render path: ``ensure`` uses the document revision.
        """
        return tuple(
            (
                focus_id,
                focus.x,
                focus.y,
                getattr(focus, "tree_idx", 0),
                tuple(tuple(group) for group in focus.prereqs),
                tuple(focus.mutex),
            )
            for focus_id, focus in focuses.items()
        )

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return floor(x / self.cell_size), floor(y / self.cell_size)

    def _cells_for_rect(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> list[tuple[int, int]]:
        cell_x0, cell_y0, cell_x1, cell_y1 = self._cell_span(x0, y0, x1, y1)
        return [
            (cell_x, cell_y)
            for cell_x in range(cell_x0, cell_x1 + 1)
            for cell_y in range(cell_y0, cell_y1 + 1)
        ]

    def _cell_span(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> tuple[int, int, int, int]:
        low_x, high_x = sorted((x0, x1))
        low_y, high_y = sorted((y0, y1))
        cell_x0, cell_y0 = self._cell(low_x, low_y)
        cell_x1, cell_y1 = self._cell(high_x, high_y)
        return cell_x0, cell_y0, cell_x1, cell_y1


__all__ = ["DEBUG_VALIDATE", "SceneEdge", "SceneIndex"]
