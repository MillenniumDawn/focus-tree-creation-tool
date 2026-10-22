"""Build :class:`~hoi4cm.models.Focus` objects from parsed focus-tree data.

Takes a :class:`~hoi4cm.focus_tree.parse.ParsedFocusTree` and produces the
canvas focuses: positions resolved (including relative anchors that point into
already-loaded trees), conditional offsets applied, and prerequisite / mutually
exclusive links wired. No tkinter, no globals — cross-tree context is passed in
via ``existing_focuses``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from copy import deepcopy

from hoi4cm.models import Focus, FocusDocument
from hoi4cm.script import dict_to_raw

from .parse import ParsedFocusTree, block_to_str

_KNOWN_FOCUS_FIELDS = frozenset(
    {
        "id",
        "icon",
        "text",
        "x",
        "y",
        "relative_position_id",
        "offset",
        "cost",
        "prerequisite",
        "mutually_exclusive",
        "search_filters",
        "allow_branch",
        "available",
        "bypass",
        "cancel",
        "will_lead_to_war_with",
        "complete_tooltip",
        "select_effect",
        "bypass_effect",
        "cancel_if_invalid",
        "continue_if_invalid",
        "available_if_capitulated",
        "completion_reward",
        "ai_will_do",
        "joint_trigger",
    }
)


class BuildContext:
    """Cross-tree name/position indexes and the allocator shared by tree builds."""

    def __init__(
        self,
        existing_focuses: Iterable[Focus] = (),
        *,
        id_floor: int = 0,
        reconcile: bool = True,
    ) -> None:
        self.id_document = FocusDocument()
        self.id_document.reserve_id(id_floor)
        self._position_by_name: dict[str, Focus] = {}
        self._link_id_by_name: dict[str, int] = {}
        self._focuses_by_id: dict[int, Focus] = {}
        focuses = list(existing_focuses)
        self.add_focuses(focuses, reconcile=reconcile and bool(focuses))

    def add_focuses(self, focuses: Iterable[Focus], *, reconcile: bool = True) -> None:
        for focus in focuses:
            self.id_document.reserve_id(focus.id)
            self._focuses_by_id[focus.id] = focus
            self._position_by_name.setdefault(focus.name, focus)
            self._link_id_by_name[focus.name] = focus.id
        if reconcile:
            self._reconcile_pending()

    def _reconcile_pending(self) -> None:
        by_id = self._focuses_by_id
        for focus in by_id.values():
            unresolved_groups = getattr(focus, "_unresolved_prereqs", [])
            while len(unresolved_groups) < len(focus.prereqs):
                unresolved_groups.append([])
            for index, unresolved in enumerate(unresolved_groups):
                resolved = []
                remaining = []
                for name in unresolved:
                    target_id = self._link_id_by_name.get(name)
                    if target_id is None:
                        remaining.append(name)
                    elif target_id not in focus.prereqs[index]:
                        resolved.append(target_id)
                focus.prereqs[index].extend(resolved)
                unresolved_groups[index] = remaining
            focus._unresolved_prereqs = unresolved_groups
            unresolved_mutex = getattr(focus, "_unresolved_mutex", [])
            for name in unresolved_mutex:
                target_id = self._link_id_by_name.get(name)
                if target_id is not None and target_id not in focus.mutex:
                    focus.mutex.append(target_id)
            focus._unresolved_mutex = [
                name for name in unresolved_mutex if name not in self._link_id_by_name
            ]

        pending = [
            focus
            for focus in by_id.values()
            if getattr(focus, "_relative_pending", False)
        ]
        done: dict[int, tuple[int, int]] = {}
        stalled: set[int] = set()
        for start in pending:
            if start.id in done or start.id in stalled:
                continue
            path: list[tuple[Focus, Focus]] = []
            seen: set[int] = set()
            current = start
            base: tuple[int, int] | None = None
            while getattr(current, "_relative_pending", False):
                if current.id in stalled:
                    stalled.update(focus.id for focus, _anchor in path)
                    break
                if current.id in seen:
                    stalled.update(focus.id for focus, _anchor in path)
                    break
                seen.add(current.id)
                anchor_name = getattr(current, "relative_position_id", None)
                anchor = (
                    self._position_by_name.get(anchor_name) if anchor_name else None
                )
                if anchor is None:
                    stalled.update(focus.id for focus, _anchor in path)
                    break
                path.append((current, anchor))
                if anchor.id in done:
                    base = done[anchor.id]
                    break
                if not getattr(anchor, "_relative_pending", False):
                    base = anchor.x, anchor.y
                    break
                current = anchor
            if not path or base is None:
                stalled.update(focus.id for focus, _anchor in path)
                continue
            for focus, anchor in reversed(path):
                raw_x = getattr(focus, "_build_gx", None)
                raw_y = getattr(focus, "_build_gy", None)
                if raw_x is None:
                    raw_x = getattr(focus, "_raw_gx", None)
                if raw_y is None:
                    raw_y = getattr(focus, "_raw_gy", None)
                if raw_x is None or raw_y is None:
                    break
                if anchor.id in done:
                    base = done[anchor.id]
                elif not getattr(anchor, "_relative_pending", False):
                    base = anchor.x, anchor.y
                base = base[0] + raw_x, base[1] + raw_y
                done[focus.id] = base
            for focus, _anchor in path:
                resolved_position = done.get(focus.id)
                if resolved_position is not None:
                    focus.x, focus.y = resolved_position
                    focus._relative_pending = False

    def _position_for(self, name: str) -> tuple[int, int] | None:
        focus = self._position_by_name.get(name)
        if focus is None:
            return None
        return focus.x, focus.y

    def _link_ids(self) -> dict[str, int]:
        return self._link_id_by_name.copy()


def _resolve_positions(
    raw_pos: dict[str, tuple[int, int, str | None]], context: BuildContext
) -> dict[str, tuple[int, int]]:
    resolved: dict[str, tuple[int, int]] = {}

    for start in raw_pos:
        if start in resolved:
            continue

        path: list[str] = []
        seen: set[str] = set()
        name = start

        while name in raw_pos and name not in resolved and name not in seen:
            seen.add(name)
            path.append(name)
            relative_to = raw_pos[name][2]
            if relative_to is None:
                name = ""
                break
            name = relative_to

        if name in resolved:
            position = resolved[name]
        elif name in seen:
            position = raw_pos[name][:2]
        else:
            position = context._position_for(name) or (0, 0)

        for path_name in reversed(path):
            x, y, _relative_to = raw_pos[path_name]
            position = position[0] + x, position[1] + y
            resolved[path_name] = position

    return resolved


def build_focuses(
    parsed: ParsedFocusTree,
    tree_idx: int,
    *,
    country_tag: str = "",
    existing_focuses: Iterable[Focus] = (),
    context: BuildContext | None = None,
    document: FocusDocument | None = None,
    id_floor: int = 0,
    register_focuses: bool = True,
) -> list[Focus]:
    """Return the list of :class:`Focus` objects for one parsed tree.

    ``tree_idx`` is the 1-based index of this extra tree. ``country_tag`` is the
    active tag used to apply matching conditional offsets. ``existing_focuses``
    are the already-loaded focuses, used to resolve cross-tree relative
    positions and prerequisite / mutex references. Reuse ``context`` across
    batch calls to index each completed batch incrementally. The caller is
    responsible for inserting the returned focuses into its own registry.
    Pass ``document`` to allocate IDs from a specific workspace. Without it,
    IDs come from ``context``'s allocator, which is seeded with
    ``existing_focuses`` and remains monotonic across calls sharing that context.
    ``id_floor`` carries a document allocator's watermark into a detached
    worker context when some previously allocated IDs are no longer live.
    """
    existing_focuses = list(existing_focuses)
    if context is None:
        context = BuildContext(
            existing_focuses, id_floor=id_floor, reconcile=register_focuses
        )
    else:
        if existing_focuses:
            context.add_focuses(existing_focuses)
        context.id_document.reserve_id(id_floor)
    if document is None:
        document = context.id_document
    else:
        document.reserve_id(id_floor)
        for focus in existing_focuses:
            document.reserve_id(focus.id)

    raw_rewards = parsed.raw_rewards
    focuses_data = parsed.focuses_data

    name_to_id = {}
    raw_pos = {}
    new_focuses = []

    # Pass 1: create Focus objects.
    for rf in focuses_data:
        fid_str = rf.get("id", "")
        if not fid_str:
            continue
        try:
            gx = int(rf.get("x", 0))
            gy = int(rf.get("y", 0))
        except ValueError, TypeError:
            gx = 0
            gy = 0
        rel_id = rf.get("relative_position_id", None)
        raw_pos[fid_str] = (gx, gy, rel_id)
        f = document.new_focus(gx, gy)
        f._raw_gx = gx  # original file coords, preserved for export
        f._raw_gy = gy
        f._unresolved_prereqs = []
        f._unresolved_mutex = []
        f._relative_pending = False
        f.tree_idx = tree_idx
        f.name = fid_str
        if rel_id:
            f.relative_position_id = rel_id
            f._rel_dx = gx
            f._rel_dy = gy
        f.gfx = rf.get("icon", "GFX_goal_generic_political_pressure")
        try:
            cost = float(rf.get("cost", "10"))
            f.cost = cost if cost != int(cost) else int(cost)
        except ValueError, TypeError:
            f.cost = 10
        aiblock = rf.get("ai_will_do", {})
        if isinstance(aiblock, dict):
            try:
                factor = aiblock.get("factor", aiblock.get("base", 1))
                f.ai_will_do = int(float(factor)) if factor is not None else 1
            except ValueError, TypeError:
                f.ai_will_do = 1
            f.ai_will_do_raw = dict_to_raw(aiblock)
        else:
            try:
                f.ai_will_do = int(float(aiblock))
            except ValueError, TypeError:
                f.ai_will_do = 1
            f.ai_will_do_raw = ""
        f.cancel_if_invalid = rf.get("cancel_if_invalid", "yes") == "yes"
        f.continue_if_invalid = rf.get("continue_if_invalid", "no") == "yes"
        f.available_if_capitulated = rf.get("available_if_capitulated", "no") == "yes"
        sf = rf.get("search_filters", "")
        if isinstance(sf, dict):
            sf = " ".join(
                str(v) for v in sf.get("_values", []) if not str(v).startswith("_")
            )
        elif isinstance(sf, list):
            sf = " ".join(str(v) for v in sf)
        f.search_filters = (
            str(sf).strip("{}").strip() if sf else "FOCUS_FILTER_POLITICAL"
        )
        f.available_cond = raw_rewards.get(
            (fid_str, "available"), block_to_str(rf.get("available", {}))
        )
        f.bypass_cond = raw_rewards.get(
            (fid_str, "bypass"), block_to_str(rf.get("bypass", {}))
        )
        f.cancel_cond = raw_rewards.get(
            (fid_str, "cancel"), block_to_str(rf.get("cancel", {}))
        )
        wltw = rf.get("will_lead_to_war_with", {})
        if isinstance(wltw, list):
            # repeated bare keys (vanilla GER_weserubung form) parse into a
            # list; join so the exporter can re-emit one line per tag
            f.will_lead_to_war_with = "\n".join(str(v) for v in wltw)
        else:
            f.will_lead_to_war_with = raw_rewards.get(
                (fid_str, "will_lead_to_war_with"), block_to_str(wltw)
            )
        f.complete_tooltip = raw_rewards.get(
            (fid_str, "complete_tooltip"),
            block_to_str(rf.get("complete_tooltip", {})),
        )
        f.select_effect = raw_rewards.get(
            (fid_str, "select_effect"), block_to_str(rf.get("select_effect", {}))
        )
        f.bypass_effect = raw_rewards.get(
            (fid_str, "bypass_effect"), block_to_str(rf.get("bypass_effect", {}))
        )
        f.allow_branch = raw_rewards.get(
            (fid_str, "allow_branch"), block_to_str(rf.get("allow_branch", {}))
        )
        text_val = rf.get("text", "")
        f.text = (
            str(text_val).strip() if text_val and not isinstance(text_val, dict) else ""
        )
        f._joint_extra = raw_rewards.get((fid_str, "_joint_extra"), "")
        f.offsets = raw_rewards.get((fid_str, "_offsets"), [])
        extras = {
            key: deepcopy(value)
            for key, value in rf.items()
            if key not in _KNOWN_FOCUS_FIELDS
        }
        if extras:
            f._script_extras = extras
        raw_rw = raw_rewards.get(fid_str, "")
        if raw_rw:
            f.effects = [{"type": "_raw_block", "fields": {"raw": raw_rw}}]
        else:
            f.effects = []
        new_focuses.append(f)
        name_to_id[fid_str] = f.id

    id_to_focus = {f.id: f for f in new_focuses}

    # Apply country-tag-matching offsets to raw_pos BEFORE resolution so all
    # relative-positioned children inherit the shift.
    active_tag = (country_tag or "").upper().strip()
    if active_tag:
        for fid_s in list(raw_pos.keys()):
            for off in raw_rewards.get((fid_s, "_offsets"), []):
                trig = off.get("trigger", "")
                if re.search(
                    r"\boriginal_tag\s*=\s*" + re.escape(active_tag) + r"\b", trig
                ):
                    rx, ry, rel = raw_pos[fid_s]
                    raw_pos[fid_s] = (rx + off["x"], ry + off["y"], rel)
                    break  # apply only the first matching offset per focus

    # Resolve relative positions — within this tree first, then cross-tree.
    pending_by_name: dict[str, bool] = {}
    for focus in new_focuses:
        focus._build_gx, focus._build_gy = raw_pos[focus.name][:2]
        if focus.name in pending_by_name:
            focus._relative_pending = pending_by_name[focus.name]
            continue
        path: list[str] = []
        seen: set[str] = set()
        anchor_name: str | None = focus.name
        pending = False
        while anchor_name and anchor_name in raw_pos:
            if anchor_name in pending_by_name:
                pending = pending_by_name[anchor_name]
                break
            if anchor_name in seen:
                break  # Relative cycles retain the parser's established fallback.
            seen.add(anchor_name)
            path.append(anchor_name)
            anchor_name = raw_pos[anchor_name][2]
        if anchor_name:
            anchor = context._position_by_name.get(anchor_name)
            pending = anchor is None or getattr(anchor, "_relative_pending", False)
        for path_name in path:
            pending_by_name[path_name] = pending
        focus._relative_pending = pending_by_name[focus.name]
    resolved_positions = _resolve_positions(raw_pos, context)
    for fid_str, fid in name_to_id.items():
        ax, ay = resolved_positions[fid_str]
        id_to_focus[fid].x = ax
        id_to_focus[fid].y = ay

    # Pass 2: link prerequisites and mutex (cross-tree lookups included).
    # Existing focuses first, then the new ones, so new focuses win on a name
    # collision — matching the monolith's insertion-ordered self.focuses.
    all_name_to_id = context._link_ids()
    for f in new_focuses:
        all_name_to_id[f.name] = f.id

    for rf in focuses_data:
        fid_str = rf.get("id", "")
        if fid_str not in name_to_id:
            continue
        f = id_to_focus[name_to_id[fid_str]]
        prereqs = rf.get("prerequisite", [])
        if isinstance(prereqs, dict):
            prereqs = [prereqs]
        for pblock in prereqs:
            if not isinstance(pblock, dict):
                continue
            pf = pblock.get("focus", [])
            if isinstance(pf, str):
                pf = [pf]
            group_fids = [all_name_to_id[pn] for pn in pf if pn in all_name_to_id]
            f.prereqs.append(group_fids)
            f._unresolved_prereqs.append([pn for pn in pf if pn not in all_name_to_id])
        mutex = rf.get("mutually_exclusive", [])
        if isinstance(mutex, dict):
            mutex = [mutex]
        for mblock in mutex:
            if not isinstance(mblock, dict):
                continue
            mf = mblock.get("focus", "")
            if isinstance(mf, str) and mf in all_name_to_id:
                mid = all_name_to_id[mf]
                if mid not in f.mutex:
                    f.mutex.append(mid)
            elif isinstance(mf, str):
                f._unresolved_mutex.append(mf)

    if register_focuses:
        context.add_focuses(new_focuses)
    return new_focuses
