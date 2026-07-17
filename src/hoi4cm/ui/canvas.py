"""Focus-tree canvas: rendering, pan/zoom, hit-testing and the minimap.

Extracted verbatim from the monolith as a mixin so the methods keep operating
on ``App`` state (``self.cv``, ``self.focuses``, ``self.offset`` …). ``App``
inherits :class:`CanvasMixin`, so behaviour is identical — this only moves the
lines out of ``hoi4_content_maker.py``.
"""

import tkinter as tk

from hoi4cm.mod import MOD
from hoi4cm.ui import (
    BG_CARD,
    BLUE,
    BORDER_G,
    BOX,
    FC_BG,
    FC_BORDER,
    FC_SEL,
    FC_SEL_BD,
    MUTEX_COL,
    ORANGE,
    PREREQ_COL,
    TEXT,
    TEXT_DIM,
    XGRID,
    YGRID,
)
from hoi4cm.ui.canvas_renderer import FocusCanvasBundle
from hoi4cm.ui.canvas_scheduler import DirtyRedrawState, RedrawChannel
from hoi4cm.ui.image_broker import ImageBroker
from hoi4cm.ui.scene_index import SceneIndex
from hoi4cm.ui.tasks import get_executor
from hoi4cm.ui.viewport import edge_visible, focus_visible, visible_world_rect

# Margin (canvas pixels, scaled by zoom) added around the viewport before
# culling: covers the card's shadow/glow overhang and the label drawn below
# it, so nothing pops in/out right at the screen edge.
_CULL_MARGIN_BOXES = 2
_FOCUS_LOD_ZOOM = 0.4


class CanvasMixin:
    """Canvas rendering + interaction methods for :class:`App`."""

    # Above this many loaded focuses, the minimap buckets dots to one per
    # occupied pixel cell and skips prereq lines (see _draw_minimap).
    _MM_DOWNSAMPLE_THRESHOLD = 2000

    def _bind_canvas(self):
        c = self.cv
        self._image_broker = ImageBroker(
            get_executor(self), generation=lambda: MOD.graphics_catalog.generation
        )
        self._image_poll_job = None
        lifecycle = getattr(self, "_lifecycle", None)
        if lifecycle is not None:
            lifecycle.add_resource(self._close_canvas_tasks)
        c.bind("<ButtonPress-1>", self._lmb_dn)
        c.bind("<B1-Motion>", self._lmb_mv)
        c.bind("<ButtonRelease-1>", self._lmb_up)
        c.bind("<ButtonPress-2>", self._pan_pr)
        c.bind("<B2-Motion>", self._pan_mv)
        c.bind("<ButtonRelease-2>", self._pan_rl)
        c.bind("<Control-ButtonPress-1>", self._pan_pr)
        c.bind("<Control-B1-Motion>", self._pan_mv)
        c.bind("<Control-ButtonRelease-1>", self._pan_rl)
        c.bind("<ButtonPress-3>", self._rmb)
        c.bind("<MouseWheel>", self._scroll)
        c.bind("<Button-4>", self._scroll)
        c.bind("<Button-5>", self._scroll)
        c.bind("<Motion>", self._motion)
        c.bind(
            "<Configure>",
            lambda e: self._redraw(RedrawChannel.VIEW, reason="configure"),
        )
        c.bind("<Leave>", lambda e: self._coord_lbl.config(text="  —  "))

    def _poll_images(self):
        self._image_poll_job = None
        lifecycle = getattr(self, "_lifecycle", None)
        if lifecycle is not None and not lifecycle.accepting:
            return
        self._image_broker.drain()
        if self._image_broker.pending:
            self._image_poll_job = self.cv.after(16, self._poll_images)

    def _start_image_poll(self):
        lifecycle = getattr(self, "_lifecycle", None)
        if (
            (lifecycle is None or lifecycle.accepting)
            and self._image_poll_job is None
            and self._image_broker.pending
        ):
            self._image_poll_job = self.cv.after(16, self._poll_images)

    def _invalidate_canvas_images(self):
        image_broker = getattr(self, "_image_broker", None)
        if image_broker is not None:
            image_broker.clear()

    def _close_canvas_tasks(self):
        for attribute in ("_image_poll_job", "_redraw_job", "_lines_job"):
            job = getattr(self, attribute, None)
            if job is None:
                continue
            try:
                self.cv.after_cancel(job)
            except tk.TclError:
                pass
            setattr(self, attribute, None)
        image_broker = getattr(self, "_image_broker", None)
        if image_broker is not None:
            image_broker.close()

    def w2c(self, gx, gy):
        """HOI4 grid integer coords -> canvas pixel coords.
        xGridSize=96, yGridSize=130 (from hoi4modutilities contentbuilder.ts)
        """
        return (
            gx * XGRID * self.zoom + self.offset[0],
            gy * YGRID * self.zoom + self.offset[1],
        )

    def c2w(self, cx, cy):
        """Canvas pixel -> HOI4 grid integer coords (snapped)."""
        return round((cx - self.offset[0]) / (XGRID * self.zoom)), round(
            (cy - self.offset[1]) / (YGRID * self.zoom)
        )

    def snap(self, gx, gy):
        return int(gx), int(gy)

    def _reset_canvas_bounds(self):
        """Shrink the usable canvas back to the minimum CANVAS_MIN_SIZE square."""
        self._canvas_min = [0, 0]
        self._canvas_max = [self.CANVAS_MIN_SIZE - 1, self.CANVAS_MIN_SIZE - 1]

    def _ensure_canvas_contains(self, gx, gy):
        """Grow the canvas by CANVAS_EXPAND_STEP toward (gx, gy) until it fits.

        A focus placed on an edge cell (e.g. the last column) expands the canvas
        in that direction too, so there is always a frontier of empty cells
        ahead. Bounds only ever grow (never shrink), so editing near an edge
        keeps the room earlier placements created. Returns True if bounds changed.
        """
        step = self.CANVAS_EXPAND_STEP
        changed = False
        while gx <= self._canvas_min[0]:
            self._canvas_min[0] -= step
            changed = True
        while gx >= self._canvas_max[0]:
            self._canvas_max[0] += step
            changed = True
        while gy <= self._canvas_min[1]:
            self._canvas_min[1] -= step
            changed = True
        while gy >= self._canvas_max[1]:
            self._canvas_max[1] += step
            changed = True
        return changed

    def _grow_canvas_to_focuses(self):
        """Expand bounds so every existing focus sits inside the usable canvas."""
        changed = False
        for f in self.focuses.values():
            if self._ensure_canvas_contains(f.x, f.y):
                changed = True
        return changed

    def _draw_canvas_bounds(self):
        """Dim everything outside the usable canvas and outline its edge."""
        self.cv.delete("canvas_mask")
        W = max(1, self.cv.winfo_width())
        H = max(1, self.cv.winfo_height())
        x0, y0 = self.w2c(self._canvas_min[0] - 0.5, self._canvas_min[1] - 0.5)
        x1, y1 = self.w2c(self._canvas_max[0] + 0.5, self._canvas_max[1] + 0.5)
        outside = "#080b12"

        def _mask(a, b, c, d):
            if c > a and d > b:
                self.cv.create_rectangle(
                    a, b, c, d, fill=outside, outline="", tags="canvas_mask"
                )

        _mask(0, 0, x0, H)  # left
        _mask(x1, 0, W, H)  # right
        _mask(max(x0, 0), 0, min(x1, W), y0)  # top
        _mask(max(x0, 0), y1, min(x1, W), H)  # bottom
        self.cv.create_rectangle(
            x0, y0, x1, y1, outline=BLUE, width=2, tags="canvas_mask"
        )
        self.cv.tag_lower("canvas_mask")
        if self.cv.find_withtag("grid"):
            self.cv.tag_lower("grid")

    def _visible_rect(self):
        """World-coord viewport rect (plus card margin), or None to cull nothing.

        Returns None before the window has mapped (``winfo_width/height``
        report 1 pre-map), and while zoomed out enough that BOX*zoom rounds
        to 0 (division-by-zero territory in ``visible_world_rect`` — treat
        it the same as "not mapped yet": don't cull anything).
        """
        W = self.cv.winfo_width()
        H = self.cv.winfo_height()
        if W <= 1 or H <= 1:
            return None
        margin = _CULL_MARGIN_BOXES * BOX * self.zoom
        return visible_world_rect(
            self.offset[0], self.offset[1], self.zoom, W, H, margin
        )

    def _canvas_runtime(self):
        if not hasattr(self, "_redraw_state"):
            self._redraw_state = DirtyRedrawState()
        if not hasattr(self, "_scene_index"):
            self._scene_index = SceneIndex()
        if not hasattr(self, "_focus_bundles"):
            self._focus_bundles = {}

    def _redraw(
        self,
        channels=RedrawChannel.VIEW | RedrawChannel.SCENE | RedrawChannel.FOCUS_LIST,
        *,
        reason="legacy",
    ):
        """Schedule one frame and merge any additional dirty channels into it."""
        self._canvas_runtime()
        if channels & RedrawChannel.SCENE and getattr(self, "_lines_job", None):
            self.cv.after_cancel(self._lines_job)
            self._lines_job = None
        if self._redraw_state.request(channels, reason) and not self._redraw_job:
            self._redraw_job = self.cv.after(16, self._do_redraw)

    def _do_redraw(self):
        self._canvas_runtime()
        self._redraw_job = None
        self._redraw_pending = False
        request = self._redraw_state.consume()
        self._render_frame(request.channels)

    def _render_frame(self, channels):
        max(1, self.cv.winfo_width())
        max(1, self.cv.winfo_height())
        self._scene_index.ensure(
            self.focuses, validate=bool(channels & RedrawChannel.SCENE)
        )
        if channels & RedrawChannel.SCENE:
            self._grow_canvas_to_focuses()
        self._draw_grid()
        self._draw_canvas_bounds()
        self._draw_coord_labels()
        vis_rect = self._visible_rect()
        self._draw_lines(vis_rect)
        if vis_rect is None:
            visible_ids = list(self.focuses)
        else:
            visible_ids = self._scene_index.query_focus_ids(vis_rect)
        self._reclaim_focus_bundles(set(visible_ids))
        for focus_id in visible_ids:
            focus = self.focuses.get(focus_id)
            if focus is not None:
                self._draw_focus(focus, vis_rect)
        self._draw_cfp_markers()
        self._draw_canvas_legend()
        self._update_statusbar()
        if channels & RedrawChannel.FOCUS_LIST:
            self._update_focus_list_selection()
        self._draw_minimap()

    def _draw_lines_throttled(self):
        """Coalesce rapid line redraws (during a drag) to ~60fps.

        The dragged focus's box is moved directly via cv.move(); only the
        connection lines need rebuilding, so this avoids a full _redraw().
        """
        if self._lines_job:
            return
        self._lines_job = self.cv.after(16, self._do_draw_lines_throttled)

    def _do_draw_lines_throttled(self):
        self._lines_job = None
        self._canvas_runtime()
        drag = getattr(self, "_drag", None)
        drag_id = drag.get("id") if drag and drag.get("moved") else None
        if drag_id is not None:
            # Single-focus geometry move (a drag): patch just that focus and its
            # edges instead of rebuilding the whole scene index every frame.
            self._scene_index.update_focus(self.focuses, drag_id)
        else:
            self._scene_index.ensure(self.focuses, validate=True)
        self._draw_lines()

    def _redraw_now(
        self,
        channels=RedrawChannel.VIEW | RedrawChannel.SCENE,
        *,
        reason="immediate",
    ):
        """Immediate redraw for zoom/resize — skips throttle."""
        self._canvas_runtime()
        if self._redraw_job:
            self.cv.after_cancel(self._redraw_job)
            self._redraw_job = None
        if self._lines_job:
            self.cv.after_cancel(self._lines_job)
            self._lines_job = None
        self._redraw_pending = False
        self._redraw_state.request(channels, reason)
        request = self._redraw_state.consume()
        self._render_frame(request.channels)

    def _draw_grid(self):
        """Draw the bounded grid as native canvas lines.

        The canvas is finite (min 10x10, grows by 5), so the grid is only a few
        dozen line items — far cheaper than the old full-viewport PhotoImage that
        was rebuilt pixel-by-pixel in Python every frame. Because the lines are
        real canvas items tagged "grid", panning is a pure ``cv.move`` with no
        rebuild; we only regenerate on zoom, resize or a bounds change.
        """
        W = max(1, self.cv.winfo_width())
        H = max(1, self.cv.winfo_height())
        z = self.zoom
        on = getattr(self, "_grid_on", True)
        stepx = XGRID * z

        # Rebuild only when something visible actually changed.
        key = (
            on,
            round(z, 4),
            tuple(self._canvas_min),
            tuple(self._canvas_max),
            round(self.offset[0], 1),
            round(self.offset[1], 1),
            W,
            H,
        )
        if key == self._grid_key and self.cv.find_withtag("grid"):
            return
        self._grid_key = key
        self.cv.delete("grid")
        self._grid_item = None
        # Hide when toggled off or so dense the lines would smear together.
        if not on or stepx < 4:
            return

        minx, miny = self._canvas_min
        maxx, maxy = self._canvas_max
        stepy = YGRID * z
        x0 = minx * XGRID * z + self.offset[0] - stepx / 2
        x1 = maxx * XGRID * z + self.offset[0] + stepx / 2
        y0 = miny * YGRID * z + self.offset[1] - stepy / 2
        y1 = maxy * YGRID * z + self.offset[1] + stepy / 2
        minor = "#1e293b"  # subtle cell line
        major = "#2d3a4e"  # brighter line every other column/row

        # Vertical cell boundaries (a boundary sits at each gx - 0.5).
        for gx in range(minx, maxx + 2):
            px = gx * XGRID * z + self.offset[0] - stepx / 2
            self.cv.create_line(
                px,
                y0,
                px,
                y1,
                fill=(major if gx % 2 == 0 else minor),
                tags="grid",
            )
        # Horizontal cell boundaries.
        for gy in range(miny, maxy + 2):
            py = gy * YGRID * z + self.offset[1] - stepy / 2
            self.cv.create_line(
                x0,
                py,
                x1,
                py,
                fill=(major if gy % 2 == 0 else minor),
                tags="grid",
            )
        self.cv.tag_lower("grid")

    def _draw_coord_labels(self):
        """Draw HOI4 x/y grid numbers along top and left so exact position is clear."""
        self.cv.delete("coord_lbl")
        W = max(1, self.cv.winfo_width())
        H = max(1, self.cv.winfo_height())
        stepx = XGRID * self.zoom
        stepy = YGRID * self.zoom
        step = min(stepx, stepy)  # use smaller axis for density checks
        if step < 16:
            return  # too dense at low zoom

        # Label every unit when zoomed in, every 2 when small
        interval = 1 if step >= 80 else 2
        fsz = max(7, min(10, int(step * 0.075)))
        font = ("Courier", fsz, "bold")

        # ── X axis labels (top row) ──────────────────────────
        world_left = -self.offset[0] / (XGRID * self.zoom)
        gx = int(world_left) - 1
        cx = gx * XGRID * self.zoom + self.offset[0]
        while cx < W + step:
            if gx % interval == 0:
                col = "#6a9a4a" if gx % 2 == 0 else "#4a6a2a"
                # Background chip
                self.cv.create_rectangle(
                    cx - fsz,
                    1,
                    cx + fsz,
                    fsz * 2 + 2,
                    fill="#0a0e08",
                    outline="",
                    tags="coord_lbl",
                )
                self.cv.create_text(
                    cx,
                    fsz + 1,
                    text=str(gx),
                    fill=col,
                    font=font,
                    anchor="center",
                    tags="coord_lbl",
                )
            cx += XGRID * self.zoom
            gx += 1

        # ── Y axis labels (left column) ──────────────────────
        world_top = -self.offset[1] / (YGRID * self.zoom)
        gy = int(world_top) - 1
        cy = gy * YGRID * self.zoom + self.offset[1]
        while cy < H + step:
            if gy % interval == 0:
                col = "#6a9a4a" if gy % 2 == 0 else "#4a6a2a"
                lbl = str(gy)
                w = fsz * len(lbl)
                self.cv.create_rectangle(
                    1,
                    cy - fsz,
                    w + 6,
                    cy + fsz,
                    fill="#0a0e08",
                    outline="",
                    tags="coord_lbl",
                )
                self.cv.create_text(
                    w // 2 + 3,
                    cy,
                    text=lbl,
                    fill=col,
                    font=font,
                    anchor="center",
                    tags="coord_lbl",
                )
            cy += YGRID * self.zoom
            gy += 1

        # ── (0,0) origin marker — bright cross so you always know the anchor ──
        ox, oy = self.w2c(0, 0)
        ms = max(6, int(12 * self.zoom))  # marker size
        self.cv.create_line(
            ox - ms, oy, ox + ms, oy, fill="#4aaa4a", width=2, tags="coord_lbl"
        )
        self.cv.create_line(
            ox, oy - ms, ox, oy + ms, fill="#4aaa4a", width=2, tags="coord_lbl"
        )
        self.cv.create_text(
            ox + ms + 3,
            oy - ms - 3,
            text="(0,0)",
            fill="#4aaa4a",
            font=("Courier", 8, "bold"),
            anchor="sw",
            tags="coord_lbl",
        )

        # Keep above the grid lines, below focuses
        if self.cv.find_withtag("grid"):
            try:
                self.cv.tag_raise("coord_lbl", "grid")
            except Exception:
                pass

    def _draw_lines(self, vis_rect=None):
        """Draw edges: solid blue elbow+arrow for prereqs; dashed orange for mutex."""
        self._canvas_runtime()
        self._scene_index.ensure(self.focuses, validate=False)
        cv = self.cv
        if vis_rect is None:
            vis_rect = self._visible_rect()
        half = BOX * self.zoom / 2
        lw = max(1, int(2.0 * self.zoom))  # line width scales with zoom
        asz = max(4, int(10 * self.zoom))  # arrowhead half-width
        aht = max(5, int(14 * self.zoom))  # arrowhead height

        indexed_edges = (
            self._scene_index.query_edges(vis_rect)
            if vis_rect is not None
            else self._scene_index.all_edges()
        )
        edges = [
            (edge.kind, edge.source_id, edge.target_id, edge.cross_tree)
            for edge in indexed_edges
            if vis_rect is None
            or edge_visible(
                self.focuses[edge.source_id].x,
                self.focuses[edge.source_id].y,
                self.focuses[edge.target_id].x,
                self.focuses[edge.target_id].y,
                vis_rect,
            )
        ]

        need = len(edges) * 2  # 1 line + 1 arrowhead polygon per edge
        while len(self._lines) < need:
            ln = cv.create_line(0, 0, 0, 0, fill=PREREQ_COL, width=2, tags="line")
            ar = cv.create_polygon(
                0, 0, 0, 0, 0, 0, fill=PREREQ_COL, outline="", tags="line"
            )
            self._lines += [ln, ar]

        for idx, (etype, aid, bid, cross) in enumerate(edges):
            ln, ar = self._lines[idx * 2], self._lines[idx * 2 + 1]
            a = self.focuses[aid]
            b = self.focuses[bid]
            ax, ay = self.w2c(a.x, a.y)
            bx, by = self.w2c(b.x, b.y)

            if etype == "arr":
                # Elbow connector: bottom of parent → midpoint → top of child
                x0, y0 = ax, ay + half
                x1, y1 = bx, by - half
                mid_y = (y0 + y1) / 2
                cv.coords(ln, x0, y0, x0, mid_y, x1, mid_y, x1, y1)
                # Solid filled triangle arrowhead pointing down into child
                cv.coords(ar, x1, y1, x1 - asz, y1 - aht, x1 + asz, y1 - aht)
                # Cross-tree prereqs: dimmer color + dashed line
                arr_col = "#94a3b8" if cross else PREREQ_COL
                arr_dash = (
                    (max(4, int(6 * self.zoom)), max(3, int(4 * self.zoom)))
                    if cross
                    else ()
                )
                cv.itemconfig(ln, fill=arr_col, width=lw, dash=arr_dash, state="normal")
                cv.itemconfig(ar, fill=arr_col, outline=arr_col, state="normal")
            else:
                # Mutex: dashed orange diagonal between the two focuses
                cv.coords(ln, ax, ay, bx, by)
                cv.coords(ar, bx, by, bx, by, bx, by)  # degenerate = invisible
                dl = max(4, int(9 * self.zoom))
                cv.itemconfig(
                    ln,
                    fill=MUTEX_COL,
                    width=max(1, lw - 1),
                    dash=(dl, dl),
                    state="normal",
                )
                cv.itemconfig(ar, state="hidden")

        for idx in range(len(edges) * 2, len(self._lines)):
            cv.itemconfig(self._lines[idx], state="hidden")

        if self._lines:
            cv.tag_lower("line")
            # Guard: grid may have no items (low zoom / toggled off).
            if cv.find_withtag("grid"):
                cv.tag_lower("grid")
            # Labels sit below lines so arrows always draw on top of text
            # Guard: tag_lower("focus_lbl","line") crashes if "line" tag has no items
            if cv.find_withtag("focus_lbl"):
                cv.tag_lower("focus_lbl", "line")

    def _delete_focus_bundle(self, focus_id):
        self._canvas_runtime()
        bundle = self._focus_bundles.pop(focus_id, None)
        if bundle is not None:
            for item in bundle.items:
                self.cv.delete(item)
        image_broker = getattr(self, "_image_broker", None)
        if image_broker is not None:
            image_broker.release(("canvas", focus_id))

    def _reclaim_focus_bundles(self, visible_ids):
        self._canvas_runtime()
        for focus_id in self._focus_bundles.keys() - visible_ids:
            self._delete_focus_bundle(focus_id)

    def _bind_focus_items(self, items, focus_id):
        for item in items:
            self.cv.tag_bind(
                item, "<ButtonPress-1>", lambda e, i=focus_id: self._foc_pr(i, e)
            )
            self.cv.tag_bind(
                item, "<B1-Motion>", lambda e, i=focus_id: self._foc_mv(i, e)
            )
            self.cv.tag_bind(
                item, "<ButtonRelease-1>", lambda e, i=focus_id: self._foc_rl(i)
            )
            self.cv.tag_bind(item, "<Enter>", lambda e, i=focus_id: self._foc_en(i))
            self.cv.tag_bind(
                item,
                "<Leave>",
                lambda e: self._hint(
                    "Right-click canvas to place focus  •  "
                    "Ctrl+drag to pan  •  Scroll to zoom"
                ),
            )

    def _draw_focus(self, f, vis_rect=None):
        """Create once; skip update if state unchanged for near-zero idle cost."""
        self._canvas_runtime()
        if vis_rect is None:
            vis_rect = self._visible_rect()
        cx, cy = self.w2c(f.x, f.y)

        if vis_rect is not None and not focus_visible(f.x, f.y, vis_rect):
            self._delete_focus_bundle(f.id)
            return

        bundle = self._focus_bundles.get(f.id)
        if bundle is not None and any(not self.cv.type(item) for item in bundle.items):
            self._focus_bundles.pop(f.id, None)
            bundle = None
        lod = "compact" if self.zoom < _FOCUS_LOD_ZOOM else "full"
        if bundle is not None and bundle.lod != lod:
            self._delete_focus_bundle(f.id)
            bundle = None
        z = self.zoom
        XGRID * z  # horizontal slot width
        box = BOX * z
        h = box / 2
        sd = max(1, int(2 * z))
        mp = max(1, int(2 * z))
        cs = max(1, int(2.0 * z))
        ico_size = max(5, int(h * 1.0))
        lbl_size = max(5, int(6 * z))
        # Label sits just below the focus box
        lbl_y = cy + h + max(3, int(4 * z))

        sel = bool(self.selected and self.selected.id == f.id)
        msel = f.id in self._multi_sel
        mut = bool(self.mutex_mode and self.mutex_src and self.mutex_src.id == f.id)

        # Tree-specific border color and badge
        tree_idx = getattr(f, "tree_idx", 0)
        badge_txt, tree_col = self._get_tree_badge(tree_idx)
        base_border = tree_col if tree_idx > 0 else FC_BORDER
        border_col = (
            FC_SEL_BD
            if sel
            else ("#00e5ff" if msel else (ORANGE if mut else base_border))
        )
        fill_col = FC_SEL if sel else ("#0a2030" if msel else FC_BG)
        bw = 3 if sel else (2 if msel else 1)

        if lod == "compact":
            state_key = (
                round(cx, 1),
                round(cy, 1),
                round(h, 1),
                border_col,
                fill_col,
                bw,
            )
            if bundle is not None and bundle.draw_key == state_key:
                return
            tag = "F" + str(f.id)
            if bundle is None:
                shadow = self.cv.create_rectangle(
                    0, 0, 1, 1, outline="", fill="#060a10", tags=("focus", tag)
                )
                box_rect = self.cv.create_rectangle(
                    0, 0, 1, 1, outline=border_col, fill=fill_col, tags=("focus", tag)
                )
                center = self.cv.create_rectangle(
                    0, 0, 1, 1, outline="", fill=border_col, tags=("focus", tag)
                )
                bundle = FocusCanvasBundle((shadow, box_rect, center), lod)
                self._focus_bundles[f.id] = bundle
                self._bind_focus_items(bundle.items, f.id)
            shadow, box_rect, center = bundle.items
            dot = max(1, int(3 * z))
            self.cv.coords(shadow, cx - h + sd, cy - h + sd, cx + h + sd, cy + h + sd)
            self.cv.coords(box_rect, cx - h, cy - h, cx + h, cy + h)
            self.cv.coords(center, cx - dot, cy - dot, cx + dot, cy + dot)
            self.cv.itemconfig(box_rect, outline=border_col, fill=fill_col, width=bw)
            self.cv.itemconfig(center, fill=border_col)
            bundle.draw_key = state_key
            image_broker = getattr(self, "_image_broker", None)
            if image_broker is not None:
                image_broker.release(("canvas", f.id))
            return

        if z >= 1.2:
            label_text = f.name
        elif z >= 0.8:
            label_text = f.name[:13] + ("..." if len(f.name) > 13 else "")
        elif z >= 0.5:
            label_text = f.name[:8] + ("..." if len(f.name) > 8 else "")
        elif z >= 0.3:
            label_text = f.name[:5] + ("..." if len(f.name) > 5 else "")
        else:
            label_text = ""

        has_offsets = bool(getattr(f, "offsets", []))
        # Fast-exit: skip if nothing changed since last draw
        state_key = (
            round(cx, 1),
            round(cy, 1),
            round(h, 1),
            sel,
            msel,
            mut,
            label_text,
            ico_size,
            lbl_size,
            getattr(f, "gfx", ""),
            tree_idx,
            has_offsets,
        )
        if bundle is not None and bundle.draw_key == state_key:
            return

        tag = "F" + str(f.id)
        fid = f.id
        cv = self.cv

        if bundle is None:
            # Create all items exactly once, bind events once
            shadow = cv.create_rectangle(
                0, 0, 1, 1, outline="", fill="#060a10", tags=("focus", tag)
            )
            mat = cv.create_rectangle(
                0, 0, 1, 1, outline=FC_BORDER, fill=BG_CARD, tags=("focus", tag)
            )
            box_rect = cv.create_rectangle(
                0, 0, 1, 1, outline=border_col, fill=fill_col, tags=("focus", tag)
            )
            rv0 = cv.create_rectangle(
                0, 0, 1, 1, fill=border_col, outline="", tags=("focus", tag)
            )
            rv1 = cv.create_rectangle(
                0, 0, 1, 1, fill=border_col, outline="", tags=("focus", tag)
            )
            rv2 = cv.create_rectangle(
                0, 0, 1, 1, fill=border_col, outline="", tags=("focus", tag)
            )
            rv3 = cv.create_rectangle(
                0, 0, 1, 1, fill=border_col, outline="", tags=("focus", tag)
            )
            glow = cv.create_rectangle(
                0, 0, 1, 1, outline=FC_SEL_BD, fill="", width=2, tags=("focus", tag)
            )
            ico = cv.create_text(
                0,
                0,
                text=f.icon,
                font=("TkDefaultFont", ico_size),
                fill=TEXT,
                tags=("focus", tag),
            )
            img_item = cv.create_image(0, 0, anchor="center", tags=("focus", tag))
            lbl_bg = cv.create_rectangle(
                0,
                0,
                1,
                1,
                fill="#0d1525",
                outline="",
                stipple="gray50",
                tags=("focus", "focus_lbl", tag),
            )
            lbl = cv.create_text(
                0,
                0,
                text=label_text,
                font=("Helvetica", lbl_size),
                fill="#e2e8f0",
                anchor="n",
                tags=("focus", "focus_lbl", tag),
            )
            badge = cv.create_text(
                0,
                0,
                text="",
                font=("Helvetica", max(5, int(5 * z)), "bold"),
                fill="#000000",
                tags=("focus", tag),
            )
            off_ind = cv.create_text(
                0,
                0,
                text="",
                font=("Helvetica", max(4, int(4 * z)), "bold"),
                fill="#06b6d4",
                tags=("focus", tag),
            )
            items = (
                shadow,
                mat,
                box_rect,
                rv0,
                rv1,
                rv2,
                rv3,
                glow,
                ico,
                img_item,
                lbl_bg,
                lbl,
                badge,
                off_ind,
            )
            bundle = FocusCanvasBundle(items, lod)
            self._focus_bundles[f.id] = bundle
            self._bind_focus_items(items, fid)
        bundle.draw_key = state_key

        # Guard: recreate if item count is stale (14 items:
        # shadow,mat,box,rv*4,glow,ico,img,lbl_bg,lbl,badge,off_ind)
        (
            shadow,
            mat,
            box_rect,
            rv0,
            rv1,
            rv2,
            rv3,
            glow,
            ico,
            img_item,
            lbl_bg,
            lbl,
            badge,
            off_ind,
        ) = bundle.items

        # Update positions (cheap coords calls, no create/delete)
        cv.coords(shadow, cx - h + sd, cy - h + sd, cx + h + sd, cy + h + sd)
        cv.coords(mat, cx - h - mp, cy - h - mp, cx + h + mp, cy + h + mp)
        cv.coords(box_rect, cx - h, cy - h, cx + h, cy + h)
        for rv, (dx, dy) in zip(
            (rv0, rv1, rv2, rv3), ((-1, -1), (1, -1), (-1, 1), (1, 1))
        ):
            cv.coords(
                rv,
                cx + dx * h - cs,
                cy + dy * h - cs,
                cx + dx * h + cs,
                cy + dy * h + cs,
            )
        cv.coords(glow, cx - h - 4, cy - h - 4, cx + h + 4, cy + h + 4)
        cv.coords(ico, cx, cy)
        cv.coords(img_item, cx, cy)
        # Label shading background — sized to fit text with small padding
        lbl_pad = max(2, int(lbl_size * 0.6))
        lbl_half = max(20, int(len(label_text) * lbl_size * 0.34))
        cv.coords(
            lbl_bg,
            cx - lbl_half,
            lbl_y - lbl_pad,
            cx + lbl_half,
            lbl_y + lbl_size + lbl_pad,
        )
        cv.coords(lbl, cx, lbl_y)
        # Badge in top-left corner of focus box
        badge_sz = max(5, int(5 * z))
        cv.coords(badge, cx - h + badge_sz, cy - h + badge_sz)

        # Update appearance (cheap itemconfig calls)
        cv.itemconfig(box_rect, outline=border_col, fill=fill_col, width=bw)
        for rv in (rv0, rv1, rv2, rv3):
            cv.itemconfig(rv, fill=border_col)
        cv.itemconfig(glow, state="normal" if sel else "hidden")
        # Use mod GFX image — fixed 64px tile, cached once, no per-zoom resize
        gfx_name = getattr(f, "gfx", "")
        mod_img = None
        image_broker = getattr(self, "_image_broker", None)
        if image_broker is not None and MOD.loaded and gfx_name:
            asset = MOD.graphics_catalog.resolve(gfx_name)
            if asset is not None:
                path = MOD.graphics_catalog.path_for(asset)
                lifecycle = getattr(self, "_lifecycle", None)
                document_token = (
                    lifecycle.token("document") if lifecycle is not None else None
                )

                def image_ready(image, fid=f.id, expected_gfx=gfx_name):
                    if (
                        lifecycle is not None
                        and document_token is not None
                        and not lifecycle.is_current(document_token)
                    ):
                        return
                    current = self.focuses.get(fid)
                    current_bundle = self._focus_bundles.get(fid)
                    if (
                        current is None
                        or getattr(current, "gfx", "") != expected_gfx
                        or current_bundle is None
                        or current_bundle.lod != "full"
                    ):
                        return
                    current_bundle.image = image
                    current_icon_item = current_bundle.items[8]
                    current_image_item = current_bundle.items[9]
                    self.cv.itemconfig(current_icon_item, state="hidden")
                    self.cv.itemconfig(current_image_item, image=image, state="normal")

                mod_img = image_broker.request(
                    asset,
                    path,
                    owner=("canvas", f.id),
                    callback=image_ready,
                )
                self._start_image_poll()
            else:
                image_broker.release(("canvas", f.id))
        elif image_broker is not None:
            image_broker.release(("canvas", f.id))
        if mod_img:
            bundle.image = mod_img
            cv.itemconfig(ico, state="hidden")
            cv.itemconfig(img_item, image=mod_img, state="normal")
        else:
            bundle.image = None
            cv.itemconfig(
                ico,
                state="normal",
                text=f.icon,
                font=("TkDefaultFont", ico_size),
                fill=TEXT,
            )
            cv.itemconfig(img_item, state="hidden")
        cv.itemconfig(lbl_bg, state="normal" if label_text else "hidden")
        cv.itemconfig(
            lbl,
            text=label_text,
            font=("Helvetica", lbl_size),
            fill="#e2e8f0",
            width=0,
            anchor="n",
            state="normal" if label_text else "hidden",
        )
        # Tree badge (shown only for extra-tree focuses at sufficient zoom)
        if badge_txt and z >= 0.4:
            cv.itemconfig(
                badge,
                text=badge_txt,
                font=("Helvetica", badge_sz, "bold"),
                fill=tree_col,
                state="normal",
            )
        else:
            cv.itemconfig(badge, state="hidden")
        # Offset indicator — cyan ⊕ in bottom-right corner when focus has offset blocks
        off_sz = max(4, int(4 * z))
        cv.coords(off_ind, cx + h - off_sz, cy + h - off_sz)
        if has_offsets and z >= 0.3:
            cv.itemconfig(
                off_ind,
                text="⊕",
                font=("Helvetica", off_sz, "bold"),
                fill="#06b6d4",
                state="normal",
            )
        else:
            cv.itemconfig(off_ind, state="hidden")

    def _focus_id_at(self, x, y):
        """Return the id of the topmost focus under a canvas pixel, or None.

        Scans by tag rather than relying on Tk's "current item", so an overlay
        such as the mutex rubber-band line never blocks the hit.
        """
        for item in reversed(self.cv.find_overlapping(x - 2, y - 2, x + 2, y + 2)):
            for tag in self.cv.gettags(item):
                if len(tag) > 1 and tag[0] == "F" and tag[1:].isdigit():
                    fid = int(tag[1:])
                    if fid in self.focuses:
                        return fid
        return None

    def _lmb_dn(self, e):
        if self.mutex_mode:
            tid = self._focus_id_at(e.x, e.y)
            if tid is not None:
                src = self.mutex_src
                if src and tid != src.id:
                    self._make_mutex(src, self.focuses[tid])
                self._end_mutex()
            return
        hits = self.cv.find_overlapping(e.x - 2, e.y - 2, e.x + 2, e.y + 2)
        if not any("focus" in self.cv.gettags(i) for i in hits):
            self._deselect()

    def _lmb_mv(self, e):
        pass

    def _lmb_up(self, e):
        pass

    def _pan_pr(self, e):
        self._pan_start = (e.x, e.y)
        self.cv.config(cursor="sizing")

    def _pan_mv(self, e):
        if not self._pan_start:
            return
        dx = e.x - self._pan_start[0]
        dy = e.y - self._pan_start[1]
        self.offset[0] += dx
        self.offset[1] += dy
        self._pan_start = (e.x, e.y)
        # Pure translate of every world item — no rebuilds, so the pan stays
        # buttery even with a big tree. Grid/focus/line items just slide.
        self.cv.move("grid", dx, dy)
        self.cv.move("focus", dx, dy)
        self.cv.move("line", dx, dy)
        self.cv.move("templine", dx, dy)
        self.cv.move("cfp", dx, dy)
        # The dim mask and coordinate ruler are screen-anchored; a redraw of just
        # these two is cheap (a handful of items) and keeps them crisp.
        self._draw_canvas_bounds()
        self._draw_coord_labels()

    def _pan_rl(self, e):
        self._pan_start = None
        self.cv.config(cursor="fleur")
        # One clean redraw on release snaps everything to exact positions.
        self._redraw_now(RedrawChannel.VIEW, reason="pan-release")

    def _scroll(self, e):
        f = 1.1 if (e.num == 4 or e.delta > 0) else 0.9
        old = self.zoom
        self.zoom = max(0.10, min(4.0, self.zoom * f))
        self.offset[0] = e.x - (e.x - self.offset[0]) * (self.zoom / old)
        self.offset[1] = e.y - (e.y - self.offset[1]) * (self.zoom / old)
        # Zoom redraws immediately (like a resize) so the wheel feels instant;
        # the 16ms throttle stays for the other channels via _redraw().
        self._redraw_now(RedrawChannel.VIEW, reason="wheel")

    def _rmb(self, e):
        hits = self.cv.find_overlapping(e.x - 2, e.y - 2, e.x + 2, e.y + 2)
        if any("focus" in self.cv.gettags(i) for i in hits):
            return
        gx, gy = self.c2w(e.x, e.y)
        if any(f.x == gx and f.y == gy for f in self.focuses.values()):
            return
        self._new_focus_at(gx, gy)

    def _motion(self, e):
        if not self._drag:
            gx, gy = self.c2w(e.x, e.y)
            self._coord_lbl.config(text=f"  x={gx}  y={gy}  ")
        if self._temp_line and self.mutex_mode:
            # Only mutex still uses drag-line visuals
            src = self.mutex_src
            if src:
                cx, cy = self.w2c(src.x, src.y)
                # Snap the free end to the center of the focus under the cursor
                # so the target is obvious before clicking.
                tid = self._focus_id_at(e.x, e.y)
                if tid is not None and tid != src.id:
                    tx, ty = self.w2c(self.focuses[tid].x, self.focuses[tid].y)
                else:
                    tx, ty = e.x, e.y
                self.cv.coords(self._temp_line, cx, cy, tx, ty)

    def _foc_pr(self, fid, e):
        if self.mutex_mode:
            # Completion is handled at the canvas level (_lmb_dn); swallow the
            # click here so it never starts a drag or selection.
            return
        f = self.focuses[fid]
        # Ctrl+click = toggle multi-select
        if self._multisel_mode or (e.state & 0x0004):  # 0x0004 = Ctrl held
            if fid in self._multi_sel:
                self._multi_sel.discard(fid)
            else:
                self._multi_sel.add(fid)
            self._redraw()
            return
        self._drag = {
            "id": fid,
            "sx": f.x,
            "sy": f.y,
            "cx": e.x,
            "cy": e.y,
            "moved": False,
            "last_snap": (f.x, f.y),
            # Other focuses don't move during a drag, so snapshot their grid
            # cells once for O(1) collision checks per motion event.
            "occupied": {(o.x, o.y) for o in self.focuses.values() if o.id != fid},
        }
        self._select(f)

    def _foc_mv(self, fid, e):
        d = self._drag
        if not d or d.get("id") != fid or self.mutex_mode:
            return
        dx = e.x - d["cx"]
        dy = e.y - d["cy"]
        if abs(dx) > 4 or abs(dy) > 4:
            d["moved"] = True
        if not d["moved"]:
            return
        f = self.focuses[fid]
        ngx = round(d["sx"] + dx / (XGRID * self.zoom))
        ngy = round(d["sy"] + dy / (YGRID * self.zoom))
        if (ngx, ngy) == d["last_snap"]:
            return
        if (ngx, ngy) in d.get("occupied", ()):
            return
        old_cx, old_cy = self.w2c(f.x, f.y)
        self.focuses.move(fid, ngx, ngy)
        new_cx, new_cy = self.w2c(f.x, f.y)
        px, py = new_cx - old_cx, new_cy - old_cy
        bundle = self._focus_bundles.get(fid)
        for item in bundle.items if bundle is not None else ():
            self.cv.move(item, px, py)
        d["last_snap"] = (ngx, ngy)
        self._fv_x.set(str(ngx))
        self._fv_y.set(str(ngy))
        self._hint(f"Dragging {self.focuses[fid].name}  →  x={ngx}  y={ngy}")
        self._draw_lines_throttled()

    def _foc_rl(self, fid):
        if self._drag.get("moved"):
            self._redraw()  # final clean redraw on release
        self._drag = {}

    def _foc_en(self, fid):
        f = self.focuses[fid]
        base = (
            f"{f.name}  •  Cost:{f.cost}  •  Effects:{len(f.effects)}  •  "
            f"Prereqs:{sum(len(g) for g in f.prereqs)}"
        )
        offs = getattr(f, "offsets", [])
        if offs:
            off_strs = [
                f"x={o['x']} y={o['y']} [{o.get('trigger','').strip()[:30]}]"
                for o in offs
            ]
            base += f"  •  Offsets: {'; '.join(off_strs)}"
        self._hint(base)

    def _draw_canvas_legend(self):
        """Draw a compact legend in the bottom-left when extra trees are loaded."""
        self.cv.delete("legend")
        if not getattr(self, "_extra_trees", []):
            return
        cv = self.cv
        ch = cv.winfo_height()
        x, y = 8, ch - 8
        items = [("■ Main tree", FC_BORDER)]
        for idx, et in enumerate(self._extra_trees, start=1):
            badge, col = self._get_tree_badge(idx)
            items.append(
                (f"■ [{badge}] {et['type'].capitalize()}: {et['tree_id']}", col)
            )
        items.append(("· · ·  cross-tree prereq", "#94a3b8"))
        for lbl, col in reversed(items):
            cv.create_text(
                x,
                y,
                text=lbl,
                fill=col,
                anchor="sw",
                font=("Helvetica", 8),
                tags="legend",
            )
            y -= 14

    def _draw_cfp_markers(self):
        """Draw continuous_focus_position marker boxes on the canvas.

        HOI4 CFP values are in internal pixel units (XGRID/YGRID multiples).
        We convert: grid_coord = cfp_value / GRID_SIZE.
        """
        self.cv.delete("cfp_marker")
        cv = self.cv
        z = self.zoom
        # 2× the old size: half-extent is now BOX*z instead of BOX*z/2
        h = BOX * z
        font_sz = max(8, int(9 * z))
        lw = max(2, int(2.5 * z))

        def _draw_box(gx, gy, color, label):
            cx, cy = self.w2c(gx, gy)
            # Subtle tinted fill via stipple (tkinter has no native alpha)
            cv.create_rectangle(
                cx - h,
                cy - h,
                cx + h,
                cy + h,
                outline=color,
                fill=color,
                stipple="gray12",
                width=lw,
                dash=(max(4, int(6 * z)), max(3, int(4 * z))),
                tags="cfp_marker",
            )
            if z >= 0.3:
                cv.create_text(
                    cx,
                    cy,
                    text=label,
                    fill=color,
                    anchor="center",
                    font=("Helvetica", font_sz, "bold"),
                    width=max(60, int(h * 1.8)),
                    tags="cfp_marker",
                )

        # Main tree CFP
        if (
            getattr(self, "_cfp_x", None) is not None
            and getattr(self, "_cfp_y", None) is not None
        ):
            _draw_box(
                self._cfp_x / XGRID,
                self._cfp_y / YGRID,
                "#22d3ee",
                "Continuous\nFocus Position",
            )

        # Extra tree CFPs
        for idx, et in enumerate(getattr(self, "_extra_trees", []), start=1):
            if et.get("cfp_x") is not None and et.get("cfp_y") is not None:
                _, col = self._get_tree_badge(idx)
                badge, _ = self._get_tree_badge(idx)
                tree_type = et.get("type", "shared")
                if tree_type == "joint":
                    col = "#a855f7"
                else:
                    col = "#f59e0b"
                _draw_box(
                    et["cfp_x"] / XGRID,
                    et["cfp_y"] / YGRID,
                    col,
                    f"Continuous\nFocus Position\n[{badge}]",
                )

    def _toggle_grid(self):
        """Toggle canvas grid visibility."""
        self._grid_on = not getattr(self, "_grid_on", True)
        # Force _draw_grid to rebuild (it honours _grid_on).
        self._grid_key = None
        self._redraw()

    def _toggle_minimap(self):
        """Show or hide the minimap overlay in the bottom-right corner."""
        self._mm_visible = not getattr(self, "_mm_visible", False)
        if self._mm_visible:
            # Create the minimap canvas lazily on first show
            if not hasattr(self, "_mm_canvas") or not self._mm_canvas.winfo_exists():
                mm = tk.Canvas(
                    self.cv,
                    bg="#070c15",
                    highlightthickness=1,
                    highlightbackground=BORDER_G,
                    cursor="crosshair",
                )
                self._mm_canvas = mm
                mm.bind("<ButtonPress-1>", self._mm_click)
                mm.bind("<B1-Motion>", self._mm_click)
                # Close button
                close_lbl = tk.Label(
                    mm,
                    text="×",
                    bg="#070c15",
                    fg=TEXT_DIM,
                    font=("Helvetica", 9, "bold"),
                    cursor="hand2",
                )
                close_lbl.place(relx=1.0, rely=0, anchor="ne", x=-2, y=2)
                close_lbl.bind("<ButtonPress-1>", lambda e: self._toggle_minimap())
            self._mm_canvas.place(
                relx=1.0, rely=1.0, anchor="se", x=-8, y=-8, width=220, height=150
            )
            self._mm_canvas.lift()
            self._draw_minimap()
        else:
            if hasattr(self, "_mm_canvas"):
                try:
                    self._mm_canvas.place_forget()
                except Exception:
                    pass

    def _draw_minimap_content(self, mm, g2mm, scale):
        downsample = len(self.focuses) > self._MM_DOWNSAMPLE_THRESHOLD
        line_idx = 0
        if not downsample:
            for f in self.focuses.values():
                fx, fy = g2mm(f.x, f.y)
                for group in f.prereqs:
                    for parent_id in group:
                        parent = self.focuses.get(parent_id)
                        if parent is None:
                            continue
                        px, py = g2mm(parent.x, parent.y)
                        if line_idx < len(self._mm_line_pool):
                            item = self._mm_line_pool[line_idx]
                            mm.coords(item, fx, fy, px, py)
                            mm.itemconfig(item, state="normal")
                        else:
                            item = mm.create_line(
                                fx,
                                fy,
                                px,
                                py,
                                fill="#1e3048",
                                width=1,
                                tags="mm_content",
                            )
                            mm.tag_lower(item)
                            self._mm_line_pool.append(item)
                        line_idx += 1
        for index in range(line_idx, len(self._mm_line_pool)):
            mm.itemconfig(self._mm_line_pool[index], state="hidden")

        dot = max(2, int(scale * 0.45))
        if downsample:
            buckets = {}
            for f in self.focuses.values():
                mx, my = g2mm(f.x, f.y)
                key = (int(mx), int(my))
                if key not in buckets:
                    buckets[key] = (mx, my, getattr(f, "tree_idx", 0))
            dot_positions = buckets.values()
        else:
            dot_positions = (
                (*g2mm(f.x, f.y), getattr(f, "tree_idx", 0))
                for f in self.focuses.values()
            )
        dot_idx = 0
        for mx, my, tree_idx in dot_positions:
            _, color = self._get_tree_badge(tree_idx)
            if tree_idx == 0:
                color = "#475569"
            if dot_idx < len(self._mm_dot_pool):
                item = self._mm_dot_pool[dot_idx]
                mm.coords(item, mx - dot, my - dot, mx + dot, my + dot)
                mm.itemconfig(item, fill=color, state="normal")
            else:
                item = mm.create_rectangle(
                    mx - dot,
                    my - dot,
                    mx + dot,
                    my + dot,
                    fill=color,
                    outline="",
                    tags="mm_content",
                )
                self._mm_dot_pool.append(item)
            dot_idx += 1
        for index in range(dot_idx, len(self._mm_dot_pool)):
            mm.itemconfig(self._mm_dot_pool[index], state="hidden")

    def _draw_minimap(self):
        """Render all focuses as small colored dots plus the viewport rectangle.

        Dots and prereq lines come from a pooled item list (like
        ``_draw_lines``'s ``self._lines``): reused and re-coordinated across
        calls instead of deleted and recreated, since a >2k-focus load makes
        "delete everything, redraw everything" the expensive part of this
        method. CFP markers / viewport rect / label are a handful of items
        regardless of tree size, so they stay delete+recreate for simplicity,
        under their own ``mm_overlay`` tag so clearing them never touches the
        pooled dots/lines.

        Above ``_MM_DOWNSAMPLE_THRESHOLD`` focuses, dots are bucketed to one
        per occupied minimap-pixel cell and prereq lines are skipped — at
        that density individual lines/dots aren't legible anyway, and
        drawing one edge/focus is no longer cheap enough to do 20k+ times
        per minimap refresh.
        """
        if not hasattr(self, "_mm_line_pool"):
            self._mm_line_pool = []
        if not hasattr(self, "_mm_dot_pool"):
            self._mm_dot_pool = []
        if not getattr(self, "_mm_visible", False):
            return
        if not hasattr(self, "_mm_canvas"):
            return
        try:
            mm = self._mm_canvas
            if not mm.winfo_exists():
                return
        except Exception:
            return

        if not self.focuses:
            for item in self._mm_line_pool:
                mm.itemconfig(item, state="hidden")
            for item in self._mm_dot_pool:
                mm.itemconfig(item, state="hidden")
            mm.delete("mm_overlay")
            return

        self._canvas_runtime()
        self._scene_index.ensure(self.focuses, validate=False)
        MM_W = mm.winfo_width() or 220
        MM_H = mm.winfo_height() or 150
        margin = 10

        cfp_key = (
            getattr(self, "_cfp_x", None),
            getattr(self, "_cfp_y", None),
            tuple(
                (et.get("cfp_x"), et.get("cfp_y"))
                for et in getattr(self, "_extra_trees", [])
            ),
        )
        bounds_key = (self._scene_index.revision, cfp_key)
        if getattr(self, "_mm_bounds_key", None) != bounds_key:
            all_xs = [f.x for f in self.focuses.values()]
            all_ys = [f.y for f in self.focuses.values()]
            if getattr(self, "_cfp_x", None) is not None:
                all_xs.append(self._cfp_x / XGRID)
            if getattr(self, "_cfp_y", None) is not None:
                all_ys.append(self._cfp_y / YGRID)
            for et in getattr(self, "_extra_trees", []):
                if et.get("cfp_x") is not None:
                    all_xs.append(et["cfp_x"] / XGRID)
                if et.get("cfp_y") is not None:
                    all_ys.append(et["cfp_y"] / YGRID)
            self._mm_world_bounds = (
                min(all_xs) - 1,
                min(all_ys) - 1,
                max(all_xs) + 1,
                max(all_ys) + 1,
            )
            self._mm_bounds_key = bounds_key
        min_x, min_y, max_x, max_y = self._mm_world_bounds
        w_span = max(1.0, max_x - min_x)
        h_span = max(1.0, max_y - min_y)

        avail_w = MM_W - margin * 2
        avail_h = MM_H - margin * 2
        scale_x = avail_w / w_span
        scale_y = avail_h / h_span
        scale = min(scale_x, scale_y)

        # Center the content within the minimap
        ox = margin + (avail_w - w_span * scale) / 2
        oy = margin + (avail_h - h_span * scale) / 2

        # Store scale/origin for click-to-pan
        self._mm_scale = scale
        self._mm_min_x = min_x
        self._mm_min_y = min_y
        self._mm_ox = ox
        self._mm_oy = oy

        def g2mm(gx, gy):
            return ox + (gx - min_x) * scale, oy + (gy - min_y) * scale

        content_key = (bounds_key, MM_W, MM_H)
        if getattr(self, "_mm_content_key", None) != content_key:
            self._draw_minimap_content(mm, g2mm, scale)
            self._mm_content_key = content_key

        # CFP markers, viewport rectangle, label: a handful of items
        # regardless of tree size, so plain delete+recreate is fine.
        mm.delete("mm_overlay")

        def _mm_cfp(gx, gy, col):
            mx, my = g2mm(gx, gy)
            s = max(3, int(scale * 0.6))
            mm.create_rectangle(
                mx - s,
                my - s,
                mx + s,
                my + s,
                outline=col,
                fill="",
                width=1,
                dash=(2, 2),
                tags="mm_overlay",
            )

        if (
            getattr(self, "_cfp_x", None) is not None
            and getattr(self, "_cfp_y", None) is not None
        ):
            _mm_cfp(self._cfp_x / XGRID, self._cfp_y / YGRID, "#22d3ee")
        for idx, et in enumerate(getattr(self, "_extra_trees", []), start=1):
            if et.get("cfp_x") is not None and et.get("cfp_y") is not None:
                _, col = self._get_tree_badge(idx)
                _mm_cfp(et["cfp_x"] / XGRID, et["cfp_y"] / YGRID, col)

        # Draw viewport rectangle
        try:
            cv_w = max(1, self.cv.winfo_width())
            cv_h = max(1, self.cv.winfo_height())
            vp_gx0 = -self.offset[0] / (XGRID * self.zoom)
            vp_gy0 = -self.offset[1] / (YGRID * self.zoom)
            vp_gx1 = vp_gx0 + cv_w / (XGRID * self.zoom)
            vp_gy1 = vp_gy0 + cv_h / (YGRID * self.zoom)
            vx0, vy0 = g2mm(vp_gx0, vp_gy0)
            vx1, vy1 = g2mm(vp_gx1, vp_gy1)
            mm.create_rectangle(
                vx0,
                vy0,
                vx1,
                vy1,
                outline="#60a5fa",
                fill="#60a5fa",
                stipple="gray12",
                width=1,
                tags="mm_overlay",
            )
        except Exception:
            pass

        # Label
        mm.create_text(
            4,
            MM_H - 4,
            text="M — minimap",
            fill="#1e3048",
            anchor="sw",
            font=("Helvetica", 7),
            tags="mm_overlay",
        )

    def _mm_click(self, e):
        """Pan the main canvas to the position clicked on the minimap."""
        if not hasattr(self, "_mm_scale") or not self._mm_scale:
            return
        gx = self._mm_min_x + (e.x - self._mm_ox) / self._mm_scale
        gy = self._mm_min_y + (e.y - self._mm_oy) / self._mm_scale
        cw = self.cv.winfo_width()
        ch = self.cv.winfo_height()
        self.offset[0] = cw / 2 - gx * XGRID * self.zoom
        self.offset[1] = ch / 2 - gy * YGRID * self.zoom
        self._grid_key = None
        self._redraw_now(RedrawChannel.VIEW, reason="minimap-pan")

    def _fit_all(self):
        """Fit all focuses into view by resetting pan/zoom."""
        if not self.focuses:
            return
        xs = [f.x for f in self.focuses.values()]
        ys = [f.y for f in self.focuses.values()]
        if not xs:
            return
        cw = self.cv.winfo_width() or 800
        ch = self.cv.winfo_height() or 600
        span_x = (max(xs) - min(xs) + 2) * XGRID
        span_y = (max(ys) - min(ys) + 2) * YGRID
        new_zoom = min(cw / max(span_x, 1), ch / max(span_y, 1), 2.0)
        new_zoom = max(new_zoom, 0.3)
        self.zoom = new_zoom
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        self.offset[0] = cw / 2 - cx * XGRID * self.zoom
        self.offset[1] = ch / 2 - cy * YGRID * self.zoom
        self._redraw_now(RedrawChannel.VIEW, reason="fit-all")
