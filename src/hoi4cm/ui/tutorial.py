"""First-launch tutorial over the application's real Tk widgets."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Protocol

from hoi4cm.core.config import cfg_load, cfg_save
from hoi4cm.core.i18n import tr
from hoi4cm.ui.theme import (
    BG_CARD,
    BG_DARK,
    BG_PANEL,
    BLUE,
    BORDER_G,
    TEXT,
    TEXT_DIM,
    YELLOW,
)

TUTORIAL_DISABLED_KEY = "tutorial_disabled"


class MenuPreview(Protocol):
    """The subset of the menubar controller used by the tutorial."""

    def show_preview(
        self, menu_key: str, item_keys: tuple[str, ...]
    ) -> list[tk.Widget]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class TutorialStep:
    """One translated explanation and the real controls it points at."""

    title_key: str
    title_default: str
    body_key: str
    body_default: str
    widget_keys: tuple[str, ...] = ()
    fallback_widget_key: str | None = None
    menu_key: str | None = None
    menu_item_keys: tuple[str, ...] = ()


TUTORIAL_STEPS = (
    TutorialStep(
        "tutorial.step.add.title",
        "Add and position a focus",
        "tutorial.step.add.body",
        (
            "Choose + Focus or right-click an empty canvas cell. Drag a focus to move "
            "it, Ctrl+drag or middle-drag to pan, and use the mouse wheel to zoom. "
            "Start by placing the main goals in the order players should encounter "
            "them."
        ),
        ("_add_focus_btn", "cv"),
    ),
    TutorialStep(
        "tutorial.step.properties.title",
        "Describe the selected focus",
        "tutorial.step.properties.body",
        (
            "Click a focus to open this sidebar. Give it a unique Focus ID, a readable "
            "name and description, an appropriate cost, and a GFX icon. Changes are "
            "applied to the selected focus as you edit."
        ),
        ("_sb_frame",),
    ),
    TutorialStep(
        "tutorial.step.relationships.title",
        "Build the focus-tree path",
        "tutorial.step.relationships.body",
        (
            "Select the later focus, choose Prereq, then pick the focus that must be "
            "completed first. Use Mutex when choosing one focus should lock out "
            "another. "
            "The arrows on the canvas show the resulting path."
        ),
        ("_conn_btn", "_mutex_btn"),
    ),
    TutorialStep(
        "tutorial.step.behaviour.title",
        "Add conditions and outcomes",
        "tutorial.step.behaviour.body",
        (
            "After selecting a focus, use Effects for completion rewards and "
            "Conditions "
            "for availability, visibility, and bypass rules. Properties controls the "
            "basic fields; Code is available when you need to inspect or edit the "
            "script."
        ),
        ("tab:Effects", "tab:Conditions", "tab:Code"),
        "_sb_frame",
    ),
    TutorialStep(
        "tutorial.step.wizards.title",
        "Use a wizard for related content",
        "tutorial.step.wizards.body",
        (
            "The Tools menu contains guided builders for national spirits, dynamic "
            "modifiers, decisions, and events. Each wizard previews its generated HOI4 "
            "script and can connect that content to your focus effects."
        ),
        menu_key="tools",
        menu_item_keys=(
            "national_spirit_builder",
            "dynamic_modifier",
            "decision_maker",
            "event_maker",
        ),
    ),
    TutorialStep(
        "tutorial.step.validate.title",
        "Validate before exporting",
        "tutorial.step.validate.body",
        (
            "Run Validate Tree after major edits. Review broken prerequisites, missing "
            "effects, and invalid GFX references, then correct every reported problem "
            "before writing files into a mod."
        ),
        menu_key="tools",
        menu_item_keys=("validate_tree",),
    ),
    TutorialStep(
        "tutorial.step.mod.title",
        "Connect the target mod",
        "tutorial.step.mod.body",
        (
            "Load Mod points the app at your mod root so it can find focus icons, "
            "localisation, and valid install folders. Settings adjusts those paths, "
            "and "
            "Set Edit Targets chooses existing files used by wizard-generated content."
        ),
        menu_key="tools",
        menu_item_keys=("load_mod", "set_edit_targets", "settings"),
    ),
    TutorialStep(
        "tutorial.step.export.title",
        "Export the finished tree",
        "tutorial.step.export.body",
        (
            "Export .txt lets you choose a standalone output file. Export to Mod "
            "writes "
            "to the loaded mod's national_focus folder. Save the editable project JSON "
            "as well, so you can reopen the visual workspace later."
        ),
        menu_key="file",
        menu_item_keys=("export_txt", "export_mod"),
    ),
)


def tutorial_is_disabled() -> bool:
    """Return whether automatic first-launch teaching is disabled."""
    return bool(cfg_load().get(TUTORIAL_DISABLED_KEY, False))


def save_tutorial_disabled(disabled: bool) -> None:
    """Persist the user's "don't show this again" choice."""
    cfg_save({TUTORIAL_DISABLED_KEY: bool(disabled)})


class HighlightOverlay:
    """Draw non-layout-changing borders over widgets in any Tk toplevel."""

    def __init__(self, *, color: str = YELLOW, thickness: int = 3, pad: int = 3):
        self._color = color
        self._thickness = thickness
        self._pad = pad
        self._frames: list[tk.Frame] = []

    def show(self, widgets: list[tk.Widget]) -> list[tk.Widget]:
        self.clear()
        visible: list[tk.Widget] = []
        seen: set[str] = set()
        for widget in widgets:
            try:
                widget.update_idletasks()
                if not widget.winfo_exists() or not widget.winfo_viewable():
                    continue
                widget_name = str(widget)
                if widget_name in seen:
                    continue
                seen.add(widget_name)
                self._show_one(widget)
                visible.append(widget)
            except tk.TclError, RuntimeError, AttributeError:
                continue
        return visible

    def _show_one(self, widget: tk.Widget) -> None:
        parent = widget.winfo_toplevel()
        parent.update_idletasks()
        left = widget.winfo_rootx() - parent.winfo_rootx() - self._pad
        top = widget.winfo_rooty() - parent.winfo_rooty() - self._pad
        width = widget.winfo_width() + (2 * self._pad)
        height = widget.winfo_height() + (2 * self._pad)
        thickness = self._thickness
        placements = (
            (left, top, width, thickness),
            (left, top + height - thickness, width, thickness),
            (left, top, thickness, height),
            (left + width - thickness, top, thickness, height),
        )
        for x_pos, y_pos, frame_width, frame_height in placements:
            frame = tk.Frame(parent, bg=self._color, bd=0)
            frame.place(
                x=x_pos,
                y=y_pos,
                width=max(frame_width, thickness),
                height=max(frame_height, thickness),
            )
            frame.lift()
            self._frames.append(frame)

    def clear(self) -> None:
        for frame in self._frames:
            try:
                frame.destroy()
            except tk.TclError, RuntimeError:
                pass
        self._frames.clear()


class TutorialController:
    """Teach the basic workflow without changing the user's project data."""

    def __init__(self, app: tk.Misc, menu: MenuPreview) -> None:
        self._app = app
        self._menu = menu
        self._highlight = HighlightOverlay()
        self._window: tk.Toplevel | None = None
        self._disabled_var: tk.BooleanVar | None = None
        self._progress_var: tk.StringVar | None = None
        self._title_var: tk.StringVar | None = None
        self._body_var: tk.StringVar | None = None
        self._back_button: tk.Button | None = None
        self._next_button: tk.Button | None = None
        self._step_index = 0
        self._active = False
        self._active_targets: list[tk.Widget] = []

    @property
    def active(self) -> bool:
        return self._active

    @property
    def step_index(self) -> int:
        return self._step_index

    def start(self, *, manual: bool = False) -> bool:
        """Open the tutorial, bypassing the saved preference when manual."""
        disabled = tutorial_is_disabled()
        if disabled and not manual:
            return False
        if self._active:
            if self._window is not None:
                self._window.lift()
            return True
        self._active = True
        self._step_index = 0
        self._disabled_var = tk.BooleanVar(master=self._app, value=disabled)
        self._build_window()
        self._show_step()
        return True

    def previous_step(self) -> None:
        if self._active and self._step_index > 0:
            self._step_index -= 1
            self._show_step()

    def next_step(self) -> None:
        if not self._active:
            return
        if self._step_index >= len(TUTORIAL_STEPS) - 1:
            self.close()
            return
        self._step_index += 1
        self._show_step()

    def close(self) -> None:
        """Close every tutorial surface and persist the checkbox when active."""
        was_active = self._active
        self._active = False
        self._highlight.clear()
        self._menu.close()
        if was_active and self._disabled_var is not None:
            save_tutorial_disabled(self._disabled_var.get())
        window = self._window
        self._window = None
        self._active_targets.clear()
        if window is not None:
            try:
                window.destroy()
            except tk.TclError, RuntimeError:
                pass

    def _build_window(self) -> None:
        disabled_var = self._disabled_var
        if disabled_var is None:
            raise RuntimeError("tutorial preference is not initialized")
        window = tk.Toplevel(self._app)
        self._window = window
        window.title(tr("tutorial.window.title", "Getting Started"))
        window.configure(bg=BORDER_G)
        window.resizable(False, False)
        window.transient(self._app.winfo_toplevel())
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.bind("<Escape>", lambda _event: self.close())
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass

        card = tk.Frame(
            window,
            bg=BG_PANEL,
            highlightthickness=1,
            highlightbackground=BLUE,
        )
        card.pack(fill="both", expand=True, padx=1, pady=1)

        self._progress_var = tk.StringVar(master=window)
        self._title_var = tk.StringVar(master=window)
        self._body_var = tk.StringVar(master=window)
        tk.Label(
            card,
            textvariable=self._progress_var,
            bg=BG_PANEL,
            fg=YELLOW,
            font=("Helvetica", 8, "bold"),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 4))
        tk.Label(
            card,
            textvariable=self._title_var,
            bg=BG_PANEL,
            fg=TEXT,
            font=("Helvetica", 14, "bold"),
            anchor="w",
        ).pack(fill="x", padx=18)
        tk.Label(
            card,
            textvariable=self._body_var,
            bg=BG_PANEL,
            fg=TEXT,
            font=("Helvetica", 10),
            justify="left",
            anchor="nw",
            wraplength=430,
        ).pack(fill="x", padx=18, pady=(10, 14))

        tk.Checkbutton(
            card,
            text=tr("tutorial.dont_show_again", "Don't show this again"),
            variable=disabled_var,
            bg=BG_PANEL,
            fg=TEXT_DIM,
            activebackground=BG_PANEL,
            activeforeground=TEXT,
            selectcolor=BG_CARD,
            font=("Helvetica", 9),
            anchor="w",
        ).pack(fill="x", padx=15, pady=(0, 12))

        buttons = tk.Frame(card, bg=BG_DARK)
        buttons.pack(fill="x")

        def make_button(text: str, command, *, primary: bool = False) -> tk.Button:
            button = tk.Button(
                buttons,
                text=text,
                command=command,
                bg="#1e3a6e" if primary else BG_CARD,
                fg=TEXT,
                activebackground=BLUE if primary else BORDER_G,
                activeforeground=TEXT,
                relief="flat",
                bd=0,
                padx=14,
                pady=7,
                cursor="hand2",
                font=("Helvetica", 9, "bold"),
            )
            return button

        self._back_button = make_button(tr("tutorial.back", "Back"), self.previous_step)
        self._back_button.pack(side="left", padx=(10, 4), pady=9)
        make_button(tr("tutorial.skip", "Skip"), self.close).pack(
            side="left", padx=4, pady=9
        )
        self._next_button = make_button(
            tr("tutorial.next", "Next"), self.next_step, primary=True
        )
        self._next_button.pack(side="right", padx=10, pady=9)

    def _show_step(self) -> None:
        window = self._window
        if not self._active or window is None:
            return
        self._highlight.clear()
        self._menu.close()
        step = TUTORIAL_STEPS[self._step_index]
        targets = self._resolve_app_targets(step)
        if step.menu_key is not None:
            targets.extend(self._menu.show_preview(step.menu_key, step.menu_item_keys))
        try:
            self._app.update_idletasks()
        except tk.TclError, RuntimeError:
            self.close()
            return
        self._active_targets = self._highlight.show(targets)
        self._set_step_text(step)
        window.update_idletasks()
        self._position_window()
        window.lift()

    def _resolve_app_targets(self, step: TutorialStep) -> list[tk.Widget]:
        targets: list[tk.Widget] = []
        for key in step.widget_keys:
            widget = self._resolve_app_widget(key)
            if widget is not None and self._is_viewable(widget):
                targets.append(widget)
        if not targets and step.fallback_widget_key is not None:
            fallback = self._resolve_app_widget(step.fallback_widget_key)
            if fallback is not None:
                targets.append(fallback)
        return targets

    def _resolve_app_widget(self, key: str) -> tk.Widget | None:
        if key.startswith("tab:"):
            tab_name = key.removeprefix("tab:")
            tab = getattr(self._app, "_tab_btns", {}).get(tab_name)
            widget = tab[0] if tab else None
        else:
            widget = getattr(self._app, key, None)
        return widget if isinstance(widget, tk.Widget) else None

    @staticmethod
    def _is_viewable(widget: tk.Widget) -> bool:
        try:
            widget.update_idletasks()
            return bool(widget.winfo_exists() and widget.winfo_viewable())
        except tk.TclError, RuntimeError, AttributeError:
            return False

    def _set_step_text(self, step: TutorialStep) -> None:
        if self._progress_var is not None:
            self._progress_var.set(
                tr(
                    "tutorial.progress",
                    "Step {current} of {total}",
                    current=self._step_index + 1,
                    total=len(TUTORIAL_STEPS),
                )
            )
        if self._title_var is not None:
            self._title_var.set(tr(step.title_key, step.title_default))
        if self._body_var is not None:
            self._body_var.set(tr(step.body_key, step.body_default))
        if self._back_button is not None:
            self._back_button.config(state="normal" if self._step_index else "disabled")
        if self._next_button is not None:
            self._next_button.config(
                text=(
                    tr("tutorial.finish", "Finish")
                    if self._step_index == len(TUTORIAL_STEPS) - 1
                    else tr("tutorial.next", "Next")
                )
            )

    def _position_window(self) -> None:
        window = self._window
        if window is None:
            return
        window.update_idletasks()
        win_width = window.winfo_reqwidth()
        win_height = window.winfo_reqheight()
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        if self._active_targets:
            target = self._active_targets[0]
            target_x = target.winfo_rootx()
            target_y = target.winfo_rooty()
            target_width = target.winfo_width()
            x_pos = target_x + target_width + 16
            if x_pos + win_width > screen_width - 12:
                x_pos = target_x - win_width - 16
            y_pos = target_y
        else:
            root = self._app.winfo_toplevel()
            x_pos = root.winfo_rootx() + max((root.winfo_width() - win_width) // 2, 0)
            y_pos = root.winfo_rooty() + max((root.winfo_height() - win_height) // 2, 0)
        x_pos = max(12, min(x_pos, screen_width - win_width - 12))
        y_pos = max(12, min(y_pos, screen_height - win_height - 48))
        window.geometry(f"+{x_pos}+{y_pos}")


__all__ = [
    "HighlightOverlay",
    "TUTORIAL_DISABLED_KEY",
    "TUTORIAL_STEPS",
    "TutorialController",
    "TutorialStep",
    "save_tutorial_disabled",
    "tutorial_is_disabled",
]
