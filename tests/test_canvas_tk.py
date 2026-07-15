"""Headless-skipped tests for CanvasMixin's viewport culling.

Needs a real Tk display to create canvas items, so CI (no python3-tk/Xvfb,
see testing.md) skips this whole module. Run locally on a dev machine with
a display to exercise it.
"""

import tkinter as tk

import pytest

from hoi4cm.models import Focus
from hoi4cm.ui.canvas import CanvasMixin

FAR_RECT = (0.0, 0.0, 10.0, 10.0)
NEAR_RECT = (490.0, 490.0, 510.0, 510.0)


@pytest.fixture
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.withdraw()
    yield root
    root.destroy()


class _FakeApp(CanvasMixin):
    """Bare host exposing just the attributes _draw_focus/_draw_lines touch."""

    def __init__(self, cv):
        self.cv = cv
        self.focuses = {}
        self.offset = [0, 0]
        self.zoom = 1.0
        self.selected = None
        self._multi_sel = set()
        self.mutex_mode = False
        self.mutex_src = None
        self._extra_trees = []

    def _get_tree_badge(self, tree_idx):
        return "", "#374151"


def _states(cv, fid):
    return {cv.itemcget(i, "state") for i in cv.find_withtag(f"F{fid}")}


def test_offscreen_focus_gets_no_items(tk_root):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    onscreen = Focus(x=1, y=1)
    offscreen = Focus(x=500, y=500)

    app._draw_focus(onscreen, FAR_RECT)
    app._draw_focus(offscreen, FAR_RECT)

    assert onscreen._items
    assert not offscreen._items
    assert offscreen._culled is True


def test_pan_onscreen_then_offscreen_toggles_state_and_culled(tk_root):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    f = Focus(x=500, y=500)

    app._draw_focus(f, FAR_RECT)
    assert not f._items
    assert f._culled is True

    app._draw_focus(f, NEAR_RECT)  # "pan" onto screen
    assert f._items
    assert f._culled is False
    # shadow/mat/box_rect are the card chrome: never legitimately hidden
    # (unlike glow/badge/img_item, which depend on selection/mod state), so
    # the uncull path having un-hidden them is exactly what this checks.
    chrome = f._items[:3]
    assert all(cv.itemcget(i, "state") != "hidden" for i in chrome)
    cx, cy = cv.coords(f._items[2])[0] + 26, cv.coords(f._items[2])[1] + 26
    assert (round(cx), round(cy)) == (500 * 96, 500 * 130)

    app._draw_focus(f, FAR_RECT)  # pan back away
    assert f._culled is True
    assert _states(cv, f.id) == {"hidden"}


def test_draw_key_fast_exits_when_unchanged(tk_root):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    f = Focus(x=5, y=5)

    app._draw_focus(f, FAR_RECT)
    box_rect = f._items[2]
    cv.move(box_rect, 37, 41)  # simulate drift a real update would correct
    nudged = cv.coords(box_rect)

    app._draw_focus(f, FAR_RECT)  # nothing about f or the rect changed
    assert cv.coords(box_rect) == nudged  # fast-exit: no recompute happened
