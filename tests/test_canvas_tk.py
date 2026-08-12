"""Tests for CanvasMixin's viewport culling and per-frame bookkeeping.

Needs a real Tk display to create canvas items (CI supplies one via Xvfb,
see testing.md); the shared `tk_root` fixture skips the module on a
headless dev box.
"""

import tkinter as tk

import pytest

from hoi4cm.models import Focus
from hoi4cm.models.document import FocusDocument
from hoi4cm.ui.canvas import CanvasMixin
from hoi4cm.ui.canvas_scheduler import RedrawChannel
from hoi4cm.ui.theme import XGRID

FAR_RECT = (0.0, 0.0, 10.0, 10.0)
NEAR_RECT = (490.0, 490.0, 510.0, 510.0)
GRID_W, GRID_H = 400, 300


@pytest.fixture
def tk_root(tk_root):
    """Hidden root: these tests drive canvas items, not real geometry."""
    tk_root.withdraw()
    return tk_root


class _FakeApp(CanvasMixin):
    """Bare host exposing just the attributes _draw_focus/_draw_lines touch."""

    CANVAS_MIN_SIZE = 10
    CANVAS_EXPAND_STEP = 5

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
        self._lines = []
        self._grid_on = True
        self._grid_key = None
        self._grid_item = None
        # _reset_canvas_bounds sets these, but spelling them out here keeps
        # them declared on the class for the tests that widen the bounds.
        self._canvas_min = [0, 0]
        self._canvas_max = [self.CANVAS_MIN_SIZE - 1, self.CANVAS_MIN_SIZE - 1]
        self._reset_canvas_bounds()

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


def test_draw_key_updates_changed_icon(tk_root):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    f = Focus(x=5, y=5)

    app._draw_focus(f, FAR_RECT)
    icon_item = app._focus_bundles[f.id].items[8]
    f.icon = "X"
    app._draw_focus(f, FAR_RECT)

    assert cv.itemcget(icon_item, "text") == "X"


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


def _grow_by_scanning_every_focus(app):
    """The pre-bbox implementation, kept as the oracle for the bbox one."""
    changed = False
    for f in app.focuses.values():
        if app._ensure_canvas_contains(f.x, f.y):
            changed = True
    return changed


@pytest.mark.parametrize(
    "positions",
    [
        [(0, 0)],
        [(3, 4), (-7, 2), (11, -9)],
        [(-40, 0), (40, 39), (0, 0), (9, 9), (10, 10)],
        [(-100, -100), (100, 100)],
        [(5, 5), (5, 5), (5, 5)],
    ],
)
def test_bbox_growth_lands_on_the_same_bounds_as_scanning_every_focus(
    tk_root, positions
):
    cv = tk.Canvas(tk_root, width=200, height=200)
    reference = _FakeApp(cv)
    app = _FakeApp(cv)
    focuses = [Focus(x, y) for x, y in positions]
    reference.focuses = {f.id: f for f in focuses}
    app.focuses = FocusDocument(focuses)

    assert app._grow_canvas_to_focuses() == _grow_by_scanning_every_focus(reference)
    assert app._canvas_min == reference._canvas_min
    assert app._canvas_max == reference._canvas_max


def test_focus_bounds_are_recomputed_when_the_document_revision_moves(tk_root):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    focus = Focus(1, 1)
    app.focuses = FocusDocument([focus])

    assert app._focus_bounds() == (1, 1, 1, 1)

    app.focuses.move(focus.id, 25, 30)

    assert app._focus_bounds() == (25, 30, 25, 30)
    assert app._grow_canvas_to_focuses() is True
    assert app._canvas_max[0] > 25 and app._canvas_max[1] > 30


def test_focus_bounds_reuses_the_cache_while_the_revision_holds(tk_root):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    focus = Focus(1, 1)
    app.focuses = FocusDocument([focus])
    app._focus_bounds()

    focus.x = 99  # direct field edit, so no revision bump

    assert app._focus_bounds() == (1, 1, 1, 1)  # cached, not rescanned
    app.focuses.touch()
    assert app._focus_bounds() == (99, 1, 99, 1)


def test_focus_bounds_of_an_empty_document_grows_nothing(tk_root):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    app.focuses = FocusDocument()
    bounds = list(app._canvas_min), list(app._canvas_max)

    assert app._focus_bounds() is None
    assert app._grow_canvas_to_focuses() is False
    assert (app._canvas_min, app._canvas_max) == bounds


def _grid_lines(cv):
    return [
        item
        for item in cv.find_withtag("grid")
        if cv.itemcget(item, "state") != "hidden"
    ]


@pytest.fixture
def mapped_canvas(tk_root):
    """A canvas with real dimensions — the grid only clips once it has some."""
    tk_root.deiconify()
    cv = tk.Canvas(tk_root, width=GRID_W, height=GRID_H)
    cv.pack()
    tk_root.update()
    if cv.winfo_width() <= 1 or cv.winfo_height() <= 1:
        pytest.fail("canvas never mapped, so there is no viewport to clip to")
    return cv


def test_grid_covers_the_viewport_without_drawing_the_whole_canvas_extent(
    mapped_canvas,
):
    cv = mapped_canvas
    app = _FakeApp(cv)
    app._canvas_min = [-500, -500]
    app._canvas_max = [500, 500]

    app._draw_grid()

    visible = _grid_lines(cv)
    # 1002 vertical + 1002 horizontal boundaries span the extent; the viewport
    # plus a screen of margin on each side needs a couple of dozen.
    assert 4 <= len(visible) <= 60
    verticals = {
        round(cv.coords(item)[0])
        for item in visible
        if cv.coords(item)[0] == cv.coords(item)[2]
    }
    # Every vertical boundary actually on screen has a line on it.
    step = XGRID * app.zoom
    on_screen = [
        round(gx * step + app.offset[0] - step / 2)
        for gx in range(-2, int(GRID_W / step) + 3)
    ]
    assert [px for px in on_screen if 0 <= px <= GRID_W]
    for px in on_screen:
        if 0 <= px <= GRID_W:
            assert px in verticals


def test_grid_reuses_its_line_items_across_regenerations(mapped_canvas):
    cv = mapped_canvas
    app = _FakeApp(cv)

    app._draw_grid()
    first = list(cv.find_withtag("grid"))
    app.zoom = 1.5
    app._draw_grid()
    second = list(cv.find_withtag("grid"))

    assert first, "expected a grid at zoom 1.0"
    assert set(first) <= set(second)  # pooled, not deleted and recreated


def test_grid_shrinking_hides_the_surplus_lines(mapped_canvas):
    cv = mapped_canvas
    app = _FakeApp(cv)
    app._canvas_min = [-500, -500]
    app._canvas_max = [500, 500]

    app._draw_grid()
    wide = len(_grid_lines(cv))
    app.zoom = 4.0  # each cell is far bigger, so far fewer boundaries fit
    app._draw_grid()
    narrow = len(_grid_lines(cv))

    assert narrow < wide
    assert len(cv.find_withtag("grid")) == wide  # pool kept, surplus hidden


def test_grid_regenerates_after_the_canvas_is_cleared(mapped_canvas):
    cv = mapped_canvas
    app = _FakeApp(cv)
    app._draw_grid()
    assert _grid_lines(cv)

    cv.delete("all")  # what a new/clear-document does
    app._draw_grid()

    assert _grid_lines(cv)


def test_grid_toggled_off_hides_every_line(mapped_canvas):
    cv = mapped_canvas
    app = _FakeApp(cv)
    app._draw_grid()
    assert _grid_lines(cv)

    app._grid_on = False
    app._draw_grid()

    assert _grid_lines(cv) == []


def test_unmapped_canvas_still_gets_a_grid_over_the_whole_extent(tk_root):
    cv = tk.Canvas(tk_root, width=200, height=200)  # withdrawn root: winfo_* == 1
    app = _FakeApp(cv)

    app._draw_grid()

    # 11 vertical + 11 horizontal boundaries for the default 10x10 canvas.
    assert len(_grid_lines(cv)) == 22


def _linked_chain(count, *, spacing=1):
    focuses = [Focus(index * spacing, 0) for index in range(count)]
    for previous, focus in zip(focuses, focuses[1:], strict=False):
        focus.prereqs = [[previous.id]]
    return focuses


def test_narrow_frame_hides_the_lines_the_wide_frame_left_behind(tk_root):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    app.focuses = FocusDocument(_linked_chain(40))

    app._draw_lines((-1.0, -1.0, 100.0, 1.0))  # every edge visible
    wide_used = app._lines_used
    app._draw_lines((-1.0, -1.0, 2.0, 1.0))  # only the first couple of edges

    assert app._lines_used < wide_used
    assert all(
        cv.itemcget(item, "state") == "hidden"
        for item in app._lines[app._lines_used : wide_used]
    )


def test_surplus_lines_are_hidden_once_not_once_per_frame(tk_root, monkeypatch):
    cv = tk.Canvas(tk_root, width=200, height=200)
    app = _FakeApp(cv)
    app.focuses = FocusDocument(_linked_chain(40))
    app._draw_lines((-1.0, -1.0, 100.0, 1.0))  # grow the pool to 40 edges
    pool = len(app._lines)
    narrow = (-1.0, -1.0, 2.0, 1.0)
    app._draw_lines(narrow)  # hides the surplus once
    assert app._lines_used < pool

    hidden = []
    original = cv.itemconfig

    def counting_itemconfig(item, **kwargs):
        if kwargs.get("state") == "hidden":
            hidden.append(item)
        return original(item, **kwargs)

    monkeypatch.setattr(cv, "itemconfig", counting_itemconfig)
    app._draw_lines(narrow)

    # The surplus is already hidden; a steady frame must not walk it again.
    # (Nothing here is a mutex edge, so no arrowhead gets hidden either.)
    assert hidden == []


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
