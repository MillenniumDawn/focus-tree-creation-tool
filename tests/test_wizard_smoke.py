"""Smoke tests: each wizard Toplevel constructs without NameError.

Covers the extraction regression class from #45 and
docs/dev/monolith-migration.md: a broken import or missing name that only
surfaces when the user clicks the wizard button. One construction per
``open_*_wizard`` against a bare ``tk_root`` with no MOD loaded keeps the
fixture cost low; widget-content assertions are intentionally thin.
"""

from __future__ import annotations

import tkinter as tk

import pytest

from hoi4cm.mod import MOD
from hoi4cm.mod import scan_cache as scan_cache_mod


@pytest.fixture(autouse=True)
def isolate_mod(tmp_path, monkeypatch):
    """Keep scan cache off disk and snapshot MOD between tests."""
    monkeypatch.setattr(scan_cache_mod, "STATE_DIR", str(tmp_path / "scan_cache"))
    snapshot = dict(MOD.__dict__)
    # wizards degrade gracefully when no mod is loaded
    MOD.loaded = False
    MOD.root = None
    MOD.is_md = False
    yield
    MOD.__dict__.clear()
    MOD.__dict__.update(snapshot)


def _stub_app(root: tk.Tk) -> tk.Tk:
    if not hasattr(root, "_hint"):
        root._hint = lambda *a, **kw: None  # type: ignore[attr-defined]
    if not hasattr(root, "_apply_md_additional_income"):
        root._apply_md_additional_income = lambda *a, **kw: ([], [])  # type: ignore[attr-defined]
    return root


def _all_descendants(widget: tk.Misc) -> list[tk.Misc]:
    out: list[tk.Misc] = []
    for child in widget.winfo_children():
        out.append(child)
        out.extend(_all_descendants(child))
    return out


def _new_toplevels(before: set[tk.Misc], root: tk.Tk) -> list[tk.Toplevel]:
    return [
        w
        for w in root.winfo_children()
        if w not in before and isinstance(w, tk.Toplevel)
    ]


def _open_and_assert(
    tk_root: tk.Tk,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    opener_module: str,
    opener_name: str,
    title_snippet: str,
) -> None:
    _stub_app(tk_root)
    # autosave writes under ~/.hoi4cm — divert to tmp_path
    import importlib

    mod = importlib.import_module(opener_module)
    if hasattr(mod, "autosave_path"):
        monkeypatch.setattr(mod, "autosave_path", lambda name: str(tmp_path / name))
    # never pop a real file dialog during smoke
    monkeypatch.setattr("tkinter.filedialog.askdirectory", lambda **kw: "")
    monkeypatch.setattr("tkinter.filedialog.askopenfilename", lambda **kw: "")
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **kw: None)
    monkeypatch.setattr("tkinter.messagebox.showwarning", lambda *a, **kw: None)
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **kw: None)
    monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a, **kw: False)

    before: set[tk.Misc] = set(tk_root.winfo_children())
    opener = getattr(mod, opener_name)
    opener(tk_root)
    tk_root.update()
    wins = _new_toplevels(before, tk_root)
    assert wins, f"{opener_name} did not create a Toplevel"
    win = wins[0]
    try:
        assert (
            title_snippet.lower() in win.title().lower()
        ), f"expected {title_snippet!r} in title {win.title()!r}"
        # thin content check — window has at least one labelled child
        assert win.winfo_children(), f"{opener_name} Toplevel has no children"
    finally:
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()
        tk_root.update()


def test_national_spirit_wizard_constructs(tk_root, tmp_path, monkeypatch):
    _open_and_assert(
        tk_root,
        tmp_path,
        monkeypatch,
        "hoi4cm.wizards.national_spirit",
        "open_national_spirit_wizard",
        "National Spirit",
    )


def test_decision_wizard_constructs(tk_root, tmp_path, monkeypatch):
    _open_and_assert(
        tk_root,
        tmp_path,
        monkeypatch,
        "hoi4cm.wizards.decision",
        "open_decision_wizard",
        "Decision",
    )


def test_dyn_mod_wizard_constructs(tk_root, tmp_path, monkeypatch):
    _open_and_assert(
        tk_root,
        tmp_path,
        monkeypatch,
        "hoi4cm.wizards.dyn_mod",
        "open_dyn_mod_wizard",
        "Dynamic",
    )


def test_event_wizard_constructs(tk_root, tmp_path, monkeypatch):
    _open_and_assert(
        tk_root,
        tmp_path,
        monkeypatch,
        "hoi4cm.wizards.event",
        "open_event_wizard",
        "Event",
    )


def test_additional_income_wizard_constructs(tk_root, tmp_path, monkeypatch):
    _open_and_assert(
        tk_root,
        tmp_path,
        monkeypatch,
        "hoi4cm.wizards.additional_income",
        "open_additional_income_wizard",
        "Additional Income",
    )


def test_effect_picker_constructs(tk_root, tmp_path, monkeypatch):
    """_shared.open_effect_picker is the helper every wizard reuses."""
    _stub_app(tk_root)
    import hoi4cm.wizards._shared as shared_mod

    # divert any autosave path if the module exposes it
    if hasattr(shared_mod, "autosave_path"):
        monkeypatch.setattr(
            shared_mod,
            "autosave_path",
            lambda name: str(tmp_path / name),  # type: ignore[attr-defined]
        )

    target = tk.Text(tk_root)
    target.pack()
    tk_root.update()
    before: set[tk.Misc] = set(tk_root.winfo_children())
    # effect picker creates a Toplevel(parent)
    try:
        shared_mod.open_effect_picker(tk_root, target)
        tk_root.update()
        wins = _new_toplevels(before, tk_root)
        assert wins, "open_effect_picker did not create a Toplevel"
        win = wins[0]
        assert win.winfo_children()
    finally:
        for w in list(tk_root.winfo_children()):
            if isinstance(w, tk.Toplevel) and w not in before:
                try:
                    w.grab_release()
                except Exception:
                    pass
                w.destroy()
        target.destroy()
        tk_root.update()
