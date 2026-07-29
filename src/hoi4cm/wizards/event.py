# ruff: noqa: E501, F821, UP031, E741, B007, B008, B023, S311
# This file was extracted from hoi4_content_maker.py. The wizard body
# retains the original monolith's style (long lines, ambiguous names,
# percent-format strings, nested helpers referenced before def). Tightening
# any of this is a separate refactor.

"""Event builder wizard."""

import json
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox

from hoi4cm.core import (
    EFFECT_CATS,
    EFFECT_DEFS,
    append_scripted_loc,
    autosave_path,
    effects_in_cat,
    sanitize_component,
    tr,
)
from hoi4cm.core.image import PIL_OK, PILImage, PILImageTk
from hoi4cm.mod import MOD
from hoi4cm.script.syntax import parse_block, tokenize
from hoi4cm.ui import (
    BG_CARD,
    BG_DARK,
    BG_PANEL,
    BLUE,
    BORDER,
    BORDER_G,
    GOLD,
    GREEN,
    ORANGE,
    RED,
    SEL_BG,
    TEXT,
    TEXT_DIM,
    _safe_after,
    _safe_after_idle,
)
from hoi4cm.wizards._graphics import (
    browser_folders,
    collect_image_pairs,
    find_catalog_image,
)
from hoi4cm.wizards._image_loader import TkImageLoader
from hoi4cm.wizards._shared import (
    _ev_gfx_cache,
    _ev_imgsize_cache,
    notifying_workspace_files,
)


def open_event_wizard(app):
    """HOI4 Event Maker — uses main app theme (BG_DARK / BG_PANEL etc.)."""

    # ── GFX lists ────────────────────────────────────────────────────
    GFX_COUNTRY = sorted(
        [
            "GFX_report_event_generic_sign_treaty2",
            "GFX_report_event_generic_handshake",
            "GFX_report_event_generic_conference",
            "GFX_report_event_generic_battle",
            "GFX_report_event_generic_military_parade",
            "GFX_report_event_generic_parliament",
            "GFX_report_event_generic_factory",
            "GFX_report_event_generic_communist_congress",
            "GFX_report_event_generic_panzer_attack",
            "GFX_report_event_generic_bombers",
            "GFX_report_event_generic_funeral",
            "GFX_report_event_generic_mussolini",
            "GFX_report_event_generic_naval_treaty",
            "GFX_report_event_generic_destroyed_vehicles",
            "GFX_report_event_generic_italian_celebration",
            "GFX_report_event_generic_italian_fascists",
            "GFX_report_event_generic_lend_lease",
            "GFX_report_event_generic_read_write",
            "GFX_report_event_generic_croatia_handshake",
            "GFX_report_event_dead_soldiers",
            "GFX_report_event_soldiers_marching",
            "GFX_report_event_soldiers_parade",
            "GFX_report_event_soldiers_in_france",
            "GFX_report_event_british_artillery",
            "GFX_report_event_british_inspect_troops",
            "GFX_report_event_canadian_soldiers",
            "GFX_report_event_chinese_soldiers_fighting",
            "GFX_report_event_chinese_soldiers",
            "GFX_report_event_chinese_army_training",
            "GFX_report_event_polish_army",
            "GFX_report_event_polish_tanks_01",
            "GFX_report_event_romanian_soldiers",
            "GFX_report_event_african_soldiers",
            "GFX_report_event_bulgarian_soldiers",
            "GFX_report_event_swedish_soldier",
            "GFX_report_event_france_parade",
            "GFX_report_event_degaulle_inspect_troops",
            "GFX_report_event_destroyers",
            "GFX_report_event_ast_navy",
            "GFX_report_event_sailors_in_working_rig",
            "GFX_report_event_usa_destroyers",
            "GFX_report_event_election_vote",
            "GFX_report_event_gathering_protest",
            "GFX_report_event_fascist_speech",
            "GFX_report_event_fascist_militia",
            "GFX_report_event_fascist_gathering",
            "GFX_report_event_fascists_posing",
            "GFX_report_event_chamberlain_announce",
            "GFX_report_event_vienna_award_negotiations",
            "GFX_report_event_vienna_award_hungary",
            "GFX_report_event_finnish_letter",
            "GFX_report_event_sign_treaty2",
            "GFX_report_event_eng_royal_family",
            "GFX_report_event_europe_funeral",
            "GFX_report_event_crowd_in_prague",
            "GFX_report_event_communists_in_riga",
            "GFX_report_event_german_speech",
            "GFX_report_event_german_troops",
            "GFX_report_event_japan_europe_pact",
            "GFX_report_event_japanese_transport_soldiers",
            "GFX_report_event_stalin_01",
            "GFX_report_event_stalin_02",
            "GFX_report_event_stalin_meeting",
            "GFX_report_event_stalin_propaganda",
            "GFX_report_event_soviet_tanks",
            "GFX_report_event_soviet_tanks_snow",
            "GFX_report_event_soviet_tank_parade",
            "GFX_report_event_soviet_soldiers_tank",
            "GFX_report_event_soviet_purge_officers_01",
            "GFX_report_event_soviet_purge_trial",
            "GFX_report_event_soviet_german_soldier_handshake",
            "GFX_report_event_soviet_japanese_pact",
            "GFX_report_event_soviet_invasion_map",
            "GFX_report_event_fighters",
            "GFX_report_event_airplane_crash",
            "GFX_report_event_radar_01",
            "GFX_report_event_physics_lab_01",
            "GFX_report_event_physics_lab_02",
            "GFX_report_event_tank_factory",
            "GFX_report_event_spain_civil_war_soldiers",
            "GFX_report_event_spr_anarchists",
            "GFX_report_event_ITA_grand_council",
            "GFX_report_event_ITA_air_crash",
            "GFX_report_event_ITA_italian_civil_war",
            "GFX_report_event_ITA_partisans",
            "GFX_report_event_SOV_demands",
            "GFX_report_event_ENG_middle_eastern_conflict",
            "GFX_report_event_ETH_ethiopian_warriors",
            "GFX_report_event_IRQ_bakr_sidqi",
            "GFX_report_event_PER_persepolis_party",
            "GFX_report_event_bul_boris_military",
            "GFX_report_event_albanian_king_zog",
            "GFX_report_event_china_politicians_captured",
            "GFX_report_event_czech_soldiers_01",
            "GFX_report_event_czech_soldiers_02",
            "GFX_report_event_french_british_officers",
            "GFX_report_event_worried_french",
            "GFX_report_event_tur_ataturk_death",
            "GFX_report_event_tur_ataturk_impassioned_speech",
            "GFX_report_event_tur_britain",
            "GFX_report_event_tur_industry",
            "GFX_report_event_tur_inonu_diplomacy",
            "GFX_report_event_tur_kemalist_officers",
            "GFX_report_event_tur_political_rally",
            "GFX_report_event_tur_turkish_soldiers",
            "GFX_report_event_tur_the_montreux_convention",
            "GFX_report_event_GetHitlerHandshakeEventPicture",
        ]
    )
    GFX_NEWS = sorted(
        [
            "GFX_news_event_generic_sign_treaty2",
            "GFX_news_event_generic_sign_treaty3",
            "GFX_news_event_generic_parliament",
            "GFX_news_event_generic_read_write",
            "GFX_news_event_generic_arab_revolt",
            "GFX_news_event_cze_little_entente",
        ]
    )

    # ── Data model ───────────────────────────────────────────────────
    _n = [1]

    class _Ev:
        def __init__(self):
            self.uid = str(id(self))
            self.etype = "country_event"
            self.eid = f"my_namespace.{_n[0]}"
            _n[0] += 1
            self.title_text = "My Event Title"
            self.desc_text = "Describe what is happening in this event."
            self.picture = "GFX_report_event_generic_handshake"
            self.major = False
            self.fire_once = False
            self.triggered = True
            self.hidden = False
            self.mtth_days = ""
            self.mtth_months = ""
            self.trigger_code = ""
            self.immediate = ""
            self.options = [
                {
                    "name": f"{self.eid}.a",
                    "text": "Option A",
                    "effects": "add_political_power = 50",
                    "ai_chance": "75",
                },
            ]

    events = []
    sel = [None]  # sel[0] = active _Ev

    # ── Autosave ─────────────────────────────────────────────────────
    _ev_autosave_path = autosave_path("event.json")

    def _ev_save_state():
        """Persist current event list to autosave file."""
        try:
            data = []
            for ev in events:
                data.append(
                    {
                        "eid": ev.eid,
                        "etype": ev.etype,
                        "title_text": ev.title_text,
                        "desc_text": ev.desc_text,
                        "picture": ev.picture,
                        "major": ev.major,
                        "fire_once": ev.fire_once,
                        "triggered": ev.triggered,
                        "hidden": ev.hidden,
                        "mtth_days": ev.mtth_days,
                        "mtth_months": ev.mtth_months,
                        "trigger_code": ev.trigger_code,
                        "immediate": ev.immediate,
                        "options": ev.options,
                    }
                )
            with open(_ev_autosave_path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2)
        except Exception:
            pass

    def _ev_load_state():
        """Restore event list from autosave file if present."""
        if not os.path.isfile(_ev_autosave_path):
            return False
        try:
            with open(_ev_autosave_path, encoding="utf-8") as fp:
                data = json.load(fp)
            if not data:
                return False
            events.clear()
            for d in data:
                ev = _Ev.__new__(_Ev)
                ev.uid = str(id(ev))
                for k, v in d.items():
                    setattr(ev, k, v)
                events.append(ev)
            return True
        except Exception:
            return False

    def _on_event_win_close():
        _ev_save_state()
        win.destroy()

    # ── Window ───────────────────────────────────────────────────────
    win = tk.Toplevel(app)
    preview_image_loader = TkImageLoader(win)
    gfx_image_loader = TkImageLoader(win)
    win.title(tr("wizard.event.title", "Event Maker"))
    win.configure(bg=BG_DARK)
    win.geometry("1320x820")
    win.resizable(True, True)
    win.grab_set()
    win.protocol("WM_DELETE_WINDOW", _on_event_win_close)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INNER FUNCTIONS — all defined before any widget building
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # ── GFX helpers ──────────────────────────────────────────────────
    def _get_active_dims():
        prof = getattr(
            MOD,
            "event_dim_profiles",
            {"vanilla": {"country": (210, 176), "news": (397, 165)}},
        )
        active = getattr(MOD, "event_dim_active_profile", "vanilla")
        dims = prof.get(
            active, prof.get("vanilla", {"country": (210, 176), "news": (397, 165)})
        )
        cw, ch = dims.get("country", (210, 176))
        nw, nh = dims.get("news", (397, 165))
        return cw, ch, nw, nh

    def _find_gfx_file(gfx_name):
        if not gfx_name:
            return None
        if gfx_name in _ev_gfx_cache:
            return _ev_gfx_cache[gfx_name]
        path = None
        if MOD.loaded:
            # 1. Exact match from scanned sprites dict
            if gfx_name in MOD.sprites:
                path = MOD.sprites[gfx_name]
            else:
                ev_dir = os.path.join(
                    MOD.root,
                    getattr(
                        MOD,
                        "path_event_pictures",
                        os.path.join("gfx", "event_pictures"),
                    ),
                )
                for prefix in ("GFX_report_event_", "GFX_news_event_", "GFX_"):
                    if gfx_name.startswith(prefix):
                        stem = gfx_name[len(prefix) :]
                        path = find_catalog_image(MOD.graphics_catalog, ev_dir, stem)
                        break
        _ev_gfx_cache[gfx_name] = path
        return path

    def _read_image_size(path):
        if path in _ev_imgsize_cache:
            return _ev_imgsize_cache[path]
        result = None
        try:
            with open(path, "rb") as f:
                magic = f.read(4)
            if magic == b"DDS ":
                with open(path, "rb") as f:
                    f.seek(12)
                    h = int.from_bytes(f.read(4), "little")
                    w = int.from_bytes(f.read(4), "little")
                result = w, h
            else:
                img = tk.PhotoImage(file=path)
                result = img.width(), img.height()
        except Exception:
            pass
        _ev_imgsize_cache[path] = result
        return result

    # ── Preview scheduler (defined early so all callbacks can reference it) ──
    _prev_job = [None]
    _prev_img_cache = {}  # (gfx_key, w, h) -> PhotoImage or None
    _prev_img_pending = set()

    def _schedule_preview(*_):
        if _prev_job[0]:
            win.after_cancel(_prev_job[0])
        _prev_job[0] = win.after(80, _render_preview)

    # ── Preview renderer (forward-references canvas widget, safe as lambda'd) ──
    def _render_preview():
        _prev_job[0] = None
        cv = preview_cv
        cv.delete("all")
        ev = sel[0]
        W = max(cv.winfo_width(), 420)
        H = max(cv.winfo_height(), 420)

        # ── empty state ──────────────────────────────────────────────
        if ev is None:
            cv.create_text(
                W // 2,
                H // 2,
                text=tr(
                    "event.empty_preview", "+ Create or select an event\nto see preview"
                ),
                fill="#5a6070",
                font=("Helvetica", 11, "italic"),
                justify="center",
            )
            return

        # ── authentic HOI4 colour palette ────────────────────────────
        # ── HOI4 in-game dark theme (matches Image 2 reference) ─────
        HOI_WIN_BG = "#0f1520"  # dark navy event window background
        HOI_PIC_BG = "#090d12"  # near-black picture area
        HOI_BORDER = "#2a3d2a"  # dark green outer frame border
        HOI_DIVIDER = "#1a2a3a"  # subtle navy divider
        HOI_INNER = "#0c1018"  # inner bevel (darker)
        HOI_BADGE = "#3a6b3a"  # green "COUNTRY EVENT" badge colour
        HOI_PIC_DSH = "#3a6b3a"  # dashed green picture placeholder border
        HOI_TITLE = "#8a9ab0"  # dim blue-grey title text
        HOI_BODY = "#c8d4e0"  # light grey body text
        HOI_BODY_BG = "#131c2b"  # title+body section background
        HOI_OPT_BG = "#0f1a2a"  # dark navy option button bg
        HOI_OPT_BDR = "#2a3a4a"  # option border
        HOI_OPT_TXT = "#e0e8f0"  # near-white option text
        SHADOW = "#000000"

        # ── layout ───────────────────────────────────────────────────
        is_news = ev.etype == "news_event"
        # news events are wider & shorter; country events taller
        BASE_W = 560 if is_news else 500
        BASE_H = 280 if is_news else 420
        PIC_H_B = 140 if is_news else 180  # base picture area height

        scale = min((W - 50) / BASE_W, (H - 60) / BASE_H, 1.2)
        ev_w = int(BASE_W * scale)
        ev_h = int(BASE_H * scale)
        pic_h = int(PIC_H_B * scale)

        x0 = (W - ev_w) // 2
        y0 = max(30, (H - ev_h - 30) // 2)

        # ── drop shadow ──────────────────────────────────────────────
        for off in (8, 5, 3):
            80 + (8 - off) * 20
            cv.create_rectangle(
                x0 + off,
                y0 + off,
                x0 + ev_w + off,
                y0 + ev_h + off,
                fill=SHADOW,
                outline="",
            )

        # ── window background ────────────────────────────────────────
        cv.create_rectangle(
            x0, y0, x0 + ev_w, y0 + ev_h, fill=HOI_WIN_BG, outline=HOI_BORDER, width=2
        )
        # inner bevel line
        cv.create_rectangle(
            x0 + 3,
            y0 + 3,
            x0 + ev_w - 3,
            y0 + ev_h - 3,
            fill="",
            outline=HOI_INNER,
            width=1,
        )

        # ── picture area ─────────────────────────────────────────────
        pic_y0 = y0 + 2
        pic_y1 = y0 + pic_h
        cv.create_rectangle(
            x0 + 2, pic_y0, x0 + ev_w - 2, pic_y1, fill=HOI_PIC_BG, outline=""
        )

        # ── Picture: load via PIL (supports DDS/TGA/PNG) ────────────────
        cx = x0 + ev_w // 2
        cy = (pic_y0 + pic_y1) // 2
        pic_w_px = ev_w - 4
        pic_h_px = pic_h - 4
        fpath = _find_gfx_file(ev.picture)
        cache_key = (ev.picture, pic_w_px, pic_h_px)
        pic_shown = False

        if cache_key in _prev_img_cache:
            cached = _prev_img_cache[cache_key]
            if cached is not None:
                cv._img_ref = cached
                cv.create_image(cx, cy, image=cached, anchor="center")
                pic_shown = True
            # else: already tried and failed, show placeholder

        elif fpath and cache_key not in _prev_img_pending:
            # Draw placeholder immediately, then load image in background
            def _decode_preview_image(item):
                path, wpw, wph = item
                if not PIL_OK:
                    return (
                        ("tk", path, wpw, wph)
                        if path.lower().endswith(".png")
                        else None
                    )

                def _decode(path_to_decode):
                    with PILImage.open(path_to_decode) as source:
                        pil = source.convert("RGBA")
                    rs = getattr(PILImage, "LANCZOS", getattr(PILImage, "ANTIALIAS", 1))
                    pw, ph = pil.size
                    ratio = min(wpw / max(pw, 1), wph / max(ph, 1))
                    return pil.resize(
                        (max(1, int(pw * ratio)), max(1, int(ph * ratio))), rs
                    )

                try:
                    return ("pil", _decode(path))
                except Exception:
                    # PIL failed (e.g. unsupported DDS compression BC1/BC3)
                    # Try alternative: look for a PNG/TGA version of the same stem
                    if path:
                        stem2 = os.path.splitext(path)[0]
                        for alt_ext in (".png", ".tga", ".jpg"):
                            alt_path = stem2 + alt_ext
                            if not os.path.exists(alt_path):
                                # Try finding it via case-insensitive walk
                                folder = os.path.dirname(path)
                                base = os.path.basename(stem2).lower() + alt_ext
                                try:
                                    for fname in os.listdir(folder):
                                        if fname.lower() == base:
                                            alt_path = os.path.join(folder, fname)
                                            break
                                except Exception:
                                    pass
                            if os.path.exists(alt_path):
                                try:
                                    return ("pil", _decode(alt_path))
                                except Exception:
                                    pass
                return None

            def _realize_preview_image(decoded):
                kind, value, *dimensions = decoded
                if kind == "pil":
                    return PILImageTk.PhotoImage(value)
                wpw, wph = dimensions
                raw = tk.PhotoImage(file=value)
                sx = max(1, raw.width() // wpw)
                sy = max(1, raw.height() // wph)
                s = max(sx, sy)
                return raw.subsample(s, s) if s > 1 else raw

            wev_uid = ev.uid if hasattr(ev, "uid") else id(ev)

            def _show_preview(item, img_ref, key=cache_key, event_uid=wev_uid):
                _prev_img_pending.discard(key)
                _prev_img_cache[key] = img_ref
                # Re-render on main thread only if same event is still selected
                if (
                    sel[0]
                    and (sel[0].uid if hasattr(sel[0], "uid") else id(sel[0]))
                    == event_uid
                ):
                    _render_preview()

            _prev_img_pending.add(cache_key)
            preview_image_loader.submit(
                (fpath, pic_w_px, pic_h_px),
                _decode_preview_image,
                realizer=_realize_preview_image,
                apply=_show_preview,
            )

        if not pic_shown:
            # Placeholder — GFX key + expected dims
            cw2, ch2, nw2, nh2 = _get_active_dims()
            exp_w2, exp_h2 = (nw2, nh2) if is_news else (cw2, ch2)
            fs_gfx = max(7, int(8 * scale))
            pw = min(int(exp_w2 * scale * 0.55), ev_w - 24)
            ph = min(int(exp_h2 * scale * 0.55), pic_h - 20)
            bx0p, bx1p = cx - pw // 2, cx + pw // 2
            by0p, by1p = cy - ph // 2, cy + ph // 2
            cv.create_rectangle(
                bx0p,
                by0p,
                bx1p,
                by1p,
                fill="",
                outline=HOI_PIC_DSH,
                dash=(4, 3),
                width=1,
            )
            gfx_short = ev.picture
            if len(gfx_short) > 36:
                gfx_short = gfx_short[:33] + "..."
            cv.create_text(
                cx,
                cy - int(8 * scale),
                text=f"[ {gfx_short} ]",
                fill=HOI_PIC_DSH,
                font=("Courier", fs_gfx),
                width=ev_w - 20,
            )
            cv.create_text(
                cx,
                cy + int(10 * scale),
                text=f"{exp_w2} × {exp_h2}",
                fill=HOI_INNER,
                font=("Courier", max(6, fs_gfx - 1)),
            )

        # ── gold divider ─────────────────────────────────────────────
        cv.create_line(x0 + 1, pic_y1, x0 + ev_w - 1, pic_y1, fill=HOI_DIVIDER, width=2)
        # thin inner highlight below divider
        cv.create_line(
            x0 + 1, pic_y1 + 2, x0 + ev_w - 1, pic_y1 + 2, fill=HOI_INNER, width=1
        )

        # ── title+body section background ───────────────────────────
        cv.create_rectangle(
            x0 + 2,
            pic_y1 + 2,
            x0 + ev_w - 2,
            y0 + ev_h - 2,
            fill=HOI_BODY_BG,
            outline="",
        )

        # ── title ────────────────────────────────────────────────────
        fs_t = max(8, int(11 * scale))
        title_y = pic_y1 + int(7 * scale)
        cv.create_text(
            x0 + ev_w // 2,
            title_y,
            text=(ev.title_text or "Event Title").upper(),
            fill=HOI_TITLE,
            font=("Georgia", fs_t, "bold"),
            anchor="n",
            width=ev_w - 24,
        )

        # ── description ──────────────────────────────────────────────
        fs_d = max(7, int(9 * scale))
        desc_y = title_y + int(fs_t * 2.2 * scale)
        cv.create_text(
            x0 + 14,
            desc_y,
            text=ev.desc_text or "Event description.",
            fill=HOI_BODY,
            font=("Georgia", fs_d),
            anchor="nw",
            width=ev_w - 28,
            justify="left",
        )

        # ── options ──────────────────────────────────────────────────
        n_opts = max(1, len(ev.options))
        opt_h = int(26 * scale)
        gap = int(4 * scale)
        total_opts_h = n_opts * opt_h + (n_opts - 1) * gap
        opts_y = y0 + ev_h - total_opts_h - int(12 * scale)

        # separator above options
        cv.create_line(
            x0 + 8,
            opts_y - int(5 * scale),
            x0 + ev_w - 8,
            opts_y - int(5 * scale),
            fill=HOI_OPT_BDR,
            width=1,
        )

        fs_o = max(7, int(9 * scale))
        for i, opt in enumerate(ev.options):
            oy = opts_y + i * (opt_h + gap)
            ox0 = x0 + 8
            ox1 = x0 + ev_w - 8
            # (no shadow — matches app theme)
            # button bg with gradient feel (two rects)
            cv.create_rectangle(
                ox0, oy, ox1, oy + opt_h, fill=HOI_OPT_BG, outline=HOI_OPT_BDR, width=1
            )
            # (no highlight line — matches app theme)
            label = opt.get("text", "Option")
            if len(label) > 50:
                label = label[:47] + "..."
            cv.create_text(
                (ox0 + ox1) // 2,
                oy + opt_h // 2,
                text=label,
                fill=HOI_OPT_TXT,
                font=("Georgia", fs_o),
            )

        # ── type badge (top-left corner tab) ─────────────────────────
        badge = "NEWS EVENT" if is_news else "COUNTRY EVENT"
        badge_fg = HOI_BADGE
        badge_bg = HOI_WIN_BG
        fs_b = max(7, int(8 * scale))
        bpad = 6
        bw = len(badge) * int(6.5 * scale) + bpad * 2
        bh = 18
        bx0 = x0
        bx1 = x0 + bw
        by0 = y0 - bh
        by1 = y0
        cv.create_rectangle(
            bx0, by0, bx1, by1, fill=badge_bg, outline=HOI_BORDER, width=1
        )
        cv.create_text(
            bx0 + bw // 2,
            by0 + bh // 2,
            text=badge,
            fill=badge_fg,
            font=("Courier", fs_b, "bold"),
        )

        # ── major badge (top-right) ───────────────────────────────────
        if ev.major:
            cv.create_text(
                x0 + ev_w - 6,
                y0 - bh // 2,
                text="★  MAJOR EVENT",
                fill="#f0c040",
                font=("Courier", fs_b, "bold"),
                anchor="e",
            )

    # ── GFX picker helpers ───────────────────────────────────────────
    def _gfx_list_for_type():
        ev_type = sel[0].etype if sel[0] else "country_event"
        base = list(GFX_NEWS) if ev_type == "news_event" else list(GFX_COUNTRY)
        if MOD.loaded and MOD.root:
            ev_dir = os.path.join(
                MOD.root,
                getattr(
                    MOD, "path_event_pictures", os.path.join("gfx", "event_pictures")
                ),
            )
            if os.path.isdir(ev_dir):
                for key, _path in collect_image_pairs(
                    ev_dir,
                    "GFX_report_event_",
                    catalog=MOD.graphics_catalog,
                    recursive=False,
                ):
                    if key not in base:
                        base.append(key)
        return sorted(set(base))

    def _refresh_list():
        for w in list_inner.winfo_children():
            w.destroy()
        filt = _ev_filter.get().strip().lower()
        visible_events = (
            [
                ev
                for ev in events
                if not filt
                or filt in ev.eid.lower()
                or filt in (ev.title_text or "").lower()
            ]
            if filt
            else events
        )
        for ev in visible_events:
            is_sel = sel[0] and sel[0].uid == ev.uid
            bg = BG_CARD if is_sel else BG_PANEL
            fr = tk.Frame(
                list_inner,
                bg=bg,
                highlightthickness=1,
                highlightbackground=BORDER_G if is_sel else BORDER,
            )
            fr.pack(fill="x", padx=4, pady=2)
            badge_col = BLUE if ev.etype == "news_event" else GREEN
            tk.Label(
                fr,
                text="N" if ev.etype == "news_event" else "C",
                bg=badge_col,
                fg=BG_DARK,
                font=("Courier", 8, "bold"),
                width=2,
            ).pack(side="left")
            tk.Label(
                fr,
                text=ev.eid,
                bg=bg,
                fg=TEXT if is_sel else TEXT_DIM,
                font=("Courier", 9),
                anchor="w",
                cursor="hand2",
            ).pack(side="left", fill="x", expand=True, padx=4)
            for w in fr.winfo_children():
                w.bind("<Button-1>", lambda e, ev=ev: _select(ev))
            fr.bind("<Button-1>", lambda e, ev=ev: _select(ev))

    def _select(ev):
        sel[0] = ev
        _populate(ev)
        _refresh_list()
        _refresh_gfx_list()
        _schedule_preview()

    def _populate(ev):
        v_etype.set(ev.etype)
        v_eid.set(ev.eid)
        v_title_text.set(ev.title_text)
        v_desc_text.delete("1.0", "end")
        v_desc_text.insert("1.0", ev.desc_text)
        v_picture.set(ev.picture)
        v_major.set(ev.major)
        v_fire_once.set(ev.fire_once)
        v_triggered.set(ev.triggered)
        v_hidden.set(ev.hidden)
        v_mtth_d.set(ev.mtth_days)
        v_mtth_m.set(ev.mtth_months)
        t_trigger.delete("1.0", "end")
        t_trigger.insert("1.0", ev.trigger_code)
        t_immediate.delete("1.0", "end")
        t_immediate.insert("1.0", ev.immediate)
        _refresh_opts()

    def _apply_event():
        ev = sel[0]
        if not ev:
            return
        _prev_img_cache.clear()  # force image reload when picture key changes
        ev.etype = v_etype.get()
        ev.eid = v_eid.get().strip()
        ev.title_text = v_title_text.get().strip()
        ev.desc_text = v_desc_text.get("1.0", "end-1c").strip()
        ev.picture = v_picture.get().strip()
        ev.major = v_major.get()
        ev.fire_once = v_fire_once.get()
        ev.triggered = v_triggered.get()
        ev.hidden = v_hidden.get()
        ev.mtth_days = v_mtth_d.get().strip()
        ev.mtth_months = v_mtth_m.get().strip()
        ev.trigger_code = t_trigger.get("1.0", "end-1c").strip()
        ev.immediate = t_immediate.get("1.0", "end-1c").strip()
        _refresh_list()
        _render_preview()
        status_lbl.config(text=f"  ✓  Applied {ev.eid}")

    def _on_type_change():
        if sel[0]:
            sel[0].etype = v_etype.get()
        _refresh_gfx_list()
        _schedule_preview()

    # ── Options ──────────────────────────────────────────────────────
    def _refresh_opts():
        for w in opt_box.winfo_children():
            w.destroy()
        if not sel[0]:
            return
        for i, opt in enumerate(sel[0].options):
            _build_opt_row(opt_box, i, opt)

    def _open_effect_picker(target_text):
        """
        Popup effect selector — mirrors the focus wizard's effect tab.
        Inserts rendered HOI4 code into target_text (a tk.Text widget).
        """
        pwin = tk.Toplevel(win)
        pwin.title(tr("effect_picker.title", "Effect Picker"))
        pwin.configure(bg=BG_DARK)
        pwin.geometry("620x580")
        pwin.resizable(True, True)
        pwin.grab_set()

        # ── header ────────────────────────────────────────────────────
        hdr = tk.Frame(pwin, bg=BG_DARK)
        hdr.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(hdr, text="🔍", bg=BG_DARK, fg=TEXT_DIM, font=("Helvetica", 11)).pack(
            side="left", padx=(0, 4)
        )
        _search_ph = tr("focus.effects.search_placeholder", "Search effects...")
        eff_search_var = tk.StringVar(value=_search_ph)
        eff_search_ent = tk.Entry(
            hdr,
            textvariable=eff_search_var,
            bg=BG_CARD,
            fg=TEXT_DIM,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        eff_search_ent.pack(fill="x", expand=True, ipady=4)

        def _ph_in(e):
            if eff_search_var.get() == _search_ph:
                eff_search_var.set("")
                eff_search_ent.config(fg=TEXT)

        def _ph_out(e):
            if not eff_search_var.get():
                eff_search_var.set(_search_ph)
                eff_search_ent.config(fg=TEXT_DIM)

        eff_search_ent.bind("<FocusIn>", _ph_in)
        eff_search_ent.bind("<FocusOut>", _ph_out)

        # ── category + effect dropdown ─────────────────────────────────
        cat_row = tk.Frame(pwin, bg=BG_DARK)
        cat_row.pack(fill="x", padx=10, pady=(4, 0))
        tk.Label(
            cat_row,
            text=tr("common.category", "Category:"),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
        ).pack(side="left")
        eff_cat = tk.StringVar(value=EFFECT_CATS[0])
        cat_menu = tk.OptionMenu(
            cat_row, eff_cat, *EFFECT_CATS, command=lambda _: _rebuild_dd()
        )
        cat_menu.config(
            bg=BG_CARD,
            fg=TEXT,
            activebackground=BORDER_G,
            font=("Helvetica", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            width=12,
            anchor="w",
        )
        cat_menu["menu"].config(
            bg=BG_CARD, fg=TEXT, activebackground=BORDER_G, font=("Helvetica", 9)
        )
        cat_menu.pack(side="left", padx=4)

        eff_type = tk.StringVar()
        dd_frame = tk.Frame(cat_row, bg=BG_DARK)
        dd_frame.pack(side="left", fill="x", expand=True)

        def _rebuild_dd(items=None):
            for w in dd_frame.winfo_children():
                w.destroy()
            if items is None:
                items = effects_in_cat(eff_cat.get())
            if not items:
                return
            eff_type.set(items[0][0])
            om = tk.OptionMenu(dd_frame, eff_type, *[k for k, _ in items])
            menu = om["menu"]
            menu.delete(0, "end")
            for k, lbl in items:
                menu.add_command(
                    label=f"{k}  —  {lbl}",
                    command=lambda v=k: [eff_type.set(v), _refresh_fields()],
                )
            om.config(
                bg=BG_CARD,
                fg=TEXT,
                activebackground=SEL_BG,
                font=("Helvetica", 9),
                relief="flat",
                highlightthickness=1,
                highlightbackground=BORDER_G,
                anchor="w",
                width=30,
            )
            om["menu"].config(
                bg=BG_CARD, fg=TEXT, activebackground=SEL_BG, font=("Helvetica", 9)
            )
            om.pack(fill="x", expand=True)
            _refresh_fields()

        def _filter_dd(*_):
            raw = eff_search_var.get()
            if raw == _search_ph or not raw.strip():
                _rebuild_dd()
                return
            q = raw.strip().lower()
            matches = [
                (k, v["label"])
                for k, v in EFFECT_DEFS.items()
                if q in k.lower()
                or q in v["label"].lower()
                or q in v.get("cat", "").lower()
            ]
            for w in dd_frame.winfo_children():
                w.destroy()
            if not matches:
                tk.Label(
                    dd_frame,
                    text=tr("focus.effects.none_found", "No effects found"),
                    bg=BG_DARK,
                    fg=TEXT_DIM,
                    font=("Helvetica", 9),
                ).pack(anchor="w")
                return
            eff_type.set(matches[0][0])
            om = tk.OptionMenu(dd_frame, eff_type, *[k for k, _ in matches])
            menu = om["menu"]
            menu.delete(0, "end")
            for k, lbl in matches:
                cat = EFFECT_DEFS[k].get("cat", "")
                menu.add_command(
                    label=f"[{cat}]  {k}  —  {lbl}",
                    command=lambda v=k: [eff_type.set(v), _refresh_fields()],
                )
            om.config(
                bg=BG_CARD,
                fg=TEXT,
                activebackground=SEL_BG,
                font=("Helvetica", 9),
                relief="flat",
                highlightthickness=1,
                highlightbackground=BORDER_G,
                anchor="w",
                width=34,
            )
            om["menu"].config(
                bg=BG_CARD, fg=TEXT, activebackground=SEL_BG, font=("Helvetica", 9)
            )
            om.pack(fill="x", expand=True)
            _refresh_fields()

        eff_search_var.trace_add("write", _filter_dd)
        eff_type.trace_add("write", lambda *_: _refresh_fields())

        # ── fields panel ───────────────────────────────────────────────
        tk.Frame(pwin, bg=BORDER_G, height=1).pack(fill="x", padx=8, pady=(6, 0))

        fields_outer = tk.Frame(pwin, bg=BG_PANEL)
        fields_outer.pack(fill="both", expand=True, padx=8, pady=4)

        fields_cv = tk.Canvas(fields_outer, bg=BG_PANEL, highlightthickness=0)
        fields_sb = tk.Scrollbar(
            fields_outer, orient="vertical", command=fields_cv.yview
        )
        fields_frm = tk.Frame(fields_cv, bg=BG_PANEL)
        fields_win = fields_cv.create_window((0, 0), window=fields_frm, anchor="nw")
        fields_cv.configure(yscrollcommand=fields_sb.set)
        fields_frm.bind(
            "<Configure>",
            lambda e: fields_cv.configure(scrollregion=fields_cv.bbox("all")),
        )
        fields_cv.bind(
            "<Configure>", lambda e: fields_cv.itemconfig(fields_win, width=e.width)
        )
        fields_cv.bind(
            "<MouseWheel>",
            lambda e: fields_cv.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )
        fields_cv.pack(side="left", fill="both", expand=True)
        fields_sb.pack(side="right", fill="y")

        # live field value store: {field_name: StringVar or Text ref}
        _fvars = {}

        def _refresh_fields(*_):
            for w in fields_frm.winfo_children():
                w.destroy()
            _fvars.clear()
            key = eff_type.get()
            defn = EFFECT_DEFS.get(key, {})
            if not defn:
                tk.Label(
                    fields_frm,
                    text=tr(
                        "effect_picker.unknown_effect",
                        "  Unknown effect: {effect}\n  Will be inserted as raw snippet.",
                        effect=repr(key),
                    ),
                    bg=BG_PANEL,
                    fg=ORANGE,
                    font=("Helvetica", 9, "italic"),
                    justify="left",
                ).pack(anchor="w", padx=8, pady=8)
                return

            tk.Label(
                fields_frm,
                text=f"  [{defn.get('cat','')}]  {defn.get('label', key)}",
                bg=BG_PANEL,
                fg=TEXT,
                font=("Helvetica", 10, "bold"),
                anchor="w",
            ).pack(fill="x", padx=8, pady=(8, 2))
            tk.Frame(fields_frm, bg=BORDER_G, height=1).pack(
                fill="x", padx=8, pady=(0, 6)
            )

            for fname, wtype, default, hint in defn.get("fields", []):
                row = tk.Frame(fields_frm, bg=BG_PANEL)
                row.pack(fill="x", padx=8, pady=3)
                tk.Label(
                    row,
                    text=f"{fname}:",
                    bg=BG_PANEL,
                    fg=TEXT_DIM,
                    font=("Helvetica", 9),
                    width=14,
                    anchor="w",
                ).pack(side="left")

                if wtype == "multiline":
                    t = tk.Text(
                        row,
                        bg=BG_CARD,
                        fg=TEXT,
                        insertbackground=BLUE,
                        font=("Courier", 9),
                        relief="flat",
                        highlightthickness=1,
                        highlightbackground=BORDER_G,
                        height=4,
                        wrap="none",
                    )
                    t.insert("1.0", default)
                    t.pack(side="left", fill="x", expand=True, ipady=2)
                    _fvars[fname] = ("text", t)

                elif wtype.startswith("dropdown:"):
                    opts = wtype.split(":")[1].split(",")
                    sv = tk.StringVar(value=default if default in opts else opts[0])
                    om = tk.OptionMenu(row, sv, *opts)
                    om.config(
                        bg=BG_CARD,
                        fg=TEXT,
                        activebackground=BORDER_G,
                        font=("Helvetica", 9),
                        relief="flat",
                        highlightthickness=1,
                        highlightbackground=BORDER_G,
                        anchor="w",
                    )
                    om["menu"].config(
                        bg=BG_CARD,
                        fg=TEXT,
                        activebackground=BORDER_G,
                        font=("Helvetica", 9),
                    )
                    om.pack(side="left", padx=2, fill="x", expand=True)
                    _fvars[fname] = ("var", sv)

                else:
                    sv = tk.StringVar(value=default)
                    tk.Entry(
                        row,
                        textvariable=sv,
                        bg=BG_CARD,
                        fg=TEXT,
                        insertbackground=BLUE,
                        font=("Helvetica", 10),
                        relief="flat",
                        highlightthickness=1,
                        highlightbackground=BORDER_G,
                    ).pack(side="left", fill="x", expand=True, ipady=3, padx=2)
                    _fvars[fname] = ("var", sv)

                if hint:
                    tk.Label(
                        row,
                        text=f"  {hint}",
                        bg=BG_PANEL,
                        fg=TEXT_DIM,
                        font=("Helvetica", 7, "italic"),
                        anchor="w",
                    ).pack(side="left", padx=(4, 0))

        # ── render HOI4 snippet ────────────────────────────────────────
        def _render_snippet():
            key = eff_type.get().strip()
            defn = EFFECT_DEFS.get(key, {})
            if not defn:
                return f"\t{key} = yes\n"
            fields = defn.get("fields", [])
            if len(fields) == 1:
                fname, wtype, _, _ = fields[0]
                kind, ref = _fvars.get(fname, ("var", tk.StringVar()))
                val = (
                    ref.get("1.0", "end-1c").strip()
                    if kind == "text"
                    else ref.get().strip()
                )
                return f"\t{key} = {val}\n"
            else:
                lines = [f"\t{key} = {{"]
                for fname, _wtype, _, _ in fields:
                    kind, ref = _fvars.get(fname, ("var", tk.StringVar()))
                    val = (
                        ref.get("1.0", "end-1c").strip()
                        if kind == "text"
                        else ref.get().strip()
                    )
                    lines.append(f"\t\t{fname} = {val}")
                lines.append("\t}")
                return "\n".join(lines) + "\n"

        # ── live preview ───────────────────────────────────────────────
        tk.Frame(pwin, bg=BORDER_G, height=1).pack(fill="x", padx=8)
        prev_frame = tk.Frame(pwin, bg=BG_DARK)
        prev_frame.pack(fill="x", padx=8, pady=(4, 0))
        tk.Label(
            prev_frame,
            text=tr("effect_picker.preview", "  Preview:"),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "bold"),
        ).pack(anchor="w")
        prev_lbl = tk.Label(
            prev_frame,
            text="",
            bg=BG_DARK,
            fg=GREEN,
            font=("Courier", 9),
            anchor="w",
            justify="left",
            padx=8,
            pady=2,
        )
        prev_lbl.pack(fill="x")

        def _update_preview(*_):
            try:
                prev_lbl.config(text=_render_snippet())
            except Exception:
                pass

        # rebind all field changes to also update preview — wire after a small delay
        def _wire_preview_traces():
            for _fname, (kind, ref) in _fvars.items():
                if kind == "var":
                    ref.trace_add("write", _update_preview)
                else:
                    ref.bind("<KeyRelease>", _update_preview)
            _update_preview()

        pwin.after(50, _wire_preview_traces)

        # ── bottom bar ─────────────────────────────────────────────────
        tk.Frame(pwin, bg=BORDER_G, height=1).pack(fill="x", padx=8, pady=(4, 0))
        bot = tk.Frame(pwin, bg=BG_DARK)
        bot.pack(fill="x", padx=10, pady=6)

        tk.Button(
            bot,
            text=tr("common.cancel", "Cancel"),
            command=pwin.destroy,
            bg=BG_CARD,
            fg=TEXT,
            relief="flat",
            font=("Helvetica", 9),
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side="right", padx=4)

        def _insert_effect():
            snippet = _render_snippet()
            target_text.insert("end", snippet)
            _schedule_preview()
            pwin.destroy()

        tk.Button(
            bot,
            text=tr("effect_picker.insert_effect", "+ Insert Effect"),
            command=_insert_effect,
            bg="#14532d",
            fg=GREEN,
            relief="flat",
            font=("Helvetica", 10, "bold"),
            padx=14,
            pady=5,
            cursor="hand2",
        ).pack(side="right")

        tk.Label(
            bot,
            text=tr(
                "effect_picker.insert_hint", "Inserts snippet at end of effects box"
            ),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "italic"),
        ).pack(side="left", padx=4)

        # ── init ───────────────────────────────────────────────────────
        _rebuild_dd()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BUILD UI — all functions defined above, safe to reference them now
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # ── Top bar ──────────────────────────────────────────────────────
    topbar = tk.Frame(win, bg=BG_DARK, height=44)
    topbar.pack(fill="x")
    topbar.pack_propagate(False)

    tk.Label(
        topbar,
        text=tr("wizard.event.header", "EVENT MAKER"),
        bg=BG_DARK,
        fg=TEXT,
        font=("Helvetica", 11, "bold"),
        padx=12,
    ).pack(side="left")
    tk.Frame(topbar, bg=BORDER_G, width=1, height=24).pack(side="left", padx=4, pady=10)

    status_lbl = tk.Label(
        topbar, text="", bg=BG_DARK, fg=TEXT_DIM, font=("Helvetica", 8, "italic")
    )
    status_lbl.pack(side="right", padx=14)

    def _build_opt_row(parent, idx, opt):
        frm = tk.Frame(
            parent, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_G
        )
        frm.pack(fill="x", pady=2)
        hdr = tk.Frame(frm, bg=BG_DARK)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text=f"  Option {idx+1}",
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "bold"),
        ).pack(side="left")
        tk.Button(
            hdr,
            text="✕",
            command=lambda i=idx: _del_option(i),
            bg=BG_DARK,
            fg=RED,
            relief="flat",
            font=("Helvetica", 9),
            cursor="hand2",
            padx=4,
        ).pack(side="right")

        def _row(lbl, key, is_text=False, height=3):
            r = tk.Frame(frm, bg=BG_CARD)
            r.pack(fill="x", padx=6, pady=2)
            tk.Label(
                r,
                text=lbl,
                bg=BG_CARD,
                fg=TEXT_DIM,
                font=("Helvetica", 8),
                width=10,
                anchor="w",
            ).pack(side="left")
            if is_text:
                t = tk.Text(
                    r,
                    bg=BG_DARK,
                    fg=TEXT,
                    insertbackground=BLUE,
                    font=("Courier", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=BORDER,
                    height=height,
                    wrap="none",
                )
                t.insert("1.0", opt.get(key, ""))
                t.pack(side="left", fill="x", expand=True, ipady=2)
                t.bind(
                    "<KeyRelease>",
                    lambda e, k=key, w=t: [
                        opt.update({k: w.get("1.0", "end-1c")}),
                        _schedule_preview(),
                    ],
                )
            else:
                sv = tk.StringVar(value=str(opt.get(key, "")))
                tk.Entry(
                    r,
                    textvariable=sv,
                    bg=BG_DARK,
                    fg=TEXT,
                    insertbackground=BLUE,
                    font=("Helvetica", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=BORDER,
                ).pack(side="left", fill="x", expand=True, ipady=2)
                sv.trace_add(
                    "write",
                    lambda *a, k=key, v=sv: [
                        opt.update({k: v.get()}),
                        _schedule_preview(),
                    ],
                )

        _row(tr("event.option.name", "name:"), "name")
        _row(tr("event.option.text", "text:"), "text")
        # Effects row with picker button
        eff_hdr_r = tk.Frame(frm, bg=BG_CARD)
        eff_hdr_r.pack(fill="x", padx=6, pady=(4, 0))
        tk.Label(
            eff_hdr_r,
            text="effects:",
            bg=BG_CARD,
            fg=TEXT_DIM,
            font=("Helvetica", 8),
            width=10,
            anchor="w",
        ).pack(side="left")
        # Build effects textbox manually so we have a direct reference for the picker
        eff_text_r = tk.Frame(frm, bg=BG_CARD)
        eff_text_r.pack(fill="x", padx=6, pady=(0, 2))
        tk.Label(
            eff_text_r,
            text="",
            bg=BG_CARD,
            fg=TEXT_DIM,
            font=("Helvetica", 8),
            width=10,
            anchor="w",
        ).pack(side="left")
        eff_t = tk.Text(
            eff_text_r,
            bg=BG_DARK,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Courier", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            height=3,
            wrap="none",
        )
        eff_t.insert("1.0", opt.get("effects", ""))
        eff_t.pack(side="left", fill="x", expand=True, ipady=2)
        eff_t.bind(
            "<KeyRelease>",
            lambda e, k="effects", w=eff_t: [
                opt.update({k: w.get("1.0", "end-1c")}),
                _schedule_preview(),
            ],
        )
        tk.Button(
            eff_hdr_r,
            text=tr("effect_picker.button_search", "Search Effect Picker"),
            bg=BG_CARD,
            fg=BLUE,
            relief="flat",
            font=("Helvetica", 8),
            cursor="hand2",
            padx=6,
            pady=1,
            highlightthickness=1,
            highlightbackground=BORDER,
            command=lambda t=eff_t: _open_effect_picker(t),
        ).pack(side="right")
        _row(tr("event.option.ai_chance", "ai_chance:"), "ai_chance")

    def _add_option():
        if not sel[0]:
            return
        n = len(sel[0].options) + 1
        sel[0].options.append(
            {
                "name": f"{sel[0].eid}.{chr(96+n)}",
                "text": f"Option {n}",
                "effects": "",
                "ai_chance": "1",
            }
        )
        _refresh_opts()
        _schedule_preview()

    def _del_option(idx):
        if not sel[0]:
            return
        if len(sel[0].options) <= 1:
            messagebox.showwarning(
                "Options", "An event must have at least one option.", parent=win
            )
            return
        sel[0].options.pop(idx)
        _refresh_opts()
        _schedule_preview()

    # ── Output generation ─────────────────────────────────────────────
    def _render_event_txt(ev):
        def ind(text, n=2):
            return (
                "\n".join("\t" * n + ln for ln in text.splitlines())
                if text.strip()
                else ""
            )

        out = [f"{ev.etype} = {{"]
        out.append(f"\tid = {ev.eid}")
        out.append(f"\ttitle = {ev.eid}.t")
        out.append(f"\tdesc = {ev.eid}.d")
        out.append(f"\tpicture = {ev.picture}")
        if ev.major:
            out.append("\tmajor = yes")
        if ev.fire_once:
            out.append("\tfire_only_once = yes")
        if ev.triggered:
            out.append("\tis_triggered_only = yes")
        if ev.hidden:
            out.append("\thidden = yes")
        if ev.trigger_code.strip():
            out.append("\ttrigger = {")
            out.append(ind(ev.trigger_code))
            out.append("\t}")
        if ev.mtth_days or ev.mtth_months:
            out.append("\tmean_time_to_happen = {")
            if ev.mtth_days:
                out.append(f"\t\tdays = {ev.mtth_days}")
            if ev.mtth_months:
                out.append(f"\t\tmonths = {ev.mtth_months}")
            out.append("\t}")
        if ev.immediate.strip():
            # Blank line before immediate block (matches MD event file convention)
            out.append("")
            out.append("\timmediate = {")
            # Do NOT inject a log line into immediate — MD convention: no log in immediate blocks
            out.append(ind(ev.immediate))
            out.append("\t}")
        out.append("")
        for opt in ev.options:
            out.append("\toption = {")
            out.append(f"\t\tname = {opt.get('name','opt')}")
            opt_effects = opt.get("effects", "").strip()
            opt_name = opt.get("name", "opt")
            # Inject log line only when there are actual effects (MD rule: log only if effects present)
            # Format matches real MD event files: [This.GetName] and "<option_name> executed"
            if opt_effects and "log = " not in opt_effects:
                out.append(
                    f'\t\tlog = "[GetDateText]: [This.GetName]: {opt_name} executed"'
                )
            if opt_effects:
                out.append(ind(opt_effects))
            out.append(f"\t\tai_chance = {{ base = {opt.get('ai_chance','1')} }}")
            out.append("\t}")
        out.append("}")
        return "\n".join(out)

    def _generate_all_txt():
        if not events:
            return ""
        ns_set = list(dict.fromkeys(ev.eid.split(".")[0] for ev in events))
        lines = ["# Generated by HOI4 Content Maker", ""]
        for ns in ns_set:
            lines.append(f"add_namespace = {ns}")
        lines.append("")
        for ev in events:
            lines.append(_render_event_txt(ev))
            lines.append("")
        return "\n".join(lines)

    def _generate_yml():
        if not events:
            return ""
        lines = ["l_english:", ""]
        for ev in events:
            lines.append(f' {ev.eid}.t: "{ev.title_text}"')
            lines.append(f' {ev.eid}.d: "{ev.desc_text}"')
            for opt in ev.options:
                lines.append(f' {opt["name"]}: "{opt.get("text",opt["name"])}"')
            lines.append("")
        return "\n".join(lines)

    # ── Top bar actions ───────────────────────────────────────────────
    def _new_event():
        ev = _Ev()
        events.append(ev)
        _select(ev)
        _refresh_list()
        status_lbl.config(text=f"  ✓  New event: {ev.eid}")

    def _delete_event():
        if not sel[0]:
            return
        if not messagebox.askyesno("Delete", f"Delete '{sel[0].eid}'?", parent=win):
            return
        events.remove(sel[0])
        sel[0] = None
        if events:
            _select(events[-1])
        else:
            preview_cv.delete("all")
        _refresh_list()

    def _export_txt():
        if not events:
            messagebox.showwarning("Export", "No events.", parent=win)
            return
        path = filedialog.asksaveasfilename(
            parent=win,
            defaultextension=".txt",
            filetypes=[("HOI4 Events", "*.txt"), ("All", "*.*")],
            title="Export Events .txt",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(_generate_all_txt())
        status_lbl.config(text=f"  ✓  Exported {len(events)} events")

    def _copy_yml():
        if not events:
            messagebox.showwarning("YML", "No events.", parent=win)
            return
        win.clipboard_clear()
        win.clipboard_append(_generate_yml())
        status_lbl.config(
            text=tr("common.status.loc_yml_copied", "  ok  Localisation YML copied!")
        )
        messagebox.showinfo(
            "Copied",
            "Localisation YML copied to clipboard.\n\nPaste into:\n"
            "  localisation/english/[modname]_l_english.yml",
            parent=win,
        )

    def _save_to_mod():
        if not events:
            messagebox.showwarning("Save", "No events to save.", parent=win)
            return

        ns = sanitize_component(events[0].eid.split(".")[0], fallback="TAG")
        saved = []
        errs = []
        warnings = []

        # ── Determine mod root and target files ───────────────────────────
        if MOD.edit_events_file:
            ev_file = MOD.edit_events_file
            mod_root = MOD.root or os.path.dirname(os.path.dirname(ev_file))
        else:
            mod_root = filedialog.askdirectory(
                parent=win,
                title="Select MOD ROOT folder (events appended to events/<ns>.txt)",
            )
            if not mod_root:
                return
            ev_file = os.path.join(mod_root, "events", f"{ns}.txt")

        if MOD.edit_loc_file and os.path.isfile(MOD.edit_loc_file):
            loc_file = MOD.edit_loc_file
        else:
            loc_file = os.path.join(
                mod_root, "localisation", "english", f"{ns}_l_english.yml"
            )
        os.makedirs(os.path.dirname(ev_file), exist_ok=True)
        os.makedirs(os.path.dirname(loc_file), exist_ok=True)
        wf = notifying_workspace_files(MOD, mod_root)

        # ── EVENTS: safe append — never touch existing content ────────────
        try:
            existing_ids = set()
            file_exists = os.path.isfile(ev_file)
            if file_exists:
                with open(ev_file, encoding="utf-8", errors="replace") as f:
                    raw = f.read()
                # Collect every id = X already in the file
                for m in re.finditer(r"\bid\s*=\s*(\S+)", raw):
                    existing_ids.add(m.group(1).strip())

            to_append = [ev for ev in events if ev.eid not in existing_ids]
            skipped = [ev.eid for ev in events if ev.eid in existing_ids]
            if skipped:
                warnings.append("Already in file (skipped): " + ", ".join(skipped))

            if to_append:
                lines = []
                if not file_exists:
                    # Brand-new file — write namespace header first
                    lines.append(f"add_namespace = {ns}")
                    lines.append("")
                else:
                    lines.append("")
                    lines.append(
                        "# ── Appended by HOI4 Content Maker ─────────────────────────────────"
                    )
                for ev in to_append:
                    lines.append("")
                    lines.append(_render_event_txt(ev))

                ev_content = "\n".join(lines) + "\n"
                if file_exists:
                    wf.append_text(ev_file, ev_content, encoding="utf-8")
                else:
                    wf.write_text(ev_file, ev_content, encoding="utf-8")
                rel = os.path.relpath(ev_file, mod_root)
                saved.append(
                    f"{rel}  (+{len(to_append)} event{'s' if len(to_append)!=1 else ''})"
                )
            else:
                warnings.append(
                    "No new events to append — all IDs already present in file."
                )

        except Exception as e:
            errs.append("Events file: " + str(e))

        # ── LOCALISATION: safe append — skip keys already present ─────────
        try:
            yml_new_lines = []
            for line in _generate_yml().splitlines():
                if not line.strip() or line.strip().startswith("l_english"):
                    continue
                yml_new_lines.append(line)

            existing_yml_keys = set()
            yml_exists = os.path.isfile(loc_file)
            # Regex accepts both the modern `key: "value"` form and the legacy `key:0 "value"` form
            _YML_KEY = re.compile(r'^\s+(\S+?)(?::\d+)?\s*[=:]?\s*"')
            if yml_exists:
                with open(loc_file, encoding="utf-8-sig", errors="replace") as f:
                    for line in f:
                        m = _YML_KEY.match(line)
                        if m:
                            existing_yml_keys.add(m.group(1))

            to_add = []
            for ln in yml_new_lines:
                m = _YML_KEY.match(ln)
                # If the line doesn't look like a loc key, keep it as-is (header/comment).
                if not m:
                    to_add.append(ln)
                elif m.group(1) not in existing_yml_keys:
                    to_add.append(ln)

            if to_add:
                if not yml_exists:
                    wf.write_text(loc_file, "l_english:\n", encoding="utf-8-sig")
                # Only add the section header if it's not already there
                needs_hdr = True
                try:
                    with open(loc_file, encoding="utf-8-sig", errors="replace") as _rf:
                        if f"##########Events - {ns}##########" in _rf.read():
                            needs_hdr = False
                except Exception:
                    pass
                loc_body = ""
                if needs_hdr:
                    loc_body += f"\n ##########Events - {ns}##########\n"
                loc_body += "\n".join(to_add) + "\n"
                wf.append_text(loc_file, loc_body, encoding="utf-8-sig")
                rel = os.path.relpath(loc_file, mod_root)
                saved.append(f"{rel}  (+{len(to_add)} keys)")
            else:
                warnings.append("No new localisation keys to append.")

        except Exception as e:
            errs.append("Localisation: " + str(e))

        # ── SCRIPTED LOC ─────────────────────────────────────────────────
        if MOD.edit_scripted_loc_file:
            sloc_blocks = []
            eid = v_id.get().strip() if "v_id" in dir() else ""
            if not eid:
                # try to grab event id from the generated output
                m3 = re.search(
                    r"id\s*=\s*([\w\.]+)",
                    _get_output_text() if callable(lambda: _get_output_text()) else "",
                )
                eid = m3.group(1) if m3 else ""
            if eid:
                sloc_blocks.append(
                    {"name": f"GET_{eid}_title", "texts": [], "default": f"{eid}.t"}
                )
                sloc_blocks.append(
                    {"name": f"GET_{eid}_desc", "texts": [], "default": f"{eid}.d"}
                )
            append_scripted_loc(
                MOD.edit_scripted_loc_file, sloc_blocks, saved, errs, mod_root
            )

        # ── Report ────────────────────────────────────────────────────────
        msg = ""
        if saved:
            msg += "Saved:\n" + "\n".join(saved)
        if warnings:
            msg += ("\n\n" if msg else "") + "Notes:\n" + "\n".join(warnings)
        if errs:
            msg += ("\n\n" if msg else "") + "Errors:\n" + "\n".join(errs)
        if not msg:
            msg = "Nothing to save."
        messagebox.showinfo("Saved to Mod", msg, parent=win)
        if saved:
            status_lbl.config(
                text=tr("common.status.saved_to_mod", "  ok  Saved to mod")
            )

    def _browse_mod_events():
        import glob as _glob
        import re as _re2

        if not MOD.loaded or not MOD.root:
            messagebox.showinfo(
                "No Mod Loaded",
                "Load a mod first to browse existing events.",
                parent=win,
            )
            return
        ev_dir = os.path.join(MOD.root, "events")
        if not os.path.isdir(ev_dir):
            messagebox.showinfo(
                "Not Found", "No events/ directory found in mod.", parent=win
            )
            return
        files = sorted(_glob.glob(os.path.join(ev_dir, "*.txt")))
        if not files:
            messagebox.showinfo(
                "No Files Found", "No .txt files found in events/.", parent=win
            )
            return

        dlg = tk.Toplevel(win)
        dlg.title("Browse Mod Events")
        dlg.configure(bg=BG_DARK)
        dlg.geometry("520x440")
        dlg.resizable(True, True)
        dlg.grab_set()
        tk.Label(
            dlg,
            text=tr("event.browser.header", "BROWSE MOD EVENTS"),
            bg=BG_DARK,
            fg=TEXT,
            font=("Helvetica", 11, "bold"),
            pady=8,
        ).pack(fill="x", padx=12)
        tk.Label(
            dlg,
            text=tr(
                "event.browser.description",
                "Select a file to import. Already-loaded events are preserved.",
            ),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
        ).pack(fill="x", padx=12)
        tk.Frame(dlg, bg=BORDER_G, height=1).pack(fill="x", pady=(4, 0))

        frm = tk.Frame(dlg, bg=BG_DARK)
        frm.pack(fill="both", expand=True, padx=10, pady=6)
        lb = tk.Listbox(
            frm,
            bg=BG_CARD,
            fg=TEXT,
            selectbackground=SEL_BG,
            selectforeground=TEXT,
            font=("Courier", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            activestyle="none",
        )
        sb = tk.Scrollbar(frm, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        for fp in files:
            lb.insert("end", f"  {os.path.basename(fp)}")

        def _do_import():
            sel = lb.curselection()
            if not sel:
                return
            fp = files[sel[0]]
            # Check for duplicate event IDs
            existing_ids = {ev.eid for ev in events}
            try:
                with open(fp, encoding="utf-8-sig", errors="replace") as f:
                    raw = f.read()
                dupes = [
                    m.group(1)
                    for m in _re2.finditer(r"\bids?\s*=\s*([^\s{}#\n]+)", raw)
                    if m.group(1) in existing_ids
                ]
            except Exception:
                dupes = []
            if dupes:
                d_str = ", ".join(sorted(set(dupes))[:8])
                if not messagebox.askyesno(
                    "Duplicate IDs",
                    f"These event IDs already exist:\n{d_str}\n\n"
                    "Import anyway? (duplicates will be added as new entries)",
                    parent=dlg,
                ):
                    return
            dlg.destroy()
            _import_txt(_path=fp)

        lb.bind("<Double-Button-1>", lambda e: _do_import())
        bot_dlg = tk.Frame(dlg, bg=BG_DARK, pady=6)
        bot_dlg.pack(fill="x")
        tk.Button(
            bot_dlg,
            text=tr("common.import_file", "Import File"),
            command=_do_import,
            bg="#14532d",
            fg="#4ade80",
            relief="flat",
            font=("Helvetica", 10, "bold"),
            padx=16,
            pady=5,
            cursor="hand2",
        ).pack(side="left", padx=10)
        tk.Button(
            bot_dlg,
            text=tr("common.cancel", "Cancel"),
            command=dlg.destroy,
            bg=BG_CARD,
            fg=TEXT,
            relief="flat",
            font=("Helvetica", 10),
            padx=12,
            pady=5,
            cursor="hand2",
        ).pack(side="right", padx=10)

    def _import_txt(_path=None):
        path = _path or filedialog.askopenfilename(
            parent=win,
            filetypes=[("HOI4 Events", "*.txt"), ("All", "*.*")],
            title="Import HOI4 Events .txt",
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                raw = f.read()
        except Exception as e:
            messagebox.showerror("Import Error", str(e), parent=win)
            return

        def _str_val(v, default=""):
            """Extract a plain string from a value that may be a str, dict, or list
            (HOI4 supports block-format title/desc with conditional triggers)."""
            if isinstance(v, str):
                return v
            if isinstance(v, dict):
                return v.get("text", default)
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and "text" in item:
                        return item["text"]
                    if isinstance(item, str):
                        return item
            return default

        tokens = tokenize(raw)
        imported = []
        i = 0
        while i < len(tokens):
            if (
                tokens[i] in ("country_event", "news_event")
                and i + 1 < len(tokens)
                and tokens[i + 1] == "="
            ):
                etype = tokens[i]
                blk, i = parse_block(tokens, i + 2)
                ev = _Ev()
                ev.etype = etype
                ev.eid = blk.get("id", ev.eid)
                ev.title_text = _str_val(blk.get("title", "")).replace(".", " ")
                ev.desc_text = _str_val(blk.get("desc", "")).replace(".", " ")
                ev.picture = blk.get("picture", "GFX_report_event_generic_handshake")
                ev.major = blk.get("major", "no") == "yes"
                ev.fire_once = blk.get("fire_only_once", "no") == "yes"
                ev.triggered = blk.get("is_triggered_only", "no") == "yes"
                ev.hidden = blk.get("hidden", "no") == "yes"
                mtth = blk.get("mean_time_to_happen", {})
                if isinstance(mtth, dict):
                    ev.mtth_days = mtth.get("days", "")
                    ev.mtth_months = mtth.get("months", "")
                opts_raw = blk.get("option", [])
                if isinstance(opts_raw, dict):
                    opts_raw = [opts_raw]
                ev.options = []
                for ob in opts_raw:
                    if not isinstance(ob, dict):
                        continue
                    ai = ob.get("ai_chance", {})
                    ai_v = (
                        ai.get("base", ai.get("factor", "1"))
                        if isinstance(ai, dict)
                        else str(ai)
                    )
                    ev.options.append(
                        {
                            "name": ob.get("name", "opt"),
                            "text": ob.get("name", "opt").replace(".", " "),
                            "effects": "",
                            "ai_chance": str(ai_v),
                        }
                    )
                if not ev.options:
                    ev.options = [
                        {
                            "name": f"{ev.eid}.a",
                            "text": "Option A",
                            "effects": "",
                            "ai_chance": "1",
                        }
                    ]
                imported.append(ev)
            else:
                i += 1
        if not imported:
            messagebox.showwarning("Import", "No events found.", parent=win)
            return
        events.extend(imported)
        _select(imported[0])
        _refresh_list()
        status_lbl.config(text=f"  ✓  Imported {len(imported)} events")

    def _show_tab(which):
        if which == "preview":
            gfx_panel.pack_forget()
            preview_panel.pack(fill="both", expand=True)
            tab_preview_btn.config(bg=BORDER_G, fg=TEXT)
            tab_gfx_btn.config(bg=BG_DARK, fg=TEXT_DIM)
        else:
            preview_panel.pack_forget()
            gfx_panel.pack(fill="both", expand=True)
            tab_gfx_btn.config(bg=BORDER_G, fg=TEXT)
            tab_preview_btn.config(bg=BG_DARK, fg=TEXT_DIM)

    def _open_event_gfx_browser():
        """Event picture browser — identical layout/behaviour to Ideas/Focus GFX browser."""
        ev_type = sel[0].etype if sel[0] else "country_event"

        # ── Resolve root folder ───────────────────────────────────────
        ev_root = None
        catalog = None
        if MOD.loaded and MOD.root:
            candidate = os.path.join(
                MOD.root,
                getattr(
                    MOD, "path_event_pictures", os.path.join("gfx", "event_pictures")
                ),
            )
            if os.path.isdir(candidate):
                ev_root = candidate
                catalog = MOD.graphics_catalog
        if not ev_root:
            ev_root = filedialog.askdirectory(
                title="Select event pictures folder  (gfx/event_pictures/)", parent=win
            )
            if not ev_root:
                return

        # ── Build folder list ─────────────────────────────────────────
        folders = browser_folders(ev_root, "[event_pictures]", catalog=catalog)
        if not folders:
            folders.append(("[selected folder]", ev_root))

        # ── Window ────────────────────────────────────────────────────
        bwin = tk.Toplevel(win)
        bwin.title(
            tr("gfx.browser.event_pictures_title", "GFX Browser  -  Event Pictures")
        )
        bwin.configure(bg=BG_DARK)
        bwin.geometry("900x580")
        bwin.resizable(True, True)
        bwin.grab_set()
        image_loader = TkImageLoader(bwin)

        panes = tk.Frame(bwin, bg=BG_DARK)
        panes.pack(fill="both", expand=True, padx=8, pady=8)

        # ── LEFT: folder list (text only, instant) ────────────────────
        lf = tk.Frame(panes, bg=BG_PANEL, width=200)
        lf.pack(side="left", fill="y", padx=(0, 6))
        lf.pack_propagate(False)
        tk.Label(
            lf,
            text=tr("gfx.folders", "  FOLDERS"),
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 9, "bold"),
            anchor="w",
            pady=6,
        ).pack(fill="x")
        tk.Frame(lf, bg=BORDER_G, height=1).pack(fill="x")
        folder_lb = tk.Listbox(
            lf,
            bg=BG_CARD,
            fg=TEXT,
            selectbackground=BLUE,
            selectforeground=TEXT,
            font=("Courier", 9),
            relief="flat",
            bd=0,
            activestyle="none",
            highlightthickness=0,
        )
        fsb = tk.Scrollbar(lf, orient="vertical", command=folder_lb.yview)
        folder_lb.configure(yscrollcommand=fsb.set)
        fsb.pack(side="right", fill="y")
        folder_lb.pack(fill="both", expand=True, padx=2, pady=4)
        for display, _ in folders:
            folder_lb.insert("end", "  " + display)

        # ── RIGHT panel ───────────────────────────────────────────────
        rf = tk.Frame(panes, bg=BG_DARK)
        rf.pack(side="left", fill="both", expand=True)

        top_r = tk.Frame(rf, bg=BG_DARK)
        top_r.pack(fill="x", pady=(0, 6))
        tk.Label(
            top_r,
            text=tr("common.filter", "Filter:"),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
        ).pack(side="left")
        search_var = tk.StringVar()
        tk.Entry(
            top_r,
            textvariable=search_var,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        ).pack(side="left", padx=6, fill="x", expand=True, ipady=3)
        status_lbl = tk.Label(
            top_r,
            text=tr("gfx.select_folder_status", "select a folder"),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
        )
        status_lbl.pack(side="right", padx=6)

        cv_frame = tk.Frame(rf, bg=BG_PANEL)
        cv_frame.pack(fill="both", expand=True)
        cv = tk.Canvas(cv_frame, bg=BG_PANEL, highlightthickness=0)
        vsb = tk.Scrollbar(cv_frame, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)

        # ── Bottom bar ────────────────────────────────────────────────
        bot = tk.Frame(bwin, bg=BG_DARK)
        bot.pack(fill="x", padx=10, pady=6)
        selected_var = tk.StringVar(value="")
        _initial_gfx = v_picture.get() if "v_picture" in dir() else ""
        tk.Label(
            bot, textvariable=selected_var, bg=BG_DARK, fg=BLUE, font=("Helvetica", 9)
        ).pack(side="left", padx=4)
        tk.Button(
            bot,
            text=tr("common.cancel", "Cancel"),
            command=bwin.destroy,
            bg=BG_CARD,
            fg=TEXT,
            relief="flat",
            font=("Helvetica", 9),
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side="right", padx=4)

        def _apply():
            gfx = selected_var.get()
            if gfx:
                v_picture.set(gfx)
                _update_gfx_compat()
                _draw_gfx_placeholder()
                _schedule_preview()
            bwin.destroy()

        _sel_btn = tk.Button(
            bot,
            text=tr("common.select_arrow", "Select ->"),
            command=_apply,
            bg="#1a3322",
            fg="#4b7a5e",
            relief="flat",
            font=("Helvetica", 10, "bold"),
            padx=14,
            pady=5,
            cursor="arrow",
            state="disabled",
        )
        _sel_btn.pack(side="right")

        def _on_sel_change(*_):
            v = selected_var.get()
            if v:
                _sel_btn.config(
                    bg="#14532d", fg="#c8f0d8", cursor="hand2", state="normal"
                )
            else:
                _sel_btn.config(
                    bg="#1a3322", fg="#4b7a5e", cursor="arrow", state="disabled"
                )

        selected_var.trace_add("write", _on_sel_change)

        # ── Grid constants (same as Ideas browser) ────────────────────
        COLS = 5
        TILE_W = 110
        TILE_H = 100
        PAD = 6
        # Images resized to fit tile (keep aspect ratio within 80x70)
        IMG_W = 80
        IMG_H = 70

        # ── State ─────────────────────────────────────────────────────
        _st = {
            "pairs": [],
            "img_cache": {},
            "drawn": set(),
            "canvas_ids": {},
            "sel_idx": None,
        }

        def _tile_xy(idx):
            col = idx % COLS
            row = idx // COLS
            return PAD + col * (TILE_W + PAD), PAD + row * (TILE_H + PAD)

        def _select_tile(idx):
            old = _st["sel_idx"]
            if old is not None and old in _st["canvas_ids"]:
                rid, _, _ = _st["canvas_ids"][old]
                cv.itemconfig(rid, fill=BG_CARD, outline=BORDER_G)
            _st["sel_idx"] = idx
            gfx_key = _st["pairs"][idx][0]
            selected_var.set(gfx_key)
            if idx in _st["canvas_ids"]:
                rid, _, _ = _st["canvas_ids"][idx]
                cv.itemconfig(rid, fill=SEL_BG, outline=BLUE)

        def _draw_tile(idx):
            if idx in _st["drawn"]:
                return
            _st["drawn"].add(idx)
            gfx_key, path = _st["pairs"][idx]
            x, y = _tile_xy(idx)
            is_sel = gfx_key == selected_var.get()
            rid = cv.create_rectangle(
                x,
                y,
                x + TILE_W,
                y + TILE_H,
                fill=SEL_BG if is_sel else BG_CARD,
                outline=BLUE if is_sel else BORDER_G,
                width=2,
                tags=("tile", f"t{idx}"),
            )
            iid = cv.create_text(
                x + TILE_W // 2,
                y + 44,
                text="...",
                fill=TEXT_DIM,
                font=("Helvetica", 14),
                tags=("tile", f"t{idx}"),
            )
            # Strip GFX prefix for label
            short = gfx_key
            for pfx in ("GFX_report_event_", "GFX_news_event_", "GFX_event_", "GFX_"):
                short = short.replace(pfx, "")
                break
            short = (short[:16] + "...") if len(short) > 16 else short
            lid = cv.create_text(
                x + TILE_W // 2,
                y + TILE_H - 14,
                text=short,
                fill=TEXT_DIM,
                font=("Helvetica", 7),
                width=TILE_W - 8,
                tags=("tile", f"t{idx}"),
            )
            _st["canvas_ids"][idx] = (rid, iid, lid)
            for item in (rid, iid, lid):
                cv.tag_bind(item, "<Button-1>", lambda e, i=idx: _select_tile(i))
                cv.tag_bind(
                    item,
                    "<Double-Button-1>",
                    lambda e, i=idx: [_select_tile(i), _apply()],
                )
            if path in _st["img_cache"]:
                _fill_image(idx)

        def _fill_image(idx):
            if idx not in _st["canvas_ids"]:
                return
            rid, iid, lid = _st["canvas_ids"][idx]
            gfx_key, path = _st["pairs"][idx]
            img = _st["img_cache"].get(path)
            cv.delete(iid)
            if img:
                new_iid = cv.create_image(
                    _tile_xy(idx)[0] + TILE_W // 2,
                    _tile_xy(idx)[1] + 42,
                    anchor="center",
                    image=img,
                    tags=("tile", f"t{idx}"),
                )
            else:
                new_iid = cv.create_text(
                    _tile_xy(idx)[0] + TILE_W // 2,
                    _tile_xy(idx)[1] + 30,
                    text="?",
                    fill=TEXT_DIM,
                    font=("Helvetica", 20),
                    tags=("tile", f"t{idx}"),
                )
            _st["canvas_ids"][idx] = (rid, new_iid, lid)
            for item in (rid, new_iid, lid):
                cv.tag_bind(item, "<Button-1>", lambda e, i=idx: _select_tile(i))
                cv.tag_bind(
                    item,
                    "<Double-Button-1>",
                    lambda e, i=idx: [_select_tile(i), _apply()],
                )

        def _decode_browser_image(item):
            idx, path = item
            if not PIL_OK:
                return None
            stem_p2 = os.path.splitext(path)[0]
            paths_to_try2 = [path] + [
                stem_p2 + alt
                for alt in (".png", ".tga", ".jpg")
                if os.path.exists(stem_p2 + alt) and stem_p2 + alt != path
            ]
            for try_path2 in paths_to_try2:
                try:
                    if not os.path.exists(try_path2):
                        continue
                    with PILImage.open(try_path2) as source:
                        pil = source.convert("RGBA")
                    rs = getattr(PILImage, "LANCZOS", getattr(PILImage, "ANTIALIAS", 1))
                    pw, ph = pil.size
                    ratio = min(IMG_W / max(pw, 1), IMG_H / max(ph, 1))
                    nw = max(1, int(pw * ratio))
                    nh = max(1, int(ph * ratio))
                    return pil.resize((nw, nh), rs)
                except Exception:
                    pass
            return None

        def _apply_browser_image(item, img):
            idx, path = item
            _st["img_cache"][path] = img
            if idx < len(_st["pairs"]) and _st["pairs"][idx][1] == path:
                _fill_image(idx)

        def _lazy_fill(*_):
            if not _st["pairs"]:
                return
            cv.update_idletasks()
            top = cv.canvasy(0)
            bottom = cv.canvasy(cv.winfo_height())
            visible = []
            for idx in range(len(_st["pairs"])):
                _, ty = _tile_xy(idx)
                if ty + TILE_H >= top and ty <= bottom:
                    _draw_tile(idx)
                    visible.append(idx)
            last = max(visible) if visible else 0
            ahead = list(range(last + 1, min(last + 41, len(_st["pairs"]))))
            to_load = [
                i
                for i in (visible + ahead)
                if _st["pairs"][i][1] not in _st["img_cache"]
            ]
            if to_load:
                snapshot = list(_st["pairs"])
                image_loader.submit_many(
                    ((i, snapshot[i][1]) for i in to_load if i < len(snapshot)),
                    _decode_browser_image,
                    realizer=lambda pil: PILImageTk.PhotoImage(pil),
                    apply=_apply_browser_image,
                )

        def _rebuild(pairs):
            image_loader.invalidate()
            cv.delete("all")
            _st["pairs"] = pairs
            _st["drawn"].clear()
            _st["canvas_ids"].clear()
            _st["sel_idx"] = None
            if not pairs:
                status_lbl.config(text=tr("gfx.icons_count", "{count} icons", count=0))
                return
            status_lbl.config(text="%d icons" % len(pairs))
            rows = (len(pairs) + COLS - 1) // COLS
            total_h = PAD + rows * (TILE_H + PAD)
            total_w = PAD + COLS * (TILE_W + PAD)
            cv.configure(scrollregion=(0, 0, total_w, total_h))
            cv.yview_moveto(0)
            _safe_after_idle(bwin, _lazy_fill)

        def _collect_files(folder_path):
            prefix = (
                "GFX_news_event_" if ev_type == "news_event" else "GFX_report_event_"
            )
            return collect_image_pairs(
                folder_path,
                prefix,
                search=search_var.get(),
                catalog=catalog,
            )

        def _load_folder(folder_path):
            status_lbl.config(text=tr("gfx.scanning", "scanning..."))
            bwin.update_idletasks()
            pairs = _collect_files(folder_path)
            _rebuild(pairs)

        def _on_folder_select(evt=None):
            s = folder_lb.curselection()
            if not s:
                return
            _load_folder(folders[s[0]][1])

        cv.bind("<Configure>", lambda e: _safe_after_idle(bwin, _lazy_fill))
        for event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cv.bind(
                event,
                lambda e: [
                    cv.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units"),
                    _safe_after_idle(bwin, _lazy_fill),
                ],
            )
        folder_lb.bind("<<ListboxSelect>>", _on_folder_select)
        search_var.trace_add(
            "write",
            lambda *_: _safe_after(
                bwin,
                300,
                lambda: _on_folder_select() if folder_lb.curselection() else None,
            ),
        )

        # Auto-select first folder
        if folders:
            folder_lb.selection_set(0)
            _load_folder(folders[0][1])

    # BUILD UI body: three-pane layout + inline GFX grid + preview canvas

    def _tb_btn(lbl, cmd, fg=TEXT):
        b = tk.Button(
            topbar,
            text=lbl,
            command=cmd,
            bg=BG_CARD,
            fg=fg,
            activebackground=BORDER_G,
            activeforeground=TEXT,
            font=("Helvetica", 9),
            relief="flat",
            padx=9,
            pady=4,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        b.pack(side="left", padx=2, pady=6)
        return b

    _tb_btn(tr("event.new", "+ New"), _new_event, GREEN)
    _tb_btn(tr("common.import_txt", "Import .txt"), _import_txt, BLUE)
    if MOD.loaded:
        _tb_btn(tr("common.browse_mod", "Browse Mod"), _browse_mod_events, BLUE)
    _tb_btn(tr("common.export_txt", "Export .txt"), _export_txt, TEXT)
    _tb_btn(tr("common.copy_yml", "Copy .yml"), _copy_yml, GOLD)
    _tb_btn(tr("common.save_to_mod", "Save to Mod"), _save_to_mod, GREEN)
    _tb_btn(tr("common.delete", "Delete"), _delete_event, RED)

    tk.Frame(win, bg=BORDER_G, height=1).pack(fill="x")

    body = tk.Frame(win, bg=BG_DARK)
    body.pack(fill="both", expand=True)

    # LEFT: event list
    left_frm = tk.Frame(body, bg=BG_PANEL, width=200)
    left_frm.pack(side="left", fill="y")
    left_frm.pack_propagate(False)
    tk.Label(
        left_frm,
        text=tr("event.list_header", "  EVENTS"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 9, "bold"),
        pady=6,
    ).pack(fill="x")
    tk.Frame(left_frm, bg=BORDER, height=1).pack(fill="x")
    # ── Event search bar ────────────────────────────────────────────────
    _ev_filter = tk.StringVar()
    ev_search_row = tk.Frame(left_frm, bg=BG_PANEL)
    ev_search_row.pack(fill="x", padx=4, pady=3)
    tk.Label(
        ev_search_row, text="🔍", bg=BG_PANEL, fg=TEXT_DIM, font=("Helvetica", 9)
    ).pack(side="left", padx=(2, 0))
    ev_filter_ent = tk.Entry(
        ev_search_row,
        textvariable=_ev_filter,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        relief="flat",
        font=("Helvetica", 9),
        highlightthickness=1,
        highlightbackground=BORDER_G,
    )
    ev_filter_ent.pack(side="left", fill="x", expand=True, ipady=3, padx=4)
    tk.Button(
        ev_search_row,
        text="✕",
        command=lambda: _ev_filter.set(""),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        relief="flat",
        font=("Helvetica", 8),
        cursor="hand2",
        padx=2,
    ).pack(side="left")
    tk.Frame(left_frm, bg=BORDER_G, height=1).pack(fill="x")

    list_cv = tk.Canvas(left_frm, bg=BG_PANEL, highlightthickness=0)
    list_sb = tk.Scrollbar(left_frm, orient="vertical", command=list_cv.yview)
    list_inner = tk.Frame(list_cv, bg=BG_PANEL)
    _list_win = list_cv.create_window((0, 0), window=list_inner, anchor="nw")
    list_cv.configure(yscrollcommand=list_sb.set)
    list_inner.bind(
        "<Configure>", lambda e: list_cv.configure(scrollregion=list_cv.bbox("all"))
    )
    list_cv.bind("<Configure>", lambda e: list_cv.itemconfig(_list_win, width=e.width))
    list_cv.bind(
        "<MouseWheel>",
        lambda e: list_cv.yview_scroll(int(-1 * (e.delta / 120)), "units"),
    )
    list_sb.pack(side="right", fill="y")
    list_cv.pack(side="left", fill="both", expand=True)
    _ev_filter.trace_add("write", lambda *_: _refresh_list())
    tk.Frame(body, bg=BORDER_G, width=1).pack(side="left", fill="y")

    # MIDDLE: scrollable form
    mid_frm = tk.Frame(body, bg=BG_PANEL, width=420)
    mid_frm.pack(side="left", fill="y")
    mid_frm.pack_propagate(False)
    tk.Label(
        mid_frm,
        text=tr("event.properties_header", "  EVENT PROPERTIES"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 9, "bold"),
        pady=6,
    ).pack(fill="x")
    tk.Frame(mid_frm, bg=BORDER, height=1).pack(fill="x")
    form_wrap = tk.Frame(mid_frm, bg=BG_PANEL)
    form_wrap.pack(fill="both", expand=True)
    form_cv = tk.Canvas(form_wrap, bg=BG_PANEL, highlightthickness=0)
    form_sb = tk.Scrollbar(form_wrap, orient="vertical", command=form_cv.yview)
    F = tk.Frame(form_cv, bg=BG_PANEL)
    PAD = {"padx": 8, "pady": 2}
    _fwid = form_cv.create_window((0, 0), window=F, anchor="nw")
    form_cv.configure(yscrollcommand=form_sb.set)
    F.bind("<Configure>", lambda e: form_cv.configure(scrollregion=form_cv.bbox("all")))
    form_cv.bind("<Configure>", lambda e: form_cv.itemconfig(_fwid, width=e.width))
    form_cv.bind(
        "<MouseWheel>",
        lambda e: form_cv.yview_scroll(int(-1 * (e.delta / 120)), "units"),
    )
    form_cv.pack(side="left", fill="both", expand=True)
    form_sb.pack(side="right", fill="y")
    tk.Frame(body, bg=BORDER_G, width=1).pack(side="left", fill="y")

    # RIGHT: tab panel
    right_frm = tk.Frame(body, bg=BG_DARK)
    right_frm.pack(side="left", fill="both", expand=True)

    tab_bar = tk.Frame(right_frm, bg=BG_DARK)
    tab_bar.pack(fill="x")
    tab_preview_btn = tk.Button(
        tab_bar,
        text=tr("event.tab.live_preview", "  LIVE PREVIEW  "),
        bg=BORDER_G,
        fg=TEXT,
        font=("Helvetica", 9, "bold"),
        relief="flat",
        padx=10,
        pady=5,
        cursor="hand2",
        command=lambda: _show_tab("preview"),
    )
    tab_preview_btn.pack(side="left")
    tab_gfx_btn = tk.Button(
        tab_bar,
        text=tr("event.tab.gfx_picker", "  GFX PICKER  "),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 9, "bold"),
        relief="flat",
        padx=10,
        pady=5,
        cursor="hand2",
        command=lambda: _show_tab("gfx"),
    )
    tab_gfx_btn.pack(side="left")
    tk.Frame(tab_bar, bg=BORDER, height=1).pack(fill="x", side="bottom")

    # LIVE PREVIEW panel
    preview_panel = tk.Frame(right_frm, bg=BG_DARK)
    tk.Label(
        preview_panel,
        text=tr("event.preview_hint", "  approximate in-game appearance"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 7, "italic"),
        pady=2,
    ).pack(fill="x")
    tk.Frame(preview_panel, bg=BORDER, height=1).pack(fill="x")
    preview_cv = tk.Canvas(preview_panel, bg=BG_DARK, highlightthickness=0)
    preview_cv.pack(fill="both", expand=True, padx=8, pady=8)
    preview_cv.bind("<Configure>", lambda e: _schedule_preview())

    # GFX PICKER panel — inline image-grid (same as Ideas/Focus browser)
    gfx_panel = tk.Frame(right_frm, bg=BG_DARK)

    _gfx_hdr = tk.Frame(gfx_panel, bg=BG_DARK)
    _gfx_hdr.pack(fill="x")
    tk.Label(
        _gfx_hdr,
        text=tr("event.picture_browser_header", "  EVENT PICTURE BROWSER"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 9, "bold"),
        pady=6,
    ).pack(side="left")
    gfx_dim_lbl = tk.Label(
        _gfx_hdr,
        text="",
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "italic"),
        anchor="e",
        padx=8,
    )
    gfx_dim_lbl.pack(side="right")
    tk.Frame(gfx_panel, bg=BORDER, height=1).pack(fill="x")

    _gfx_flt = tk.Frame(gfx_panel, bg=BG_DARK)
    _gfx_flt.pack(fill="x", padx=8, pady=4)
    tk.Label(
        _gfx_flt,
        text=tr("common.filter", "Filter:"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 9),
    ).pack(side="left")
    v_gfx_search = tk.StringVar()
    tk.Entry(
        _gfx_flt,
        textvariable=v_gfx_search,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Helvetica", 10),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    ).pack(side="left", padx=6, fill="x", expand=True, ipady=3)
    gfx_status_lbl = tk.Label(
        _gfx_flt,
        text=tr("event.gfx_load_hint", "load a mod or Browse GFX >"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 8),
    )
    gfx_status_lbl.pack(side="right", padx=4)

    gfx_compat_lbl = tk.Label(
        gfx_panel,
        text="",
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "bold"),
        anchor="w",
        padx=10,
    )
    gfx_compat_lbl.pack(fill="x")

    _gfx_cv_frame = tk.Frame(gfx_panel, bg=BG_PANEL)
    _gfx_cv_frame.pack(fill="both", expand=True)
    gfx_cv = tk.Canvas(_gfx_cv_frame, bg=BG_PANEL, highlightthickness=0)
    _gfx_vsb = tk.Scrollbar(_gfx_cv_frame, orient="vertical", command=gfx_cv.yview)
    gfx_cv.configure(yscrollcommand=_gfx_vsb.set)
    _gfx_vsb.pack(side="right", fill="y")
    gfx_cv.pack(side="left", fill="both", expand=True)

    _gfx_bot = tk.Frame(gfx_panel, bg=BG_DARK)
    _gfx_bot.pack(fill="x", padx=8, pady=6)
    _gfx_sel_lbl = tk.Label(
        _gfx_bot, text="", bg=BG_DARK, fg=BLUE, font=("Helvetica", 9)
    )
    _gfx_sel_lbl.pack(side="left", padx=4)
    tk.Button(
        _gfx_bot,
        text=tr("gfx.browse_gfx", "Browse GFX >"),
        command=_open_event_gfx_browser,
        bg=BG_CARD,
        fg=TEXT_DIM,
        relief="flat",
        font=("Helvetica", 9),
        cursor="hand2",
        padx=10,
        pady=4,
    ).pack(side="right", padx=4)
    _gfx_sel_btn = tk.Button(
        _gfx_bot,
        text=tr("common.select_arrow", "Select ->"),
        bg="#1a3322",
        fg="#4b7a5e",
        relief="flat",
        font=("Helvetica", 10, "bold"),
        padx=14,
        pady=4,
        cursor="arrow",
        state="disabled",
    )
    _gfx_sel_btn.pack(side="right", padx=2)

    GFX_COLS = 5
    GFX_TILE_W = 110
    GFX_TILE_H = 100
    GFX_PAD = 6
    GFX_IMG_W = 80
    GFX_IMG_H = 70

    _gfx_st = {
        "pairs": [],
        "img_cache": {},
        "drawn": set(),
        "canvas_ids": {},
        "sel_idx": None,
        "selected": "",
    }

    def _gfx_tile_xy(idx):
        col = idx % GFX_COLS
        row = idx // GFX_COLS
        return GFX_PAD + col * (GFX_TILE_W + GFX_PAD), GFX_PAD + row * (
            GFX_TILE_H + GFX_PAD
        )

    def _gfx_select_tile(idx):
        old = _gfx_st["sel_idx"]
        if old is not None and old in _gfx_st["canvas_ids"]:
            rid, _, _ = _gfx_st["canvas_ids"][old]
            gfx_cv.itemconfig(rid, fill=BG_CARD, outline=BORDER_G)
        _gfx_st["sel_idx"] = idx
        gfx_key = _gfx_st["pairs"][idx][0]
        _gfx_st["selected"] = gfx_key
        _gfx_sel_lbl.config(text=gfx_key[-40:] if len(gfx_key) > 40 else gfx_key)
        _gfx_sel_btn.config(bg="#14532d", fg="#c8f0d8", cursor="hand2", state="normal")
        if idx in _gfx_st["canvas_ids"]:
            rid, _, _ = _gfx_st["canvas_ids"][idx]
            gfx_cv.itemconfig(rid, fill=SEL_BG, outline=BLUE)
        # Live-update the preview immediately on every tile click
        v_picture.set(gfx_key)
        if sel[0]:
            sel[0].picture = gfx_key
        _update_gfx_compat(gfx_key)
        _schedule_preview()

    def _gfx_apply_sel():
        gfx = _gfx_st.get("selected", "")
        if gfx:
            v_picture.set(gfx)
            if sel[0]:
                sel[0].picture = gfx
            _update_gfx_compat(gfx)
            _schedule_preview()
            _show_tab("preview")

    _gfx_sel_btn.config(command=_gfx_apply_sel)

    def _gfx_draw_tile(idx):
        if idx in _gfx_st["drawn"]:
            return
        _gfx_st["drawn"].add(idx)
        gfx_key, path = _gfx_st["pairs"][idx]
        x, y = _gfx_tile_xy(idx)
        is_sel = gfx_key == _gfx_st.get("selected", "")
        rid = gfx_cv.create_rectangle(
            x,
            y,
            x + GFX_TILE_W,
            y + GFX_TILE_H,
            fill=SEL_BG if is_sel else BG_CARD,
            outline=BLUE if is_sel else BORDER_G,
            width=2,
            tags=("gtile", f"gt{idx}"),
        )
        iid = gfx_cv.create_text(
            x + GFX_TILE_W // 2,
            y + 44,
            text="...",
            fill=TEXT_DIM,
            font=("Helvetica", 14),
            tags=("gtile", f"gt{idx}"),
        )
        short = gfx_key
        for pfx in ("GFX_report_event_", "GFX_news_event_", "GFX_event_", "GFX_"):
            if short.startswith(pfx):
                short = short[len(pfx) :]
                break
        short = (short[:16] + "...") if len(short) > 16 else short
        lid = gfx_cv.create_text(
            x + GFX_TILE_W // 2,
            y + GFX_TILE_H - 14,
            text=short,
            fill=TEXT_DIM,
            font=("Helvetica", 7),
            width=GFX_TILE_W - 8,
            tags=("gtile", f"gt{idx}"),
        )
        _gfx_st["canvas_ids"][idx] = (rid, iid, lid)
        for item in (rid, iid, lid):
            gfx_cv.tag_bind(item, "<Button-1>", lambda e, i=idx: _gfx_select_tile(i))
            gfx_cv.tag_bind(
                item,
                "<Double-Button-1>",
                lambda e, i=idx: [_gfx_select_tile(i), _gfx_apply_sel()],
            )
        if path in _gfx_st["img_cache"]:
            _gfx_fill_image(idx)

    def _gfx_fill_image(idx):
        if idx not in _gfx_st["canvas_ids"]:
            return
        rid, iid, lid = _gfx_st["canvas_ids"][idx]
        gfx_key, path = _gfx_st["pairs"][idx]
        img = _gfx_st["img_cache"].get(path)
        gfx_cv.delete(iid)
        if img:
            new_iid = gfx_cv.create_image(
                _gfx_tile_xy(idx)[0] + GFX_TILE_W // 2,
                _gfx_tile_xy(idx)[1] + 44,
                anchor="center",
                image=img,
                tags=("gtile", f"gt{idx}"),
            )
        else:
            new_iid = gfx_cv.create_text(
                _gfx_tile_xy(idx)[0] + GFX_TILE_W // 2,
                _gfx_tile_xy(idx)[1] + 34,
                text="?",
                fill=TEXT_DIM,
                font=("Helvetica", 20),
                tags=("gtile", f"gt{idx}"),
            )
        _gfx_st["canvas_ids"][idx] = (rid, new_iid, lid)
        for item in (rid, new_iid, lid):
            gfx_cv.tag_bind(item, "<Button-1>", lambda e, i=idx: _gfx_select_tile(i))
            gfx_cv.tag_bind(
                item,
                "<Double-Button-1>",
                lambda e, i=idx: [_gfx_select_tile(i), _gfx_apply_sel()],
            )

    def _gfx_decode_image(item):
        i, path = item
        if not PIL_OK:
            return None
        paths_to_try = [path]
        # Also queue alt extensions in case primary (DDS) fails
        stem_p = os.path.splitext(path)[0]
        for alt in (".png", ".tga", ".jpg"):
            ap = stem_p + alt
            if ap != path and os.path.exists(ap):
                paths_to_try.append(ap)
        for try_path in paths_to_try:
            try:
                if not os.path.exists(try_path):
                    continue
                with PILImage.open(try_path) as source:
                    pil = source.convert("RGBA")
                rs = getattr(PILImage, "LANCZOS", getattr(PILImage, "ANTIALIAS", 1))
                pw, ph = pil.size
                ratio = min(GFX_IMG_W / max(pw, 1), GFX_IMG_H / max(ph, 1))
                nw2 = max(1, int(pw * ratio))
                nh2 = max(1, int(ph * ratio))
                return pil.resize((nw2, nh2), rs)
            except Exception:
                pass
        return None

    def _gfx_apply_image(item, img):
        i, path = item
        _gfx_st["img_cache"][path] = img
        if i < len(_gfx_st["pairs"]) and _gfx_st["pairs"][i][1] == path:
            _gfx_fill_image(i)

    def _gfx_lazy_fill(*_):
        if not _gfx_st["pairs"]:
            return
        gfx_cv.update_idletasks()
        top = gfx_cv.canvasy(0)
        bottom = gfx_cv.canvasy(gfx_cv.winfo_height())
        visible = []
        for idx in range(len(_gfx_st["pairs"])):
            _, ty = _gfx_tile_xy(idx)
            if ty + GFX_TILE_H >= top and ty <= bottom:
                _gfx_draw_tile(idx)
                visible.append(idx)
        last = max(visible) if visible else 0
        ahead = list(range(last + 1, min(last + 41, len(_gfx_st["pairs"]))))
        to_load = [
            i
            for i in (visible + ahead)
            if _gfx_st["pairs"][i][1] not in _gfx_st["img_cache"]
        ]
        if to_load:
            snap = list(_gfx_st["pairs"])
            gfx_image_loader.submit_many(
                ((i, snap[i][1]) for i in to_load if i < len(snap)),
                _gfx_decode_image,
                realizer=lambda pil: PILImageTk.PhotoImage(pil),
                apply=_gfx_apply_image,
            )

    def _gfx_rebuild(pairs):
        gfx_image_loader.invalidate()
        gfx_cv.delete("all")
        _gfx_st.update(
            {"pairs": pairs, "drawn": set(), "canvas_ids": {}, "sel_idx": None}
        )
        if not pairs:
            gfx_status_lbl.config(text=tr("gfx.icons_count", "{count} icons", count=0))
            return
        gfx_status_lbl.config(text="%d icons" % len(pairs))
        rows = (len(pairs) + GFX_COLS - 1) // GFX_COLS
        total_h = GFX_PAD + rows * (GFX_TILE_H + GFX_PAD)
        total_w = GFX_PAD + GFX_COLS * (GFX_TILE_W + GFX_PAD)
        gfx_cv.configure(scrollregion=(0, 0, total_w, total_h))
        gfx_cv.yview_moveto(0)
        _safe_after_idle(win, _gfx_lazy_fill)

    def _refresh_gfx_list(*_):
        ev_type = sel[0].etype if sel[0] else "country_event"
        cw, ch, nw, nh = _get_active_dims()
        pname = getattr(MOD, "event_dim_active_profile", "vanilla")
        if ev_type == "news_event":
            gfx_dim_lbl.config(
                text="news_event: %dx%d  profile: %s  GFX_news_event_*"
                % (nw, nh, pname),
                fg=GREEN,
            )
        else:
            gfx_dim_lbl.config(
                text="country_event: %dx%d  profile: %s  GFX_report_event_*"
                % (cw, ch, pname),
                fg=TEXT_DIM,
            )
        if MOD.loaded and MOD.root:
            ev_dir = os.path.join(
                MOD.root,
                getattr(
                    MOD, "path_event_pictures", os.path.join("gfx", "event_pictures")
                ),
            )
            if os.path.isdir(ev_dir):
                prefix = (
                    "GFX_news_event_"
                    if ev_type == "news_event"
                    else "GFX_report_event_"
                )
                pairs = collect_image_pairs(
                    ev_dir,
                    prefix,
                    search=v_gfx_search.get(),
                    catalog=MOD.graphics_catalog,
                )
                _gfx_rebuild(pairs)
                return
        gfx_status_lbl.config(
            text=tr("event.gfx_load_hint", "load a mod or Browse GFX >")
        )

    def _update_gfx_compat(gfx_name=None):
        if gfx_name is None:
            gfx_name = v_picture.get() if sel[0] else ""
        if not gfx_name:
            gfx_compat_lbl.config(text="", fg=TEXT_DIM)
            return
        ev_type = sel[0].etype if sel[0] else "country_event"
        cw, ch, nw, nh = _get_active_dims()
        exp_w, exp_h = (cw, ch) if ev_type == "country_event" else (nw, nh)
        pname = getattr(MOD, "event_dim_active_profile", "vanilla")
        fpath = _find_gfx_file(gfx_name)
        if fpath:
            dims = _read_image_size(fpath)
            if dims:
                fw, fh = dims
                if fw == exp_w and fh == exp_h:
                    gfx_compat_lbl.config(
                        text="  ok  %dx%d matches %s %s" % (fw, fh, pname, ev_type),
                        fg=GREEN,
                    )
                else:
                    gfx_compat_lbl.config(
                        text="  warn  %dx%d expected %dx%d (%s)"
                        % (fw, fh, exp_w, exp_h, pname),
                        fg=ORANGE,
                    )
                return
        is_r = gfx_name.startswith("GFX_report_event_")
        is_n = gfx_name.startswith("GFX_news_event_")
        if ev_type == "country_event":
            if is_r:
                gfx_compat_lbl.config(
                    text="  ok  correct prefix (expected %dx%d)" % (exp_w, exp_h),
                    fg=GREEN,
                )
            elif is_n:
                gfx_compat_lbl.config(
                    text="  warn  GFX_news_event_* is for news_event", fg=ORANGE
                )
            else:
                gfx_compat_lbl.config(
                    text="  load mod to validate (%dx%d)" % (exp_w, exp_h), fg=TEXT_DIM
                )
        else:
            if is_n:
                gfx_compat_lbl.config(
                    text="  ok  correct prefix (expected %dx%d)" % (exp_w, exp_h),
                    fg=GREEN,
                )
            elif is_r:
                gfx_compat_lbl.config(
                    text="  warn  GFX_report_event_* is for country_event", fg=ORANGE
                )
            else:
                gfx_compat_lbl.config(
                    text="  load mod to validate (%dx%d)" % (exp_w, exp_h), fg=TEXT_DIM
                )

    def _on_gfx_select(evt=None):
        pass

    def _draw_gfx_placeholder(gfx_name=None):
        pass

    gfx_cv.bind("<Configure>", lambda e: _safe_after_idle(win, _gfx_lazy_fill))
    for _gev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        gfx_cv.bind(
            _gev,
            lambda e: [
                gfx_cv.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units"),
                _safe_after_idle(win, _gfx_lazy_fill),
            ],
        )
    v_gfx_search.trace_add("write", lambda *_: _safe_after(win, 300, _refresh_gfx_list))

    def _hsep():
        tk.Frame(F, bg=BORDER, height=1).pack(fill="x", padx=6, pady=4)

    def _sec(text):
        tk.Label(
            F,
            text=f"  {text}",
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "bold"),
            pady=3,
        ).pack(fill="x")

    def _lbl(text):
        tk.Label(
            F,
            text=text,
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 7, "italic"),
            anchor="w",
            padx=10,
        ).pack(fill="x")

    def _entry_var(label, default=""):
        if label:
            tk.Label(
                F,
                text=label,
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 8),
                anchor="w",
            ).pack(fill="x", padx=8, pady=(3, 0))
        sv = tk.StringVar(value=default)
        tk.Entry(
            F,
            textvariable=sv,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
        ).pack(fill="x", padx=8, ipady=3, pady=(0, 1))
        sv.trace_add("write", _schedule_preview)
        return sv

    def _textbox(label, height=3):
        if label:
            tk.Label(
                F,
                text=label,
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 8),
                anchor="w",
            ).pack(fill="x", padx=8, pady=(3, 0))
        t = tk.Text(
            F,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Courier", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            height=height,
            wrap="word",
        )
        t.pack(fill="x", padx=8, pady=(0, 2))
        t.bind("<KeyRelease>", _schedule_preview)
        return t

    # ── Type ──────────────────────────────────────────────────────
    _sec(tr("event.section.type", "TYPE"))
    type_row = tk.Frame(F, bg=BG_PANEL)
    type_row.pack(fill="x", **PAD)
    v_etype = tk.StringVar(value="country_event")
    for val, lbl in [
        ("country_event", tr("event.type.country_event", "Country Event")),
        ("news_event", tr("event.type.news_event", "News Event")),
    ]:
        tk.Radiobutton(
            type_row,
            text=lbl,
            variable=v_etype,
            value=val,
            bg=BG_PANEL,
            fg=TEXT,
            selectcolor=BG_DARK,
            activebackground=BG_PANEL,
            font=("Helvetica", 9),
            command=_on_type_change,
        ).pack(side="left", padx=8)
    v_etype.trace_add(
        "write", _schedule_preview
    )  # safe: _schedule_preview defined above

    # ── Identity ──────────────────────────────────────────────────
    _hsep()
    _sec(tr("event.section.identity", "IDENTITY"))
    v_eid = _entry_var(
        tr("event.field.event_id", "Event ID  (namespace.number):"), "my_namespace.1"
    )
    v_title_text = _entry_var(
        tr("event.field.title_text", "Title text  (shown in preview):"),
        "My Event Title",
    )

    _lbl(tr("event.field.description", "  Description:"))
    v_desc_text = _textbox("", height=4)

    # ── Picture ───────────────────────────────────────────────────
    _hsep()
    _sec(tr("event.section.picture", "PICTURE"))
    pic_row = tk.Frame(F, bg=BG_PANEL)
    pic_row.pack(fill="x", padx=8, pady=2)
    tk.Label(
        pic_row,
        text=tr("event.field.gfx_key", "GFX key:"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 8),
    ).pack(side="left")
    v_picture = tk.StringVar(value="GFX_report_event_generic_handshake")
    tk.Entry(
        pic_row,
        textvariable=v_picture,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Helvetica", 9),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER,
    ).pack(side="left", fill="x", expand=True, ipady=2, padx=(4, 4))
    tk.Button(
        pic_row,
        text=tr("gfx.browse_gfx", "Browse GFX >"),
        command=_open_event_gfx_browser,
        bg=BG_CARD,
        fg=TEXT_DIM,
        relief="flat",
        font=("Helvetica", 8),
        cursor="hand2",
        padx=6,
    ).pack(side="right")
    v_picture.trace_add("write", _schedule_preview)
    _lbl(tr("event.hint.browse_gfx", "  Click 'Browse GFX' to open the image browser"))

    # ── Flags ─────────────────────────────────────────────────────
    _hsep()
    _sec(tr("event.section.flags", "FLAGS"))
    v_major = tk.BooleanVar(value=False)
    v_fire_once = tk.BooleanVar(value=False)
    v_triggered = tk.BooleanVar(value=True)
    v_hidden = tk.BooleanVar(value=False)
    flags_row = tk.Frame(F, bg=BG_PANEL)
    flags_row.pack(fill="x", padx=8)
    for v, lbl in [
        (v_major, "major"),
        (v_fire_once, "fire_only_once"),
        (v_triggered, "is_triggered_only"),
        (v_hidden, "hidden"),
    ]:
        tk.Checkbutton(
            flags_row,
            text=lbl,
            variable=v,
            bg=BG_PANEL,
            fg=TEXT_DIM,
            selectcolor=BG_DARK,
            activebackground=BG_PANEL,
            font=("Helvetica", 8),
            cursor="hand2",
        ).pack(anchor="w")
        v.trace_add("write", _schedule_preview)

    # ── MTTH ──────────────────────────────────────────────────────
    _hsep()
    _sec(
        tr(
            "event.section.mtth",
            "MEAN TIME TO HAPPEN  (leave blank for is_triggered_only)",
        )
    )
    mtth_row = tk.Frame(F, bg=BG_PANEL)
    mtth_row.pack(fill="x", padx=8, pady=2)
    tk.Label(
        mtth_row,
        text=tr("event.field.days", "days:"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 8),
        width=7,
    ).pack(side="left")
    v_mtth_d = tk.StringVar()
    tk.Entry(
        mtth_row,
        textvariable=v_mtth_d,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Helvetica", 9),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER,
        width=6,
    ).pack(side="left", ipady=2, padx=(0, 10))
    tk.Label(
        mtth_row,
        text=tr("event.field.months", "months:"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 8),
        width=8,
    ).pack(side="left")
    v_mtth_m = tk.StringVar()
    tk.Entry(
        mtth_row,
        textvariable=v_mtth_m,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Helvetica", 9),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER,
        width=6,
    ).pack(side="left", ipady=2)
    v_mtth_d.trace_add("write", _schedule_preview)
    v_mtth_m.trace_add("write", _schedule_preview)

    # ── Trigger / Immediate ───────────────────────────────────────
    _hsep()
    _sec(
        tr(
            "event.section.trigger",
            "TRIGGER  (raw HOI4 - leave blank if is_triggered_only)",
        )
    )
    t_trigger = _textbox("", height=3)
    _hsep()
    imm_hdr = tk.Frame(F, bg=BG_PANEL)
    imm_hdr.pack(fill="x", padx=8, pady=(4, 0))
    tk.Label(
        imm_hdr,
        text=tr("event.section.immediate_effects", "IMMEDIATE EFFECTS  (optional)"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "bold"),
    ).pack(side="left")
    tk.Button(
        imm_hdr,
        text=tr("effect_picker.button_search", "Search Effect Picker"),
        bg=BG_CARD,
        fg=BLUE,
        relief="flat",
        font=("Helvetica", 8),
        cursor="hand2",
        padx=6,
        pady=1,
        highlightthickness=1,
        highlightbackground=BORDER,
        command=lambda: _open_effect_picker(t_immediate),
    ).pack(side="right")
    t_immediate = _textbox("", height=3)

    # ── Options ───────────────────────────────────────────────────
    _hsep()
    opt_hdr = tk.Frame(F, bg=BG_PANEL)
    opt_hdr.pack(fill="x", padx=8, pady=2)
    tk.Label(
        opt_hdr,
        text=tr("event.section.options", "OPTIONS"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "bold"),
    ).pack(side="left")
    tk.Button(
        opt_hdr,
        text=tr("event.add_option", "+ Add Option"),
        command=_add_option,
        bg=BG_CARD,
        fg=GREEN,
        relief="flat",
        font=("Helvetica", 8),
        cursor="hand2",
        padx=6,
        pady=2,
        highlightthickness=1,
        highlightbackground=BORDER,
    ).pack(side="right")
    opt_box = tk.Frame(F, bg=BG_PANEL)
    opt_box.pack(fill="x", padx=6, pady=4)

    # ── Apply button ──────────────────────────────────────────────
    _hsep()
    tk.Button(
        F,
        text=tr("common.apply_changes", "Apply Changes"),
        command=_apply_event,
        bg=BG_CARD,
        fg=GREEN,
        font=("Helvetica", 10, "bold"),
        relief="flat",
        pady=5,
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    ).pack(fill="x", padx=8, pady=(0, 12))

    # ── Init ─────────────────────────────────────────────────────
    _refresh_gfx_list()
    # Restore autosave if available, otherwise create one blank event
    if _ev_load_state() and events:
        _select(events[0])
        _refresh_list()
    else:
        _new_event()
    _show_tab("preview")
    win.after(50, _schedule_preview)  # wait for canvas to get real dimensions
