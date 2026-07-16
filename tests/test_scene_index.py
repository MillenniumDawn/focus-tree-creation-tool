from hoi4cm.models import Focus
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
