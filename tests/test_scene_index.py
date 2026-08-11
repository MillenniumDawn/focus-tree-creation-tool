from hoi4cm.models import Focus
from hoi4cm.models.document import FocusDocument
from hoi4cm.ui.scene_index import SceneIndex


def _focus(focus_id, x, y):
    focus = Focus(x, y)
    focus.id = focus_id
    return focus


def test_focus_query_returns_only_cells_overlapping_viewport():
    focuses = {1: _focus(1, 1, 1), 2: _focus(2, 50, 50)}
    index = SceneIndex(cell_size=4)
    index.rebuild(focuses)

    assert index.query_focus_ids((0, 0, 5, 5)) == [1]


def test_edge_query_includes_crossing_edge_with_offscreen_endpoints():
    left = _focus(1, -100, 5)
    right = _focus(2, 100, 5)
    right.prereqs = [[left.id]]
    index = SceneIndex(cell_size=8)
    index.rebuild({left.id: left, right.id: right})

    edges = index.query_edges((0, 0, 10, 10))

    assert [(edge.source_id, edge.target_id) for edge in edges] == [(1, 2)]


def test_validate_rebuilds_after_legacy_direct_mutation():
    focus = _focus(1, 1, 1)
    focuses = {focus.id: focus}
    index = SceneIndex(cell_size=4)
    index.rebuild(focuses)
    revision = index.revision

    focus.x = 20

    assert index.ensure(focuses, validate=True) is True
    assert index.revision == revision + 1
    assert index.query_focus_ids((16, 0, 24, 4)) == [1]


def test_view_only_ensure_does_not_validate_legacy_objects():
    focus = _focus(1, 1, 1)
    focuses = {focus.id: focus}
    index = SceneIndex(cell_size=4)
    index.rebuild(focuses)
    focus.x = 20

    assert index.ensure(focuses, validate=False) is False
    assert index.query_focus_ids((0, 0, 4, 4)) == [1]


def test_ensure_defaults_to_trusting_the_document_revision():
    document = FocusDocument([_focus(1, 1, 1)])
    index = SceneIndex(cell_size=4)
    index.rebuild(document)

    assert index.ensure(document) is False  # revision unchanged: no O(F) work

    document.move(1, 20, 1)

    assert index.ensure(document) is True
    assert index.query_focus_ids((16, 0, 24, 4)) == [1]


def test_ensure_sees_every_document_mutation_kind_without_validating():
    document = FocusDocument([_focus(1, 1, 1), _focus(2, 2, 2)])
    index = SceneIndex(cell_size=4)
    index.rebuild(document)

    # Each of these is a distinct path onto the geometry the index caches;
    # trusting the revision is only sound because every one of them bumps it.
    document.link_prerequisite(2, [1])
    assert index.ensure(document) is True
    assert [(edge.source_id, edge.target_id) for edge in index.all_edges()] == [(1, 2)]

    document.link_mutex(1, 2)
    assert index.ensure(document) is True
    assert len(index.all_edges()) == 2

    document.add(_focus(3, 9, 9))
    assert index.ensure(document) is True
    assert index.query_focus_ids((8, 8, 10, 10)) == [3]

    document.delete_many([3])
    assert index.ensure(document) is True
    assert index.query_focus_ids((8, 8, 10, 10)) == []

    # The legacy escape hatch for direct field edits.
    document[1].x = 30
    document.touch()
    assert index.ensure(document) is True
    assert index.query_focus_ids((28, 0, 32, 4)) == [1]


def test_direct_field_edit_without_touch_needs_the_debug_validate_path():
    document = FocusDocument([_focus(1, 1, 1)])
    index = SceneIndex(cell_size=4)
    index.rebuild(document)

    document[1].x = 20  # bypasses move()/touch(), so no revision bump

    assert index.ensure(document) is False  # the cost of trusting the revision
    assert index.ensure(document, validate=True) is True
    assert index.query_focus_ids((16, 0, 24, 4)) == [1]


def _rebuilt(focuses, *, cell_size):
    reference = SceneIndex(cell_size=cell_size)
    reference.rebuild(focuses)
    return reference


def _assert_equivalent(index, focuses, *, cell_size):
    reference = _rebuilt(focuses, cell_size=cell_size)
    rects = [
        (0, 0, 10, 10),
        (36, 36, 44, 44),
        (0, 0, 50, 50),
        (-5, -5, 3, 3),
        (25, 25, 35, 35),
    ]
    for rect in rects:
        assert index.query_focus_ids(rect) == reference.query_focus_ids(rect)
        assert index.query_edges(rect) == reference.query_edges(rect)


def test_update_focus_matches_full_rebuild_after_move():
    a = _focus(1, 0, 0)
    b = _focus(2, 5, 0)
    c = _focus(3, 5, 5)
    b.prereqs = [[1]]
    c.prereqs = [[2]]
    a.mutex = [3]
    c.mutex = [1]
    focuses = {1: a, 2: b, 3: c}
    index = SceneIndex(cell_size=4)
    index.rebuild(focuses)

    b.x, b.y = 40, 40
    index.update_focus(focuses, 2)

    _assert_equivalent(index, focuses, cell_size=4)


def test_update_focus_moves_edge_into_and_out_of_wide_bucket():
    a = _focus(1, 0, 0)
    b = _focus(2, 1, 0)
    b.prereqs = [[1]]
    focuses = {1: a, 2: b}
    index = SceneIndex(cell_size=1)
    index.rebuild(focuses)

    b.x, b.y = 30, 30  # edge now spans 31x31 cells -> wide bucket
    index.update_focus(focuses, 2)
    _assert_equivalent(index, focuses, cell_size=1)

    b.x, b.y = 1, 0  # back to a narrow edge -> leaves the wide bucket
    index.update_focus(focuses, 2)
    _assert_equivalent(index, focuses, cell_size=1)


def test_update_focus_falls_back_to_rebuild_for_unknown_focus():
    focus = _focus(1, 1, 1)
    focuses = {1: focus}
    index = SceneIndex(cell_size=4)
    index.rebuild(focuses)

    focuses[2] = _focus(2, 9, 9)
    index.update_focus(focuses, 2)

    assert index.query_focus_ids((8, 8, 10, 10)) == [2]
