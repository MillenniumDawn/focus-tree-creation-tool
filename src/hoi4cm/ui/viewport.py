"""Pure viewport-culling math for the focus-tree canvas.

No tkinter import: this is testable without a display and reusable outside
``CanvasMixin`` (minimap downsampling, a future low-zoom LOD pass, ...).

Vocabulary matches ``canvas.py``'s own ``w2c``/``c2w`` naming: "world"
coords are the HOI4 grid integers stored on a ``Focus`` (``f.x``/``f.y``);
"canvas" coords are the pixels a Tk item is drawn at. ``w2c`` is
``gx * XGRID * zoom + offset_x``, ``gy * YGRID * zoom + offset_y`` — the
functions below invert that to find which world-coord rectangle the current
canvas viewport covers, so culling can compare against raw ``f.x``/``f.y``
without transforming every focus to pixels first.
"""

from hoi4cm.ui.theme import XGRID, YGRID


def visible_world_rect(offset_x, offset_y, zoom, width, height, margin=0.0):
    """World-coord rect covering a ``width`` x ``height`` canvas viewport.

    ``margin`` is in canvas pixels (e.g. ``2 * BOX * zoom``) and is expanded
    on every side before converting to world units, so a card whose center
    is just outside the raw viewport but whose card/label/shadow would still
    paint into it isn't culled. Converted per-axis since ``XGRID`` != ``YGRID``.

    Returns ``(x0, y0, x1, y1)`` with ``x0 <= x1`` and ``y0 <= y1``.
    """
    z = zoom or 1e-9
    mgx = margin / (XGRID * z)
    mgy = margin / (YGRID * z)
    x0 = (-offset_x) / (XGRID * z) - mgx
    x1 = (width - offset_x) / (XGRID * z) + mgx
    y0 = (-offset_y) / (YGRID * z) - mgy
    y1 = (height - offset_y) / (YGRID * z) + mgy
    return (x0, y0, x1, y1)


def focus_visible(fx, fy, rect):
    """True if world point ``(fx, fy)`` falls inside ``rect``."""
    x0, y0, x1, y1 = rect
    return x0 <= fx <= x1 and y0 <= fy <= y1


def edge_visible(ax, ay, bx, by, rect, pad=0.0):
    """True if the padded bbox of an edge overlaps ``rect``.

    Tests the bbox of the two world-coord endpoints, not the endpoints
    themselves: a straight or elbowed connector between two off-screen
    focuses (one far left, one far right) can still cross the viewport, and
    endpoint-only testing would wrongly cull it.
    """
    x0, y0, x1, y1 = rect
    ex0, ex1 = (ax, bx) if ax <= bx else (bx, ax)
    ey0, ey1 = (ay, by) if ay <= by else (by, ay)
    ex0 -= pad
    ey0 -= pad
    ex1 += pad
    ey1 += pad
    return ex0 <= x1 and ex1 >= x0 and ey0 <= y1 and ey1 >= y0


__all__ = ["edge_visible", "focus_visible", "visible_world_rect"]
