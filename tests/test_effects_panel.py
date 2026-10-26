"""Tests for the effects-panel refresh-skip optimization.

The signature drives whether ``_refresh_effects`` tears down and rebuilds the
effect cards. It covers everything a card renders, so a match means a rebuild
would draw the same thing. These tests pin that contract, including that it
survives CPython recycling a freed focus's memory address.

Tests ``test_*raw*`` exercise the raw-effect key/value row wiring (:class:`
_RawFieldRow`) headlessly through the :class:`ui_fakes.AppFake` mixin host,
including undo coalescing via a real :class:`UndoStack`.
"""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

from ui_fakes import AppFake

import hoi4_content_maker as app_module
from hoi4cm.core.undo import UndoStack
from hoi4cm.models import Focus
from hoi4cm.ui.effects_panel import (
    _effects_signature,
    _next_unused_raw_key,
    _RawFieldRow,
)


class _FakeVar:
    """StringVar stand-in whose writes fire the bound write trace, like Tk."""

    def __init__(self, value=""):
        self.value = value
        self.on_write: Callable[[], Any] | None = None

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        if self.on_write is not None:
            self.on_write()


def _focus(effects, fid="focus_a"):
    return SimpleNamespace(id=fid, effects=effects)


def test_signature_changes_on_value_edit():
    eff = {"type": "add_war_support", "fields": {"value": "0.1"}}
    focus = _focus([eff])
    before = _effects_signature(focus, focus.effects)
    eff["fields"]["value"] = "0.5"
    assert _effects_signature(focus, focus.effects) != before


def test_signature_matches_identical_content():
    """Equal content is the whole key — fresh dicts holding it must still match."""
    focus = _focus([{"type": "add_war_support", "fields": {"value": "0.1"}}])
    before = _effects_signature(focus, focus.effects)
    focus.effects = [{"type": "add_war_support", "fields": {"value": "0.1"}}]
    assert _effects_signature(focus, focus.effects) == before


def test_signature_changes_on_field_key_added():
    """The add-field action adds a key to the same dict; must force a rebuild."""
    eff = {"type": "_raw_block", "fields": {"raw": "x"}}
    focus = _focus([eff])
    before = _effects_signature(focus, focus.effects)
    eff["fields"]["key1"] = "value"
    assert _effects_signature(focus, focus.effects) != before


def test_signature_changes_on_type_change():
    eff = {"type": "add_war_support", "fields": {}}
    focus = _focus([eff])
    before = _effects_signature(focus, focus.effects)
    eff["type"] = "add_stability"
    assert _effects_signature(focus, focus.effects) != before


def test_signature_changes_on_focus_change():
    """Two focuses with identical effects still differ by focus id."""
    eff = {"type": "add_war_support", "fields": {}}
    assert _effects_signature(_focus([eff], "a"), [eff]) != _effects_signature(
        _focus([eff], "b"), [eff]
    )


def test_signature_survives_address_reuse():
    """A freed focus's memory address must not alias onto its replacement.

    CPython hands the same address back for the next object of that size, so
    keying on ``id()`` let a reloaded tree reuse a stale signature and skip
    the rebuild, leaving the sidebar bound to the previous focus's data.
    """
    a = _focus([{"type": "add_war_support", "fields": {"value": "0.1"}}], "a")
    before = _effects_signature(a, a.effects)
    del a
    b = _focus([{"type": "add_war_support", "fields": {"value": "0.9"}}], "b")
    assert _effects_signature(b, b.effects) != before


# ── Raw-effect key/value rows ─────────────────────────────────────────────


def _as_app(app: AppFake) -> app_module.App:
    return cast(app_module.App, app)


def _fields(focus):
    """The field dict of the raw effect under test, narrowed for assertions."""
    fields = focus.effects[0]["fields"]
    assert isinstance(fields, dict)
    return fields


def _raw_app(fields):
    """A headless effects-panel host holding one raw effect with ``fields``."""
    focus = Focus(id=7)
    focus.effects = [{"type": "custom_imported", "fields": dict(fields)}]
    app = AppFake([focus])
    app.selected = focus
    app._undo_stack = UndoStack()

    def push_undo(label="action", touched_ids=None, run=None):
        app_module.App._push_undo(_as_app(app), label, touched_ids, run=run)

    app._push_undo = push_undo
    return app, focus


def _wired_row(app, key):
    """A raw row state with key/value vars wired exactly like ``_entry_row``."""
    row = _RawFieldRow(app, 0, key)
    kvar = _FakeVar(key)
    kvar.on_write = lambda: row.on_key_text(kvar)
    vvar = _FakeVar()
    vvar.on_write = lambda: row.on_value_text(vvar)
    return row, kvar, vvar


def test_full_typed_key_name_is_one_undo_run():
    """A keystroke stream renames once: one run, restored by a single undo."""
    app, focus = _raw_app({"old": "1"})
    _row, kvar, _vvar = _wired_row(app, "old")
    for text in ("n", "ne", "new"):
        kvar.set(text)

    assert _fields(focus) == {"new": "1"}
    assert len(app._undo_stack) == 1
    result = app._undo_stack.undo(app.focuses, Focus.from_dict)
    assert result is not None
    assert result[0] == "edit effect"
    assert _fields(app.focuses[7]) == {"old": "1"}


def test_value_edit_targets_latest_valid_renamed_key():
    """Value edits must follow the renamed key, never resurrect the old one."""
    app, focus = _raw_app({"old": "1"})
    _row, kvar, vvar = _wired_row(app, "old")
    kvar.set("new")
    revision = app.focuses.content_revision
    vvar.set("5")

    assert _fields(focus) == {"new": "5"}
    assert app.focuses.content_revision > revision
    assert len(app._undo_stack) == 2  # rename run + value run stay separate


def test_rejected_collision_then_value_edit_then_continuing_rename():
    """A colliding rename keeps both fields, and editing continues cleanly."""
    app, focus = _raw_app({"old": "1", "taken": "2"})
    _row, kvar, vvar = _wired_row(app, "old")
    revision = app.focuses.content_revision

    kvar.set("taken")

    assert kvar.value == "old"  # entry text restored to the committed key
    assert _fields(focus) == {"old": "1", "taken": "2"}
    assert len(app._undo_stack) == 0
    assert app.focuses.content_revision == revision

    vvar.set("9")

    assert _fields(focus) == {"old": "9", "taken": "2"}

    kvar.set("renamed")

    assert _fields(focus) == {"renamed": "9", "taken": "2"}
    assert kvar.value == "renamed"
    assert len(app._undo_stack) == 2


def test_rename_keeps_the_field_slot_order():
    """Renaming must not shove the row to the end of the card and export."""
    app, focus = _raw_app({"a": "1", "b": "2", "c": "3"})
    _row, kvar, _vvar = _wired_row(app, "b")
    kvar.set("x")

    assert list(_fields(focus)) == ["a", "x", "c"]


def test_add_raw_effect_field_picks_unused_key():
    """Adding a field must never overwrite an existing ``keyN``."""
    app, focus = _raw_app({"key0": "0", "key2": "2"})
    app._add_raw_effect_field(0)

    fields = _fields(focus)
    assert fields == {"key0": "0", "key2": "2", "key1": "value"}

    app._add_raw_effect_field(0)

    assert "key3" in fields


def test_next_unused_raw_key_scans_for_free_name():
    assert _next_unused_raw_key({}) == "key0"
    assert _next_unused_raw_key({"foo": 1}) == "key0"
    assert _next_unused_raw_key({"key0": ""}) == "key1"
    assert _next_unused_raw_key({"key0": "", "key2": ""}) == "key1"
