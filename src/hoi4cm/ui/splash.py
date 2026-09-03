"""Cinematic launch splash — dark themed, animated title."""

import tkinter as tk

from hoi4cm.core.logger import get_logger

log = get_logger("splash")


def show_splash(callback, apply_dpi_scaling=None):
    """Show a borderless animated splash screen, then invoke *callback*.

    *apply_dpi_scaling* is an optional callable that receives the splash
    root and configures per-monitor DPI scaling. The caller (the monolith
    App) provides this because platform-specific DPI setup lives there.
    """

    log.info("Splash: creating Tk root...")
    root = tk.Tk()
    if apply_dpi_scaling is not None:
        apply_dpi_scaling(root)
    log.info("Splash: Tk root created")
    root.overrideredirect(True)  # borderless
    root.attributes("-topmost", True)
    root.configure(bg="#000000")

    SW = root.winfo_screenwidth()
    SH = root.winfo_screenheight()
    W, H = 860, 480
    root.geometry(f"{W}x{H}+{(SW - W) // 2}+{(SH - H) // 2}")

    # Layered canvas
    cv = tk.Canvas(root, width=W, height=H, bg="#000000", highlightthickness=0)
    cv.pack(fill="both", expand=True)

    # ── Background gradient blocks ──────────────────────────────────
    for i in range(H):
        ratio = i / H
        r_c = int(6 + 8 * ratio)
        g_c = int(10 + 6 * ratio)
        b_c = int(16 + 12 * ratio)
        cv.create_line(0, i, W, i, fill=f"#{r_c:02x}{g_c:02x}{b_c:02x}")

    # Subtle grid lines
    for x in range(0, W, 55):
        cv.create_line(x, 0, x, H, fill="#0d1520", width=1)
    for y in range(0, H, 55):
        cv.create_line(0, y, W, y, fill="#0d1520", width=1)

    # Corner accent lines
    acc = "#1e3a6e"
    cv.create_line(0, 0, 120, 0, fill=acc, width=2)
    cv.create_line(0, 0, 0, 80, fill=acc, width=2)
    cv.create_line(W, 0, W - 120, 0, fill=acc, width=2)
    cv.create_line(W, 0, W, 80, fill=acc, width=2)
    cv.create_line(0, H, 120, H, fill=acc, width=2)
    cv.create_line(0, H, 0, H - 80, fill=acc, width=2)
    cv.create_line(W, H, W - 120, H, fill=acc, width=2)
    cv.create_line(W, H, W, H - 80, fill=acc, width=2)

    # Blue top accent bar
    cv.create_rectangle(0, 0, W, 3, fill="#3b82f6", outline="")

    # ── Static elements ─────────────────────────────────────────────
    # Melon decoration
    deco = cv.create_text(
        W // 2,
        115,
        text="🍉",
        fill="#ffffff",
        font=("Segoe UI Emoji", 60),
        anchor="center",
    )

    # Subtitle line above
    sub1 = cv.create_text(
        W // 2,
        165,
        text="CONTENT MAKER FOR",
        fill="#1e3a6e",
        font=("Courier", 11, "bold"),
        anchor="center",
    )

    # Main title — starts invisible
    title = cv.create_text(
        W // 2,
        230,
        text="Hearts of Iron 4",
        fill="#000000",
        font=("Georgia", 44, "bold"),
        anchor="center",
    )

    # By line — starts invisible
    byline = cv.create_text(
        W // 2,
        295,
        text="Millennium Dawn Team",
        fill="#000000",
        font=("Courier", 14),
        anchor="center",
    )

    # Version / loading bar container
    cv.create_rectangle(
        W // 2 - 180, 370, W // 2 + 180, 382, fill="#0d1117", outline="#21262d"
    )
    bar_fill = cv.create_rectangle(
        W // 2 - 180, 370, W // 2 - 180, 382, fill="#3b82f6", outline=""
    )
    bar_lbl = cv.create_text(
        W // 2,
        395,
        text="Initializing…",
        fill="#374151",
        font=("Courier", 9),
        anchor="center",
    )

    # Bottom credit
    cv.create_text(
        W // 2,
        460,
        text="hoi4_focus_maker  •  v2.0",
        fill="#1e2a3a",
        font=("Courier", 8),
        anchor="center",
    )

    # ── Animation state ─────────────────────────────────────────────
    state = {"frame": 0, "done": False}

    def lerp(a, b, t):
        return a + (b - a) * max(0, min(1, t))

    def ease_out(t):
        return 1 - (1 - t) ** 3

    def ease_in_out(t):
        return t * t * (3 - 2 * t)

    def to_hex(r, g, b):
        return f"#{int(r):02x}{int(g):02x}{int(b):02x}"

    def animate():
        f = state["frame"]
        if state["done"]:
            return

        # ── Deco pulse (frames 0-20) ──
        if f <= 30:
            t = ease_out(f / 20)
            ri = int(lerp(0x1E, 0x58, t))
            gi = int(lerp(0x3A, 0xA6, t))
            bi = int(lerp(0x6E, 0xFF, t))
            cv.itemconfig(deco, fill=to_hex(ri, gi, bi))
            cv.itemconfig(
                sub1,
                fill=to_hex(
                    int(lerp(0x1E, 0x6E, t)),
                    int(lerp(0x3A, 0x76, t)),
                    int(lerp(0x6E, 0x81, t)),
                ),
            )

        # ── Title fade in (frames 10-45) ──
        if 10 <= f <= 55:
            t = ease_out((f - 10) / 35)
            ri = int(lerp(0, 0xE6, t))
            gi = int(lerp(0, 0xED, t))
            bi = int(lerp(0, 0xF3, t))
            cv.itemconfig(title, fill=to_hex(ri, gi, bi))
            # Slight float-in effect via y position
            y_pos = lerp(250, 230, t)
            cv.coords(title, W // 2, y_pos)

        # ── Byline fade in (frames 30-60) ──
        if 30 <= f <= 70:
            t = ease_out((f - 30) / 30)
            ri = int(lerp(0, 0x58, t))
            gi = int(lerp(0, 0xA6, t))
            bi = int(lerp(0, 0xFF, t))
            cv.itemconfig(byline, fill=to_hex(ri, gi, bi))

        # ── Progress bar (frames 50-100) ──
        if 50 <= f <= 100:
            t = ease_in_out((f - 50) / 50)
            x_end = lerp(W // 2 - 180, W // 2 + 180, t)
            cv.coords(bar_fill, W // 2 - 180, 370, x_end, 382)
            labels = [
                "Initializing…",
                "Loading assets…",
                "Building canvas…",
                "Applying dark theme…",
                "Ready.",
            ]
            idx = int(t * (len(labels) - 1))
            cv.itemconfig(bar_lbl, text=labels[min(idx, len(labels) - 1)])

        # ── Fade out everything (frames 110-120) ──
        if f >= 110:
            t = (f - 110) / 10
            # Darken by overlaying black rectangle
            if "overlay" not in state:
                state["overlay"] = cv.create_rectangle(
                    0, 0, W, H, fill="#000000", outline="", stipple="gray50"
                )
            if t >= 1.0:
                log.info("Splash: animation done, destroying splash root...")
                root.destroy()
                log.info("Splash: root destroyed, calling app launcher...")
                state["done"] = True
                # Tk swallows exceptions raised inside this after-callback, so a
                # failure during App construction would silently leave a half-built
                # window. Log it loudly instead of letting it disappear.
                try:
                    callback()
                except Exception:
                    log.exception(
                        "Splash: fatal exception during app construction — "
                        "check log for details"
                    )
                return

        state["frame"] += 1
        root.after(33, animate)  # ~30 fps

    root.after(80, animate)
    root.mainloop()
