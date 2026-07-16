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

from hoi4cm.models import Focus
from hoi4cm.script import dict_to_raw

from .parse import ParsedFocusTree, block_to_str


class BuildContext:
    def __init__(self, existing_focuses: Iterable[Focus] = ()) -> None:
        self._position_by_name: dict[str, Focus] = {}
        self._link_id_by_name: dict[str, int] = {}
        self.add_focuses(existing_focuses)

    def add_focuses(self, focuses: Iterable[Focus]) -> None:
        for focus in focuses:
            self._position_by_name.setdefault(focus.name, focus)
            self._link_id_by_name[focus.name] = focus.id

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
) -> list[Focus]:
    """Return the list of :class:`Focus` objects for one parsed tree.

    ``tree_idx`` is the 1-based index of this extra tree. ``country_tag`` is the
    active tag used to apply matching conditional offsets. ``existing_focuses``
    are the already-loaded focuses, used to resolve cross-tree relative
    positions and prerequisite / mutex references. Reuse ``context`` across
    batch calls to index each completed batch incrementally. The caller is
    responsible for inserting the returned focuses into its own registry.
    """
    if context is None:
        context = BuildContext(existing_focuses)
    else:
        context.add_focuses(existing_focuses)

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
        except Exception:
            gx = 0
            gy = 0
        rel_id = rf.get("relative_position_id", None)
        raw_pos[fid_str] = (gx, gy, rel_id)
        f = Focus(gx, gy)
        f._raw_gx = gx  # original file coords, preserved for export
        f._raw_gy = gy
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
        except Exception:
            f.cost = 10
        aiblock = rf.get("ai_will_do", {})
        if isinstance(aiblock, dict):
            try:
                f.ai_will_do = int(float(aiblock.get("factor", aiblock.get("base", 1))))
            except Exception:
                f.ai_will_do = 1
            f.ai_will_do_raw = dict_to_raw(aiblock)
        else:
            try:
                f.ai_will_do = int(float(aiblock))
            except Exception:
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
        f.will_lead_to_war_with = raw_rewards.get(
            (fid_str, "will_lead_to_war_with"),
            block_to_str(rf.get("will_lead_to_war_with", {})),
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
            if group_fids:
                f.prereqs.append(group_fids)
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

    context.add_focuses(new_focuses)
    return new_focuses
