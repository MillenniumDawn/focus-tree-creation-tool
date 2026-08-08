"""Tests for the effects-panel refresh-skip optimization.

The signature drives whether ``_refresh_effects`` tears down and rebuilds the
effect cards. It must be stable across value edits (so live-typing doesn't
rebuild) and change on any structural change (add/remove/undo, new field
key, type change, different focus). These tests pin that contract.
"""

import tkinter as tk
from types import SimpleNamespace

from hoi4cm.mod import MOD
from hoi4cm.ui.effects_panel import EffectsMixin, _effects_signature


def _focus(effects):
    return SimpleNamespace(effects=effects)


def test_signature_stable_across_value_edits():
    """A live-edit to a field value must not change the signature."""
    eff = {"type": "add_war_support", "fields": {"value": "0.1"}}
    focus = _focus([eff])
    before = _effects_signature(focus, focus.effects)
    eff["fields"]["value"] = "0.5"
    assert _effects_signature(focus, focus.effects) == before


def test_signature_changes_on_new_effect_object():
    """Undo/load replaces effect dicts; the signature must differ."""
    focus = _focus([{"type": "add_war_support", "fields": {"value": "0.1"}}])
    before = _effects_signature(focus, focus.effects)
    focus.effects = [{"type": "add_war_support", "fields": {"value": "0.1"}}]
    assert _effects_signature(focus, focus.effects) != before


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
    """Different focus objects (even with identical effects) must differ."""
    eff = {"type": "add_war_support", "fields": {}}
    assert _effects_signature(_focus([eff]), [eff]) != _effects_signature(
        _focus([eff]), [eff]
    )


class _Harness(EffectsMixin):
    def __init__(self, root):
        self._eff_box = tk.Frame(root)
        self.selected: object | None = None
        self._effects_sig = None


def test_refresh_effects_skips_rebuild_when_unchanged(tk_root, monkeypatch):
    """Re-rendering the same effects must not tear down and rebuild the cards."""
    h = _Harness(tk_root)
    calls = []
    monkeypatch.setattr(h, "_draw_eff_card", lambda i, eff: calls.append(i))
    h.selected = _focus([{"type": "add_war_support", "fields": {"value": "0.1"}}])
    h._refresh_effects()
    assert calls == [0]
    h._refresh_effects()  # unchanged -> skip
    assert calls == [0]


def test_refresh_effects_rebuilds_when_forced(tk_root, monkeypatch):
    """force=True must rebuild even when the signature is unchanged."""
    h = _Harness(tk_root)
    calls = []
    monkeypatch.setattr(h, "_draw_eff_card", lambda i, eff: calls.append(i))
    h.selected = _focus([{"type": "add_war_support", "fields": {"value": "0.1"}}])
    h._refresh_effects()
    h._refresh_effects(force=True)
    assert calls == [0, 0]


def test_refresh_effects_rebuilds_when_flag_disabled(tk_root, monkeypatch):
    """sidebar_refresh_skip=False must disable the skip entirely."""
    h = _Harness(tk_root)
    calls = []
    monkeypatch.setattr(h, "_draw_eff_card", lambda i, eff: calls.append(i))
    h.selected = _focus([{"type": "add_war_support", "fields": {"value": "0.1"}}])
    monkeypatch.setattr(MOD, "sidebar_refresh_skip", False)
    h._refresh_effects()
    h._refresh_effects()
    assert calls == [0, 0]
