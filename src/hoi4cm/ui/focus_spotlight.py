"""Floating focus artwork and radial actions above an app-owned dimming veil."""

from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import font as tkfont
from typing import Any

from hoi4cm.mod import MOD
from hoi4cm.ui.image_broker import ImageTransform

TRANSPARENT = "#010203"
CYAN = "#56c8dd"
TEXT = "#e6edf3"


@dataclass(frozen=True)
class SpotlightLayout:
    width: int
    height: int
    preview: tuple[int, int, int, int]
    buttons: tuple[tuple[int, int], ...]
    button_size: tuple[int, int]


def spotlight_layout(
    width, button_width, button_height, scale=1.0, preview_height=None
):
    """Radial at desktop widths; compact rows below the art on narrow windows.

    Coordinates are independent of tree position and zoom. The transparent
    viewport scrolls only when even the compact composition cannot fit.
    Button order matches ACTIONS, not visual left-to-right order.
    """
    gap = round(24 * scale)
    cw = round(220 * scale)
    ch = preview_height or round(240 * scale)
    bw, bh = button_width, button_height
    wide_width = 2 * bw + cw + 2 * gap
    top = bh + gap
    if width >= wide_width:
        cx = bw + gap
        middle = (wide_width - bw) // 2
        upper = top + round(20 * scale)
        lower = top + ch - bh - round(12 * scale)
        inset = round(16 * scale)
        positions = (
            (middle, 0),
            (0, upper),
            (wide_width - bw, upper),
            (wide_width - bw - inset, lower),
            (inset, lower),
            (middle, top + ch + gap),
        )
        return SpotlightLayout(
            wide_width, top + ch + gap + bh, (cx, top, cw, ch), positions, (bw, bh)
        )
    columns = 2 if width >= 2 * bw + gap else 1
    content_width = max(cw, columns * bw + (columns - 1) * gap)
    middle = (content_width - bw) // 2
    row_top = top + ch + gap
    positions = [(middle, 0)]
    positions.extend(
        (
            (content_width - columns * bw - (columns - 1) * gap) // 2
            + (i % columns) * (bw + gap),
            row_top + (i // columns) * (bh + gap // 2),
        )
        for i in range(4)
    )
    positions[3], positions[4] = positions[4], positions[3]
    bottom = row_top + (4 // columns) * (bh + gap // 2) + gap // 2
    positions.append((middle, bottom))
    return SpotlightLayout(
        content_width,
        bottom + bh,
        ((content_width - cw) // 2, top, cw, ch),
        tuple(positions),
        (bw, bh),
    )


class RoundedAction(tk.Canvas):
    """Rounded surface around a native, keyboard-accessible Tk button."""

    def __init__(self, parent, label, image, command, *, destructive=False):
        super().__init__(
            parent,
            bg=TRANSPARENT,
            highlightthickness=0,
            takefocus=False,
            cursor="hand2",
        )
        self.destructive = destructive
        self.hover = False
        self.focused = False
        self.pressed = False
        self.button = tk.Button(
            self,
            text=label,
            image=image,
            compound="left",
            anchor="w",
            command=command,
            bg="#182430",
            fg="#ef6b73" if destructive else TEXT,
            activeforeground=TEXT,
            activebackground="#203442",
            relief="flat",
            bd=0,
            highlightthickness=0,
            takefocus=True,
            cursor="hand2",
            font=("Segoe UI", 11),
        )
        self.item = self.create_window(0, 0, window=self.button, anchor="center")
        self.bind("<Configure>", lambda _: self.paint())
        for widget in (self, self.button):
            widget.bind("<Enter>", lambda _: self.set_state(hover=True))
            widget.bind("<Leave>", lambda _: self.set_state(hover=False))
        self.button.bind("<FocusIn>", lambda _: self.set_state(focused=True))
        self.button.bind("<FocusOut>", lambda _: self.set_state(focused=False))
        self.button.bind("<Return>", lambda _: self.button.invoke() or "break")
        self.bind("<ButtonPress-1>", lambda _: self.set_state(pressed=True))
        self.bind("<ButtonRelease-1>", self.release)

    def set_state(self, **values):
        for name, value in values.items():
            setattr(self, name, value)
        self.paint()

    def release(self, event):
        was_pressed = self.pressed
        self.set_state(pressed=False)
        if (
            was_pressed
            and 0 <= event.x < self.winfo_width()
            and 0 <= event.y < self.winfo_height()
        ):
            self.button.invoke()
        return "break"

    def paint(self):
        w, h = self.winfo_width(), self.winfo_height()
        fill = (
            ("#352630" if self.hover else "#251f2a")
            if self.destructive
            else ("#203442" if self.hover else "#182430")
        )
        accent = "#ef6b73" if self.destructive else CYAN
        outline = (
            accent
            if self.hover or self.focused
            else ("#8d4d58" if self.destructive else "#3d566b")
        )
        self.delete("surface")
        r, inset = min(12, h / 4), 3
        self.create_polygon(
            inset + r,
            inset,
            w - inset - r,
            inset,
            w - inset,
            inset,
            w - inset,
            inset + r,
            w - inset,
            h - inset - r,
            w - inset,
            h - inset,
            w - inset - r,
            h - inset,
            inset + r,
            h - inset,
            inset,
            h - inset,
            inset,
            h - inset - r,
            inset,
            inset + r,
            inset,
            inset,
            smooth=True,
            splinesteps=24,
            fill=fill,
            outline=outline,
            width=2 if self.focused else 1,
            tags="surface",
        )
        self.tag_lower("surface")
        self.coords(self.item, w / 2, h / 2)
        self.itemconfigure(self.item, width=max(1, w - 28), height=max(1, h - 14))
        self.button.configure(bg=fill, activebackground=fill)


class FocusSpotlight:
    """A color-keyed foreground keeps the tree visible between every control.

    Windows Tk supplies native color-key transparency; unsupported window
    systems report the compositor limitation instead of showing an opaque panel.
    """

    def __init__(self, app: Any, actions, invoke, dismiss):
        self.app, self.actions = app, actions
        self.invoke, self.dismiss = invoke, dismiss
        self.backdrop = None
        self.window = None
        self.focus_id = None
        self.buttons: list[tk.Button] = []
        self.images: list[tk.PhotoImage] = []
        self.surfaces: list[RoundedAction] = []
        self.artwork = None
        self._art_size = None
        self._layout_key = None
        self._previous_grab = None
        self.scroll = self.vbar = self.hbar = None
        self.content = self.preview = None
        self.close_button = self.name_label = self.duration_label = None
        self._art_item = self._fallback = None
        self._owner = ("spotlight", id(self))
        self._configure_binding = app.bind("<Configure>", self._configured, add="+")

    def _configured(self, event):
        if event.widget is self.app:
            self.reflow()

    def open(self, focus):
        self.focus_id = focus.id
        self._previous_grab = self.app.grab_current()
        self.backdrop = tk.Toplevel(self.app)
        self.backdrop.withdraw()
        self.backdrop.overrideredirect(True)
        self.backdrop.transient(self.app)
        self.backdrop.configure(bg="#02050b")
        self.backdrop.attributes("-alpha", 0.72)
        self.backdrop.bind("<ButtonRelease-1>", lambda _: self.dismiss() or "break")
        self.window = tk.Toplevel(self.app)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.transient(self.app)
        self.window.attributes("-transparentcolor", TRANSPARENT)
        self.window.configure(bg=TRANSPARENT)
        self.window.bind("<Escape>", lambda _: self.dismiss() or "break")
        self.window.bind("<Tab>", lambda e: self.step(-1 if e.state & 1 else 1))
        self.window.bind("<ISO_Left_Tab>", lambda _: self.step(-1))
        self.window.bind("<ButtonRelease-1>", self._outside)
        self.window.bind("<KeyPress>", self._key)
        self.window.bind("<MouseWheel>", self._wheel)
        self.window.bind(
            "<Button-4>", lambda _: self.scroll.yview_scroll(-1, "units") or "break"
        )
        self.window.bind(
            "<Button-5>", lambda _: self.scroll.yview_scroll(1, "units") or "break"
        )
        self.scroll = tk.Canvas(self.window, bg=TRANSPARENT, highlightthickness=0)
        self.vbar = tk.Scrollbar(self.window, command=self.scroll.yview)
        self.hbar = tk.Scrollbar(
            self.window, orient="horizontal", command=self.scroll.xview
        )
        self.scroll.configure(
            yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set
        )
        self.content = tk.Frame(self.scroll, bg=TRANSPARENT)
        self.scroll.create_window(0, 0, window=self.content, anchor="nw")
        self.close_button = tk.Button(
            self.window,
            text="Close ×",
            command=self.dismiss,
            bg=TRANSPARENT,
            activebackground="#203442",
            activeforeground=CYAN,
            fg=TEXT,
            relief="flat",
            takefocus=True,
            highlightcolor=CYAN,
            highlightbackground=TRANSPARENT,
            highlightthickness=2,
        )
        self.preview = tk.Canvas(
            self.content,
            bg=TRANSPARENT,
            highlightthickness=0,
        )
        self._art_item = self.preview.create_image(0, 0, anchor="center")
        self._fallback = self.preview.create_text(
            0, 0, text=focus.icon, fill=TEXT, font=("Segoe UI", 52)
        )
        self.name_label = tk.Label(
            self.preview,
            text=focus.loc_name or focus.name,
            bg=TRANSPARENT,
            fg=TEXT,
            font=("Segoe UI", 15, "bold"),
            justify="center",
        )
        self.duration_label = tk.Label(
            self.preview,
            text=f"{focus.cost * 7:g} days",
            bg=TRANSPARENT,
            fg=CYAN,
            font=("Segoe UI", 11),
        )
        scale = self._scale()
        for action, label in self.actions:
            source = tk.PhotoImage(
                master=self.window,
                data=(
                    Path(__file__).with_name("assets") / f"{action}.png"
                ).read_bytes(),
            )
            icon = source.subsample(max(1, math.ceil(source.width() / (24 * scale))))
            self.images.append(icon)
            surface = RoundedAction(
                self.content,
                label,
                icon,
                lambda action=action: self.invoke(action),
                destructive=action == "delete",
            )
            self.surfaces.append(surface)
            self.buttons.append(surface.button)
        self.reflow()
        self.backdrop.deiconify()
        self.window.deiconify()
        self.backdrop.lift(self.app)
        self.window.lift(self.backdrop)
        self.window.grab_set()
        self.window.lift()
        self.buttons[0].focus_force()

    def _scale(self):
        return max(0.5, float(self.app.tk.call("tk", "scaling")) / (96 / 72))

    def reflow(self):
        if self.window is None:
            return
        if self.focus_id not in self.app.focuses:
            self.dismiss()
            return
        app = self.app
        width, height = app.winfo_width(), app.winfo_height()
        x, y = app.winfo_rootx(), app.winfo_rooty()
        scale = self._scale()
        key = (width, height, x, y, scale)
        if key == self._layout_key:
            return
        self._layout_key = key
        self.backdrop.geometry(f"{width}x{height}+{x}+{y}")
        font = tkfont.Font(root=app, font=("Segoe UI", 11))
        bw = max(
            round(200 * scale),
            max(font.measure(label) for _, label in self.actions) + round(72 * scale),
        )
        bh = max(round(48 * scale), font.metrics("linespace") + round(24 * scale))
        self.name_label.configure(wraplength=round(216 * scale))
        name_height = self.name_label.winfo_reqheight()
        art_size = round((168 if height >= 500 * scale else 140) * scale)
        label_gap = round(8 * scale)
        duration_height = self.duration_label.winfo_reqheight()
        preview_height = art_size + name_height + duration_height + 2 * label_gap
        margin = round(16 * scale)
        available_width = max(1, width - 2 * margin)
        layout = spotlight_layout(available_width, bw, bh, scale, preview_height)
        viewport_w = min(available_width, layout.width)
        close_height = round(36 * scale)
        viewport_h = min(max(1, height - 2 * margin - close_height), layout.height)
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.scroll.place(
            x=(width - viewport_w) // 2,
            y=close_height + (height - close_height - viewport_h) // 2,
            width=viewport_w,
            height=viewport_h,
        )
        self.content.configure(width=layout.width, height=layout.height)
        self.scroll.configure(scrollregion=(0, 0, layout.width, layout.height))
        self.vbar.place_forget()
        self.hbar.place_forget()
        if layout.height > viewport_h:
            self.vbar.place(
                x=(width + viewport_w) // 2,
                y=close_height,
                height=height - close_height - margin,
                width=margin,
            )
        if layout.width > viewport_w:
            self.hbar.place(
                x=margin, y=height - margin, width=width - 2 * margin, height=margin
            )
        self.close_button.place(
            x=width - round(104 * scale),
            y=round(6 * scale),
            width=round(88 * scale),
            height=round(30 * scale),
        )
        cx, cy, cw, ch = layout.preview
        self.preview.place(x=cx, y=cy, width=cw, height=ch)
        self.preview.coords(self._art_item, cw / 2, art_size / 2)
        self.preview.coords(self._fallback, cw / 2, art_size / 2)
        self.preview.itemconfigure(self._fallback, font=("Segoe UI", round(96 * scale)))
        self.name_label.place(x=0, y=art_size + label_gap, width=cw, height=name_height)
        self.duration_label.place(
            x=0,
            y=art_size + name_height + 2 * label_gap,
            width=cw,
            height=duration_height,
        )
        for surface, (bx, by) in zip(self.surfaces, layout.buttons, strict=True):
            surface.place(x=bx, y=by, width=bw, height=bh)
        self._request_art((art_size, art_size))

    def _request_art(self, size):
        if size == self._art_size:
            return
        self._art_size = size
        focus = self.app.focuses[self.focus_id]
        broker = self.app._image_broker
        asset = (
            MOD.graphics_catalog.resolve(focus.gfx)
            if MOD.loaded and focus.gfx
            else None
        )
        if asset is None or broker is None:
            return
        expected = self.focus_id

        def ready(image):
            if self.window is None or self.focus_id != expected:
                return
            if image is not None and size == self._art_size:
                self.artwork = image
                self.preview.itemconfigure(self._art_item, image=image)
                self.preview.itemconfigure(self._fallback, state="hidden")

        image = broker.request(
            asset,
            MOD.graphics_catalog.path_for(asset),
            transform=ImageTransform(size=size, preserve_aspect=True),
            owner=self._owner,
            callback=ready,
        )
        ready(image)
        self.app._start_image_poll()

    def _outside(self, event):
        # Color-key holes route to the grabbed Toplevel. Consume the release
        # so the dismissed click cannot reach a real focus underneath.
        if event.widget in (self.window, self.scroll, self.content, self.preview):
            self.dismiss()
        return "break"

    def _key(self, event):
        if event.keysym in ("space", "Return", "Tab", "ISO_Left_Tab", "Escape"):
            return None
        if event.keysym in ("Up", "Down"):
            return self.step(-1 if event.keysym == "Up" else 1)
        return "break"

    def step(self, direction):
        items = [*self.buttons, self.close_button]
        current = self.app.focus_get()
        index = items.index(current) if current in items else 0
        target = items[(index + direction) % len(items)]
        target.focus_set()
        if target is self.close_button:
            return "break"
        # Compact layouts scroll the focused native control into view.
        top = target.master.winfo_y()
        viewport = self.scroll.winfo_height()
        total = self.content.winfo_height()
        self.scroll.yview_moveto(
            max(0, min(top - viewport / 2, total - viewport)) / max(1, total)
        )
        return "break"

    def _wheel(self, event):
        self.scroll.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def close(self):
        if self.window is None:
            return
        if self.app._image_broker is not None:
            self.app._image_broker.release(self._owner)
        self.window.grab_release()
        self.window.destroy()
        self.backdrop.destroy()
        self.window = self.backdrop = None
        self.focus_id = None
        self.buttons.clear()
        self.images.clear()
        self.surfaces.clear()
        self.artwork = None
        self._art_size = self._layout_key = None
        if self._previous_grab is not None and self._previous_grab.winfo_exists():
            self._previous_grab.grab_set()
        self._previous_grab = None

    def dispose(self):
        self.close()
        self.app.unbind("<Configure>", self._configure_binding)


__all__ = ["FocusSpotlight", "SpotlightLayout", "spotlight_layout"]
