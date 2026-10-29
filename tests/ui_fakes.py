"""One shared host double for headless tests of the UI mixins."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

from hoi4cm.core.undo import UndoStack
from hoi4cm.editor.extra_tree_undo import ExtraTreeUndoHistory
from hoi4cm.models import Focus
from hoi4cm.models.document import FocusDocument
from hoi4cm.ui.canvas import CanvasMixin
from hoi4cm.ui.effects_panel import EffectsMixin
from hoi4cm.ui.mod_loading import ModLoadingMixin


class _FakeTcl:
    def call(self, *_args: object) -> object:
        return ()


class AppFake(CanvasMixin, ModLoadingMixin, EffectsMixin):
    """Shared App-shaped host with overrideable Tk and app callbacks."""

    cv: Any
    _mod_lbl: Any
    _lifecycle: Any

    CANVAS_MIN_SIZE = 10
    CANVAS_EXPAND_STEP = 5

    def __init__(self, focuses=(), cv: Any = None) -> None:
        super().__init__()
        self.focuses = FocusDocument(focuses)
        self.cv = cv if cv is not None else Mock()
        self.offset = [0, 0]
        self.zoom = 1.0
        self.selected = None
        self._extra_trees: list[dict[str, Any]] = []
        self._shared_focuses: list[Focus] = []
        self._joint_focuses: list[Focus] = []
        self._lifecycle = None
        self._validation_worst: dict[int, Any] = {}
        self._cfp_x = None
        self._cfp_y = None
        # Canvas-owned state comes from the shared mixin initializer so the
        # headless contract matches production (canvas.py._init_canvas_state).
        self._init_canvas_state()
        self._default_focus_prefix = ""
        self._config_write_warned = False
        self._mod_image_resource_registered = False
        self._eb_win = None
        self._effects_sig = None
        self._undo_stack = UndoStack()
        self._tree_undo_history = ExtraTreeUndoHistory()
        self._snapshot_extra_tree_state = Mock(return_value=None)
        # Data-member callbacks (the mixin declares them Callable-style), so
        # the override shapes match the host protocols.
        self._schedule_validation = Mock(side_effect=self._count_validation)
        self._select = Mock()
        self._deselect = Mock()
        self._make_mutex = Mock()
        self._end_mutex = Mock()
        self._push_undo = Mock()
        self.__dict__["_draw_lines_throttled"] = Mock()
        self._fv_x = Mock()
        self._fv_y = Mock()
        self._coord_lbl = Mock()
        self._new_focus_at = Mock()
        self._populate = Mock()
        self._hint = Mock()
        self._hide_form = Mock()
        if cv is None:
            self.__dict__["_redraw"] = Mock()
            self.__dict__["_draw_lines"] = Mock()
            self.__dict__["_draw_grid"] = Mock()
        self._refresh_prereqs = Mock()
        self._refresh_mutex = Mock()
        self.__dict__["_refresh_effects"] = Mock()
        self._focus_list_cache = Mock()
        self._save_offsets_to_focus = Mock()
        self._refresh_offsets = Mock()
        self._begin_document_generation = Mock()
        self._invalidate_tree_badges = Mock()
        self._refresh_loaded_trees_panel = Mock()
        self._refresh_tree_meta_panel = Mock()
        self._invalidate_focus_list_structure = Mock()
        self._update_focus_list_selection = Mock()
        self._update_statusbar = Mock()
        self._reset_canvas_bounds()
        self.callbacks: list[Callable[[], None]] = []
        self.loaded_roots: list[str] = []
        self.after_calls: list[tuple[int, Callable[[], None]]] = []
        self.visibility_updates = 0
        self.dropdown_refreshes = 0
        self.status_updates = 0
        self.invalidations = 0
        self.redraws = 0
        self.validation_schedules = 0
        self.tk = _FakeTcl()

    def after(self, _milliseconds: int, callback: Callable[[], None]) -> object:
        self.callbacks.append(callback)
        return callback

    def _count_validation(self) -> None:
        self.validation_schedules += 1

    def after_cancel(self, identifier: object) -> None:
        self.callbacks = [cb for cb in self.callbacks if cb is not identifier]

    def winfo_exists(self) -> int:
        return 1

    def _on_mod_loaded(self, root: str) -> None:
        self.loaded_roots.append(root)

    def _get_mod_suggestions(self, etype: str, fname: str) -> list[str]:
        return ["built_in"]

    def _get_tree_badge(self, _tree_idx: int) -> tuple[str, str]:
        return "", "#374151"

    def flush(self) -> None:
        while self.callbacks:
            self.callbacks.pop(0)()
