from __future__ import annotations

import hashlib
import json
import os
import re
import stat as stat_module
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from hoi4cm.mod import scan_cache
from hoi4cm.mod.workspace_cache import WorkspaceCache

_CACHE_VERSION = 1
_IMAGE_EXTENSIONS = (".dds", ".png", ".tga")
# Pre-catalog builds dropped this JSON sidecar in the mod root. The SQLite
# scan cache replaced it; clean the stray file up so it stops confusing users.
_LEGACY_SIDECAR_NAME = ".hoi4cm_gfx_cache.json"
_SPRITE_BLOCK_RE = re.compile(r"spriteType\s*=\s*\{")
_SPRITE_NAME_RE = re.compile(r'\bname\s*=\s*"([^"]+)"')
_SPRITE_TEXTURE_RE = re.compile(r'\btexturefile\s*=\s*"([^"]+)"')


@dataclass(frozen=True)
class FileStamp:
    mtime_ns: int
    ctime_ns: int
    size: int


@dataclass(frozen=True)
class PathReference:
    source_id: str
    relative_path: str

    def resolve(self, source_roots: Mapping[str, str]) -> str:
        if self.source_id == "absolute":
            return self.relative_path
        root = source_roots[self.source_id]
        if self.relative_path == ".":
            return root
        return os.path.join(root, self.relative_path)


@dataclass(frozen=True)
class DirectoryRecord:
    path: PathReference
    exists: bool
    stamp: FileStamp


@dataclass(frozen=True)
class ImageRecord:
    path: PathReference
    stamp: FileStamp


@dataclass(frozen=True)
class SpriteDeclaration:
    name: str
    texture_path: PathReference
    texture_path_lower: str
    top_level: bool
    strict_extension: bool


@dataclass(frozen=True)
class GfxFileRecord:
    path: PathReference
    stamp: FileStamp
    declarations: tuple[SpriteDeclaration, ...]


@dataclass(frozen=True)
class GraphicsSnapshot:
    directories: tuple[DirectoryRecord, ...]
    images: tuple[ImageRecord, ...]
    gfx_files: tuple[GfxFileRecord, ...]
    goal_images: tuple[PathReference, ...]
    idea_images: tuple[PathReference, ...]

    @property
    def cacheable(self) -> bool:
        return all(
            declaration.texture_path.source_id != "absolute"
            for gfx_file in self.gfx_files
            for declaration in gfx_file.declarations
        )

    def to_data(self) -> dict[str, object]:
        return {
            "directories": [
                {
                    "path": _path_to_data(record.path),
                    "exists": record.exists,
                    "stamp": _stamp_to_data(record.stamp),
                }
                for record in self.directories
            ],
            "images": [
                {
                    "path": _path_to_data(record.path),
                    "stamp": _stamp_to_data(record.stamp),
                }
                for record in self.images
            ],
            "gfx_files": [
                {
                    "path": _path_to_data(record.path),
                    "stamp": _stamp_to_data(record.stamp),
                    "declarations": [
                        {
                            "name": declaration.name,
                            "texture_path": _path_to_data(declaration.texture_path),
                            "texture_path_lower": declaration.texture_path_lower,
                            "top_level": declaration.top_level,
                            "strict_extension": declaration.strict_extension,
                        }
                        for declaration in record.declarations
                    ],
                }
                for record in self.gfx_files
            ],
            "goal_images": [_path_to_data(path) for path in self.goal_images],
            "idea_images": [_path_to_data(path) for path in self.idea_images],
        }

    @classmethod
    def from_data(cls, data: Mapping[str, object]) -> GraphicsSnapshot:
        directories = tuple(
            DirectoryRecord(
                path=_path_from_data(item["path"]),
                exists=_as_bool(item["exists"]),
                stamp=_stamp_from_data(item["stamp"]),
            )
            for item in _mapping_items(data.get("directories"))
        )
        images = tuple(
            ImageRecord(
                path=_path_from_data(item["path"]),
                stamp=_stamp_from_data(item["stamp"]),
            )
            for item in _mapping_items(data.get("images"))
        )
        gfx_files = []
        for item in _mapping_items(data.get("gfx_files")):
            declarations = tuple(
                SpriteDeclaration(
                    name=_as_str(declaration["name"]),
                    texture_path=_path_from_data(declaration["texture_path"]),
                    texture_path_lower=_as_str(declaration["texture_path_lower"]),
                    top_level=_as_bool(declaration["top_level"]),
                    strict_extension=_as_bool(declaration["strict_extension"]),
                )
                for declaration in _mapping_items(item.get("declarations"))
            )
            gfx_files.append(
                GfxFileRecord(
                    path=_path_from_data(item["path"]),
                    stamp=_stamp_from_data(item["stamp"]),
                    declarations=declarations,
                )
            )
        return cls(
            directories=directories,
            images=images,
            gfx_files=tuple(gfx_files),
            goal_images=tuple(
                _path_from_data(item)
                for item in _mapping_values(data.get("goal_images"))
            ),
            idea_images=tuple(
                _path_from_data(item)
                for item in _mapping_values(data.get("idea_images"))
            ),
        )


@dataclass(frozen=True)
class GraphicsScanConfig:
    path_goals: str
    path_ideas_gfx: str
    path_event_pictures: str = ""
    custom_gfx_dirs: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssetRef:
    source_id: str
    relative_path: str
    stamp: FileStamp
    generation: int


@dataclass
class GraphicsMetrics:
    cache_status: str = "miss"
    directory_listings: int = 0
    directory_stats: int = 0
    image_stats: int = 0
    gfx_file_stats: int = 0
    gfx_reads: int = 0


@dataclass
class GraphicsMaps:
    sprites: dict[str, str] = field(default_factory=dict)
    idea_sprites: dict[str, str] = field(default_factory=dict)
    decision_sprites: dict[str, str] = field(default_factory=dict)


class GraphicsCatalog:
    def __init__(self) -> None:
        self.generation = 0
        self.last_metrics = GraphicsMetrics()
        self._image_stamps: dict[PathReference, FileStamp] = {}
        self._install_snapshot(GraphicsSnapshot((), (), (), (), ()))
        self._source_roots: dict[str, str] = {}
        self._scan_roots: dict[str, str] = {}
        self._sprite_refs: dict[str, PathReference] = {}
        self._idea_refs: dict[str, PathReference] = {}
        self._decision_refs: dict[str, PathReference] = {}
        self._root = ""
        self._config = GraphicsScanConfig("", "")
        self._root_identity = ""
        self._config_fingerprint = ""

    def refresh(
        self,
        root: str,
        config: GraphicsScanConfig,
        *,
        read_text: Callable[[str], str],
    ) -> GraphicsMaps:
        self.last_metrics = GraphicsMetrics()
        root = os.path.abspath(root)
        source_roots = self._source_roots_for(root, config)
        root_identity = _root_identity(root)
        config_fingerprint = _config_fingerprint(config)
        cache = WorkspaceCache(scan_cache.database_path(root))
        cached_data = cache.load_graphics(
            schema_version=_CACHE_VERSION,
            root_identity=root_identity,
            config_fingerprint=config_fingerprint,
        )

        snapshot = self._load_snapshot(cached_data, source_roots)
        if snapshot is None:
            snapshot = self._scan_snapshot(root, config, source_roots, read_text)
            if snapshot.cacheable:
                cache.store_graphics(
                    snapshot.to_data(),
                    schema_version=_CACHE_VERSION,
                    root_identity=root_identity,
                    config_fingerprint=config_fingerprint,
                )
        else:
            self.last_metrics.cache_status = "hit"

        self.generation += 1
        self._install_snapshot(snapshot)
        self._source_roots = source_roots
        self._scan_roots = self._extra_scan_roots(root, config)
        self._root = root
        self._config = config
        self._root_identity = root_identity
        self._config_fingerprint = config_fingerprint
        self._derive_references(root, config)
        _remove_legacy_sidecar(root)
        return self._materialize_maps()

    def _install_snapshot(self, snapshot: GraphicsSnapshot) -> None:
        self._snapshot = snapshot
        self._image_stamps = {record.path: record.stamp for record in snapshot.images}

    def note_written(
        self, path: str, *, read_text: Callable[[str], str]
    ) -> GraphicsMaps | None:
        if not self._root:
            return None
        absolute_path = os.path.abspath(path)
        reference = self._reference_for_path(absolute_path)
        if reference is None:
            return None
        suffix = os.path.splitext(absolute_path)[1]
        suffix_lower = suffix.lower()
        if suffix_lower not in _IMAGE_EXTENSIONS and suffix_lower != ".gfx":
            return None
        try:
            path_stat = os.stat(absolute_path)
        except OSError:
            return self.note_deleted(absolute_path)

        images = list(self._snapshot.images)
        gfx_files = list(self._snapshot.gfx_files)
        if suffix_lower in _IMAGE_EXTENSIONS:
            images = _replace_or_append(
                images, ImageRecord(reference, _stamp_from_stat(path_stat))
            )
        elif self._is_interface_file(absolute_path):
            interface_root = os.path.join(self._root, "interface")
            gfx_files = _replace_or_append(
                gfx_files,
                GfxFileRecord(
                    reference,
                    _stamp_from_stat(path_stat),
                    tuple(
                        _parse_declarations(
                            read_text(absolute_path),
                            top_level=os.path.normcase(os.path.dirname(absolute_path))
                            == os.path.normcase(interface_root),
                            strict_extension=os.path.basename(absolute_path).endswith(
                                ".gfx"
                            ),
                        )
                    ),
                ),
            )
        else:
            return None
        return self._replace_snapshot(absolute_path, images, gfx_files)

    def note_deleted(self, path: str) -> GraphicsMaps | None:
        if not self._root:
            return None
        absolute_path = os.path.abspath(path)
        reference = self._reference_for_path(absolute_path)
        if reference is None:
            return None
        images = [
            record for record in self._snapshot.images if record.path != reference
        ]
        gfx_files = [
            record for record in self._snapshot.gfx_files if record.path != reference
        ]
        if len(images) == len(self._snapshot.images) and len(gfx_files) == len(
            self._snapshot.gfx_files
        ):
            return None
        return self._replace_snapshot(absolute_path, images, gfx_files)

    def resolve(self, gfx_name: str, *, family: str = "sprites") -> AssetRef | None:
        references = {
            "sprites": self._sprite_refs,
            "ideas": self._idea_refs,
            "decisions": self._decision_refs,
        }.get(family)
        if references is None:
            raise ValueError(f"unknown graphics family: {family}")
        path = references.get(gfx_name)
        if path is None:
            return None
        return AssetRef(
            source_id=path.source_id,
            relative_path=path.relative_path,
            stamp=self._stamp_for_path(path),
            generation=self.generation,
        )

    def query(
        self, *, under: str | None = None, search: str = ""
    ) -> tuple[AssetRef, ...]:
        under_path = os.path.normcase(os.path.abspath(under)) if under else None
        search_text = search.casefold().strip()
        assets: list[tuple[str, AssetRef]] = []
        seen_paths: set[str] = set()
        for record in self._snapshot.images:
            try:
                absolute_path = record.path.resolve(self._source_roots)
            except KeyError:
                continue
            normalized = os.path.normcase(os.path.abspath(absolute_path))
            if normalized in seen_paths:
                continue
            if under_path is not None and not _is_under(normalized, under_path):
                continue
            if search_text and search_text not in absolute_path.casefold():
                continue
            seen_paths.add(normalized)
            assets.append(
                (
                    absolute_path.casefold(),
                    AssetRef(
                        source_id=record.path.source_id,
                        relative_path=record.path.relative_path,
                        stamp=record.stamp,
                        generation=self.generation,
                    ),
                )
            )
        assets.sort(key=lambda item: item[0])
        return tuple(asset for _path, asset in assets)

    def path_for(self, asset: AssetRef) -> str:
        return PathReference(asset.source_id, asset.relative_path).resolve(
            self._source_roots
        )

    def _replace_snapshot(
        self,
        changed_path: str,
        images: list[ImageRecord],
        gfx_files: list[GfxFileRecord],
    ) -> GraphicsMaps:
        directories = self._updated_directories(changed_path)
        goals_root = _configured_path(self._root, self._config.path_goals)
        if not os.path.isdir(goals_root):
            goals_root = os.path.join(self._root, "gfx", "interface")
        ideas_root = _configured_path(self._root, self._config.path_ideas_gfx)
        self.generation += 1
        self._install_snapshot(
            GraphicsSnapshot(
                directories=directories,
                images=tuple(images),
                gfx_files=tuple(gfx_files),
                goal_images=tuple(
                    record.path
                    for record in images
                    if _is_under(record.path.resolve(self._source_roots), goals_root)
                ),
                idea_images=tuple(
                    record.path
                    for record in images
                    if _is_under(record.path.resolve(self._source_roots), ideas_root)
                ),
            )
        )
        self._derive_references(self._root, self._config)
        if self._snapshot.cacheable:
            WorkspaceCache(scan_cache.database_path(self._root)).store_graphics(
                self._snapshot.to_data(),
                schema_version=_CACHE_VERSION,
                root_identity=self._root_identity,
                config_fingerprint=self._config_fingerprint,
            )
        return self._materialize_maps()

    def _updated_directories(self, changed_path: str) -> tuple[DirectoryRecord, ...]:
        records = {record.path: record for record in self._snapshot.directories}
        directory = os.path.dirname(changed_path)
        while True:
            reference = self._reference_for_path(directory)
            if reference is None:
                break
            try:
                directory_stat = os.stat(directory)
            except OSError:
                record = DirectoryRecord(reference, False, FileStamp(0, 0, 0))
            else:
                record = DirectoryRecord(
                    reference, True, _stamp_from_stat(directory_stat)
                )
            records[reference] = record
            parent = os.path.dirname(directory)
            if parent == directory:
                break
            directory = parent
        return tuple(records.values())

    def _reference_for_path(self, path: str) -> PathReference | None:
        records = (
            *(record.path for record in self._snapshot.images),
            *(record.path for record in self._snapshot.gfx_files),
            *(record.path for record in self._snapshot.directories),
        )
        matches = []
        for record in records:
            try:
                record_path = record.resolve(self._source_roots)
            except KeyError:
                continue
            if _is_under(path, record_path):
                matches.append((len(record_path), record))
        if matches:
            _length, record = max(matches, key=lambda item: item[0])
            return _reference_for(
                record.source_id, self._source_roots[record.source_id], path
            )

        candidates = sorted(
            self._scan_roots.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        )
        for source_id, source_root in candidates:
            if _is_under(path, source_root):
                return _reference_for(source_id, self._source_roots[source_id], path)
        if _is_under(path, self._root):
            return _reference_for("mod", self._root, path)
        return None

    def _stamp_for_path(self, path: PathReference) -> FileStamp:
        for candidate in _image_candidates(path):
            stamp = self._image_stamps.get(candidate)
            if stamp is not None:
                return stamp
        return FileStamp(0, 0, 0)

    def _is_interface_file(self, path: str) -> bool:
        return _is_under(path, os.path.join(self._root, "interface"))

    def _load_snapshot(
        self,
        data: Mapping[str, object] | None,
        source_roots: Mapping[str, str],
    ) -> GraphicsSnapshot | None:
        if data is None:
            return None
        try:
            snapshot = GraphicsSnapshot.from_data(data)
        except KeyError, TypeError, ValueError:
            return None
        return snapshot if self._snapshot_is_current(snapshot, source_roots) else None

    def _snapshot_is_current(
        self,
        snapshot: GraphicsSnapshot,
        source_roots: Mapping[str, str],
    ) -> bool:
        current = True
        for record in snapshot.directories:
            self.last_metrics.directory_stats += 1
            try:
                stat = os.stat(record.path.resolve(source_roots))
            except KeyError, OSError:
                if record.exists:
                    current = False
                continue
            if not record.exists or not stat_module.S_ISDIR(stat.st_mode):
                current = False
                continue
            if _stamp_from_stat(stat) != record.stamp:
                current = False

        for record in snapshot.gfx_files:
            self.last_metrics.gfx_file_stats += 1
            try:
                stat = os.stat(record.path.resolve(source_roots))
            except KeyError, OSError:
                current = False
                continue
            if _stamp_from_stat(stat) != record.stamp:
                current = False

        # Stat the known image paths too. Directory mtimes don't change when a
        # file is overwritten in place, so an image edit that keeps the same
        # name would otherwise leave a stale FileStamp — and that stamp is the
        # thumbnail cache key. Restatting is cheaper than a full rescan.
        for record in snapshot.images:
            self.last_metrics.image_stats += 1
            try:
                stat = os.stat(record.path.resolve(source_roots))
            except KeyError, OSError:
                current = False
                continue
            if _stamp_from_stat(stat) != record.stamp:
                current = False
        return current

    def _scan_snapshot(
        self,
        root: str,
        config: GraphicsScanConfig,
        source_roots: Mapping[str, str],
        read_text: Callable[[str], str],
    ) -> GraphicsSnapshot:
        directories: list[DirectoryRecord] = []
        images: list[ImageRecord] = []
        gfx_files: list[GfxFileRecord] = []
        scanned_roots: list[str] = []

        interface_root = os.path.join(root, "interface")
        gfx_root = os.path.join(root, "gfx")
        self._scan_tree(
            "mod",
            root,
            interface_root,
            read_gfx=True,
            read_text=read_text,
            directories=directories,
            images=images,
            gfx_files=gfx_files,
        )
        scanned_roots.append(interface_root)
        self._scan_tree(
            "mod",
            root,
            gfx_root,
            read_gfx=False,
            read_text=read_text,
            directories=directories,
            images=images,
            gfx_files=gfx_files,
        )
        scanned_roots.append(gfx_root)

        goals_root = _configured_path(root, config.path_goals)
        if not os.path.isdir(goals_root):
            goals_root = os.path.join(root, "gfx", "interface")
        ideas_root = _configured_path(root, config.path_ideas_gfx)
        extra_roots = [("goals", goals_root), ("ideas", ideas_root)]
        if config.path_event_pictures:
            extra_roots.append(
                ("events", _configured_path(root, config.path_event_pictures))
            )
        extra_roots.extend(
            (f"custom:{index}", os.path.abspath(path))
            for index, path in enumerate(config.custom_gfx_dirs)
        )
        for source_id, scan_root in extra_roots:
            if any(_is_under(scan_root, existing) for existing in scanned_roots):
                continue
            source_root = source_roots[source_id]
            self._scan_tree(
                source_id,
                source_root,
                scan_root,
                read_gfx=False,
                read_text=read_text,
                directories=directories,
                images=images,
                gfx_files=gfx_files,
            )
            scanned_roots.append(scan_root)

        goal_images = tuple(
            record.path
            for record in images
            if _is_under(record.path.resolve(source_roots), goals_root)
        )
        idea_images = tuple(
            record.path
            for record in images
            if _is_under(record.path.resolve(source_roots), ideas_root)
        )
        return GraphicsSnapshot(
            directories=tuple(directories),
            images=tuple(images),
            gfx_files=tuple(gfx_files),
            goal_images=goal_images,
            idea_images=idea_images,
        )

    def _scan_tree(
        self,
        source_id: str,
        source_root: str,
        scan_root: str,
        *,
        read_gfx: bool,
        read_text: Callable[[str], str],
        directories: list[DirectoryRecord],
        images: list[ImageRecord],
        gfx_files: list[GfxFileRecord],
    ) -> None:
        def scan(directory: str, *, top_level: bool) -> None:
            path_ref = _reference_for(source_id, source_root, directory)
            self.last_metrics.directory_stats += 1
            try:
                stat = os.stat(directory)
            except OSError:
                directories.append(DirectoryRecord(path_ref, False, FileStamp(0, 0, 0)))
                return
            if not os.path.isdir(directory):
                directories.append(DirectoryRecord(path_ref, False, FileStamp(0, 0, 0)))
                return

            directories.append(DirectoryRecord(path_ref, True, _stamp_from_stat(stat)))
            self.last_metrics.directory_listings += 1
            try:
                entries = list(os.scandir(directory))
            except OSError:
                return

            child_directories = []
            for entry in entries:
                try:
                    is_directory = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if is_directory:
                    child_directories.append(entry.path)
                    continue
                suffix = os.path.splitext(entry.name)[1]
                suffix_lower = suffix.lower()
                if suffix_lower in _IMAGE_EXTENSIONS:
                    self.last_metrics.image_stats += 1
                    try:
                        entry_stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    images.append(
                        ImageRecord(
                            _reference_for(source_id, source_root, entry.path),
                            _stamp_from_stat(entry_stat),
                        )
                    )
                if not read_gfx or suffix_lower != ".gfx":
                    continue
                self.last_metrics.gfx_file_stats += 1
                try:
                    entry_stat = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                self.last_metrics.gfx_reads += 1
                declarations = tuple(
                    _parse_declarations(
                        read_text(entry.path),
                        top_level=top_level,
                        strict_extension=entry.name.endswith(".gfx"),
                    )
                )
                gfx_files.append(
                    GfxFileRecord(
                        _reference_for(source_id, source_root, entry.path),
                        _stamp_from_stat(entry_stat),
                        declarations,
                    )
                )
            for child in child_directories:
                scan(child, top_level=False)

        scan(scan_root, top_level=True)

    def _derive_references(self, root: str, config: GraphicsScanConfig) -> None:
        declarations = (
            declaration
            for gfx_file in self._snapshot.gfx_files
            for declaration in gfx_file.declarations
        )
        declaration_list = tuple(declarations)
        self._sprite_refs = {}
        self._idea_refs = {}
        self._decision_refs = {}

        for declaration in declaration_list:
            if (
                declaration.top_level
                and declaration.strict_extension
                and (
                    "goals" in declaration.texture_path_lower
                    or "focus" in declaration.texture_path_lower
                )
            ):
                self._sprite_refs[declaration.name] = declaration.texture_path
            if (
                declaration.top_level
                and declaration.strict_extension
                and (
                    "ideas" in declaration.texture_path_lower
                    or "idea" in declaration.texture_path_lower
                )
            ):
                self._idea_refs[declaration.name] = declaration.texture_path
            self._decision_refs[declaration.name] = declaration.texture_path

        for path in self._snapshot.goal_images:
            stem = Path(path.relative_path).stem
            self._sprite_refs.setdefault(f"GFX_focus_{stem}", path)
        for path in self._snapshot.idea_images:
            stem = Path(path.relative_path).stem
            self._idea_refs.setdefault(f"GFX_idea_{stem}", path)
        for index in range(len(config.custom_gfx_dirs)):
            custom_root = os.path.abspath(config.custom_gfx_dirs[index])
            for record in self._snapshot.images:
                try:
                    full_path = record.path.resolve(self._source_roots)
                except KeyError:
                    continue
                if _is_under(full_path, custom_root):
                    stem = Path(record.path.relative_path).stem
                    self._idea_refs.setdefault(f"GFX_idea_{stem}", record.path)

        gfx_root = os.path.join(root, "gfx")
        for record in self._snapshot.images:
            try:
                full_path = record.path.resolve(self._source_roots)
            except KeyError:
                continue
            if not _is_under(full_path, gfx_root):
                continue
            stem = Path(record.path.relative_path).stem
            relative = os.path.relpath(full_path, root).replace(os.sep, "/").lower()
            if "decisions" in relative:
                self._decision_refs.setdefault(f"GFX_decision_{stem}", record.path)
                self._decision_refs.setdefault(
                    f"GFX_decision_category_{stem}", record.path
                )
            elif "ideas" in relative:
                self._decision_refs.setdefault(f"GFX_idea_{stem}", record.path)
            elif "goals" not in relative and "focus" not in relative:
                self._decision_refs.setdefault(f"GFX_{stem}", record.path)

    def _materialize_maps(self) -> GraphicsMaps:
        return GraphicsMaps(
            sprites={
                key: path.resolve(self._source_roots)
                for key, path in self._sprite_refs.items()
            },
            idea_sprites={
                key: path.resolve(self._source_roots)
                for key, path in self._idea_refs.items()
            },
            decision_sprites={
                key: path.resolve(self._source_roots)
                for key, path in self._decision_refs.items()
            },
        )

    @staticmethod
    def _source_roots_for(root: str, config: GraphicsScanConfig) -> dict[str, str]:
        source_roots = {"mod": root}
        goals_root = _configured_path(root, config.path_goals)
        ideas_root = _configured_path(root, config.path_ideas_gfx)
        source_roots["goals"] = root if _is_under(goals_root, root) else goals_root
        source_roots["ideas"] = root if _is_under(ideas_root, root) else ideas_root
        if config.path_event_pictures:
            events_root = _configured_path(root, config.path_event_pictures)
            source_roots["events"] = (
                root if _is_under(events_root, root) else events_root
            )
        source_roots.update(
            {
                f"custom:{index}": os.path.abspath(path)
                for index, path in enumerate(config.custom_gfx_dirs)
            }
        )
        return source_roots

    @staticmethod
    def _extra_scan_roots(root: str, config: GraphicsScanConfig) -> dict[str, str]:
        interface_root = os.path.join(root, "interface")
        gfx_root = os.path.join(root, "gfx")
        goals_root = _configured_path(root, config.path_goals)
        if not os.path.isdir(goals_root):
            goals_root = os.path.join(root, "gfx", "interface")
        roots = {
            "goals": goals_root,
            "ideas": _configured_path(root, config.path_ideas_gfx),
        }
        if config.path_event_pictures:
            roots["events"] = _configured_path(root, config.path_event_pictures)
        roots.update(
            {
                f"custom:{index}": os.path.abspath(path)
                for index, path in enumerate(config.custom_gfx_dirs)
            }
        )
        return {
            source_id: scan_root
            for source_id, scan_root in roots.items()
            if not any(
                _is_under(scan_root, existing)
                for existing in (interface_root, gfx_root)
            )
        }


def _parse_declarations(
    text: str, *, top_level: bool, strict_extension: bool
) -> Iterable[SpriteDeclaration]:
    for block in _iter_sprite_blocks(text):
        name_match = _SPRITE_NAME_RE.search(block)
        texture_match = _SPRITE_TEXTURE_RE.search(block)
        if name_match is None or texture_match is None:
            continue
        texture_raw = (
            texture_match.group(1).strip().replace("\\\\", "/").replace("\\", "/")
        )
        texture_path = texture_raw.replace("/", os.sep)
        reference = (
            PathReference("absolute", texture_path)
            if os.path.isabs(texture_path)
            else PathReference("mod", texture_path)
        )
        yield SpriteDeclaration(
            name=name_match.group(1).strip(),
            texture_path=reference,
            texture_path_lower=texture_raw.lower(),
            top_level=top_level,
            strict_extension=strict_extension,
        )


def _iter_sprite_blocks(text: str) -> Iterable[str]:
    offset = 0
    while offset < len(text):
        match = _SPRITE_BLOCK_RE.search(text, offset)
        if match is None:
            return
        depth = 1
        end = match.end()
        while end < len(text) and depth > 0:
            if text[end] == "{":
                depth += 1
            elif text[end] == "}":
                depth -= 1
            end += 1
        yield text[match.start() : end]
        offset = end


def _stamp_from_stat(stat: os.stat_result) -> FileStamp:
    return FileStamp(
        mtime_ns=stat.st_mtime_ns,
        ctime_ns=stat.st_ctime_ns,
        size=stat.st_size,
    )


def _reference_for(source_id: str, source_root: str, path: str) -> PathReference:
    relative_path = os.path.relpath(path, source_root)
    return PathReference(source_id, relative_path)


def _image_candidates(path: PathReference) -> tuple[PathReference, ...]:
    if not path.relative_path.lower().endswith(".dds"):
        return (path,)
    stem = os.path.splitext(path.relative_path)[0]
    return (
        path,
        PathReference(path.source_id, stem + ".png"),
        PathReference(path.source_id, stem + ".tga"),
    )


def _replace_or_append(records, replacement):
    for index, record in enumerate(records):
        if record.path == replacement.path:
            records[index] = replacement
            return records
    records.append(replacement)
    return records


def _configured_path(root: str, configured_path: str) -> str:
    return os.path.abspath(os.path.join(root, configured_path))


def _remove_legacy_sidecar(root: str) -> None:
    sidecar = os.path.join(root, _LEGACY_SIDECAR_NAME)
    try:
        if os.path.isfile(sidecar):
            os.remove(sidecar)
    except OSError:
        pass


def _is_under(path: str, parent: str) -> bool:
    path = os.path.normcase(os.path.abspath(path))
    parent = os.path.normcase(os.path.abspath(parent))
    try:
        return os.path.commonpath((path, parent)) == parent
    except ValueError:
        return False


def _root_identity(root: str) -> str:
    normalized = os.path.normcase(os.path.abspath(root))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _config_fingerprint(config: GraphicsScanConfig) -> str:
    payload = json.dumps(
        {
            "path_goals": config.path_goals,
            "path_ideas_gfx": config.path_ideas_gfx,
            "path_event_pictures": config.path_event_pictures,
            "custom_gfx_dirs": [
                os.path.normcase(os.path.abspath(path))
                for path in config.custom_gfx_dirs
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _path_to_data(path: PathReference) -> dict[str, object]:
    if path.source_id == "absolute" or os.path.isabs(path.relative_path):
        raise ValueError("absolute paths are not cacheable")
    return {"source_id": path.source_id, "relative_path": path.relative_path}


def _path_from_data(data: object) -> PathReference:
    item = _as_mapping(data)
    source_id = _as_str(item["source_id"])
    relative_path = _as_str(item["relative_path"])
    if source_id == "absolute" or os.path.isabs(relative_path):
        raise ValueError("cached path must be relative")
    return PathReference(source_id, relative_path)


def _stamp_to_data(stamp: FileStamp) -> dict[str, object]:
    return {
        "mtime_ns": stamp.mtime_ns,
        "ctime_ns": stamp.ctime_ns,
        "size": stamp.size,
    }


def _stamp_from_data(data: object) -> FileStamp:
    item = _as_mapping(data)
    return FileStamp(
        mtime_ns=_as_int(item["mtime_ns"]),
        ctime_ns=_as_int(item["ctime_ns"]),
        size=_as_int(item["size"]),
    )


def _mapping_items(data: object) -> tuple[Mapping[str, object], ...]:
    return tuple(_as_mapping(item) for item in _mapping_values(data))


def _mapping_values(data: object) -> tuple[object, ...]:
    if not isinstance(data, list):
        raise TypeError("expected list")
    return tuple(data)


def _as_mapping(data: object) -> Mapping[str, object]:
    if not isinstance(data, dict):
        raise TypeError("expected mapping")
    if not all(isinstance(key, str) for key in data):
        raise TypeError("expected string keys")
    return data


def _as_str(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("expected string")
    return value


def _as_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError("expected bool")
    return value


def _as_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("expected int")
    return value


__all__ = [
    "AssetRef",
    "FileStamp",
    "GraphicsCatalog",
    "GraphicsMaps",
    "GraphicsMetrics",
    "GraphicsScanConfig",
]
