"""Tests for the effects-panel refresh-skip optimization.

The signature drives whether ``_refresh_effects`` tears down and rebuilds the
effect cards. It covers everything a card renders, so a match means a rebuild
would draw the same thing. These tests pin that contract, including that it
survives CPython recycling a freed focus's memory address.
"""

from types import SimpleNamespace

from hoi4cm.ui.effects_panel import _effects_signature


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
