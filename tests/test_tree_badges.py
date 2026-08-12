"""Tests for the precomputed extra-tree badge table.

The table replaces a per-call scan over the trees ahead of the one being
asked about, so the thing worth pinning is that it still numbers and colours
trees exactly the way that scan did.
"""

from hoi4cm.ui.tree_badges import JOINT_COLORS, SHARED_COLORS, build_tree_badges


def _trees(*types):
    return [{"type": kind, "tree_id": f"tree_{i}"} for i, kind in enumerate(types)]


def _reference(extra_trees, tree_idx):
    """The pre-table derivation, kept as the oracle for these tests."""
    info = extra_trees[tree_idx - 1]
    if info["type"] == "shared":
        n = sum(1 for t in extra_trees[: tree_idx - 1] if t["type"] == "shared")
        return ("S" if n == 0 else f"S{n + 1}"), SHARED_COLORS[n % len(SHARED_COLORS)]
    n = sum(1 for t in extra_trees[: tree_idx - 1] if t["type"] == "joint")
    return ("J" if n == 0 else f"J{n + 1}"), JOINT_COLORS[n % len(JOINT_COLORS)]


def test_empty_tree_list_has_no_badges():
    assert build_tree_badges([]) == []


def test_first_tree_of_each_type_is_unnumbered():
    badges = build_tree_badges(_trees("shared", "joint"))

    assert [badge for badge, _ in badges] == ["S", "J"]
    assert [color for _, color in badges] == [SHARED_COLORS[0], JOINT_COLORS[0]]


def test_numbering_counts_within_type_not_position():
    badges = build_tree_badges(_trees("shared", "joint", "shared", "joint", "shared"))

    assert [badge for badge, _ in badges] == ["S", "J", "S2", "J2", "S3"]


def test_colors_cycle_once_a_type_runs_past_its_palette():
    kinds = ["shared"] * (len(SHARED_COLORS) + 2)
    badges = build_tree_badges(_trees(*kinds))

    assert badges[len(SHARED_COLORS)][1] == SHARED_COLORS[0]
    assert badges[len(SHARED_COLORS) + 1][1] == SHARED_COLORS[1]


def test_unknown_tree_type_is_badged_as_joint():
    # _get_tree_badge's original branch was `if shared: ... else: ...`, so
    # anything that isn't "shared" (an old project file, a hand-edited type)
    # lands on the joint palette rather than raising.
    badges = build_tree_badges(_trees("mystery", "joint"))

    assert [badge for badge, _ in badges] == ["J", "J2"]


def test_table_matches_the_per_call_derivation_it_replaced():
    kinds = ["shared", "joint", "joint", "shared", "shared", "joint", "shared"] * 3
    extra_trees = _trees(*kinds)

    badges = build_tree_badges(extra_trees)

    assert badges == [
        _reference(extra_trees, idx) for idx in range(1, len(extra_trees) + 1)
    ]
