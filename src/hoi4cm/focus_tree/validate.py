"""Pure focus-tree validator with caller-supplied optional lookup data."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass
from typing import Literal, NamedTuple

from hoi4cm.core.paths import read_file
from hoi4cm.models import Focus

Severity = Literal["error", "warning", "info"]
DEFAULT_GFX = "GFX_goal_generic_political_pressure"
MAX_ISSUES = 300
_KEY_RE = re.compile(r"\s+(\S+?)(?::\d+)?\s*[=:]?\s*\"")

SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    focus_id: int | None
    focus_name: str | None
    message: str
    field: str | None = None

    def sort_key(self):
        return (SEVERITY_RANK.get(self.severity, 99), self.focus_name or "", self.code)


def _extract_loc_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for line in text.splitlines():
        m = _KEY_RE.match(line)
        if m:
            keys.add(m.group(1))
    return keys


def collect_loc_keys_from_text(text: str | None) -> set[str] | None:
    if text is None:
        return None
    return _extract_loc_keys(text)


def collect_loc_keys_from_file(path: str | None) -> set[str] | None:
    """Read localisation keys, returning ``None`` when the file is unavailable."""
    if not path or not os.path.isfile(path):
        return None
    try:
        return collect_loc_keys_from_text(read_file(path))
    except Exception:
        return None


def validate_document(
    doc: Mapping[int, Focus | _ValidationFocus],
    *,
    sprites: Mapping[str, str] | None = None,
    loc_keys: set[str] | None = None,
    include_default_icon_warning: bool = True,
    max_issues: int = MAX_ISSUES,
) -> list[Issue]:
    """Validate a focus document.

    doc: FocusDocument, ValidationSnapshot, or plain mapping id->Focus.
    sprites: MOD.sprites dict (gfx_name -> path) or None to skip GFX check.
    loc_keys: set of localisation keys present in the .yml or None to skip.
    max_issues: cap on the returned list; excess issues are dropped and
        replaced with one trailing "issues_truncated" info issue.
    """
    issues: list[Issue] = []
    if not doc:
        return issues

    id_set = set(doc.keys())
    # name -> list of ids
    name_to_ids: dict[str, list[int]] = defaultdict(list)
    for fid, focus in doc.items():
        name_to_ids[focus.name].append(fid)

    # duplicate names (game IDs)
    for name, ids in name_to_ids.items():
        if len(ids) > 1:
            issues.append(
                Issue(
                    "error",
                    "duplicate_name",
                    ids[0],
                    name,
                    (
                        f"duplicate focus name '{name}' used by "
                        f"{len(ids)} focuses (ids {sorted(ids)})"
                    ),
                    field="name",
                )
            )

    # occupied positions
    occupied: Mapping[tuple[int, int], Collection[int]] | None = getattr(
        doc, "occupied_positions", None
    )
    if occupied is None:
        positions: defaultdict[tuple[int, int], set[int]] = defaultdict(set)
        for fid, focus in doc.items():
            positions[(focus.x, focus.y)].add(fid)
        occupied = positions

    for (x, y), occupants in occupied.items():
        if len(occupants) <= 1:
            continue
        # focuses from different loaded trees legitimately share coordinates
        by_tree: dict[int, list[int]] = defaultdict(list)
        for fid in occupants:
            by_tree[getattr(doc[fid], "tree_idx", 0)].append(fid)
        for tree_occupants in by_tree.values():
            if len(tree_occupants) <= 1:
                continue
            sorted_ids = sorted(tree_occupants)
            names = [doc[i].name for i in sorted_ids]
            issues.append(
                Issue(
                    "error",
                    "position_collision",
                    sorted_ids[0],
                    doc[sorted_ids[0]].name,
                    (
                        f"position collision at x={x} y={y}: "
                        f"{', '.join(names)} (ids {sorted_ids}) share the same cell"
                    ),
                    field="x",
                )
            )

    # name lookup for relative_position_id
    name_to_one_id = {name: ids[0] for name, ids in name_to_ids.items()}

    for fid, focus in doc.items():
        # broken prereqs
        for grp_idx, grp in enumerate(getattr(focus, "prereqs", [])):
            for pid in grp:
                if pid not in id_set:
                    issues.append(
                        Issue(
                            "error",
                            "broken_prereq",
                            fid,
                            focus.name,
                            (
                                f"[{focus.name}] broken prereq "
                                f"→ id:{pid} (group {grp_idx})"
                            ),
                            field="prereqs",
                        )
                    )
        # broken mutex
        for mid in getattr(focus, "mutex", []):
            if mid not in id_set:
                issues.append(
                    Issue(
                        "error",
                        "broken_mutex",
                        fid,
                        focus.name,
                        f"[{focus.name}] broken mutex → id:{mid}",
                        field="mutex",
                    )
                )
        # relative_position_id
        rel = getattr(focus, "relative_position_id", None)
        if rel:
            if rel not in name_to_one_id:
                issues.append(
                    Issue(
                        "error",
                        "relative_position_unresolved",
                        fid,
                        focus.name,
                        (
                            f"[{focus.name}] relative_position_id "
                            f"'{rel}' does not match any focus"
                        ),
                        field="relative_position_id",
                    )
                )
        # empty effects
        if not getattr(focus, "effects", []):
            issues.append(
                Issue(
                    "warning",
                    "empty_effects",
                    fid,
                    focus.name,
                    f"[{focus.name}] no effects in completion_reward",
                    field="effects",
                )
            )
        # default/missing icon
        gfx = getattr(focus, "gfx", "")
        if include_default_icon_warning and (not gfx or gfx == DEFAULT_GFX):
            issues.append(
                Issue(
                    "warning",
                    "default_icon",
                    fid,
                    focus.name,
                    f"[{focus.name}] using default/missing icon GFX",
                    field="gfx",
                )
            )
        # GFX not in sprites
        if sprites is not None and gfx and gfx not in sprites:
            # don't double-report default as missing if already warned; still
            # worth surfacing for custom GFX. If include_default_icon_warning,
            # default already emitted above; skip duplicate missing for default.
            if gfx != DEFAULT_GFX or not include_default_icon_warning:
                issues.append(
                    Issue(
                        "warning",
                        "gfx_missing",
                        fid,
                        focus.name,
                        f"[{focus.name}] icon '{gfx}' not found in loaded sprites",
                        field="gfx",
                    )
                )
        # missing loc keys
        if loc_keys is not None:
            if focus.name not in loc_keys:
                issues.append(
                    Issue(
                        "warning",
                        "loc_missing",
                        fid,
                        focus.name,
                        f"[{focus.name}] missing localisation key '{focus.name}'",
                        field="name",
                    )
                )
            desc_key = f"{focus.name}_desc"
            if desc_key not in loc_keys:
                issues.append(
                    Issue(
                        "warning",
                        "loc_missing_desc",
                        fid,
                        focus.name,
                        f"[{focus.name}] missing localisation key '{desc_key}'",
                        field="desc",
                    )
                )

    # prerequisite cycles
    # build adjacency: child -> parents that exist
    adjacency: dict[int, list[int]] = {}
    for fid, focus in doc.items():
        parents: list[int] = []
        for grp in getattr(focus, "prereqs", []):
            for pid in grp:
                if pid in id_set:
                    parents.append(pid)
        adjacency[fid] = parents

    # DFS cycle detection
    visited: dict[int, int] = {}  # 0 unvisited, 1 visiting, 2 done
    stack: list[int] = []
    cycles_reported: set[tuple[int, ...]] = set()

    def dfs(node: int):
        visited[node] = 1
        stack.append(node)
        for parent in adjacency.get(node, []):
            state = visited.get(parent, 0)
            if state == 1:
                # found cycle
                idx = stack.index(parent)
                cycle = tuple(stack[idx:] + [parent])
                # normalize to sorted tuple for dedup
                key = tuple(sorted(cycle))
                if key not in cycles_reported:
                    cycles_reported.add(key)
                    names = " → ".join(doc[c].name for c in stack[idx:] + [parent])
                    issues.append(
                        Issue(
                            "error",
                            "prereq_cycle",
                            node,
                            doc[node].name,
                            f"prerequisite cycle: {names}",
                            field="prereqs",
                        )
                    )
            elif state == 0:
                dfs(parent)
        stack.pop()
        visited[node] = 2

    for nid in list(id_set):
        if visited.get(nid, 0) == 0:
            dfs(nid)

    issues.sort(key=lambda issue: issue.sort_key())
    if len(issues) > max_issues:
        hidden = len(issues) - max_issues
        issues = issues[:max_issues]
        issues.append(
            Issue(
                "info",
                "issues_truncated",
                None,
                None,
                f"{hidden} more issue(s) not shown (showing first {max_issues})",
            )
        )
    return issues


def worst_severity_per_focus(issues: list[Issue]) -> dict[int, Severity]:
    """Return worst severity per focus_id among issues that have a focus_id."""
    worst: dict[int, Severity] = {}
    for issue in issues:
        if issue.focus_id is None:
            continue
        cur = worst.get(issue.focus_id)
        if cur is None or SEVERITY_RANK[issue.severity] < SEVERITY_RANK[cur]:
            worst[issue.focus_id] = issue.severity
    return worst


class _ValidationFocus(NamedTuple):
    name: str
    x: int
    y: int
    tree_idx: int
    prereqs: tuple[tuple[int, ...], ...]
    mutex: tuple[int, ...]
    relative_position_id: str | None
    effects: bool
    gfx: str


@dataclass(frozen=True)
class ValidationSnapshot(Mapping[int, _ValidationFocus]):
    """Detached focus mapping and occupied-position index for validation."""

    focuses: Mapping[int, _ValidationFocus]
    occupied_positions: Mapping[tuple[int, int], Collection[int]] | None = None

    def __getitem__(self, focus_id: int) -> _ValidationFocus:
        return self.focuses[focus_id]

    def __iter__(self) -> Iterator[int]:
        return iter(self.focuses)

    def __len__(self) -> int:
        return len(self.focuses)


def _detached_focus(focus: Focus) -> _ValidationFocus:
    prereqs: tuple[tuple[int, ...], ...] = ()
    if focus.prereqs:
        prereqs = tuple(tuple(group) for group in focus.prereqs)
    mutex = tuple(focus.mutex) if focus.mutex else ()
    return _ValidationFocus(
        focus.name,
        focus.x,
        focus.y,
        focus.tree_idx,
        prereqs,
        mutex,
        focus.relative_position_id,
        bool(focus.effects),
        focus.gfx,
    )


def capture_validation_snapshot(document: Mapping[int, Focus]) -> ValidationSnapshot:
    """Copy validator inputs and the document's position index."""
    by_id = getattr(document, "by_id", document)
    focused = {focus_id: _detached_focus(focus) for focus_id, focus in by_id.items()}
    occupied = getattr(document, "occupied_positions", None)
    if occupied is not None:
        occupied = {
            cell: frozenset(occupants)
            for cell, occupants in occupied.items()
            if len(occupants) > 1
        }
    return ValidationSnapshot(focused, occupied)


__all__ = [
    "DEFAULT_GFX",
    "MAX_ISSUES",
    "Issue",
    "Severity",
    "ValidationSnapshot",
    "capture_validation_snapshot",
    "collect_loc_keys_from_file",
    "collect_loc_keys_from_text",
    "validate_document",
    "worst_severity_per_focus",
]
