"""Tests for the effects-panel refresh-skip optimization.

The signature drives whether ``_refresh_effects`` tears down and rebuilds the
effect cards. It covers everything a card renders, so a match means a rebuild
would draw the same thing. These tests pin that contract, including that it
survives CPython recycling a freed focus's memory address.
"""

import tkinter as tk
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from hoi4cm.core.undo import UndoStack
from hoi4cm.mod import MOD
from hoi4cm.models import Focus, FocusDocument
from hoi4cm.ui.effects_panel import EffectsMixin, _effects_signature


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


class _Harness(EffectsMixin, tk.Frame):
    def __init__(self, root):
        tk.Frame.__init__(self, root)
        self._eff_box = tk.Frame(self)
        self._eff_box.pack()
        self.focuses = FocusDocument()
        self.selected: Focus | SimpleNamespace | None = None
        self._effects_sig = None
        self._undo_stack = UndoStack()
        self._focus_list_cache = Mock()
        self._invalidate_focus_list_structure = Mock()
        self._hint = Mock()
        self._flash_added = Mock()

    def _get_mod_suggestions(self, etype, fname):
        return []

    def _mk_btn(self, parent, text, cmd=None, **kwargs):
        return tk.Button(parent, text=text, command=cmd or (lambda: None))

    def _push_undo(self, label="action", touched_ids=None):
        self._undo_stack.push(label, self.focuses, touched_ids)


def _descendants(widget, kind):
    found = []
    for child in widget.winfo_children():
        if isinstance(child, kind):
            found.append(child)
        found.extend(_descendants(child, kind))
    return found


def _confirm_parameter_dialog(harness, key, value=None):
    harness._open_effect_params(key)
    dialogs = [
        child for child in _descendants(harness, tk.Toplevel) if child.winfo_exists()
    ]
    assert len(dialogs) == 1
    dialog = dialogs[0]
    entries = _descendants(dialog, tk.Entry)
    assert len(entries) == 1
    if value is not None:
        entries[0].delete(0, "end")
        entries[0].insert(0, value)
    add_button = next(
        button
        for button in _descendants(dialog, tk.Button)
        if "Add Effect" in button.cget("text")
    )
    add_button.invoke()


def test_add_effect_defaults_snapshots_and_restores_focus(tk_root, monkeypatch):
    monkeypatch.setattr(MOD, "loaded", False)
    focus = Focus()
    focus.effects = [{"type": "add_ideas", "fields": {"idea_name": "old"}}]
    harness = _Harness(tk_root)
    harness.focuses = FocusDocument([focus])
    harness.selected = focus
    before = deepcopy(focus.to_dict())

    harness._add_effect_type("add_war_support")

    assert focus.effects[-1] == {
        "type": "add_war_support",
        "fields": {"amount": "0.05"},
    }
    entry = harness._undo_stack._stack[-1]
    assert entry[0] == "add effect"
    assert entry[2][focus.id] == before
    harness._focus_list_cache.invalidate.assert_called_once_with()
    harness._invalidate_focus_list_structure.assert_called_once_with()

    result = harness._undo_stack.undo(harness.focuses, Focus.from_dict)
    assert result == ("add effect", {focus.id}, set())
    assert harness.focuses[focus.id].to_dict() == before


def test_add_effect_copies_supplied_fields(tk_root, monkeypatch):
    monkeypatch.setattr(MOD, "loaded", False)
    focus = Focus()
    harness = _Harness(tk_root)
    harness.focuses = FocusDocument([focus])
    harness.selected = focus
    supplied = {"amount": "0.25"}

    harness._add_effect_type("add_war_support", supplied)
    supplied["amount"] = "0.9"
    supplied["extra"] = "caller-only"

    assert focus.effects == [{"type": "add_war_support", "fields": {"amount": "0.25"}}]
    assert focus.effects[0]["fields"] is not supplied


def test_parameter_callback_adds_defaults_and_supplied_fields(tk_root, monkeypatch):
    monkeypatch.setattr(MOD, "loaded", False)
    focus = Focus()
    harness = _Harness(tk_root)
    harness.focuses = FocusDocument([focus])
    harness.selected = focus

    _confirm_parameter_dialog(harness, "add_war_support")
    _confirm_parameter_dialog(harness, "add_war_support", "0.42")

    assert focus.effects == [
        {"type": "add_war_support", "fields": {"amount": "0.05"}},
        {"type": "add_war_support", "fields": {"amount": "0.42"}},
    ]


def test_effect_card_entry_callback_updates_focus(tk_root, monkeypatch):
    monkeypatch.setattr(MOD, "loaded", False)
    focus = Focus()
    focus.effects = [{"type": "add_war_support", "fields": {"amount": "0.1"}}]
    harness = _Harness(tk_root)
    harness.focuses = FocusDocument([focus])
    harness.selected = focus

    harness._refresh_effects()
    entries = _descendants(harness._eff_box, tk.Entry)
    assert len(entries) == 1
    entries[0].delete(0, "end")
    entries[0].insert(0, "0.35")

    assert focus.effects[0]["fields"] == {"amount": "0.35"}


def test_remove_effect_snapshots_and_restores_exact_focus(tk_root, monkeypatch):
    monkeypatch.setattr(MOD, "loaded", False)
    focus = Focus()
    focus.effects = [
        {"type": "add_ideas", "fields": {"idea_name": "first"}},
        {"type": "add_ideas", "fields": {"idea_name": "second"}},
    ]
    harness = _Harness(tk_root)
    harness.focuses = FocusDocument([focus])
    harness.selected = focus
    before = deepcopy(focus.to_dict())

    harness._refresh_effects()
    remove_button = next(
        button
        for button in _descendants(harness._eff_box, tk.Button)
        if button.cget("text") == "✕"
    )
    remove_button.invoke()

    assert focus.effects == [{"type": "add_ideas", "fields": {"idea_name": "second"}}]
    entry = harness._undo_stack._stack[-1]
    assert entry[0] == "remove effect"
    assert entry[2][focus.id] == before
    harness._focus_list_cache.invalidate.assert_called_once_with()
    harness._invalidate_focus_list_structure.assert_called_once_with()

    result = harness._undo_stack.undo(harness.focuses, Focus.from_dict)
    assert result == ("remove effect", {focus.id}, set())
    assert harness.focuses[focus.id].to_dict() == before


def test_add_effect_without_selection_is_a_noop(tk_root):
    harness = _Harness(tk_root)

    harness._add_effect_type("add_war_support")
    harness._rm_effect(0)

    assert not harness.focuses
    assert len(harness._undo_stack) == 0
    harness._hint.assert_called_once()


def test_live_effect_edits_update_and_ignore_stale_or_unselected(tk_root):
    focus = Focus()
    focus.effects = [
        {"type": "custom", "fields": {}},
        {"type": "custom", "fields": {}},
    ]
    harness = _Harness(tk_root)
    harness.focuses = FocusDocument([focus])
    harness.selected = focus
    value = tk.StringVar(value="updated")
    text = tk.Text(harness)
    text.insert("1.0", "multiline value")

    harness._live_eff_field(0, "value", value)
    harness._live_eff_text(1, "text", text)
    expected = [
        {"type": "custom", "fields": {"value": "updated"}},
        {"type": "custom", "fields": {"text": "multiline value"}},
    ]
    assert focus.effects == expected
    stale_value = tk.StringVar(value="stale")
    stale_text = tk.Text(harness)
    stale_text.insert("1.0", "stale")
    harness._live_eff_field(2, "value", stale_value)
    harness._live_eff_text(2, "text", stale_text)
    harness.selected = None
    harness._live_eff_field(0, "value", stale_value)
    harness._live_eff_text(0, "text", stale_text)

    assert focus.effects == expected


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
