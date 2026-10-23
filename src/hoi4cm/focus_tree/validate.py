"""Pure focus-tree validator with caller-supplied optional lookup data."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Collection, Iterator, Mapping
from dataclasses import dataclass
from typing import Literal, NamedTuple

from hoi4cm.core.i18n import tr
from hoi4cm.core.paths import read_file_with_encoding
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
        return _sort_key(self.severity, self.focus_name, self.code)


def _sort_key(severity: str, focus_name: str | None, code: str):
    return (SEVERITY_RANK.get(severity, 99), focus_name or "", code)


class _Pending(NamedTuple):
    """An issue whose message is rendered only if it survives the cap.

    A document can raise far more issues than ``max_issues``, and translating
    every message is the slowest part of building them. ``message`` is one of
    the ``_msg_*`` functions below and ``args`` are its arguments.
    """

    severity: Severity
    code: str
    focus_id: int | None
    focus_name: str | None
    message: Callable[..., str]
    args: tuple[object, ...]
    field: str | None = None

    def sort_key(self):
        return _sort_key(self.severity, self.focus_name, self.code)

    def render(self) -> Issue:
        return Issue(
            self.severity,
            self.code,
            self.focus_id,
            self.focus_name,
            self.message(*self.args),
            self.field,
        )


def _msg_duplicate_name(name: str, ids: list[int]) -> str:
    return tr(
        "validation.issue.duplicate_name",
        "duplicate focus name '{name}' used by {count} focuses (ids {ids})",
        name=name,
        count=len(ids),
        ids=sorted(ids),
    )


def _msg_position_collision(x: int, y: int, names: list[str], ids: list[int]) -> str:
    return tr(
        "validation.issue.position_collision",
        "position collision at x={x} y={y}: {names} (ids {ids}) share the same cell",
        x=x,
        y=y,
        names=", ".join(names),
        ids=ids,
    )


def _msg_broken_prereq(name: str, pid: int, group: int) -> str:
    return tr(
        "validation.issue.broken_prereq",
        "[{name}] broken prereq → id:{id} (group {group})",
        name=name,
        id=pid,
        group=group,
    )


def _msg_broken_mutex(name: str, mid: int) -> str:
    return tr(
        "validation.issue.broken_mutex",
        "[{name}] broken mutex → id:{id}",
        name=name,
        id=mid,
    )


def _msg_relative_position_unresolved(name: str, target: str) -> str:
    return tr(
        "validation.issue.relative_position_unresolved",
        "[{name}] relative_position_id '{target}' does not match any focus",
        name=name,
        target=target,
    )


def _msg_empty_effects(name: str) -> str:
    return tr(
        "validation.issue.empty_effects",
        "[{name}] no effects in completion_reward",
        name=name,
    )


def _msg_default_icon(name: str) -> str:
    return tr(
        "validation.issue.default_icon",
        "[{name}] using default/missing icon GFX",
        name=name,
    )


def _msg_gfx_missing(name: str, gfx: str) -> str:
    return tr(
        "validation.issue.gfx_missing",
        "[{name}] icon '{gfx}' not found in loaded sprites",
        name=name,
        gfx=gfx,
    )


def _msg_loc_missing(name: str, loc_key: str) -> str:
    return tr(
        "validation.issue.loc_missing",
        "[{name}] missing localisation key '{loc_key}'",
        name=name,
        loc_key=loc_key,
    )


def _msg_prereq_cycle(names: str) -> str:
    return tr(
        "validation.issue.prereq_cycle", "prerequisite cycle: {names}", names=names
    )


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
    if not path:
        return None
    text, encoding = read_file_with_encoding(path)
    return collect_loc_keys_from_text(text) if encoding is not None else None


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
    pending: list[_Pending] = []
    if not doc:
        return []

    id_set = set(doc.keys())
    # name -> list of ids
    name_to_ids: dict[str, list[int]] = defaultdict(list)
    for fid, focus in doc.items():
        name_to_ids[focus.name].append(fid)

    # duplicate names (game IDs)
    for name, ids in name_to_ids.items():
        if len(ids) > 1:
            pending.append(
                _Pending(
                    "error",
                    "duplicate_name",
                    ids[0],
                    name,
                    _msg_duplicate_name,
                    (name, ids),
                    "name",
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
            pending.append(
                _Pending(
                    "error",
                    "position_collision",
                    sorted_ids[0],
                    doc[sorted_ids[0]].name,
                    _msg_position_collision,
                    (x, y, names, sorted_ids),
                    "x",
                )
            )

    # name lookup for relative_position_id
    name_to_one_id = {name: ids[0] for name, ids in name_to_ids.items()}

    for fid, focus in doc.items():
        # broken prereqs
        for grp_idx, grp in enumerate(getattr(focus, "prereqs", [])):
            for pid in grp:
                if pid not in id_set:
                    pending.append(
                        _Pending(
                            "error",
                            "broken_prereq",
                            fid,
                            focus.name,
                            _msg_broken_prereq,
                            (focus.name, pid, grp_idx),
                            "prereqs",
                        )
                    )
        # broken mutex
        for mid in getattr(focus, "mutex", []):
            if mid not in id_set:
                pending.append(
                    _Pending(
                        "error",
                        "broken_mutex",
                        fid,
                        focus.name,
                        _msg_broken_mutex,
                        (focus.name, mid),
                        "mutex",
                    )
                )
        # relative_position_id
        rel = getattr(focus, "relative_position_id", None)
        if rel:
            if rel not in name_to_one_id:
                pending.append(
                    _Pending(
                        "error",
                        "relative_position_unresolved",
                        fid,
                        focus.name,
                        _msg_relative_position_unresolved,
                        (focus.name, rel),
                        "relative_position_id",
                    )
                )
        # empty effects
        if not getattr(focus, "effects", []):
            pending.append(
                _Pending(
                    "warning",
                    "empty_effects",
                    fid,
                    focus.name,
                    _msg_empty_effects,
                    (focus.name,),
                    "effects",
                )
            )
        # default/missing icon
        gfx = getattr(focus, "gfx", "")
        if include_default_icon_warning and (not gfx or gfx == DEFAULT_GFX):
            pending.append(
                _Pending(
                    "warning",
                    "default_icon",
                    fid,
                    focus.name,
                    _msg_default_icon,
                    (focus.name,),
                    "gfx",
                )
            )
        # GFX not in sprites
        if sprites is not None and gfx and gfx not in sprites:
            # don't double-report default as missing if already warned; still
            # worth surfacing for custom GFX. If include_default_icon_warning,
            # default already emitted above; skip duplicate missing for default.
            if gfx != DEFAULT_GFX or not include_default_icon_warning:
                pending.append(
                    _Pending(
                        "warning",
                        "gfx_missing",
                        fid,
                        focus.name,
                        _msg_gfx_missing,
                        (focus.name, gfx),
                        "gfx",
                    )
                )
        # missing loc keys
        if loc_keys is not None:
            if focus.name not in loc_keys:
                pending.append(
                    _Pending(
                        "warning",
                        "loc_missing",
                        fid,
                        focus.name,
                        _msg_loc_missing,
                        (focus.name, focus.name),
                        "name",
                    )
                )
            desc_key = f"{focus.name}_desc"
            if desc_key not in loc_keys:
                pending.append(
                    _Pending(
                        "warning",
                        "loc_missing_desc",
                        fid,
                        focus.name,
                        _msg_loc_missing,
                        (focus.name, desc_key),
                        "desc",
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
                    pending.append(
                        _Pending(
                            "error",
                            "prereq_cycle",
                            node,
                            doc[node].name,
                            _msg_prereq_cycle,
                            (names,),
                            "prereqs",
                        )
                    )
            elif state == 0:
                dfs(parent)
        stack.pop()
        visited[node] = 2

    for nid in list(id_set):
        if visited.get(nid, 0) == 0:
            dfs(nid)

    pending.sort(key=_Pending.sort_key)
    hidden = len(pending) - max_issues
    issues = [item.render() for item in pending[:max_issues]]
    if hidden > 0:
        issues.append(
            Issue(
                "info",
                "issues_truncated",
                None,
                None,
                tr(
                    "validation.issue.issues_truncated",
                    "{hidden} more issue(s) not shown (showing first {limit})",
                    hidden=hidden,
                    limit=max_issues,
                ),
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
