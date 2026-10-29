"""Minimap sizing and click-to-pan, driven through the host double."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ui_fakes import AppFake

from hoi4cm.models import Focus
from hoi4cm.ui.theme import XGRID, YGRID

CANVAS_SIZE = (800, 600)


def _minimap_host(focuses, reported_size):
    cv = Mock()
    cv.winfo_width.return_value, cv.winfo_height.return_value = CANVAS_SIZE
    fake = AppFake(focuses, cv=cv)
    mm = Mock()
    mm.winfo_exists.return_value = 1
    mm.winfo_width.return_value, mm.winfo_height.return_value = reported_size
    fake._mm_visible = True
    fake._mm_canvas = mm
    return fake, mm


@pytest.mark.parametrize(
    "reported_size,expected_size",
    [
        ((0, 0), (220, 150)),
        ((1, 1), (220, 150)),
        ((1, 300), (220, 300)),
        ((400, 1), (400, 150)),
        ((400, 300), (400, 300)),
    ],
)
def test_minimap_keeps_each_realized_dimension(reported_size, expected_size):
    fake, _ = _minimap_host(
        [Focus(id=1, x=1, y=1), Focus(id=2, x=2, y=2)], reported_size
    )

    fake._draw_minimap()

    assert fake._mm_content_key[-2:] == expected_size
    width, height = expected_size
    assert fake._mm_scale == pytest.approx(min((width - 20) / 3, (height - 20) / 3))


@pytest.mark.parametrize("index", [0, 1])
def test_minimap_click_on_a_dot_centers_its_focus(monkeypatch, index):
    # Opposite corners of the tree, so the clicks land at the content extremes.
    focuses = [Focus(id=1, x=-3, y=4), Focus(id=2, x=9, y=-2)]
    fake, mm = _minimap_host(focuses, (1, 1))
    monkeypatch.setattr(fake, "_redraw_now", Mock())

    fake._draw_minimap()

    dots = [
        call.args
        for call in mm.create_rectangle.call_args_list
        if call.kwargs.get("tags") == "mm_content"
    ]
    left, top, right, bottom = dots[index]
    fake._mm_click(SimpleNamespace(x=(left + right) / 2, y=(top + bottom) / 2))

    focus = focuses[index]
    assert fake.offset[0] == pytest.approx(
        CANVAS_SIZE[0] / 2 - focus.x * XGRID * fake.zoom
    )
    assert fake.offset[1] == pytest.approx(
        CANVAS_SIZE[1] / 2 - focus.y * YGRID * fake.zoom
    )
