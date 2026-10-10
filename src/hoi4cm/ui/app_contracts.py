"""Structural state contracts for the UI mixins hosted by ``App``.

These protocols describe the state shared at the mixin boundary.  Keeping the
common, persistent state here makes an absent or renamed host attribute a type
error instead of a silent default from ``getattr``.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Protocol

from hoi4cm.models import Focus, FocusDocument
from hoi4cm.ui.image_broker import ImageBroker
from hoi4cm.ui.lifecycle import ApplicationLifecycle


class CanvasHost(Protocol):
    """State required by the canvas interaction and drawing mixin."""

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
    _validation_worst: dict[int, Any]
    _lifecycle: ApplicationLifecycle | None
    _image_broker: ImageBroker | None


class EffectsHost(Protocol):
    """State required by the sidebar effects mixin."""

    selected: Focus | None
    _eb_win: tk.Toplevel | None
    _effects_sig: object | None


class ModLoadingHost(Protocol):
    """State required by the mod-loading mixin."""

    _mod_lbl: Any
    cv: Any
    _focus_bundles: dict[int, Any]
    _lifecycle: ApplicationLifecycle | None
    _config_write_warned: bool
    _mod_image_resource_registered: bool
