"""The ``ModContext`` class — mod asset discovery and image loading.

When a mod is loaded, the context walks the mod's directory tree once,
indexes GFX sprites, idea/decision/event IDs, dynamic modifiers, country
tags, and MD money-system file paths. The App and every wizard read from
this single instance (``MOD``).

The scanner is pure-Python: no tkinter. The image loader uses Pillow when
available; without it ``get_image`` returns ``None`` and the rest of the
app still works.
"""

import os
import re
import time
from collections.abc import Callable

from hoi4cm.core.concurrency import DaemonThreadPoolExecutor
from hoi4cm.core.config import cfg_load, cfg_save
from hoi4cm.core.image import PIL_OK as _PIL_OK
from hoi4cm.core.image import PILImage as _PILImage
from hoi4cm.core.image import PILImageTk as _PILImageTk
from hoi4cm.core.logger import get_logger
from hoi4cm.core.lru import LRUCache
from hoi4cm.core.paths import read_file
from hoi4cm.mod.graphics_catalog import GraphicsCatalog, GraphicsScanConfig
from hoi4cm.mod.scan_cache import ScanCache
from hoi4cm.script.syntax import parse_block, parse_script, tokenize

_log = get_logger("mod")

# Bound on the in-memory PhotoImage cache (mirrors the GFX browser's own
# cache). Each drawn focus pins its image through the canvas image broker, so
# evicting a cold entry here never blanks something on screen.
_SPRITE_IMG_CACHE_SIZE = 512


# Pre-compiled regexes used by the ID scanners (compiled once, not per file).
_ID_RE = re.compile(r"\bid\s*=\s*(\S+)")
_EVENT_ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\.\d+")
_NUM_ID_RE = re.compile(r"\d+")
_BLOCK_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]+)\s*=\s*\{", re.MULTILINE)
_TAG_RE = re.compile(r"^([A-Z]{2,3})\s*=", re.MULTILINE)
_VARIABLE_RE = re.compile(
    r"(?:set_variable|add_to_variable)\s*=\s*\{\s*([A-Za-z][A-Za-z0-9_]*)\s*="
)

# Block-level keywords that are not decision IDs.
_DECISION_KEYWORDS = frozenset(
    {"category", "target_trigger", "available", "visible", "modifier", "cost"}
)


def detect_loc_file(mod_root, raw_text):
    """Guess the localisation .yml matching an imported focus-tree file.

    Looks for a country tag in ``raw_text`` (the first ``TAG_something``
    identifier) and checks a few conventional filenames under
    ``mod_root/localisation/english/``. Returns the matched path, or ``""``
    if no mod root, no tag, or no matching file was found.
    """
    if not mod_root:
        return ""
    tag_m = re.search(r"\b([A-Z]{2,4})_[A-Za-z]", raw_text)
    if not tag_m:
        return ""
    tag = tag_m.group(1)
    candidates = (
        f"MD_focus_{tag}_l_english.yml",
        f"{tag}_focus_l_english.yml",
        f"{tag}_focuses_l_english.yml",
    )
    loc_dir = os.path.join(mod_root, "localisation", "english")
    if not os.path.isdir(loc_dir):
        return ""
    for cand in candidates:
        cand_path = os.path.join(loc_dir, cand)
        if os.path.isfile(cand_path):
            return cand_path
    return ""


class ModContext:
    """Holds all discovered mod assets: sprites, events, ideas, decisions, etc."""

    def __init__(self):
        self.root = None  # mod root path
        self.sprites = {}  # gfx_name -> abs_path  (all spriteTypes)
        self.sprite_imgs = LRUCache(_SPRITE_IMG_CACHE_SIZE)  # gfx_name -> PhotoImage
        self.focus_ids = []  # all focus IDs across national_focus/
        self.event_ids = {}  # file_stem -> [id, ...]
        self.idea_ids = []  # all idea/spirit IDs
        self.decision_ids = []  # all decision IDs
        self.decision_cats = []  # all decision category IDs
        self.dyn_mod_ids = []  # common/dynamic_modifiers/*
        self.country_tags = []  # TAG list
        self.variables = set()  # known variable names from set_variable/add_to_variable
        self.loaded = False
        self.use_cache = True  # SQLite per-file scan cache (disable in tests)
        self._cache = None  # active ScanCache during a scan(), else None
        self.sidebar_refresh_skip = True  # skip rebuild when sidebar data unchanged
        self.is_md = False  # True when Millennium Dawn is detected
        self.mod_name = ""  # basename of mod root
        self._status = ""
        self._img_errors = []  # list of error strings for debugging

        # Extra asset stores
        self.idea_sprites = {}  # gfx_name -> abs_path  (ideas GFX)
        self.decision_sprites = {}  # gfx_name -> abs_path  (decisions GFX)
        self.custom_gfx_dirs = []  # user-added extra GFX dirs
        self.graphics_catalog = GraphicsCatalog()
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
        ("sidebar_refresh_skip", "sidebar_refresh_skip", True),
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
        # Pending graphics-snapshot patches (note_file_written / _deleted) are
        # persisted here and at the next mod refresh, not on every write.
        self.graphics_catalog.flush_cache()

    # ── HOI4 script tokeniser (same as main parser) ─────────────────
    @staticmethod
    def _tokenize(s):
        return tokenize(s)

    @staticmethod
    def _parse_block(tokens, pos):
        return parse_block(tokens, pos)

    def _read(self, path):
        return read_file(path)

    @staticmethod
    def _txt_paths(directory):
        """Sorted absolute paths of ``*.txt`` files directly in *directory*."""
        return [
            os.path.join(directory, f)
            for f in sorted(os.listdir(directory))
            if f.endswith(".txt")
        ]

    def _scan_files_cached(self, domain, paths, extract_fn):
        """Read & extract each file, serving unchanged files from the scan cache.

        *extract_fn* maps file text to a JSON-serialisable contribution. Files
        whose ``(mtime, size)`` matches the cache are not re-read; the rest
        have their read+extract submitted together to one thread pool, so a
        file's read (which releases the GIL on disk access) overlaps another
        file's extraction instead of running as two fully serial passes.
        Cache put/prune/commit stay on this (the calling) thread since
        ScanCache's sqlite connection isn't thread-safe. A single file is
        handled inline, without pool overhead. Returns an ordered
        ``{path: contribution}`` following *paths*.
        """
        contrib = {}
        sigs = {}
        to_read = []
        for p in paths:
            try:
                st = os.stat(p)
                sig = (st.st_mtime, st.st_size)
            except OSError:
                sig = (0.0, 0)
            sigs[p] = sig
        if self._cache:
            contrib.update(self._cache.get_many(domain, sigs))
        to_read = [p for p in paths if p not in contrib]

        def read_and_extract(p):
            return extract_fn(self._read(p))

        if len(to_read) == 1:
            contrib[to_read[0]] = read_and_extract(to_read[0])
        elif to_read:
            workers = min(8, (os.cpu_count() or 4), len(to_read))
            with DaemonThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="hoi4cm-scan"
            ) as ex:
                futures = [ex.submit(read_and_extract, p) for p in to_read]
                for p, fut in zip(to_read, futures, strict=True):
                    contrib[p] = fut.result()

        if self._cache:
            self._cache.put_many(
                domain,
                [(p, sigs[p][0], sigs[p][1], contrib[p]) for p in to_read],
            )
            self._cache.prune(domain, paths)
            self._cache.commit()

        return {p: contrib[p] for p in paths}

    @staticmethod
    def _parse_text(src):
        """Parse a HOI4 script string into a dict tree."""
        try:
            return parse_script(src)
        except ValueError, TypeError, RuntimeError, OSError:
            return {}

    def _parse_file(self, path):
        """Parse a HOI4 script file into a dict tree."""
        try:
            return self._parse_text(self._read(path))
        except OSError, ValueError, TypeError, RuntimeError:
            return {}

    # ── Scanners ─────────────────────────────────────────────────────
    def _scan_gfx_unified(self):
        self.decision_sprites.clear()
        self.idea_sprites.clear()
        maps = self.graphics_catalog.refresh(
            self.root,
            GraphicsScanConfig(
                path_goals=self.path_goals,
                path_ideas_gfx=self.path_ideas_gfx,
                path_event_pictures=self.path_event_pictures,
                custom_gfx_dirs=tuple(self.custom_gfx_dirs),
            ),
            read_text=self._read,
        )
        self.sprites.update(maps.sprites)
        self.idea_sprites.update(maps.idea_sprites)
        self.decision_sprites.update(maps.decision_sprites)

    def note_file_written(self, path):
        maps = self.graphics_catalog.note_written(path, read_text=self._read)
        if maps is not None:
            self._apply_graphics_maps(maps)

    def note_file_deleted(self, path):
        maps = self.graphics_catalog.note_deleted(path)
        if maps is not None:
            self._apply_graphics_maps(maps)

    def _apply_graphics_maps(self, maps):
        for target, source, removed in (
            (self.sprites, maps.sprites, maps.removed_sprites),
            (self.idea_sprites, maps.idea_sprites, maps.removed_idea_sprites),
            (
                self.decision_sprites,
                maps.decision_sprites,
                maps.removed_decision_sprites,
            ),
        ):
            for name in removed:
                target.pop(name, None)
            target.update(source)
        # Incremental maps name only the sprites whose backing file changed;
        # evict just those decoded images instead of flushing the whole LRU.
        changed = set(maps.sprites)
        changed.update(maps.removed_sprites)
        changed.update(maps.removed_idea_sprites)
        changed.update(maps.removed_decision_sprites)
        if changed:
            self.sprite_imgs.evict(lambda key: key[0] in changed)

    # ── Per-file extractors (pure text → JSON-serialisable contribution) ──
    @staticmethod
    def _extract_national_focus(src):
        return {
            "focus_ids": [m.group(1).strip() for m in _ID_RE.finditer(src)],
            "variables": [m.group(1) for m in _VARIABLE_RE.finditer(src)],
        }

    @staticmethod
    def _extract_events(src):
        ids = []
        for m in _ID_RE.finditer(src):
            eid = m.group(1).strip()
            if _EVENT_ID_RE.match(eid) or _NUM_ID_RE.match(eid):
                ids.append(eid)
        return ids

    @staticmethod
    def _extract_ideas(src):
        out = []
        ideas_block = ModContext._parse_text(src).get("ideas", {})
        if isinstance(ideas_block, dict):
            for _cat, cat_block in ideas_block.items():
                if isinstance(cat_block, dict):
                    for idea_id in cat_block:
                        if not idea_id.startswith("_"):
                            out.append(idea_id)
        return out

    @staticmethod
    def _extract_decision_ids(src):
        return [
            m.group(1)
            for m in _BLOCK_RE.finditer(src)
            if m.group(1) not in _DECISION_KEYWORDS
        ]

    @staticmethod
    def _extract_block_names(src):
        return [m.group(1) for m in _BLOCK_RE.finditer(src)]

    @staticmethod
    def _extract_tags(src):
        return [m.group(1) for m in _TAG_RE.finditer(src)]

    # ── Directory scanners (aggregate per-file contributions) ────────────
    def _scan_national_focus(self):
        """Scan common/national_focus/ once for focus IDs *and* variable names.

        Both used to walk this directory separately, reading every file twice.
        """
        d = os.path.join(self.root, "common", "national_focus")
        if not os.path.isdir(d):
            return
        paths = self._txt_paths(d)
        results = self._scan_files_cached("focus", paths, self._extract_national_focus)
        focus_seen = dict.fromkeys(self.focus_ids)
        for p in paths:
            contrib = results[p]
            for fid in contrib["focus_ids"]:
                focus_seen[fid] = None
            self.variables.update(contrib["variables"])
        self.focus_ids = list(focus_seen)

    def _scan_events(self):
        d = os.path.join(self.root, "events")
        if not os.path.isdir(d):
            return
        paths = self._txt_paths(d)
        results = self._scan_files_cached("events", paths, self._extract_events)
        for p in paths:
            ids = results[p]
            if ids:
                self.event_ids[os.path.basename(p)[:-4]] = ids

    def _scan_ideas(self):
        d = os.path.join(self.root, "common", "ideas")
        if not os.path.isdir(d):
            return
        paths = self._txt_paths(d)
        results = self._scan_files_cached("ideas", paths, self._extract_ideas)
        seen = dict.fromkeys(self.idea_ids)
        for p in paths:
            for idea_id in results[p]:
                seen[idea_id] = None
        self.idea_ids = list(seen)

    def _scan_decisions(self):
        # Gather all candidate files per domain first; a single cache call per
        # domain keeps prune() from dropping the other directory's rows.
        dec_paths = []
        cat_paths = []
        for sub in ("decisions", "common/decisions"):
            d = os.path.join(self.root, sub.replace("/", os.sep))
            if not os.path.isdir(d):
                continue
            dec_paths.extend(self._txt_paths(d))
            cats_d = os.path.join(d, "categories")
            if os.path.isdir(cats_d):
                cat_paths.extend(self._txt_paths(cats_d))
        dec_res = self._scan_files_cached(
            "decisions", dec_paths, self._extract_decision_ids
        )
        cat_res = self._scan_files_cached(
            "decision_cats", cat_paths, self._extract_block_names
        )
        ids_seen = dict.fromkeys(self.decision_ids)
        for p in dec_paths:
            for did in dec_res[p]:
                ids_seen[did] = None
        cats_seen = dict.fromkeys(self.decision_cats)
        for p in cat_paths:
            for cid in cat_res[p]:
                cats_seen[cid] = None
        self.decision_ids = list(ids_seen)
        self.decision_cats = list(cats_seen)

    def _scan_dyn_mods(self):
        d = os.path.join(self.root, "common", "dynamic_modifiers")
        if not os.path.isdir(d):
            return
        paths = self._txt_paths(d)
        results = self._scan_files_cached("dyn_mods", paths, self._extract_block_names)
        seen = dict.fromkeys(self.dyn_mod_ids)
        for p in paths:
            for mid in results[p]:
                seen[mid] = None
        self.dyn_mod_ids = list(seen)

    def _scan_tags(self):
        d = os.path.join(self.root, "common", "country_tags")
        if not os.path.isdir(d):
            return
        paths = self._txt_paths(d)
        results = self._scan_files_cached("tags", paths, self._extract_tags)
        seen = dict.fromkeys(self.country_tags)
        for p in paths:
            for tag in results[p]:
                seen[tag] = None
        self.country_tags = list(seen)

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
            except (OSError, ValueError, RuntimeError, AttributeError) as exc:
                last_err = f"{os.path.basename(try_path)}: {exc}"

        self.sprite_imgs[key] = None
        self._img_errors.append(f"LOAD FAILED {gfx_name}: {last_err}")
        return None

    def scan(self, root, progress_cb: Callable | None = None):
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
            ("GFX (sprites/ideas/decisions)", self._scan_gfx_unified),
            ("Focus IDs", self._scan_national_focus),
            ("Events", self._scan_events),
            ("Ideas/Spirits", self._scan_ideas),
            ("Decisions", self._scan_decisions),
            ("Dynamic Modifiers", self._scan_dyn_mods),
            ("Country Tags", self._scan_tags),
            ("MD Money System", self._scan_md_money_files),
        ]
        self._cache = ScanCache(root) if self.use_cache else None
        try:
            for i, (label, fn) in enumerate(steps):
                if progress_cb:
                    progress_cb(i, len(steps), label)
                t0 = time.perf_counter()
                try:
                    fn()
                except (OSError, ValueError, RuntimeError, TypeError) as exc:
                    _log.warning("scan step %s failed: %s", label, exc, exc_info=True)
                _log.debug(
                    "scan step %s: %.1fms", label, (time.perf_counter() - t0) * 1000
                )
        finally:
            if self._cache:
                self._cache.close()
                self._cache = None

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


__all__ = ["ModContext", "detect_loc_file"]
