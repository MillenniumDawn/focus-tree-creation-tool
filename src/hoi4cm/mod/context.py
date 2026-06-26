"""The ``ModContext`` class — mod asset discovery and image loading.

When a mod is loaded, the context walks the mod's directory tree once,
indexes GFX sprites, idea/decision/event IDs, dynamic modifiers, country
tags, and MD money-system file paths. The App and every wizard read from
this single instance (``MOD``).

The scanner is pure-Python: no tkinter. The image loader uses Pillow when
available; without it ``get_image`` returns ``None`` and the rest of the
app still works.
"""

import json
import os
import re
from typing import Callable, Optional

from hoi4cm.core.config import cfg_load, cfg_save
from hoi4cm.core.image import PIL_OK as _PIL_OK
from hoi4cm.core.image import PILImage as _PILImage
from hoi4cm.core.image import PILImageTk as _PILImageTk
from hoi4cm.core.logger import get_logger
from hoi4cm.core.paths import read_file

_log = get_logger("mod")


# Pre-compiled regexes used by the .gfx-file scanners.
_SPRITE_BLOCK_RE = re.compile(r"spriteType\s*=\s*\{")
_SPRITE_NAME_RE = re.compile(r'\bname\s*=\s*"([^"]+)"')
_SPRITE_TEX_RE = re.compile(r'\btexturefile\s*=\s*"([^"]+)"')

# Image extensions the scanners look for on disk.
_IMAGE_EXTS = (".dds", ".png", ".tga")


def _iter_sprite_blocks(text):
    """Yield (start, end, content) for each top-level ``spriteType = { ... }`` block."""
    i = 0
    while i < len(text):
        m = _SPRITE_BLOCK_RE.search(text, i)
        if not m:
            return
        depth = 1
        j = m.end()
        while j < len(text) and depth > 0:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        yield m.start(), j, text[m.start() : j]
        i = j


def _iter_image_paths(root_dir):
    """Yield (filename, abs_path) for every image file under ``root_dir``."""
    for dirpath, _dirs, files in os.walk(root_dir):
        for fname in files:
            if fname.lower().endswith(_IMAGE_EXTS):
                yield fname, os.path.join(dirpath, fname)


def _index_image_files(root_dir, prefix, target):
    """Walk ``root_dir`` and add every image file to ``target`` as ``prefix + stem``."""
    for fname, full in _iter_image_paths(root_dir):
        stem = os.path.splitext(fname)[0]
        target.setdefault(prefix + stem, full)


def _iface_dir_mtime(root):
    """Max mtime of files in ``root/interface/`` (0 if missing)."""
    iface = os.path.join(root, "interface")
    if not os.path.isdir(iface):
        return 0
    latest = 0
    for fn in os.listdir(iface):
        try:
            latest = max(latest, os.path.getmtime(os.path.join(iface, fn)))
        except OSError:
            pass
    return latest


class ModContext:
    """Holds all discovered mod assets: sprites, events, ideas, decisions, etc."""

    def __init__(self):
        self.root = None  # mod root path
        self.sprites = {}  # gfx_name -> abs_path  (all spriteTypes)
        self.sprite_imgs = {}  # gfx_name -> PhotoImage (loaded on demand)
        self.focus_ids = []  # all focus IDs across national_focus/
        self.event_ids = {}  # file_stem -> [id, ...]
        self.idea_ids = []  # all idea/spirit IDs
        self.decision_ids = []  # all decision IDs
        self.decision_cats = []  # all decision category IDs
        self.dyn_mod_ids = []  # common/dynamic_modifiers/*
        self.country_tags = []  # TAG list
        self.variables = set()  # known variable names from set_variable/add_to_variable
        self.loaded = False
        self.is_md = False  # True when Millennium Dawn is detected
        self.mod_name = ""  # basename of mod root
        self._status = ""
        self._img_errors = []  # list of error strings for debugging

        # Extra asset stores
        self.idea_sprites = {}  # gfx_name -> abs_path  (ideas GFX)
        self.decision_sprites = {}  # gfx_name -> abs_path  (decisions GFX)
        self.custom_gfx_dirs = []  # user-added extra GFX dirs
        self.country_tag_names = {}  # TAG -> display name  e.g. {"SOV": "Soviet Union"}
        self.loc_token_style = (
            "colon"  # "colon" = [TAG:NameWithFlag], "dot" = [TAG.GetName]
        )

        # Configurable scan paths (can be changed in Settings)
        self.path_goals = os.path.join("gfx", "interface", "goals")
        self.path_ideas_gfx = os.path.join("gfx", "interface", "ideas")
        self.path_event_pictures = os.path.join("gfx", "event_pictures")

        # Event GFX dimension profiles (vanilla defaults)
        self.event_dim_profiles = {
            "vanilla": {"country": (210, 176), "news": (397, 165)},
        }
        self.event_dim_active_profile = "vanilla"

        # User-selected edit targets (set after mod load prompt)
        self.edit_ideas_file = ""
        self.edit_events_file = ""
        self.edit_events_ns = ""
        self.edit_focus_file = ""
        self.edit_decisions_file = ""
        self.edit_decisions_cat_file = ""
        self.edit_loc_file = ""
        self.edit_scripted_loc_file = ""

        # MD Additional Income system file paths (auto-discovered on mod load)
        self.md_money_system_file = ""
        self.md_money_scripted_loc_file = ""
        self.md_money_yml_file = ""

        # custom_mod_path is referenced in the original settings dialog
        self.custom_mod_path = ""

        # Load any previously saved config
        self._load_config()

    # ── Persisted config ────────────────────────────────────────────
    # (config key, attribute name, allow-falsy-override). ``allow_falsy``
    # is False for boolean fields where a missing config should keep the
    # default rather than resetting to False.
    _PERSISTED_ATTRS = (
        ("path_goals", "path_goals", True),
        ("path_ideas_gfx", "path_ideas_gfx", True),
        ("path_event_pictures", "path_event_pictures", True),
        ("event_dim_profiles", "event_dim_profiles", True),
        ("event_dim_active_profile", "event_dim_active_profile", True),
        ("custom_mod_path", "custom_mod_path", True),
        ("custom_gfx_dirs", "custom_gfx_dirs", True),
        ("country_tag_names", "country_tag_names", True),
        ("loc_token_style", "loc_token_style", True),
        ("is_md_override", "is_md", False),
    )

    def _load_config(self):
        """Apply saved config values to this ModContext instance."""
        cfg = cfg_load()
        for key, attr, allow_falsy in self._PERSISTED_ATTRS:
            if key in cfg and (allow_falsy or cfg[key]):
                setattr(self, attr, cfg[key])
        # Window geometry is restored separately by the App on startup.
        self._saved_geometry = cfg.get("window_geometry", "")
        self._recent_mods = cfg.get("recent_mods", [])

    def save_config(self, window_geometry: str = ""):
        """Persist current path/preference settings to disk.

        ``window_geometry`` is passed in by the App at shutdown — the
        context doesn't need to know about the Tk window directly.
        """
        out = {key: getattr(self, attr) for key, attr, _ in self._PERSISTED_ATTRS}
        out.update(
            {
                "window_geometry": window_geometry,
                "last_mod_path": self.root if self.loaded else "",
                "recent_mods": getattr(self, "_recent_mods", []),
            }
        )
        cfg_save(out)

    # ── HOI4 script tokeniser (same as main parser) ─────────────────
    @staticmethod
    def _tokenize(s):
        tokens = []
        i = 0
        while i < len(s):
            c = s[i]
            if c in " \t\n\r":
                i += 1
                continue
            if c in "{}":
                tokens.append(c)
                i += 1
                continue
            if c == "=":
                tokens.append("=")
                i += 1
                continue
            if c == "#":
                while i < len(s) and s[i] != "\n":
                    i += 1
                continue
            if c == '"':
                j = i + 1
                while j < len(s) and s[j] != '"':
                    j += 1
                tokens.append(s[i + 1 : j])
                i = j + 1
                continue
            j = i
            while j < len(s) and s[j] not in ' \t\n\r{}="#':
                j += 1
            if j > i:
                tokens.append(s[i:j])
            i = j
        return tokens

    @staticmethod
    def _parse_block(tokens, pos):
        result = {}
        pos += 1
        while pos < len(tokens) and tokens[pos] != "}":
            key = tokens[pos]
            pos += 1
            if pos >= len(tokens):
                break
            if tokens[pos] == "=":
                pos += 1
                if pos >= len(tokens):
                    break
                if tokens[pos] == "{":
                    val, pos = ModContext._parse_block(tokens, pos)
                else:
                    val = tokens[pos]
                    pos += 1
                if key in result:
                    ex = result[key]
                    if not isinstance(ex, list):
                        result[key] = [ex]
                    result[key].append(val)
                else:
                    result[key] = val
            else:
                if key not in ("", "=", "{", "}"):
                    result.setdefault("_values", []).append(key)
        return result, pos + 1

    def _read(self, path):
        return read_file(path)

    def _parse_file(self, path):
        """Parse a HOI4 script file into a dict tree."""
        try:
            src = self._read(path)
            tokens = self._tokenize(src)
            tokens = ["{"] + tokens + ["}"]
            result, _ = self._parse_block(tokens, 0)
            return result
        except Exception:
            return {}

    # ── Scanners ─────────────────────────────────────────────────────
    @staticmethod
    def _parse_sprites_from_gfx(text, predicate):
        """Yield (name, abs_path) for every spriteType in *text* matching *predicate*.

        ``predicate`` receives the lowercased texture path and returns True
        to keep the sprite (used to filter for "goals", "ideas", etc.).
        """
        for _start, _end, block in _iter_sprite_blocks(text):
            nm = _SPRITE_NAME_RE.search(block)
            tx = _SPRITE_TEX_RE.search(block)
            if not (nm and tx):
                continue
            tex_raw = tx.group(1).strip().replace("\\\\", "/").replace("\\", "/")
            if not predicate(tex_raw.lower()):
                continue
            yield nm.group(1).strip(), tex_raw.replace("/", os.sep)

    def _scan_gfx(self):
        """Scan ONLY gfx/interface/goals/ — the focus icon folder."""
        goals_dir = os.path.join(self.root, "gfx", "interface", "goals")
        if not os.path.isdir(goals_dir):
            # fallback: try without goals subfolder
            goals_dir = os.path.join(self.root, "gfx", "interface")
        if not os.path.isdir(goals_dir):
            return

        # Also parse .gfx files in interface/ that reference goals textures
        iface = os.path.join(self.root, "interface")
        if os.path.isdir(iface):
            for fname in os.listdir(iface):
                if not fname.endswith(".gfx"):
                    continue
                content = self._read(os.path.join(iface, fname))
                for name, rel_path in self._parse_sprites_from_gfx(
                    content,
                    lambda tex: "goals" in tex or "focus" in tex,
                ):
                    self.sprites[name] = os.path.join(self.root, rel_path)

        # Also directly index every image file in gfx/interface/goals/
        for fname, full in _iter_image_paths(goals_dir):
            stem = os.path.splitext(fname)[0]
            self.sprites.setdefault("GFX_focus_" + stem, full)

    def _scan_idea_gfx(self):
        """Scan gfx/interface/ideas/ (and any custom GFX dirs) for idea sprites."""
        self.idea_sprites.clear()
        ideas_dir = os.path.join(self.root, self.path_ideas_gfx)
        # Also scan interface/*.gfx for idea-related sprites
        iface = os.path.join(self.root, "interface")
        if os.path.isdir(iface):
            for fname in os.listdir(iface):
                if not fname.endswith(".gfx"):
                    continue
                content = self._read(os.path.join(iface, fname))
                for name, rel_path in self._parse_sprites_from_gfx(
                    content,
                    lambda tex: "ideas" in tex or "idea" in tex,
                ):
                    self.idea_sprites[name] = os.path.join(self.root, rel_path)
        # Walk the configured ideas dir + custom dirs for raw image files
        if os.path.isdir(ideas_dir):
            _index_image_files(ideas_dir, "GFX_idea_", self.idea_sprites)
        for cdir in self.custom_gfx_dirs:
            if os.path.isdir(cdir):
                _index_image_files(cdir, "GFX_idea_", self.idea_sprites)

    def _scan_decision_gfx(self):
        """Scan ALL .gfx files in interface/ (recursively) for any spriteType.

        Results are cached in a JSON sidecar file (.hoi4cm_gfx_cache.json) to
        avoid re-walking the gfx/ tree on every mod load.
        """
        self.decision_sprites.clear()
        cache_file = os.path.join(self.root, ".hoi4cm_gfx_cache.json")
        iface_mtime = _iface_dir_mtime(self.root)
        if os.path.isfile(cache_file):
            try:
                with open(cache_file, encoding="utf-8") as f:
                    cached = json.load(f)
                if abs(cached.get("iface_mtime", 0) - iface_mtime) < 2:
                    self.decision_sprites.update(cached.get("sprites", {}))
                    return
            except Exception:
                pass

        # Step 1: parse every .gfx file under interface/ recursively
        iface = os.path.join(self.root, "interface")
        if os.path.isdir(iface):
            for dirpath, _dirs, files in os.walk(iface):
                for fname in files:
                    if not fname.lower().endswith(".gfx"):
                        continue
                    content = self._read(os.path.join(dirpath, fname))
                    for name, rel_path in self._parse_sprites_from_gfx(
                        content, lambda _tex: True
                    ):
                        self.decision_sprites[name] = os.path.join(self.root, rel_path)

        # Step 2: also directly index image files under gfx/
        gfx_root = os.path.join(self.root, "gfx")
        if os.path.isdir(gfx_root):
            for path, full in _iter_image_paths(gfx_root):
                stem = os.path.splitext(os.path.basename(path))[0]
                rel = os.path.relpath(full, self.root).replace(os.sep, "/").lower()
                if "decisions" in rel:
                    keys = (
                        f"GFX_decision_{stem}",
                        f"GFX_decision_category_{stem}",
                    )
                    for key in keys:
                        self.decision_sprites.setdefault(key, full)
                elif "ideas" in rel:
                    self.decision_sprites.setdefault(f"GFX_idea_{stem}", full)
                elif "goals" in rel or "focus" in rel:
                    pass  # handled by _scan_gfx
                else:
                    self.decision_sprites.setdefault(f"GFX_{stem}", full)

        # Write cache
        try:
            cache_data = {
                "iface_mtime": iface_mtime,
                "sprites": dict(self.decision_sprites),
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False)
        except Exception:
            pass

    def _scan_focuses(self):
        d = os.path.join(self.root, "common", "national_focus")
        if not os.path.isdir(d):
            return
        for fname in os.listdir(d):
            if not fname.endswith(".txt"):
                continue
            src = self._read(os.path.join(d, fname))
            for m in re.finditer(r"\bid\s*=\s*(\S+)", src):
                fid = m.group(1).strip()
                if fid not in self.focus_ids:
                    self.focus_ids.append(fid)

    def _scan_events(self):
        d = os.path.join(self.root, "events")
        if not os.path.isdir(d):
            return
        for fname in os.listdir(d):
            if not fname.endswith(".txt"):
                continue
            stem = fname[:-4]
            src = self._read(os.path.join(d, fname))
            ids = []
            for m in re.finditer(r"\bid\s*=\s*(\S+)", src):
                eid = m.group(1).strip()
                if re.match(r"[A-Za-z_][A-Za-z0-9_]*\.\d+", eid) or re.match(
                    r"\d+", eid
                ):
                    ids.append(eid)
            if ids:
                self.event_ids[stem] = ids

    def _scan_ideas(self):
        d = os.path.join(self.root, "common", "ideas")
        if not os.path.isdir(d):
            return
        for fname in os.listdir(d):
            if not fname.endswith(".txt"):
                continue
            data = self._parse_file(os.path.join(d, fname))
            ideas_block = data.get("ideas", {})
            if isinstance(ideas_block, dict):
                for _cat, cat_block in ideas_block.items():
                    if isinstance(cat_block, dict):
                        for idea_id in cat_block:
                            if (
                                not idea_id.startswith("_")
                                and idea_id not in self.idea_ids
                            ):
                                self.idea_ids.append(idea_id)

    def _scan_decisions(self):
        for sub in ("decisions", "common/decisions"):
            d = os.path.join(self.root, sub.replace("/", os.sep))
            if not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                if not fname.endswith(".txt"):
                    continue
                src = self._read(os.path.join(d, fname))
                for m in re.finditer(
                    r"^([A-Za-z][A-Za-z0-9_]+)\s*=\s*\{", src, re.MULTILINE
                ):
                    did = m.group(1)
                    if did not in (
                        "category",
                        "target_trigger",
                        "available",
                        "visible",
                        "modifier",
                        "cost",
                    ):
                        if did not in self.decision_ids:
                            self.decision_ids.append(did)
            cats_d = os.path.join(d, "categories")
            if os.path.isdir(cats_d):
                for fname in os.listdir(cats_d):
                    if not fname.endswith(".txt"):
                        continue
                    src = self._read(os.path.join(cats_d, fname))
                    for m in re.finditer(
                        r"^([A-Za-z][A-Za-z0-9_]+)\s*=\s*\{", src, re.MULTILINE
                    ):
                        cid = m.group(1)
                        if cid not in self.decision_cats:
                            self.decision_cats.append(cid)

    def _scan_dyn_mods(self):
        d = os.path.join(self.root, "common", "dynamic_modifiers")
        if not os.path.isdir(d):
            return
        for fname in os.listdir(d):
            if not fname.endswith(".txt"):
                continue
            src = self._read(os.path.join(d, fname))
            for m in re.finditer(
                r"^([A-Za-z][A-Za-z0-9_]+)\s*=\s*\{", src, re.MULTILINE
            ):
                mid = m.group(1)
                if mid not in self.dyn_mod_ids:
                    self.dyn_mod_ids.append(mid)

    def _scan_tags(self):
        d = os.path.join(self.root, "common", "country_tags")
        if not os.path.isdir(d):
            return
        for fname in os.listdir(d):
            if not fname.endswith(".txt"):
                continue
            src = self._read(os.path.join(d, fname))
            for m in re.finditer(r"^([A-Z]{2,3})\s*=", src, re.MULTILINE):
                tag = m.group(1)
                if tag not in self.country_tags:
                    self.country_tags.append(tag)

    def _scan_variables(self):
        """Scan national_focus files for set_variable / add_to_variable names."""
        d = os.path.join(self.root, "common", "national_focus")
        if not os.path.isdir(d):
            return
        for fname in os.listdir(d):
            if not fname.endswith(".txt"):
                continue
            src = self._read(os.path.join(d, fname))
            for m in re.finditer(
                r"(?:set_variable|add_to_variable)\s*=\s*\{\s*([A-Za-z][A-Za-z0-9_]*)\s*=",
                src,
            ):
                self.variables.add(m.group(1))

    def _scan_md_money_files(self):
        """Auto-discover the three MD additional income system files."""
        if not self.root:
            return
        r = self.root
        p = os.path.join(r, "common", "scripted_effects", "00_money_system.txt")
        self.md_money_system_file = p if os.path.isfile(p) else ""
        sloc_dir = os.path.join(r, "common", "scripted_localisation")
        self.md_money_scripted_loc_file = ""
        if os.path.isdir(sloc_dir):
            for fn in os.listdir(sloc_dir):
                if "money" in fn.lower() and fn.endswith(".txt"):
                    self.md_money_scripted_loc_file = os.path.join(sloc_dir, fn)
                    break
        yml = os.path.join(r, "localisation", "english", "MD_money_l_english.yml")
        self.md_money_yml_file = yml if os.path.isfile(yml) else ""

    # ── Load image for a sprite ───────────────────────────────────────
    def get_image(self, gfx_name, size=(64, 64)):
        """Return a PhotoImage for gfx_name, or None.

        Caches both successes and failures (None means "we already tried")
        so the wizard code can call this repeatedly without re-opening the
        same file.
        """
        if not gfx_name:
            return None
        key = (gfx_name, size)
        if key in self.sprite_imgs:
            return self.sprite_imgs[key]

        path = self.sprites.get(gfx_name)
        if not path:
            self.sprite_imgs[key] = None
            self._img_errors.append("NOT IN SPRITES: " + gfx_name)
            return None
        if not os.path.exists(path):
            self.sprite_imgs[key] = None
            self._img_errors.append("FILE NOT FOUND: " + path)
            return None

        if not _PIL_OK:
            self.sprite_imgs[key] = None
            self._img_errors.append("Pillow not available")
            return None

        try_paths = [path]
        if path.lower().endswith(".dds"):
            stem = os.path.splitext(path)[0]
            for alt_ext in (".png", ".tga", ".jpg"):
                alt = stem + alt_ext
                if os.path.exists(alt):
                    try_paths.append(alt)

        resample = getattr(_PILImage, "LANCZOS", getattr(_PILImage, "ANTIALIAS", 1))
        last_err = ""
        for try_path in try_paths:
            try:
                img = _PILImage.open(try_path).convert("RGBA")
                img = img.resize(size, resample)
                photo = _PILImageTk.PhotoImage(img)
                self.sprite_imgs[key] = photo
                return photo
            except Exception as e:
                last_err = f"{os.path.basename(try_path)}: {e}"

        self.sprite_imgs[key] = None
        self._img_errors.append(f"LOAD FAILED {gfx_name}: {last_err}")
        return None

    def scan(self, root, progress_cb: Optional[Callable] = None):
        self.root = root
        self.mod_name = os.path.basename(root)
        self.sprites.clear()
        self.sprite_imgs.clear()
        self._img_errors.clear()
        self.decision_sprites.clear()
        self.focus_ids.clear()
        self.event_ids.clear()
        self.idea_ids.clear()
        self.decision_ids.clear()
        self.decision_cats.clear()
        self.dyn_mod_ids.clear()
        self.country_tags.clear()
        self.variables.clear()
        self.loaded = False

        name_lower = self.mod_name.lower()
        self.is_md = (
            "millennium" in name_lower
            or "md" == name_lower
            or "millennium_dawn" in name_lower
        )
        if not self.is_md:
            desc_path = os.path.join(root, "descriptor.mod")
            if os.path.exists(desc_path):
                desc_txt = self._read(desc_path).lower()
                self.is_md = "millennium" in desc_txt

        steps = [
            ("GFX sprites", self._scan_gfx),
            ("Idea GFX", self._scan_idea_gfx),
            ("Decision GFX", self._scan_decision_gfx),
            ("Focus IDs", self._scan_focuses),
            ("Events", self._scan_events),
            ("Ideas/Spirits", self._scan_ideas),
            ("Decisions", self._scan_decisions),
            ("Dynamic Modifiers", self._scan_dyn_mods),
            ("Country Tags", self._scan_tags),
            ("Variables", self._scan_variables),
            ("MD Money System", self._scan_md_money_files),
        ]
        for i, (label, fn) in enumerate(steps):
            if progress_cb:
                progress_cb(i, len(steps), label)
            try:
                fn()
            except Exception as e:
                _log.warning("scan step %s failed: %s", label, e)

        self.loaded = True
        if progress_cb:
            progress_cb(len(steps), len(steps), "Done")

    def summary(self):
        md_badge = "  [MD]" if self.is_md else ""
        n_spr = len(self.sprites)
        n_idea_spr = len(self.idea_sprites)
        n_dec_spr = len(self.decision_sprites)
        n_focus = len(self.focus_ids)
        n_idea = len(self.idea_ids)
        n_dyn = len(self.dyn_mod_ids)
        n_tags = len(self.country_tags)
        return (
            f"{n_spr} focus sprites  •  {n_idea_spr} idea sprites  •  "
            f"{n_dec_spr} decision sprites  •  "
            f"{n_focus} focus IDs  •  {n_idea} ideas  •  "
            f"{n_dyn} dyn modifiers  •  {n_tags} tags{md_badge}"
        )


__all__ = ["ModContext"]
