from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from math import floor


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
        self._wide_edges: tuple[int, ...] = ()
        self._focus_order: dict[int, int] = {}
        self._positions: dict[int, tuple[float, float]] = {}
        self._edges: tuple[SceneEdge, ...] = ()
        self._edge_bounds: tuple[tuple[float, float, float, float], ...] = ()

    def rebuild(self, focuses: Mapping[int, object]) -> None:
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

        edge_cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        wide_edges: list[int] = []
        edge_bounds: list[tuple[float, float, float, float]] = []
        for index, edge in enumerate(edges):
            source = focuses[edge.source_id]
            target = focuses[edge.target_id]
            edge_bounds.append(
                (
                    min(source.x, target.x),
                    min(source.y, target.y),
                    max(source.x, target.x),
                    max(source.y, target.y),
                )
            )
            cell_x0, cell_y0, cell_x1, cell_y1 = self._cell_span(
                source.x, source.y, target.x, target.y
            )
            cell_count = (cell_x1 - cell_x0 + 1) * (cell_y1 - cell_y0 + 1)
            if cell_count > 256:
                wide_edges.append(index)
                continue
            for cell_x in range(cell_x0, cell_x1 + 1):
                for cell_y in range(cell_y0, cell_y1 + 1):
                    edge_cells[(cell_x, cell_y)].append(index)

        self._focus_cells = dict(focus_cells)
        self._edge_cells = dict(edge_cells)
        self._wide_edges = tuple(wide_edges)
        self._focus_order = focus_order
        self._positions = positions
        self._edges = tuple(edges)
        self._edge_bounds = tuple(edge_bounds)
        self._signature = self.signature(focuses)
        self._document_revision = getattr(focuses, "revision", None)
        self.revision += 1

    def ensure(self, focuses: Mapping[int, object], *, validate: bool) -> bool:
        document_revision = getattr(focuses, "revision", None)
        changed = document_revision != self._document_revision
        if validate and not changed:
            changed = self.signature(focuses) != self._signature
        if not self.revision or changed:
            self.rebuild(focuses)
            return True
        return False

    def update_focus(self, focuses: Mapping[int, object], focus_id: int) -> None:
        if focus_id not in focuses:
            self.rebuild(focuses)
            return
        self.rebuild(focuses)

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
    def signature(focuses: Mapping[int, object]) -> tuple[object, ...]:
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


__all__ = ["SceneEdge", "SceneIndex"]
