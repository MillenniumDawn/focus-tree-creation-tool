"""Badge text and colour for each loaded extra focus tree.

The canvas asks for a tree's badge once per visible focus per redraw, plus
once per minimap dot and once per legend row. Deriving it on demand means
counting the same-typed trees ahead of it — O(extra trees) per call, so
O(extra trees x visible focuses) per frame. The whole table is O(n) to build
and only changes when a tree is loaded or unloaded, so callers build it once
and index into it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

# Cycled per tree of that type, so adjacent trees stay distinguishable.
SHARED_COLORS = ("#f59e0b", "#fb923c", "#fcd34d", "#f97316")
JOINT_COLORS = ("#a855f7", "#818cf8", "#c084fc", "#60a5fa")


def build_tree_badges(
    extra_trees: Iterable[Mapping[str, Any]],
) -> list[tuple[str, str]]:
    """Return ``(badge_text, color)`` per extra tree, in ``tree_idx - 1`` order.

    Shared trees are labelled S, S2, S3 …, joint trees J, J2, J3 …, numbered
    within their own type, matching how a tree's badge reads on the canvas.
    """
    badges: list[tuple[str, str]] = []
    shared = 0
    joint = 0
    for info in extra_trees:
        if info.get("type") == "shared":
            label = "S" if shared == 0 else f"S{shared + 1}"
            badges.append((label, SHARED_COLORS[shared % len(SHARED_COLORS)]))
            shared += 1
        else:
            label = "J" if joint == 0 else f"J{joint + 1}"
            badges.append((label, JOINT_COLORS[joint % len(JOINT_COLORS)]))
            joint += 1
    return badges


__all__ = ["JOINT_COLORS", "SHARED_COLORS", "build_tree_badges"]
