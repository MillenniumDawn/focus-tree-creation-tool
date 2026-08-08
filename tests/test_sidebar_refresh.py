"""Tests for the monolith sidebar refresh-skip signatures.

The signatures must include the focus's own id so that switching to a
different focus always rebuilds — even when the new focus's data is
byte-identical to the previous one. Without it, an unsaved offset edit on
focus A would leak onto a focus B that happens to share A's original offsets,
and `_save_offsets_to_focus` would write A's edit into B.
"""

import tkinter as tk
from types import SimpleNamespace

import hoi4_content_maker as m


class _Harness:
    def __init__(self, root):
        self._offset_box = tk.Frame(root)
        self._prereq_box = tk.Frame(root)
        self._mutex_box = tk.Frame(root)
        self.selected: object | None = None
        self.focuses = {}
        self._offsets_sig = None
        self._prereqs_sig = None
        self._mutex_sig = None
        self._offset_entries = []


def _refresh_offsets(h, f):
    m.App._refresh_offsets.__get__(h, _Harness)(f)


def _focus(fid, x=0):
    return SimpleNamespace(id=fid, offsets=[{"x": x, "y": 0, "trigger": ""}])


def test_refresh_offsets_rebuilds_on_focus_switch(tk_root):
    """A different focus with identical offsets must rebuild, not skip.

    Reproduces the stale-widget bug: an unsaved edit on A's offset must not
    leak onto B when B shares A's original offsets.
    """
    h = _Harness(tk_root)
    a, b = _focus("a"), _focus("b")
    h.selected = a
    _refresh_offsets(h, a)
    # Simulate an unsaved edit on A's x entry.
    h._offset_entries[0][0].set("5")
    h.selected = b
    _refresh_offsets(h, b)
    # B's widget must show B's data (x=0), not A's stale edit (x=5).
    assert h._offset_entries[0][0].get() == "0"


def test_refresh_offsets_rebuilds_after_address_reuse(tk_root):
    """A freed focus's memory address must not alias onto its replacement.

    The signature used to key on ``id(f)``, which CPython hands straight back
    for the next object of that size. Dropping focus A and loading focus B
    into A's address gave B a signature identical to A's, so the rebuild was
    skipped and A's unsaved edit stayed in the widget for B to inherit.
    """
    h = _Harness(tk_root)
    a = _focus("a")
    h.selected = a
    _refresh_offsets(h, a)
    h._offset_entries[0][0].set("5")  # unsaved edit on A
    h.selected = None
    del a  # last reference to A goes away, freeing its address
    b = _focus("b")  # same offsets, lands on A's address
    h.selected = b
    _refresh_offsets(h, b)
    assert h._offset_entries[0][0].get() == "0"


def test_refresh_offsets_skips_same_focus(tk_root):
    """Re-rendering the same focus must skip the rebuild."""
    h = _Harness(tk_root)
    a = _focus("a")
    h.selected = a
    _refresh_offsets(h, a)
    entries = h._offset_entries
    _refresh_offsets(h, a)
    assert h._offset_entries is entries
