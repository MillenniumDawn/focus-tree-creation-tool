"""The event wizard's inline GFX tab writes the picked tile into the picture field."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import pytest
from tk_helpers import cleanup_toplevels, collect_texts, release_grab

import hoi4cm.wizards.event as event_mod
from hoi4cm.mod import MOD
from hoi4cm.ui.thumbnail_grid import VirtualThumbnailGrid


def _descendants(widget: tk.Misc) -> list[tk.Misc]:
    found: list[tk.Misc] = []
    stack: list[tk.Misc] = [widget]
    while stack:
        current = stack.pop()
        found.append(current)
        stack.extend(current.winfo_children())
    return found


def test_selecting_a_tile_fills_the_picture_field(
    tk_root: tk.Tk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_grab(tk_root)
    mod_root = tmp_path / "mod"
    pictures = mod_root / "gfx" / "event_pictures"
    pictures.mkdir(parents=True)
    for stem in ("alpha", "beta"):
        (pictures / f"{stem}.png").write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr(event_mod, "autosave_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(MOD, "loaded", True)
    monkeypatch.setattr(MOD, "root", str(mod_root))
    try:
        event_mod.open_event_wizard(tk_root)
        tk_root.update()
        widgets = _descendants(tk_root)
        grid = next(w for w in widgets if isinstance(w, VirtualThumbnailGrid))
        picture = next(
            w
            for w in widgets
            if isinstance(w, tk.Entry)
            and w.get() == "GFX_report_event_generic_handshake"
        )

        grid.select(1)
        tk_root.update()

        assert picture.get() == "GFX_report_event_beta"
        assert "GFX_report_event_beta" in collect_texts(tk_root)
    finally:
        cleanup_toplevels(tk_root)
