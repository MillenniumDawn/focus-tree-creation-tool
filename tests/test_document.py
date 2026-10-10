import random
from collections import defaultdict

import pytest

from hoi4cm.models import Focus, FocusDocument


def _focus(focus_id, *, name=None, x=0, y=0, tree_idx=0):
    focus = Focus(id=1, x=x, y=y)
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


def _surviving_references(document, deleted):
    """What the old full-survivor scan left on each survivor."""
    expected = {}
    for focus_id, focus in document.items():
        if focus_id in deleted:
            continue
        groups = [[p for p in group if p not in deleted] for group in focus.prereqs]
        expected[focus_id] = (
            [group for group in groups if group],
            [other for other in focus.mutex if other not in deleted],
        )
    return expected


def _random_focus(rng, focus_id, pool):
    focus = _focus(
        focus_id,
        name=f"name_{rng.randrange(5)}",
        x=rng.randrange(6),
        y=rng.randrange(6),
        tree_idx=rng.randrange(3),
    )
    for _ in range(rng.randrange(3)):
        focus.prereqs.append([rng.choice(pool) for _ in range(rng.randrange(1, 3))])
    focus.mutex = [rng.choice(pool) for _ in range(rng.randrange(2))]
    return focus


_RANDOM_OPERATIONS = (
    "add",
    "replace",
    "extend",
    "extend_replace",
    "move",
    "delete_clean",
    "delete_keep",
    "link_prerequisite",
    "unlink_prerequisite",
    "link_mutex",
    "unlink_mutex",
    "set_tree",
    "set_trees",
    "rename_touch",
)
_DANGLING_IDS = (9001, 9002)


@pytest.mark.parametrize("seed", [4815162342, 7, 1234567, 99991])
def test_randomized_mixed_operations_keep_indexes_exact(seed):
    rng = random.Random(seed)
    document = FocusDocument()
    next_id = 1
    previous_revision = document.revision

    for _ in range(400):
        ids = list(document)
        pool = [*ids, *_DANGLING_IDS]
        operation = rng.choice(_RANDOM_OPERATIONS)
        if len(ids) > 30:
            operation = "delete_clean"
        elif not ids:
            operation = "add"

        if operation == "add":
            document.add(_random_focus(rng, next_id, pool))
            next_id += 1
        elif operation == "replace":
            document.add(_random_focus(rng, rng.choice(ids), pool), replace=True)
        elif operation == "extend":
            batch = [
                _random_focus(rng, next_id + offset, pool)
                for offset in range(rng.randrange(1, 6))
            ]
            next_id += len(batch)
            document.extend(batch)
        elif operation == "extend_replace":
            reused = rng.sample(ids, rng.randrange(1, min(4, len(ids)) + 1))
            batch = [_random_focus(rng, focus_id, pool) for focus_id in reused]
            batch.append(_random_focus(rng, next_id, pool))
            next_id += 1
            document.extend(batch, replace=True)
        elif operation == "move":
            document.move(
                rng.choice(ids), rng.randrange(6), rng.randrange(6), allow_occupied=True
            )
        elif operation in ("delete_clean", "delete_keep"):
            victims = rng.sample(ids, rng.randrange(1, min(5, len(ids)) + 1))
            victims.append(rng.choice(pool))
            clean = operation == "delete_clean"
            existing = set(victims) & set(ids)
            expected = _surviving_references(document, existing)
            assert document.delete_many(victims, clean_references=clean) == existing
            if clean:
                assert {
                    focus_id: (focus.prereqs, focus.mutex)
                    for focus_id, focus in document.items()
                } == expected
        elif operation == "link_prerequisite":
            parents = rng.sample(pool, rng.randrange(1, 4))
            document.link_prerequisite(
                rng.choice(ids), parents, mode=rng.choice(("or", "and"))
            )
        elif operation == "unlink_prerequisite":
            child = document[rng.choice(ids)]
            if child.prereqs:
                document.unlink_prerequisite_group(
                    child.id, rng.randrange(len(child.prereqs))
                )
        elif operation == "link_mutex":
            document.link_mutex(rng.choice(ids), rng.choice(ids))
        elif operation == "unlink_mutex":
            document.unlink_mutex(rng.choice(ids), rng.choice(pool))
        elif operation == "set_tree":
            document.set_tree(rng.choice(ids), rng.randrange(4))
        elif operation == "set_trees":
            targets = rng.sample(ids, rng.randrange(1, min(5, len(ids)) + 1))
            document.set_trees({focus_id: rng.randrange(4) for focus_id in targets})
        else:
            document[rng.choice(ids)].name = f"name_{rng.randrange(7)}"
            document.touch()

        assert document.revision >= previous_revision
        previous_revision = document.revision
        assert document.id_set == frozenset(document)
        _assert_indexes(document)


def _bystanders(count=6):
    """Unrelated focuses so small deletes and adds take the patch path."""
    return [
        _focus(100 + index, name=f"bystander_{index}", x=100 + index, y=100)
        for index in range(count)
    ]


def test_names_keep_insertion_order_through_add_and_delete():
    document = FocusDocument(_bystanders())
    for focus_id in (30, 10, 20):
        document.add(_focus(focus_id, name="dup"))

    assert document.names["dup"] == (30, 10, 20)
    assert (document.first_by_name["dup"], document.last_by_name["dup"]) == (30, 20)

    document.delete_many((10,))
    assert document.names["dup"] == (30, 20)

    document.delete_many((30,))
    assert document.names["dup"] == (20,)
    assert (document.first_by_name["dup"], document.last_by_name["dup"]) == (20, 20)

    document.delete_many((20,))
    assert "dup" not in document.names
    assert "dup" not in document.first_by_name
    assert "dup" not in document.last_by_name


def test_replace_keeps_the_slot_in_the_name_tuple():
    document = FocusDocument(
        (_focus(10, name="dup"), _focus(20, name="dup"), _focus(30, name="dup"))
    )

    document.add(_focus(20, name="dup", x=4), replace=True)

    assert document.names["dup"] == (10, 20, 30)
    assert document.occupied_positions == {(0, 0): {10, 30}, (4, 0): {20}}
    _assert_indexes(document)


def test_replace_with_rename_into_shared_name_follows_dict_order():
    document = FocusDocument(
        (_focus(10, name="x"), _focus(20, name="y"), _focus(30, name="y"))
    )

    document.add(_focus(10, name="y"), replace=True)

    assert document.names == {"y": (10, 20, 30)}
    assert document.first_by_name == {"y": 10}
    assert document.last_by_name == {"y": 30}
    _assert_indexes(document)


def test_extend_replace_keeps_existing_slots_and_appends_new_ids():
    document = FocusDocument(
        (_focus(10, name="dup"), _focus(20, name="dup"), _focus(30, name="other"))
    )

    document.extend((_focus(40, name="dup"), _focus(10, name="dup", y=2)), replace=True)

    assert list(document) == [10, 20, 30, 40]
    assert document.names["dup"] == (10, 20, 40)
    _assert_indexes(document)


def test_deleting_the_last_occupant_leaves_no_empty_buckets():
    parent = _focus(1, x=1, tree_idx=1)
    child = _focus(2, x=2, tree_idx=2)
    child.prereqs = [[1]]
    child.mutex = [1]
    document = FocusDocument((parent, child, *_bystanders()))

    document.delete_many((2,))

    assert (2, 0) not in document.occupied_positions
    assert 2 not in document.tree_membership
    assert 1 not in document.reverse_prerequisites
    assert 1 not in document.reverse_mutex
    assert "focus_2" not in document.names
    _assert_indexes(document)


def test_unlink_prerequisite_group_keeps_parents_another_group_still_names():
    parent = _focus(1)
    child = _focus(2)
    child.prereqs = [[1], [1, 3]]
    document = FocusDocument((parent, child, _focus(3)))

    document.unlink_prerequisite_group(2, 0)
    assert document.reverse_prerequisites == {1: {2}, 3: {2}}

    document.unlink_prerequisite_group(2, 0)
    assert document.reverse_prerequisites == {}
    _assert_indexes(document)


def test_unlink_mutex_drops_emptied_buckets_even_for_a_missing_partner():
    left = _focus(1)
    right = _focus(2)
    document = FocusDocument((left, right))
    document.link_mutex(1, 2)
    left.mutex.append(77)
    document.touch()

    document.unlink_mutex(1, 2)
    assert document.reverse_mutex == {77: {1}}

    document.unlink_mutex(1, 77)
    assert document.reverse_mutex == {}
    _assert_indexes(document)


def test_set_tree_drops_the_emptied_tree_bucket():
    document = FocusDocument((_focus(1, tree_idx=1), _focus(2)))

    document.set_tree(1, 3)
    assert document.tree_membership == {3: {1}, 0: {2}}

    document.set_trees({1: 0, 2: 5})
    assert document.tree_membership == {0: {1}, 5: {2}}
    _assert_indexes(document)


def test_delete_many_cleans_references_through_the_reverse_indexes():
    root = _focus(1)
    other = _focus(2)
    gone = _focus(3)
    chained = _focus(4)
    chained.prereqs = [[1, 3], [3], [2]]
    chained.mutex = [3, 2]
    solo = _focus(5)
    solo.prereqs = [[3]]
    solo.mutex = [3]
    untouched = _focus(6)
    untouched.prereqs = [[1]]
    untouched.mutex = [2]
    untouched_prereqs, untouched_mutex = untouched.prereqs, untouched.mutex
    mutex_only = _focus(7)
    mutex_only.mutex = [2, 3]
    document = FocusDocument((root, other, gone, chained, solo, untouched, mutex_only))

    assert document.delete_many((3,)) == {3}

    assert chained.prereqs == [[1], [2]]
    assert chained.mutex == [2]
    assert (solo.prereqs, solo.mutex) == ([], [])
    assert mutex_only.mutex == [2]
    # Survivors that never named the deleted id are not rewritten.
    assert untouched.prereqs is untouched_prereqs
    assert untouched.mutex is untouched_mutex
    assert document.reverse_prerequisites == {1: {4, 6}, 2: {4}}
    assert document.reverse_mutex == {2: {4, 6, 7}}
    _assert_indexes(document)


def test_delete_many_without_cleanup_keeps_dangling_references_indexed():
    gone = _focus(3)
    gone.prereqs = [[1]]
    survivor = _focus(4)
    survivor.prereqs = [[3]]
    survivor.mutex = [3]
    document = FocusDocument((_focus(1), gone, survivor))

    document.delete_many((3,), clean_references=False)

    assert survivor.prereqs == [[3]]
    assert survivor.mutex == [3]
    assert document.reverse_prerequisites == {3: {4}}
    assert document.reverse_mutex == {3: {4}}
    _assert_indexes(document)


def test_incremental_operations_do_not_rebuild_indexes(monkeypatch):
    document = FocusDocument(_focus(index, x=index) for index in range(1, 201))
    builds = []
    real_build = document._build_indexes

    def counted_build():
        builds.append(1)
        return real_build()

    monkeypatch.setattr(document, "_build_indexes", counted_build)

    document.add(_focus(500, name="fresh", x=500))
    document.add(_focus(500, name="fresh", x=501), replace=True)
    document.extend((_focus(501, x=502), _focus(502, x=503)))
    document.link_prerequisite(1, (2, 3), mode="and")
    document.unlink_prerequisite_group(1, 0)
    document.link_mutex(4, 5)
    document.unlink_mutex(4, 5)
    document.set_tree(6, 2)
    document.set_trees({6: 0, 7: 1})
    document.move(8, 600, 0)
    document.delete_many((500,))
    document.delete_many((501, 502), clean_references=False)

    assert builds == []
    assert document.validate_indexes()
    builds.clear()

    document.touch()
    assert builds == [1]


def test_extend_replacing_with_renames_builds_once(monkeypatch):
    document = FocusDocument(_focus(index, x=index) for index in range(1, 201))
    builds = []
    real_build = document._build_indexes

    def counted_build():
        builds.append(1)
        return real_build()

    monkeypatch.setattr(document, "_build_indexes", counted_build)

    document.extend(
        (_focus(index, name=f"renamed_{index}", x=index) for index in range(1, 51)),
        replace=True,
    )

    assert builds == [1]
    assert document.validate_indexes()


def test_batches_as_large_as_the_document_take_the_full_build():
    document = FocusDocument((_focus(1), _focus(2)))

    document.extend((_focus(3, name="dup"), _focus(4, name="dup")))
    assert document.names["dup"] == (3, 4)
    _assert_indexes(document)

    document.delete_many((1, 2, 3))
    assert list(document) == [4]
    _assert_indexes(document)


def test_incremental_operations_tolerate_stale_indexes():
    first, second, third = _focus(1), _focus(2), _focus(3)
    document = FocusDocument((first, second, third))
    # Legacy direct edits leave the indexes stale until touch().
    first.name = "renamed"
    second.x = 9
    second.prereqs = [[1]]
    second.mutex = [3]
    third.tree_idx = 4
    document.reverse_prerequisites[3] = {99}
    document.reverse_mutex[2] = {98}

    document.link_prerequisite(3, (1,))
    document.unlink_prerequisite_group(2, 0)
    document.link_mutex(1, 2)
    document.unlink_mutex(1, 2)
    document.unlink_mutex(1, 2)
    document.set_tree(3, 0)
    document.add(_focus(1, name="again"), replace=True)
    document.add(_focus(4, name="renamed"))
    document.extend((_focus(5),))
    document.delete_many((3, 4))
    document.delete_many((2,), clean_references=False)

    document.touch()
    assert document.validate_indexes()


@pytest.mark.parametrize(
    ("mutate", "structural"),
    [
        (lambda doc: doc.add(_focus(9)), True),
        (lambda doc: doc.add(_focus(1, name="other"), replace=True), True),
        (lambda doc: doc.extend((_focus(9),)), True),
        (lambda doc: doc.delete_many((1,)), True),
        (lambda doc: doc.link_prerequisite(1, (2,)), False),
        (lambda doc: doc.unlink_prerequisite_group(2, 0), False),
        (lambda doc: doc.link_mutex(1, 2), False),
        (lambda doc: doc.unlink_mutex(1, 2), False),
        (lambda doc: doc.set_tree(1, 3), False),
        (lambda doc: doc.set_trees({1: 3, 2: 4}), False),
    ],
)
def test_mutations_bump_the_revision_once_and_id_set_only_when_structural(
    mutate, structural
):
    child = _focus(2)
    child.prereqs = [[1]]
    document = FocusDocument((_focus(1), child))
    revision = document.revision
    cached = document.id_set

    mutate(document)

    assert document.revision == revision + 1
    assert document.id_set == frozenset(document)
    assert (document.id_set is cached) is not structural
    assert document.validate_indexes()
