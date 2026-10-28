"""Structural state contracts for the UI mixins hosted by ``App``.

These protocols describe the state shared at the mixin boundary.  Keeping the
common, persistent state here makes an absent or renamed host attribute a type
error instead of a silent default from ``getattr``.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Any, Protocol

from hoi4cm.focus_tree.validate import Severity
from hoi4cm.models import Focus, FocusDocument
from hoi4cm.ui.canvas_renderer import FocusCanvasBundle
from hoi4cm.ui.canvas_scheduler import DirtyRedrawState
from hoi4cm.ui.image_broker import ImageBroker
from hoi4cm.ui.lifecycle import ApplicationLifecycle
from hoi4cm.ui.scene_index import SceneIndex

# ``cv.after`` returns the Tcl job id that ``after_cancel`` round-trips.
type AfterJob = str
# Pooled-frame cache keys: each captures the inputs its generation depends
# on; ``None`` means "nothing generated yet".
type LinesKey = tuple[
    float, float, float, int, tuple[float, float, float, float] | None
]
type GridKey = tuple[
    bool, float, tuple[int, ...], tuple[int, ...], float, float, int, int
]
type CoordLabelKey = tuple[int, int, float, tuple[float, ...]]
type LegendKey = tuple[int, tuple[tuple[str, str], ...]]
type LegendStackKey = tuple[int, float, tuple[float, ...], int | None]
type CfpPair = tuple[int | None, int | None]
type MinimapBoundsKey = tuple[int, tuple[int | None, int | None, tuple[CfpPair, ...]]]


class CanvasHost(Protocol):
    """State required by the canvas interaction and drawing mixin.

    ``CanvasMixin`` binds this protocol as a type-check-time base only (the
    runtime mixin chain keeps ``Protocol`` out of ``App``'s MRO — see
    ``tests/test_app_mixin_mro.py``). Host-provided callbacks are declared
    as ``Callable`` data members so hosts that define methods or Mocks both
    satisfy them.
    """

    # Host sizing constants every subclass carries.
    CANVAS_MIN_SIZE: int
    CANVAS_EXPAND_STEP: int

    cv: tk.Canvas
    focuses: FocusDocument
    offset: list[float]
    zoom: float
    selected: Focus | None
    _multi_sel: set[int]
    _multisel_mode: bool
    mutex_src: Focus | None
    mutex_mode: bool
    _canvas_min: list[int]
    _canvas_max: list[int]
    _extra_trees: list[dict[str, Any]]
    _grid_on: bool
    _validation_worst: dict[int, Severity]
    _lifecycle: ApplicationLifecycle | None
    _image_broker: ImageBroker | None
    # Shared with the mod-loading mixin (bundle reclamation, image releases).
    _focus_bundles: dict[int, FocusCanvasBundle]
    _push_undo: Callable[..., object]
    _lines: list[int]
    _lines_used: int
    _lines_key: LinesKey | None
    _temp_line: int | None
    _pan_start: tuple[int, int] | None
    _drag: dict[str, Any]
    _redraw_state: DirtyRedrawState
    _redraw_pending: bool
    _redraw_job: AfterJob | None
    _lines_job: AfterJob | None
    _scene_index: SceneIndex
    _canvas_probe: int
    _rendering_frame: bool
    _focus_line_stack_dirty: bool
    _grid_pool: list[int]
    _grid_used: int
    _grid_key: GridKey | None
    _grid_item: int | None
    _coord_label_pools: dict[str, list[int]]
    _coord_label_styles: dict[str, list[dict[str, Any]]]
    _coord_label_used: dict[str, int]
    _coord_label_key: CoordLabelKey | None
    _legend_pool: list[int]
    _legend_used: int
    _legend_key: LegendKey | None
    _legend_stack_key: LegendStackKey | None
    # Host-owned document values the canvas draws (None = not set).
    _cfp_x: int | None
    _cfp_y: int | None
    _mm_visible: bool
    # Optional Tk handle until first show; pooled minimap content.
    _mm_canvas: tk.Canvas | None
    _mm_line_pool: list[int]
    _mm_line_used: int
    _mm_dot_pool: list[int]
    _mm_dot_used: int
    _mm_bounds_key: MinimapBoundsKey | None
    _mm_content_key: tuple[MinimapBoundsKey, int, int] | None
    _mm_world_bounds: tuple[float, float, float, float]
    # Geometry caches, None until the first render while the overlay shows.
    _mm_scale: float | None
    _mm_min_x: float | None
    _mm_min_y: float | None
    _mm_ox: float | None
    _mm_oy: float | None
    _image_poll_job: AfterJob | None
    _focus_bounds_cache: tuple[int | None, tuple[int, ...] | None]
    _fv_x: tk.StringVar
    _fv_y: tk.StringVar
    _coord_lbl: tk.Label
    # Host-provided callbacks (methods on the host, Mocks in test doubles).
    _select: Callable[..., None]
    _deselect: Callable[..., None]
    _make_mutex: Callable[..., None]
    _end_mutex: Callable[..., None]
    _new_focus_at: Callable[..., None]
    _hint: Callable[..., None]
    _get_tree_badge: Callable[..., tuple[str, str]]
    _update_statusbar: Callable[..., None]
    _update_focus_list_selection: Callable[..., None]


class EffectsHost(Protocol):
    """State required by the sidebar effects mixin."""

    selected: Focus | None
    _eb_win: tk.Toplevel | None
    _effects_sig: object | None


class ModLoadingHost(Protocol):
    """State required by the mod-loading mixin."""

    _mod_lbl: tk.Label
    cv: tk.Canvas
    _focus_bundles: dict[int, FocusCanvasBundle]
    _lifecycle: ApplicationLifecycle | None
    _config_write_warned: bool
    _mod_image_resource_registered: bool

    def _schedule_validation(self) -> None: ...
