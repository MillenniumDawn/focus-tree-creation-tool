"""Tests for the monolith sidebar refresh-skip signatures.

The signatures must include the focus object identity so that switching to a
different focus always rebuilds — even when the new focus's data is
byte-identical to the previous one. Without the focus id, an unsaved offset
edit on focus A would leak onto a focus B that happens to share A's original
offsets, and a later save would write A's edit into B.
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


def test_refresh_offsets_rebuilds_on_focus_switch(tk_root):
    """A different focus with identical offsets must rebuild, not skip.

    Reproduces the stale-widget bug: an unsaved edit on A's offset must not
    leak onto B when B shares A's original offsets.
    """
    h = _Harness(tk_root)
    a = SimpleNamespace(offsets=[{"x": 0, "y": 0, "trigger": ""}])
    b = SimpleNamespace(offsets=[{"x": 0, "y": 0, "trigger": ""}])
    h.selected = a
    _refresh_offsets(h, a)
    # Simulate an unsaved edit on A's x entry.
    h._offset_entries[0][0].set("5")
    h.selected = b
    _refresh_offsets(h, b)
    # B's widget must show B's data (x=0), not A's stale edit (x=5).
    assert h._offset_entries[0][0].get() == "0"


def test_refresh_offsets_skips_same_focus(tk_root):
    """Re-rendering the same focus must skip the rebuild."""
    h = _Harness(tk_root)
    a = SimpleNamespace(offsets=[{"x": 0, "y": 0, "trigger": ""}])
    h.selected = a
    _refresh_offsets(h, a)
    entries = h._offset_entries
    _refresh_offsets(h, a)
    assert h._offset_entries is entries
