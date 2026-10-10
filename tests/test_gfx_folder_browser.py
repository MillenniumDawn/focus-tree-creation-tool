"""Tests for the shared folder-list GFX picker."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from hoi4cm.mod import MOD
from hoi4cm.ui.gfx_browser import open_folder_gfx_browser
from hoi4cm.ui.thumbnail_grid import VirtualThumbnailGrid
from hoi4cm.wizards.national_spirit import open_national_spirit_wizard

FOLDERS = [("[root]", "/gfx/root"), ("sub", "/gfx/root/sub")]
PAIRS = {
    "/gfx/root": [
        ("GFX_idea_alpha", "/gfx/root/alpha.png"),
        ("GFX_idea_beta", "/gfx/root/beta.png"),
    ],
    "/gfx/root/sub": [("GFX_idea_gamma", "/gfx/root/sub/gamma.png")],
}


def _descendants(widget: tk.Misc) -> list[tk.Misc]:
    found: list[tk.Misc] = []
    stack: list[tk.Misc] = [widget]
    while stack:
        current = stack.pop()
        found.append(current)
        stack.extend(current.winfo_children())
    return found


@dataclass
class Opened:
    win: tk.Toplevel
    calls: list[tuple[str, str]]
    chosen: list[str]

    def widgets(self) -> list[tk.Misc]:
        return _descendants(self.win)

    def listbox(self) -> tk.Listbox:
        return next(w for w in self.widgets() if isinstance(w, tk.Listbox))

    def grid(self) -> VirtualThumbnailGrid:
        return next(w for w in self.widgets() if isinstance(w, VirtualThumbnailGrid))

    def button(self, text: str) -> tk.Button:
        return next(
            w
            for w in self.widgets()
            if isinstance(w, tk.Button) and text in w.cget("text")
        )

    def label_texts(self) -> list[str]:
        return [str(w.cget("text")) for w in self.widgets() if isinstance(w, tk.Label)]


@pytest.fixture
def opened(tk_root: tk.Tk) -> Iterator[Opened]:
    calls: list[tuple[str, str]] = []
    chosen: list[str] = []

    def collect_pairs(folder: str, search: str) -> list[tuple[str, str]]:
        calls.append((folder, search))
        return PAIRS[folder]

    before = set(tk_root.winfo_children())
    open_folder_gfx_browser(
        tk_root,
        title="Test Browser",
        folders=FOLDERS,
        collect_pairs=collect_pairs,
        on_select=chosen.append,
        label_prefixes=("GFX_idea_",),
    )
    tk_root.update()
    wins = [
        w
        for w in tk_root.winfo_children()
        if w not in before and isinstance(w, tk.Toplevel)
    ]
    assert len(wins) == 1
    try:
        yield Opened(wins[0], calls, chosen)
    finally:
        for win in wins:
            if win.winfo_exists():
                win.destroy()
        tk_root.update()


def test_opens_and_lists_folders(opened: Opened) -> None:
    assert opened.win.title() == "Test Browser"
    assert opened.listbox().get(0, "end") == ("  [root]", "  sub")
    assert opened.listbox().curselection() == (0,)
    assert opened.calls == [("/gfx/root", "")]
    assert "2 icons" in opened.label_texts()
    assert opened.button("Select").cget("state") == "disabled"


def test_tile_labels_drop_the_label_prefixes(opened: Opened) -> None:
    grid = opened.grid()
    grid.refresh()
    canvas = grid.canvas
    texts = {
        canvas.itemcget(item, "text")
        for item in canvas.find_all()
        if canvas.type(item) == "text"
    }
    assert {"alpha", "beta"} <= texts


def test_select_calls_on_select_with_key_and_closes(
    tk_root: tk.Tk, opened: Opened
) -> None:
    opened.grid().select(1)
    select = opened.button("Select")
    assert select.cget("state") == "normal"
    select.invoke()
    tk_root.update()
    assert opened.chosen == ["GFX_idea_beta"]
    assert not opened.win.winfo_exists()


def test_activate_selects_and_closes_once(tk_root: tk.Tk, opened: Opened) -> None:
    opened.grid()._activate(0)
    tk_root.update()
    assert opened.chosen == ["GFX_idea_alpha"]
    assert not opened.win.winfo_exists()


def test_cancel_closes_without_calling_on_select(
    tk_root: tk.Tk, opened: Opened
) -> None:
    opened.grid().select(0)
    opened.button("Cancel").invoke()
    tk_root.update()
    assert opened.chosen == []
    assert not opened.win.winfo_exists()


def test_choosing_another_folder_loads_its_pairs_and_keeps_selection(
    tk_root: tk.Tk, opened: Opened
) -> None:
    opened.grid().select(1)
    listbox = opened.listbox()
    listbox.selection_clear(0, "end")
    listbox.selection_set(1)
    listbox.event_generate("<<ListboxSelect>>")
    tk_root.update()
    assert opened.calls[-1] == ("/gfx/root/sub", "")
    assert "1 icons" in opened.label_texts()
    opened.button("Select").invoke()
    assert opened.chosen == ["GFX_idea_beta"]


def test_national_spirit_picture_picker_fills_the_picture_field(
    tk_root: tk.Tk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "free_trade.png").write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr(MOD, "loaded", False)
    monkeypatch.setattr("tkinter.filedialog.askdirectory", lambda **kw: str(tmp_path))
    open_national_spirit_wizard(tk_root)
    wizard = next(w for w in tk_root.winfo_children() if isinstance(w, tk.Toplevel))
    try:
        browse = next(
            w
            for w in _descendants(wizard)
            if isinstance(w, tk.Button) and w.cget("text") == "⊞"
        )
        entry = next(
            w for w in browse.master.winfo_children() if isinstance(w, tk.Entry)
        )
        before = set(wizard.winfo_children())
        browse.invoke()
        tk_root.update()
        picker = next(
            w
            for w in wizard.winfo_children()
            if w not in before and isinstance(w, tk.Toplevel)
        )
        assert "Ideas" in picker.title()
        grid = next(
            w for w in _descendants(picker) if isinstance(w, VirtualThumbnailGrid)
        )
        grid.select(0)
        next(
            w
            for w in _descendants(picker)
            if isinstance(w, tk.Button) and "Select" in w.cget("text")
        ).invoke()
        tk_root.update()
        assert entry.get() == "GFX_idea_free_trade"
        assert not picker.winfo_exists()
    finally:
        wizard.destroy()
        tk_root.update()
