"""Headless-skipped tests for CanvasMixin's viewport culling.

Needs a real Tk display to create canvas items, so CI (no python3-tk/Xvfb,
see testing.md) skips this whole module. Run locally on a dev machine with
a display to exercise it.
"""

import tkinter as tk

import pytest

from hoi4cm.models import Focus
from hoi4cm.ui.canvas import CanvasMixin
from hoi4cm.ui.canvas_scheduler import RedrawChannel

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
        self._redraw_job = None
        self._lines_job = None

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

    assert onscreen.id in app._focus_bundles
    assert offscreen.id not in app._focus_bundles


def test_pan_onscreen_then_offscreen_reclaims_bundle(tk_root):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    f = Focus(x=500, y=500)

    app._draw_focus(f, FAR_RECT)
    assert f.id not in app._focus_bundles

    app._draw_focus(f, NEAR_RECT)  # "pan" onto screen
    items = app._focus_bundles[f.id].items
    # shadow/mat/box_rect are the card chrome: never legitimately hidden
    # (unlike glow/badge/img_item, which depend on selection/mod state), so
    # the uncull path having un-hidden them is exactly what this checks.
    chrome = items[:3]
    assert all(cv.itemcget(i, "state") != "hidden" for i in chrome)
    cx, cy = cv.coords(items[2])[0] + 26, cv.coords(items[2])[1] + 26
    assert (round(cx), round(cy)) == (500 * 96, 500 * 130)

    app._draw_focus(f, FAR_RECT)  # pan back away
    assert not cv.find_withtag(f"F{f.id}")
    assert f.id not in app._focus_bundles


def test_draw_key_fast_exits_when_unchanged(tk_root):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    f = Focus(x=5, y=5)

    app._draw_focus(f, FAR_RECT)
    box_rect = app._focus_bundles[f.id].items[2]
    cv.move(box_rect, 37, 41)  # simulate drift a real update would correct
    nudged = cv.coords(box_rect)

    app._draw_focus(f, FAR_RECT)  # nothing about f or the rect changed
    assert cv.coords(box_rect) == nudged  # fast-exit: no recompute happened


def test_retained_focus_bundles_are_bounded_by_visible_set(tk_root):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    focuses = [Focus(x=index * 10, y=0) for index in range(20)]
    app.focuses = {focus.id: focus for focus in focuses}

    for focus in focuses:
        app._draw_focus(focus, (-1, -1, 5, 5))
    assert len(app._focus_bundles) == 1

    for focus in focuses:
        app._draw_focus(focus, (185, -1, 205, 5))
    assert len(app._focus_bundles) <= 2
    assert len(cv.find_withtag("focus")) <= 28


def test_low_zoom_uses_three_item_focus_lod(tk_root):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    app.zoom = 0.3
    focus = Focus(x=1, y=1)

    app._draw_focus(focus, FAR_RECT)

    assert len(app._focus_bundles[focus.id].items) == 3
    assert app._focus_bundles[focus.id].lod == "compact"


def test_wheel_redraw_requests_share_one_tk_job(tk_root, monkeypatch):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    callbacks = []
    monkeypatch.setattr(
        cv,
        "after",
        lambda delay, callback: callbacks.append((delay, callback)) or "after#1",
    )

    app._redraw(RedrawChannel.VIEW, reason="wheel")
    app._redraw(RedrawChannel.VIEW, reason="wheel")

    assert len(callbacks) == 1


def test_full_redraw_cancels_pending_line_job(tk_root, monkeypatch):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    app._lines_job = "after#lines"
    canceled = []
    monkeypatch.setattr(cv, "after_cancel", canceled.append)
    monkeypatch.setattr(cv, "after", lambda delay, callback: "after#frame")

    app._redraw(reason="drag-release")

    assert canceled == ["after#lines"]
    assert app._lines_job is None
