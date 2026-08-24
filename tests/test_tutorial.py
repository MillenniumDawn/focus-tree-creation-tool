"""First-launch tutorial behaviour and Tk construction tests."""

import json
import tkinter as tk
from pathlib import Path

from hoi4cm.ui import tutorial as tutorial_mod


class _FakeMenu:
    def __init__(self, target: tk.Widget) -> None:
        self.target = target
        self.preview_calls: list[tuple[str, tuple[str, ...]]] = []
        self.close_calls = 0

    def show_preview(
        self, menu_key: str, item_keys: tuple[str, ...]
    ) -> list[tk.Widget]:
        self.preview_calls.append((menu_key, item_keys))
        return [self.target]

    def close(self) -> None:
        self.close_calls += 1


def _install_tutorial_targets(root: tk.Tk) -> _FakeMenu:
    toolbar = tk.Frame(root)
    toolbar.pack(fill="x")
    root._add_focus_btn = tk.Button(toolbar, text="+ Focus")  # type: ignore[attr-defined]
    root._add_focus_btn.pack(side="left")  # type: ignore[attr-defined]
    root._conn_btn = tk.Button(toolbar, text="Prereq")  # type: ignore[attr-defined]
    root._conn_btn.pack(side="left")  # type: ignore[attr-defined]
    root._mutex_btn = tk.Button(toolbar, text="Mutex")  # type: ignore[attr-defined]
    root._mutex_btn.pack(side="left")  # type: ignore[attr-defined]

    body = tk.Frame(root)
    body.pack(fill="both", expand=True)
    root.cv = tk.Canvas(body, width=360, height=220)  # type: ignore[attr-defined]
    root.cv.pack(side="left", fill="both", expand=True)  # type: ignore[attr-defined]
    root._sb_frame = tk.Frame(body, width=220)  # type: ignore[attr-defined]
    root._sb_frame.pack(side="right", fill="y")  # type: ignore[attr-defined]
    tab_bar = tk.Frame(root._sb_frame)  # type: ignore[attr-defined]
    tab_bar.pack(fill="x")
    root._tab_btns = {}  # type: ignore[attr-defined]
    for name in ("Effects", "Conditions", "Code"):
        button = tk.Button(tab_bar, text=name)
        button.pack(side="left")
        root._tab_btns[name] = (button, tk.Frame(root._sb_frame))  # type: ignore[attr-defined]

    preview_target = tk.Frame(root, width=300, height=24)
    preview_target.pack()
    preview_target.pack_propagate(False)
    root.geometry("900x600")
    root.update()
    return _FakeMenu(preview_target)


def _find_widgets(parent: tk.Misc, widget_type: type[tk.Widget]) -> list[tk.Widget]:
    found: list[tk.Widget] = []
    for child in parent.winfo_children():
        if isinstance(child, widget_type):
            found.append(child)
        found.extend(_find_widgets(child, widget_type))
    return found


def test_tutorial_has_complete_beginner_workflow():
    assert len(tutorial_mod.TUTORIAL_STEPS) == 8
    assert tutorial_mod.TUTORIAL_STEPS[4].menu_key == "tools"
    assert tutorial_mod.TUTORIAL_STEPS[-1].menu_key == "file"
    assert tutorial_mod.TUTORIAL_STEPS[-1].menu_item_keys == (
        "export_txt",
        "export_mod",
    )


def test_every_tutorial_key_exists_in_each_locale():
    keys = {
        "menu.help",
        "menu.start_tutorial",
        "menu.start_tutorial.tip",
        "tutorial.window.title",
        "tutorial.progress",
        "tutorial.dont_show_again",
        "tutorial.back",
        "tutorial.skip",
        "tutorial.next",
        "tutorial.finish",
    }
    for step in tutorial_mod.TUTORIAL_STEPS:
        keys.update((step.title_key, step.body_key))
    locale_dir = Path(__file__).parents[1] / "locales"
    for path in locale_dir.glob("*.json"):
        strings = json.loads(path.read_text(encoding="utf-8"))
        assert keys <= strings.keys(), f"missing tutorial keys in {path.name}"


def test_automatic_start_honours_saved_preference(tk_root, monkeypatch):
    monkeypatch.setattr(
        tutorial_mod,
        "cfg_load",
        lambda: {tutorial_mod.TUTORIAL_DISABLED_KEY: True},
    )
    menu = _FakeMenu(tk.Frame(tk_root))
    controller = tutorial_mod.TutorialController(tk_root, menu)

    assert controller.start() is False
    assert controller.active is False


def test_tutorial_walks_real_menu_previews_and_persists_checkbox(tk_root, monkeypatch):
    saved: dict[str, bool] = {}
    monkeypatch.setattr(tutorial_mod, "cfg_load", lambda: dict(saved))
    monkeypatch.setattr(tutorial_mod, "cfg_save", lambda values: saved.update(values))
    menu = _install_tutorial_targets(tk_root)
    controller = tutorial_mod.TutorialController(tk_root, menu)

    assert controller.start(manual=True) is True
    tk_root.update()
    assert controller.active is True
    assert controller.step_index == 0

    for _ in range(4):
        controller.next_step()
        tk_root.update()
    assert menu.preview_calls[-1] == (
        "tools",
        (
            "national_spirit_builder",
            "dynamic_modifier",
            "decision_maker",
            "event_maker",
        ),
    )

    controller.next_step()
    controller.next_step()
    controller.next_step()
    tk_root.update()
    assert menu.preview_calls[-3:] == [
        ("tools", ("validate_tree",)),
        ("tools", ("load_mod", "set_edit_targets", "settings")),
        ("file", ("export_txt", "export_mod")),
    ]

    windows = [
        child for child in tk_root.winfo_children() if isinstance(child, tk.Toplevel)
    ]
    assert windows
    checkbuttons = _find_widgets(windows[0], tk.Checkbutton)
    assert len(checkbuttons) == 1
    checkbuttons[0].invoke()
    controller.next_step()

    assert controller.active is False
    assert saved[tutorial_mod.TUTORIAL_DISABLED_KEY] is True
    assert menu.close_calls > 0


def test_manual_start_bypasses_disabled_preference(tk_root, monkeypatch):
    saved = {tutorial_mod.TUTORIAL_DISABLED_KEY: True}
    monkeypatch.setattr(tutorial_mod, "cfg_load", lambda: dict(saved))
    monkeypatch.setattr(tutorial_mod, "cfg_save", lambda values: saved.update(values))
    menu = _install_tutorial_targets(tk_root)
    controller = tutorial_mod.TutorialController(tk_root, menu)

    assert controller.start(manual=True) is True
    controller.close()
    assert saved[tutorial_mod.TUTORIAL_DISABLED_KEY] is True
