"""Headless regression tests: typed canvas-owned state created once per host
by ``_init_canvas_state`` (defaults, isolation, no re-construction on redraw,
optional minimap handles)."""

from __future__ import annotations

import tkinter as tk
from unittest.mock import Mock, call

from ui_fakes import AppFake


def _contract_defaults() -> dict[str, object]:
    return {
        "_multi_sel": set(),
        "_multisel_mode": False,
        "mutex_src": None,
        "mutex_mode": False,
        "_lines": [],
        "_lines_used": 0,
        "_lines_key": None,
        "_temp_line": None,
        "_pan_start": None,
        "_drag": {},
        "_grid_on": True,
        "_grid_pool": [],
        "_grid_used": 0,
        "_grid_key": None,
        "_grid_item": None,
        "_redraw_pending": False,
        "_redraw_job": None,
        "_lines_job": None,
        "_rendering_frame": False,
        "_focus_line_stack_dirty": False,
        "_coord_label_key": None,
        "_legend_used": 0,
        "_legend_key": None,
        "_legend_stack_key": None,
        "_cfp_x": None,
        "_cfp_y": None,
        "_mm_visible": False,
        "_mm_canvas": None,
        "_mm_line_pool": [],
        "_mm_line_used": 0,
        "_mm_dot_pool": [],
        "_mm_dot_used": 0,
        "_mm_bounds_key": None,
        "_mm_content_key": None,
        "_mm_world_bounds": (0.0, 0.0, 0.0, 0.0),
        "_mm_scale": None,
        "_mm_min_x": None,
        "_mm_min_y": None,
        "_mm_ox": None,
        "_mm_oy": None,
        "_image_broker": None,
        "_image_poll_job": None,
        "_focus_bounds_cache": (None, None),
    }


def test_init_canvas_state_produces_protocol_defaults():
    fake = AppFake()
    for attribute, default in _contract_defaults().items():
        assert getattr(fake, attribute) == default, attribute


def test_init_canvas_state_is_per_instance_shared_with_hosts():
    first = AppFake()
    second = AppFake()
    for attribute in (
        "_multi_sel",
        "_lines",
        "_drag",
        "_grid_pool",
        "_legend_pool",
        "_coord_label_pools",
        "_coord_label_styles",
        "_coord_label_used",
        "_mm_line_pool",
        "_mm_dot_pool",
        "_scene_index",
        "_redraw_state",
        "_focus_bundles",
    ):
        assert getattr(first, attribute) is not getattr(second, attribute), attribute


def test_canvas_runtime_objects_created_once_per_instance():
    """A real draw-path call must reuse, not rebuild, the scheduler/probe."""
    state = AppFake()._redraw_state
    fake = AppFake(cv=Mock())
    assert fake._redraw_state is not state  # per-instance, not shared
    scene = fake._scene_index
    probe = fake._canvas_probe
    redraw_state = fake._redraw_state
    for _ in range(2):
        fake._draw_lines((0, 0, 400, 400))
        assert fake._redraw_state is redraw_state
        assert fake._scene_index is scene
        assert fake._canvas_probe is probe
        assert fake._lines_key is not None  # the draw ran through this state


def test_grid_toggle_only_invalidates_its_own_cache():
    fake = AppFake()
    fake._redraw_job = "job"
    fake._grid_key = (True, 1.0, (0, 0), (9, 9), 0.0, 0.0, 800, 600)
    fake._legend_key = (3, (("a", "#111111"),))
    fake._toggle_grid()
    assert fake._grid_on is False
    assert fake._grid_key is None
    assert fake._redraw_job == "job"
    assert fake._legend_key == (3, (("a", "#111111"),))


def test_optional_minimap_handles_stay_optional_until_used():
    fake = AppFake()
    fake._draw_minimap()
    assert fake._mm_visible is False
    assert fake._mm_canvas is None
    assert fake._mm_scale is None


def test_visible_minimap_without_a_canvas_does_not_create_one():
    fake = AppFake(cv=Mock())
    fake._mm_visible = True
    fake._draw_minimap()
    assert fake._mm_canvas is None


def test_minimap_dead_canvas_is_a_silent_no_op():
    """A destroyed minimap widget swallows tk.TclError (original semantics)."""
    fake = AppFake()
    dead = Mock(winfo_exists=Mock(side_effect=tk.TclError("destroyed")))
    fake._mm_visible = True
    fake._mm_canvas = dead
    fake._draw_minimap()
    assert dead.delete.call_count == 0


def test_close_canvas_tasks_cancels_and_clears_jobs():
    fake = AppFake(cv=Mock())
    fake._image_poll_job = "job-image"
    fake._redraw_job = "job-redraw"
    fake._lines_job = "job-lines"
    broker = Mock()
    fake._image_broker = broker
    fake._close_canvas_tasks()
    assert fake.cv.after_cancel.call_args_list == [
        call("job-image"),
        call("job-redraw"),
        call("job-lines"),
    ]
    broker.close.assert_called_once_with()
    assert fake._image_poll_job is None
    assert fake._redraw_job is None
    assert fake._lines_job is None


def test_close_canvas_tasks_finishes_after_a_cancel_error():
    fake = AppFake(cv=Mock())
    fake._image_poll_job = "job-image"
    fake._redraw_job = "job-redraw"
    fake._lines_job = "job-lines"
    fake.cv.after_cancel.side_effect = [tk.TclError("already deleted"), None, None]
    broker = Mock()
    fake._image_broker = broker

    fake._close_canvas_tasks()

    assert fake.cv.after_cancel.call_args_list == [
        call("job-image"),
        call("job-redraw"),
        call("job-lines"),
    ]
    assert fake._image_poll_job is None
    assert fake._redraw_job is None
    assert fake._lines_job is None
    broker.close.assert_called_once_with()


def test_validate_canvas_probe_resets_pools_not_scheduler():
    fake = AppFake(cv=Mock())
    # Distinct sentinel ids per create: the Mock would otherwise hand back
    # the same object twice.
    fake.cv.create_line = Mock(side_effect=[1, 2])
    fake._init_canvas_state()
    stale_probe = fake._canvas_probe
    stale_scene = fake._scene_index
    stale_state = fake._redraw_state
    # Simulate a stale probe: the sentinel check reports "missing".
    fake._canvas_item_exists = Mock(return_value=False)
    fake._lines_used = 3
    fake._grid_used = 5
    fake._validate_canvas_probe()
    # The stale probe was checked exactly once, then really recreated.
    assert fake._canvas_item_exists.call_args_list[-1].args == (stale_probe,)
    assert fake._canvas_probe == 2
    assert fake._canvas_probe is not stale_probe
    assert fake._lines_used == 0
    assert fake._grid_used == 0
    # The scheduler objects were reused, not rebuilt.
    assert fake._scene_index is stale_scene
    assert fake._redraw_state is stale_state
