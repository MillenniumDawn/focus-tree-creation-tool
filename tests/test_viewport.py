"""Tests for hoi4cm.ui.viewport — pure canvas viewport-culling math.

No tkinter import here (matching the module under test), so these run in
plain CI with no display.
"""

from hoi4cm.ui.theme import XGRID, YGRID
from hoi4cm.ui.viewport import edge_visible, focus_visible, visible_world_rect


def test_visible_world_rect_basic_no_margin():
    rect = visible_world_rect(0, 0, 1.0, XGRID * 10, YGRID * 10, margin=0.0)
    assert rect == (0.0, 0.0, 10.0, 10.0)


def test_visible_world_rect_respects_offset():
    # A positive offset shifts the world origin right/down on screen, so the
    # world-coord viewport shifts left/up (negative) to compensate.
    rect = visible_world_rect(XGRID, YGRID, 1.0, XGRID * 10, YGRID * 10, margin=0.0)
    x0, y0, x1, y1 = rect
    assert x0 == -1.0
    assert y0 == -1.0
    assert x1 == 9.0
    assert y1 == 9.0


def test_visible_world_rect_always_ordered():
    """x0 <= x1 and y0 <= y1 regardless of sign of offset/zoom inputs."""
    for offset_x, offset_y, zoom in [(0, 0, 1.0), (-500, 300, 0.05), (900, -900, 4.0)]:
        x0, y0, x1, y1 = visible_world_rect(offset_x, offset_y, zoom, 800, 600, 20.0)
        assert x0 <= x1
        assert y0 <= y1


def test_visible_world_rect_zoom_extreme_zoomed_out():
    """At the min zoom canvas.py clamps to, the world-rect widens a lot."""
    x0, y0, x1, y1 = visible_world_rect(50, 50, 0.05, 800, 600, margin=0.0)
    assert x1 - x0 == (800 / (XGRID * 0.05))
    assert y1 - y0 == (600 / (YGRID * 0.05))
    assert x1 - x0 > 100  # zoomed way out: viewport spans a huge world range


def test_visible_world_rect_zoom_extreme_zoomed_in():
    """At the max zoom canvas.py clamps to, the world-rect narrows a lot."""
    x0, y0, x1, y1 = visible_world_rect(0, 0, 4.0, 400, 400, margin=0.0)
    assert x1 - x0 == (400 / (XGRID * 4.0))
    assert y1 - y0 == (400 / (YGRID * 4.0))
    assert x1 - x0 < 2  # zoomed way in: viewport covers only a couple cells


def test_margin_expands_rect_per_axis():
    """Margin is in pixels and converted per-axis since XGRID != YGRID."""
    rect = visible_world_rect(0, 0, 1.0, XGRID * 10, YGRID * 10, margin=XGRID)
    x0, y0, x1, y1 = rect
    assert x0 == -1.0  # XGRID px of margin == exactly 1 world unit on the x axis
    assert x1 == 11.0
    # The same pixel margin covers a smaller fraction of a (taller) y cell.
    assert y0 == -(XGRID / YGRID)
    assert y1 == 10 + (XGRID / YGRID)


def test_focus_visible_boundary_inclusive():
    rect = (0.0, 0.0, 10.0, 10.0)
    assert focus_visible(0, 5, rect) is True
    assert focus_visible(10, 5, rect) is True
    assert focus_visible(5, 0, rect) is True
    assert focus_visible(5, 10, rect) is True


def test_focus_visible_just_outside_boundary():
    rect = (0.0, 0.0, 10.0, 10.0)
    assert focus_visible(-0.01, 5, rect) is False
    assert focus_visible(10.01, 5, rect) is False


def test_focus_visible_respects_margin_expanded_rect():
    tight = visible_world_rect(0, 0, 1.0, XGRID * 10, YGRID * 10, margin=0.0)
    padded = visible_world_rect(0, 0, 1.0, XGRID * 10, YGRID * 10, margin=XGRID)
    assert focus_visible(-0.5, 5, tight) is False
    assert focus_visible(-0.5, 5, padded) is True


def test_edge_visible_both_endpoints_onscreen():
    rect = (0.0, 0.0, 10.0, 10.0)
    assert edge_visible(1, 1, 9, 9, rect) is True


def test_edge_visible_both_endpoints_offscreen_but_bbox_crosses():
    """An elbow/line between two offscreen focuses can still cross the screen."""
    rect = (0.0, 0.0, 10.0, 10.0)
    assert edge_visible(-100, 5, 100, 5, rect) is True


def test_edge_visible_both_endpoints_offscreen_and_bbox_misses():
    rect = (0.0, 0.0, 10.0, 10.0)
    assert edge_visible(-100, -100, -50, -50, rect) is False


def test_edge_visible_pad_extends_bbox():
    rect = (0.0, 0.0, 10.0, 10.0)
    assert edge_visible(11, 5, 20, 5, rect) is False
    assert edge_visible(11, 5, 20, 5, rect, pad=1.5) is True


def test_edge_visible_touching_boundary_is_visible():
    rect = (0.0, 0.0, 10.0, 10.0)
    assert edge_visible(10, 10, 20, 20, rect) is True
