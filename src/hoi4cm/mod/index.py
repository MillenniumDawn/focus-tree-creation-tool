"""Pure mod-asset index. No Tk objects and no user-config writes.

A worker may scan a candidate index. It must not receive the App image cache
or the live settings object. Pass a :class:`ScanSettings` snapshot instead.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from hoi4cm.core.concurrency import DaemonThreadPoolExecutor
from hoi4cm.core.logger import get_logger
from hoi4cm.core.paths import read_file
from hoi4cm.mod.context import find_loc_files
from hoi4cm.mod.graphics_catalog import (
    GraphicsCatalog,
    GraphicsScanConfig,
    ScanCancelled,
)
from hoi4cm.mod.scan_cache import ScanCache
from hoi4cm.script.syntax import parse_script

_log = get_logger("mod")

_ID_RE = re.compile(r"\bid\s*=\s*(\S+)")
_EVENT_ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\.\d+")
_NUM_ID_RE = re.compile(r"\d+")
_BLOCK_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]+)\s*=\s*\{", re.MULTILINE)
_TAG_RE = re.compile(r"^([A-Z]{2,3})\s*=", re.MULTILINE)
_VARIABLE_RE = re.compile(
    r"(?:set_variable|add_to_variable)\s*=\s*\{\s*([A-Za-z][A-Za-z0-9_]*)\s*="
)
_DECISION_KEYWORDS = frozenset(
    {"category", "target_trigger", "available", "visible", "modifier", "cost"}
)

# Fields ``scan()`` rebinds (scalars) or refills (containers). ``adopt_scan``
# moves both groups onto the loaded index and leaves edit targets alone.
_SCAN_SCALARS = (
    "root",
    "mod_name",
    "loaded",
    "is_md",
    "md_money_system_file",
    "md_money_scripted_loc_file",
    "md_money_yml_file",
)
_SCAN_CONTAINERS = (
    "sprites",
    "idea_sprites",
    "decision_sprites",
    "focus_ids",
    "event_ids",
    "idea_ids",
    "decision_ids",
    "decision_cats",
    "scripted_effect_ids",
    "scripted_trigger_ids",
    "on_action_ids",
    "dyn_mod_ids",
    "character_ids",
    "country_tags",
    "variables",
    "failed_steps",
    "unparsable_files",
)


@dataclass(frozen=True)
class ScanSettings:
    """Inputs copied before a scan so the worker does not share live settings."""

    path_goals: str = os.path.join("gfx", "interface", "goals")
    path_ideas_gfx: str = os.path.join("gfx", "interface", "ideas")
    path_event_pictures: str = os.path.join("gfx", "event_pictures")
    custom_gfx_dirs: tuple[str, ...] = ()
    md_mode_override: bool | None = None
    loc_language: str = "english"
    use_cache: bool = True


class ModIndex:
    """Discovered mod assets: sprites, events, ideas, decisions, and tags."""

    def __init__(self) -> None:
        self.root: str | None = None
        self.sprites: dict[str, str] = {}
        self.focus_ids: list[str] = []
        self.event_ids: dict[str, list[str]] = {}
        self.idea_ids: list[str] = []
        self.decision_ids: list[str] = []
        self.decision_cats: list[str] = []
        self.scripted_effect_ids: list[str] = []
        self.scripted_trigger_ids: list[str] = []
        self.on_action_ids: list[str] = []
        self.dyn_mod_ids: list[str] = []
        self.character_ids: list[str] = []
        self.country_tags: list[str] = []
        self.variables: set[str] = set()
        self.loaded = False
        self.use_cache = True
        self._cache: ScanCache | None = None
        self.is_md = False
        self.mod_name = ""
        self.failed_steps: list[str] = []
        self.unparsable_files: list[str] = []
        self.idea_sprites: dict[str, str] = {}
        self.decision_sprites: dict[str, str] = {}
        self.graphics_catalog = GraphicsCatalog()
        self.md_money_system_file = ""
        self.md_money_scripted_loc_file = ""
        self.md_money_yml_file = ""
        self._settings: ScanSettings | None = None

    def _scan_settings(self) -> ScanSettings:
        if self._settings is None:
            return ScanSettings(use_cache=self.use_cache)
        return replace(self._settings, use_cache=self.use_cache)

    def _read(self, path):
        return read_file(path)

    @staticmethod
    def _txt_paths(directory):
        """Sorted absolute paths of ``*.txt`` files directly in *directory*."""
        names = os.listdir(directory)
        return [
            os.path.join(directory, name)
            for name in sorted(names)
            if name.endswith(".txt")
        ]

    def _scan_files_cached(self, domain, paths, extract_fn):
        """Read and extract each file, serving unchanged files from the cache."""
        contrib = {}
        sigs = {}
        for path in paths:
            try:
                stat = os.stat(path)
                sig = (stat.st_mtime, stat.st_size)
            except OSError:
                sig = (0.0, 0)
            sigs[path] = sig
        if self._cache:
            contrib.update(self._cache.get_many(domain, sigs))
        to_read = [path for path in paths if path not in contrib]
        unparsable = []

        def read_and_extract(path):
            src = self._read(path)
            if src is None:
                return False, extract_fn("")
            try:
                return True, extract_fn(src)
            except (ValueError, TypeError, RuntimeError, OSError) as exc:
                _log.warning("could not parse %s: %s", path, exc)
                unparsable.append(path)
                return False, extract_fn("")

        successful_reads = []
        if len(to_read) == 1:
            path = to_read[0]
            readable, contribution = read_and_extract(path)
            contrib[path] = contribution
            if readable:
                successful_reads.append(path)
        elif to_read:
            workers = min(8, (os.cpu_count() or 4), len(to_read))
            with DaemonThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="hoi4cm-scan"
            ) as executor:
                futures = [executor.submit(read_and_extract, path) for path in to_read]
                for path, future in zip(to_read, futures, strict=True):
                    readable, contribution = future.result()
                    contrib[path] = contribution
                    if readable:
                        successful_reads.append(path)

        self.unparsable_files.extend(sorted(unparsable))
        if self._cache:
            self._cache.put_many(
                domain,
                [
                    (path, sigs[path][0], sigs[path][1], contrib[path])
                    for path in successful_reads
                ],
            )
            self._cache.prune(domain, paths)
            self._cache.commit()
        return {path: contrib[path] for path in paths}

    @staticmethod
    def _parse_text(src):
        """Parse a HOI4 script string into a dict tree."""
        return parse_script(src)

    def _scan_gfx_unified(self, cancelled: threading.Event | None = None):
        self.decision_sprites.clear()
        self.idea_sprites.clear()
        root = self.root
        if not root:
            return
        settings = self._scan_settings()
        maps = self.graphics_catalog.refresh(
            root,
            GraphicsScanConfig(
                path_goals=settings.path_goals,
                path_ideas_gfx=settings.path_ideas_gfx,
                path_event_pictures=settings.path_event_pictures,
                custom_gfx_dirs=settings.custom_gfx_dirs,
            ),
            read_text=self._read,
            cancelled=cancelled,
        )
        self.sprites.update(maps.sprites)
        self.idea_sprites.update(maps.idea_sprites)
        self.decision_sprites.update(maps.decision_sprites)

    def note_file_written(self, path) -> set[str]:
        """Update the catalog and return sprite names whose images are stale."""
        maps = self.graphics_catalog.note_written(path, read_text=self._read)
        if maps is None:
            return set()
        return self._apply_graphics_maps(maps)

    def note_file_deleted(self, path) -> set[str]:
        """Update the catalog and return sprite names whose images are stale."""
        maps = self.graphics_catalog.note_deleted(path)
        if maps is None:
            return set()
        return self._apply_graphics_maps(maps)

    def _apply_graphics_maps(self, maps) -> set[str]:
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
        changed = set(maps.sprites)
        changed.update(maps.removed_sprites)
        changed.update(maps.removed_idea_sprites)
        changed.update(maps.removed_decision_sprites)
        return changed

    @staticmethod
    def _extract_national_focus(src):
        return {
            "focus_ids": [match.group(1).strip() for match in _ID_RE.finditer(src)],
            "variables": [match.group(1) for match in _VARIABLE_RE.finditer(src)],
        }

    @staticmethod
    def _extract_events(src):
        ids = []
        for match in _ID_RE.finditer(src):
            event_id = match.group(1).strip()
            if _EVENT_ID_RE.match(event_id) or _NUM_ID_RE.match(event_id):
                ids.append(event_id)
        return ids

    @staticmethod
    def _extract_ideas(src):
        out = []
        ideas_block = ModIndex._parse_text(src).get("ideas", {})
        if isinstance(ideas_block, dict):
            for _category, cat_block in ideas_block.items():
                if isinstance(cat_block, dict):
                    for idea_id in cat_block:
                        if not idea_id.startswith("_"):
                            out.append(idea_id)
        return out

    @staticmethod
    def _extract_characters(src):
        characters = ModIndex._parse_text(src).get("characters", {})
        if isinstance(characters, dict):
            blocks = (characters,)
        elif isinstance(characters, list):
            blocks = characters
        else:
            blocks = ()
        return [
            character_id
            for block in blocks
            if isinstance(block, dict)
            for character_id in block
            if isinstance(character_id, str) and not character_id.startswith("_")
        ]

    @staticmethod
    def _extract_decision_ids(src):
        return [
            match.group(1)
            for match in _BLOCK_RE.finditer(src)
            if match.group(1) not in _DECISION_KEYWORDS
        ]

    @staticmethod
    def _extract_block_names(src):
        return [match.group(1) for match in _BLOCK_RE.finditer(src)]

    @staticmethod
    def _block_names(parsed):
        return [
            name
            for name, value in parsed.items()
            if isinstance(name, str)
            and name != "_values"
            and isinstance(value, (dict, list))
        ]

    @staticmethod
    def _extract_scripted_names(src):
        return ModIndex._block_names(ModIndex._parse_text(src))

    @staticmethod
    def _extract_on_actions(src):
        parsed = ModIndex._parse_text(src)
        if "on_actions" not in parsed:
            return ModIndex._block_names(parsed)
        blocks = parsed["on_actions"]
        if isinstance(blocks, dict):
            blocks = (blocks,)
        elif isinstance(blocks, list):
            blocks = tuple(block for block in blocks if isinstance(block, dict))
        else:
            blocks = ()
        return [name for block in blocks for name in ModIndex._block_names(block)]

    @staticmethod
    def _extract_tags(src):
        return [match.group(1) for match in _TAG_RE.finditer(src)]

    def _scan_national_focus(self):
        """Scan common/national_focus/ once for focus IDs and variable names."""
        root = self.root
        if not root:
            return
        directory = os.path.join(root, "common", "national_focus")
        if not os.path.isdir(directory):
            return
        paths = self._txt_paths(directory)
        results = self._scan_files_cached("focus", paths, self._extract_national_focus)
        focus_seen = dict.fromkeys(self.focus_ids)
        for path in paths:
            contrib = results[path]
            for focus_id in contrib["focus_ids"]:
                focus_seen[focus_id] = None
            self.variables.update(contrib["variables"])
        self.focus_ids = list(focus_seen)

    def _scan_events(self):
        root = self.root
        if not root:
            return
        directory = os.path.join(root, "events")
        if not os.path.isdir(directory):
            return
        paths = self._txt_paths(directory)
        results = self._scan_files_cached("events", paths, self._extract_events)
        for path in paths:
            ids = results[path]
            if ids:
                self.event_ids[os.path.basename(path)[:-4]] = ids

    def _scan_id_list(self, attr, domain, extract_fn, *subdir):
        """Fill list *attr* with de-duplicated IDs from ``root/<subdir>/*.txt``."""
        root = self.root
        if not root:
            return
        directory = os.path.join(root, *subdir)
        if not os.path.isdir(directory):
            return
        paths = self._txt_paths(directory)
        results = self._scan_files_cached(domain, paths, extract_fn)
        seen = dict.fromkeys(item for path in paths for item in results[path])
        setattr(self, attr, list(seen))

    def _scan_ideas(self):
        self._scan_id_list("idea_ids", "ideas", self._extract_ideas, "common", "ideas")

    def _scan_characters(self):
        self._scan_id_list(
            "character_ids",
            "characters",
            self._extract_characters,
            "common",
            "characters",
        )

    def _scan_decisions(self):
        root = self.root
        if not root:
            return
        dec_paths = []
        cat_paths = []
        for sub in ("decisions", "common/decisions"):
            directory = os.path.join(root, sub.replace("/", os.sep))
            if not os.path.isdir(directory):
                continue
            dec_paths.extend(self._txt_paths(directory))
            cats_dir = os.path.join(directory, "categories")
            if os.path.isdir(cats_dir):
                cat_paths.extend(self._txt_paths(cats_dir))
        dec_res = self._scan_files_cached(
            "decisions", dec_paths, self._extract_decision_ids
        )
        cat_res = self._scan_files_cached(
            "decision_cats", cat_paths, self._extract_block_names
        )
        ids_seen = dict.fromkeys(self.decision_ids)
        for path in dec_paths:
            for decision_id in dec_res[path]:
                ids_seen[decision_id] = None
        cats_seen = dict.fromkeys(self.decision_cats)
        for path in cat_paths:
            for category_id in cat_res[path]:
                cats_seen[category_id] = None
        self.decision_ids = list(ids_seen)
        self.decision_cats = list(cats_seen)

    def _scan_scripted_effects(self):
        self._scan_id_list(
            "scripted_effect_ids",
            "scripted_effects",
            self._extract_scripted_names,
            "common",
            "scripted_effects",
        )

    def _scan_scripted_triggers(self):
        self._scan_id_list(
            "scripted_trigger_ids",
            "scripted_triggers",
            self._extract_scripted_names,
            "common",
            "scripted_triggers",
        )

    def _scan_on_actions(self):
        self._scan_id_list(
            "on_action_ids",
            "on_actions",
            self._extract_on_actions,
            "common",
            "on_actions",
        )

    def _scan_dyn_mods(self):
        self._scan_id_list(
            "dyn_mod_ids",
            "dyn_mods",
            self._extract_block_names,
            "common",
            "dynamic_modifiers",
        )

    def _scan_tags(self):
        self._scan_id_list(
            "country_tags", "tags", self._extract_tags, "common", "country_tags"
        )

    def _scan_md_money_files(self):
        """Auto-discover the three MD additional income system files."""
        if not self.root or not self.is_md:
            self.md_money_system_file = ""
            self.md_money_scripted_loc_file = ""
            self.md_money_yml_file = ""
            return
        from hoi4cm.focus_tree.loc import LocTarget

        root = self.root
        money_path = os.path.join(
            root, "common", "scripted_effects", "00_money_system.txt"
        )
        self.md_money_system_file = money_path if os.path.isfile(money_path) else ""
        sloc_dir = os.path.join(root, "common", "scripted_localisation")
        self.md_money_scripted_loc_file = ""
        if os.path.isdir(sloc_dir):
            try:
                names = os.listdir(sloc_dir)
            except OSError:
                names = []
            for name in names:
                if "money" in name.lower() and name.endswith(".txt"):
                    self.md_money_scripted_loc_file = os.path.join(sloc_dir, name)
                    break
        target = LocTarget(self._scan_settings().loc_language)
        yml = os.path.join(
            root, "localisation", target.dirname(), target.filename("MD_money")
        )
        if os.path.isfile(yml):
            self.md_money_yml_file = yml
            return
        target_name = target.filename("MD_money").casefold()
        self.md_money_yml_file = next(
            (
                path
                for path in find_loc_files(root, language=target.language)
                if os.path.basename(path).casefold() == target_name
            ),
            "",
        )

    def rescan_md_money(self, loc_language: str) -> None:
        """Rediscover MD money files after a settings change on the Tk thread."""
        self._settings = replace(self._scan_settings(), loc_language=loc_language)
        self._scan_md_money_files()

    def new_scan_candidate(self, settings: ScanSettings | None = None) -> ModIndex:
        """Return an empty index that continues this catalog's generation."""
        candidate = ModIndex()
        if settings is None:
            settings = ScanSettings(use_cache=self.use_cache)
        candidate.use_cache = settings.use_cache
        candidate._settings = settings
        candidate.graphics_catalog.generation = self.graphics_catalog.generation
        return candidate

    def adopt_scan(self, candidate: ModIndex) -> None:
        """Adopt a completed candidate. Does not touch any image cache."""
        if candidate is self or not candidate.loaded or not candidate.root:
            raise ValueError("cannot adopt an incomplete mod scan")
        for name in _SCAN_SCALARS + _SCAN_CONTAINERS:
            setattr(self, name, getattr(candidate, name))
        self.graphics_catalog = candidate.graphics_catalog
        self._settings = candidate._settings
        self.use_cache = candidate.use_cache

    def scan(
        self,
        root,
        settings: ScanSettings | None = None,
        progress_cb: Callable | None = None,
        *,
        cancelled: threading.Event | None = None,
    ):
        """Scan *root* in place. Return True, or None when cancelled.

        Callers that load a mod should scan a :meth:`new_scan_candidate` and
        adopt it on the Tk thread. A cancelled scan leaves ``loaded`` false.
        """
        if cancelled is not None and cancelled.is_set():
            return None
        if settings is None:
            settings = self._scan_settings()
        self._settings = settings
        self.use_cache = settings.use_cache
        self.root = root
        self.mod_name = os.path.basename(root)
        self.sprites.clear()
        self.failed_steps.clear()
        self.unparsable_files.clear()
        self.decision_sprites.clear()
        self.focus_ids.clear()
        self.event_ids.clear()
        self.idea_ids.clear()
        self.decision_ids.clear()
        self.decision_cats.clear()
        self.scripted_effect_ids.clear()
        self.scripted_trigger_ids.clear()
        self.on_action_ids.clear()
        self.dyn_mod_ids.clear()
        self.character_ids.clear()
        self.country_tags.clear()
        self.variables.clear()
        self.md_money_system_file = ""
        self.md_money_scripted_loc_file = ""
        self.md_money_yml_file = ""
        self.loaded = False

        name_lower = self.mod_name.lower()
        detected = (
            "millennium" in name_lower
            or name_lower == "md"
            or "millennium_dawn" in name_lower
        )
        if not detected:
            desc_path = os.path.join(root, "descriptor.mod")
            if os.path.exists(desc_path):
                desc_txt = (self._read(desc_path) or "").lower()
                detected = "millennium" in desc_txt
        if not detected:
            detected = os.path.isfile(
                os.path.join(root, "common", "scripted_effects", "00_money_system.txt")
            )
        override = settings.md_mode_override
        self.is_md = override if isinstance(override, bool) else detected

        def gfx_step() -> None:
            self._scan_gfx_unified(cancelled)

        steps = [
            ("GFX (sprites/ideas/decisions)", gfx_step),
            ("Focus IDs", self._scan_national_focus),
            ("Events", self._scan_events),
            ("Ideas/Spirits", self._scan_ideas),
            ("Characters", self._scan_characters),
            ("Scripted Effects", self._scan_scripted_effects),
            ("Scripted Triggers", self._scan_scripted_triggers),
            ("On Actions", self._scan_on_actions),
            ("Decisions", self._scan_decisions),
            ("Dynamic Modifiers", self._scan_dyn_mods),
            ("Country Tags", self._scan_tags),
        ]
        if self.is_md:
            steps.append(("MD Money System", self._scan_md_money_files))
        self._cache = ScanCache(root) if self.use_cache else None
        try:
            for index, (label, fn) in enumerate(steps):
                if cancelled is not None and cancelled.is_set():
                    return None
                if progress_cb:
                    progress_cb(index, len(steps), label)
                started = time.perf_counter()
                try:
                    fn()
                except ScanCancelled:
                    return None
                except (OSError, ValueError, RuntimeError, TypeError) as exc:
                    _log.warning("scan step %s failed: %s", label, exc, exc_info=True)
                    self.failed_steps.append(label)
                _log.debug(
                    "scan step %s: %.1fms",
                    label,
                    (time.perf_counter() - started) * 1000,
                )
        finally:
            if self._cache:
                self._cache.close()
                self._cache = None

        if cancelled is not None and cancelled.is_set():
            return None
        self.loaded = True
        if progress_cb:
            progress_cb(len(steps), len(steps), "Done")
        return True

    def summary(self):
        md_badge = "  [MD]" if self.is_md else ""
        return (
            f"{len(self.sprites)} focus sprites  •  "
            f"{len(self.idea_sprites)} idea sprites  •  "
            f"{len(self.decision_sprites)} decision sprites  •  "
            f"{len(self.focus_ids)} focus IDs  •  {len(self.idea_ids)} ideas  •  "
            f"{len(self.dyn_mod_ids)} dyn modifiers  •  "
            f"{len(self.country_tags)} tags{md_badge}"
        )


__all__ = ["ModIndex", "ScanSettings"]
