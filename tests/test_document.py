import random
from collections import defaultdict

import pytest

from hoi4cm.models import Focus, FocusDocument


def _focus(focus_id, *, name=None, x=0, y=0, tree_idx=0):
    focus = Focus(x, y)
    focus.id = focus_id
    focus.name = name or f"focus_{focus_id}"
    focus.tree_idx = tree_idx
    return focus


def _reference_indexes(document):
    names = defaultdict(list)
    trees = defaultdict(set)
    positions = defaultdict(set)
    prerequisites = defaultdict(set)
    mutex = defaultdict(set)
    for focus_id, focus in document.items():
        names[focus.name].append(focus_id)
        trees[focus.tree_idx].add(focus_id)
        positions[(focus.x, focus.y)].add(focus_id)
        for group in focus.prereqs:
            for parent_id in group:
                prerequisites[parent_id].add(focus_id)
        for other_id in focus.mutex:
            mutex[other_id].add(focus_id)
    frozen_names = {name: tuple(ids) for name, ids in names.items()}
    return {
        "names": frozen_names,
        "first": {name: ids[0] for name, ids in frozen_names.items()},
        "last": {name: ids[-1] for name, ids in frozen_names.items()},
        "trees": dict(trees),
        "positions": dict(positions),
        "prerequisites": dict(prerequisites),
        "mutex": dict(mutex),
    }


def _assert_indexes(document):
    expected = _reference_indexes(document)
    assert document.names == expected["names"]
    assert document.first_by_name == expected["first"]
    assert document.last_by_name == expected["last"]
    assert document.tree_membership == expected["trees"]
    assert document.occupied_positions == expected["positions"]
    assert document.reverse_prerequisites == expected["prerequisites"]
    assert document.reverse_mutex == expected["mutex"]
    assert document.validate_indexes()


def test_link_prerequisite_and_mode_validation():
    parent_a = _focus(1)
    parent_b = _focus(2)
    child = _focus(3)
    document = FocusDocument((parent_a, parent_b, child))

    document.link_prerequisite(child.id, (parent_a.id, parent_b.id), mode="and")

    assert child.prereqs == [[parent_a.id], [parent_b.id]]
    with pytest.raises(ValueError, match="mode must be 'or' or 'and'"):
        document.link_prerequisite(child.id, (parent_a.id,), mode="invalid")


def test_duplicate_name_lookup_has_explicit_first_and_last_policy():
    first = _focus(10, name="duplicate")
    last = _focus(20, name="duplicate")
    document = FocusDocument((first, last))

    assert document.find_by_name("duplicate", policy="first") is first
    assert document.find_by_name("duplicate", policy="last") is last


def test_by_name_is_first_match_view_over_first_by_name():
    first = _focus(10, name="duplicate")
    last = _focus(20, name="duplicate")
    other = _focus(30, name="unique")
    document = FocusDocument((first, last, other))

    lookup = document.by_name

    assert lookup["duplicate"] is first
    assert lookup.get("unique") is other
    assert lookup.get("missing") is None
    assert set(lookup) == {"duplicate", "unique"}
    assert len(lookup) == 2
    # View tracks the live index; no rebuild or copy on access.
    first.name = "renamed"
    document.touch()
    assert document.by_name["renamed"] is first
    # The second focus still owns "duplicate" after the first renames away.
    assert document.by_name["duplicate"] is last


def test_mapping_delete_missing_id_raises_key_error():
    document = FocusDocument()

    with pytest.raises(KeyError):
        del document[42]


def test_legacy_direct_mutation_can_be_detected_and_rebuilt():
    focus = _focus(1, name="before")
    document = FocusDocument((focus,))
    revision = document.revision
    focus.name = "after"
    focus.x = 12

    assert not document.validate_indexes()
    assert not document.validate_indexes(rebuild=True)
    assert document.revision == revision + 1
    assert document.first_by_name == {"after": 1}
    assert document.occupied_positions == {(12, 0): {1}}


def test_bulk_add_and_tree_update_rebuild_once():
    document = FocusDocument()
    focuses = [_focus(index, tree_idx=1) for index in range(1, 101)]

    document.extend(focuses)
    after_extend = document.revision
    document.set_trees({focus.id: 2 for focus in focuses})

    assert after_extend == 1
    assert document.revision == 2
    assert document.tree_membership == {2: set(range(1, 101))}
    _assert_indexes(document)


def test_bulk_add_rejects_duplicate_ids_without_partial_update():
    document = FocusDocument((_focus(1),))

    with pytest.raises(KeyError, match="focus id already exists"):
        document.extend((_focus(2), _focus(1)))

    assert list(document) == [1]


def test_move_updates_positions_without_full_rebuild():
    document = FocusDocument((_focus(1, x=0, y=0), _focus(2, x=1, y=1)))
    revision = document.revision

    assert document.move(1, 5, 5) is True

    assert document.revision == revision + 1
    assert document.occupied_positions == {(5, 5): {1}, (1, 1): {2}}
    assert document.validate_indexes()
    _assert_indexes(document)


def test_move_shifts_raw_and_relative_export_coords():
    """Issue #115: a canvas move must carry through to the extra-tree raw
    coordinates, not just the plain x/y used by the main-tree exporter."""
    document = FocusDocument((_focus(1, x=0, y=0), _focus(2, x=1, y=1)))
    root, child = document[1], document[2]
    root._raw_gx, root._raw_gy = 0, 0
    child._raw_gx, child._raw_gy = 1, 1
    child._rel_dx, child._rel_dy = 1, 1
    child.relative_position_id = root.name

    assert document.move(child.id, 4, -1)

    assert (child._raw_gx, child._raw_gy) == (4, -1)
    assert (child._rel_dx, child._rel_dy) == (4, -1)
    assert (root._raw_gx, root._raw_gy) == (0, 0)


def test_move_leaves_focuses_without_raw_coords_untouched():
    document = FocusDocument((_focus(1, x=0, y=0),))

    assert document.move(1, 5, 5)

    assert not hasattr(document[1], "_raw_gx")
    assert not hasattr(document[1], "_rel_dx")


def test_position_free_respects_except_id_and_occupants():
    document = FocusDocument((_focus(1, x=0, y=0), _focus(2, x=1, y=1)))

    assert document.position_free(2, 2) is True
    assert document.position_free(1, 1) is False
    assert document.position_free(1, 1, except_id=2) is True
    assert document.position_free(1, 1, except_id=1) is False
    assert document.move(1, 1, 1) is False
    assert document.move(1, 1, 1, allow_occupied=True) is True


def test_rename_prefix_bumps_revision_so_cached_ui_refreshes():
    document = FocusDocument((_focus(1, name="OLD_a"), _focus(2, name="keep")))
    revision = document.revision

    renamed = document.rename_prefix("OLD_", "NEW_")

    assert renamed == 1
    assert document.revision == revision + 1
    assert document.first_by_name == {"NEW_a": 1, "keep": 2}


def test_randomized_mutations_match_reference_indexes():
    rng = random.Random(4815162342)
    document = FocusDocument()
    next_id = 1
    previous_revision = document.revision

    for _ in range(300):
        operation = rng.choice(("add", "move", "prereq", "mutex", "delete", "tree"))
        ids = list(document)
        if operation == "add" or not ids:
            focus = _focus(
                next_id,
                name=f"name_{rng.randrange(5)}",
                x=rng.randrange(8),
                y=rng.randrange(8),
                tree_idx=rng.randrange(3),
            )
            document.add(focus)
            next_id += 1
        elif operation == "move":
            document.move(
                rng.choice(ids), rng.randrange(8), rng.randrange(8), allow_occupied=True
            )
        elif operation == "prereq" and len(ids) > 1:
            child, parent = rng.sample(ids, 2)
            document.link_prerequisite(child, (parent,))
        elif operation == "mutex" and len(ids) > 1:
            left, right = rng.sample(ids, 2)
            document.link_mutex(left, right)
        elif operation == "delete":
            document.delete_many(
                rng.sample(ids, rng.randrange(1, min(3, len(ids)) + 1))
            )
        elif operation == "tree":
            document.set_tree(rng.choice(ids), rng.randrange(3))

        assert document.revision >= previous_revision
        previous_revision = document.revision
        _assert_indexes(document)
