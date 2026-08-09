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
    # refresh() returns complete maps and empty removed lists. Incremental
    # updates (note_written / note_deleted) return only the names whose entry
    # changed, with dropped names listed per family; consumers apply them with
    # update + pop, never clear-and-replace.
    removed_sprites: tuple[str, ...] = ()
    removed_idea_sprites: tuple[str, ...] = ()
    removed_decision_sprites: tuple[str, ...] = ()


@dataclass
class _MapDelta:
    """Names an incremental update must re-apply or drop, per family."""

    upsert: dict[str, set[str]] = field(
        default_factory=lambda: {"sprites": set(), "ideas": set(), "decisions": set()}
    )
    remove: dict[str, set[str]] = field(
        default_factory=lambda: {"sprites": set(), "ideas": set(), "decisions": set()}
    )


@dataclass(frozen=True)
class _ImageClaims:
    """Sprite-map names one image record would derive, per family.

    Idea claims carry a priority: the configured ideas root beats custom dirs,
    matching the order the full derive used to iterate them.
    """

    sprites: tuple[str, ...] = ()
    ideas: tuple[tuple[tuple[int, ...], str], ...] = ()
    decisions: tuple[str, ...] = ()


class GraphicsCatalog:
    def __init__(self) -> None:
        self.generation = 0
        self.last_metrics = GraphicsMetrics()
        self._install_snapshot(GraphicsSnapshot((), (), (), (), ()))
        self._source_roots: dict[str, str] = {}
        self._scan_roots: dict[str, str] = {}
        self._sprite_refs: dict[str, PathReference] = {}
        self._idea_refs: dict[str, PathReference] = {}
        self._decision_refs: dict[str, PathReference] = {}
        # Disk-derived names (GFX_focus_*, GFX_idea_*, ...) that would exist
        # even when a .gfx declaration currently shadows them, so a removed
        # declaration can restore them without rescanning every image.
        self._sprite_claims: dict[str, PathReference] = {}
        self._idea_claims: dict[str, tuple[tuple[int, ...], PathReference]] = {}
        self._decision_claims: dict[str, PathReference] = {}
        # Declaration name -> count, per resolved texture path: the names whose
        # decoded image goes stale when that file is rewritten in place.
        self._declared_names_by_texture: dict[str, dict[str, int]] = {}
        # name -> (file position, gfx file) of the last declaration of name,
        # so an edited .gfx file knows in O(1) whether it still has the last
        # word or must defer to a later file.
        self._last_declarer: dict[str, tuple[int, PathReference]] = {}
        self._file_order: dict[PathReference, int] = {}
        self._root = ""
        self._config = GraphicsScanConfig("", "")
        self._goals_root = ""
        self._ideas_root = ""
        self._gfx_root = ""
        self._custom_roots: tuple[str, ...] = ()
        self._root_identity = ""
        self._config_fingerprint = ""
        # Set when an incremental update patched the in-memory state; the
        # SQLite snapshot is re-stored at the next refresh or flush_cache(),
        # not on every write.
        self._cache_dirty = False

    def refresh(
        self,
        root: str,
        config: GraphicsScanConfig,
        *,
        read_text: Callable[[str], str],
    ) -> GraphicsMaps:
        self.last_metrics = GraphicsMetrics()
        self._flush_cache()
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
            self._cache_dirty = True
        else:
            self.last_metrics.cache_status = "hit"

        self.generation += 1
        self._install_snapshot(snapshot)
        self._source_roots = source_roots
        self._scan_roots = self._extra_scan_roots(root, config)
        self._root = root
        self._config = config
        self._goals_root = _configured_path(root, config.path_goals)
        if not os.path.isdir(self._goals_root):
            self._goals_root = os.path.join(root, "gfx", "interface")
        self._ideas_root = _configured_path(root, config.path_ideas_gfx)
        self._gfx_root = os.path.join(root, "gfx")
        self._custom_roots = tuple(
            os.path.abspath(path) for path in config.custom_gfx_dirs
        )
        self._root_identity = root_identity
        self._config_fingerprint = config_fingerprint
        self._derive_references(root, config)
        _remove_legacy_sidecar(root)
        if self._cache_dirty:
            self._flush_cache()
        return self._materialize_maps()

    def _install_snapshot(self, snapshot: GraphicsSnapshot) -> None:
        self._snapshot = snapshot
        self._directories = {record.path: record for record in snapshot.directories}
        self._images = {record.path: record for record in snapshot.images}
        self._gfx_files = {record.path: record for record in snapshot.gfx_files}

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

        if suffix_lower in _IMAGE_EXTENSIONS:
            self._update_directories(absolute_path)
            delta = self._apply_image_record(
                reference, ImageRecord(reference, _stamp_from_stat(path_stat))
            )
        elif self._is_interface_file(absolute_path):
            interface_root = os.path.join(self._root, "interface")
            record = GfxFileRecord(
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
            )
            self._update_directories(absolute_path)
            delta = self._apply_gfx_record(reference, record)
        else:
            return None
        self.generation += 1
        self._cache_dirty = True
        return self._materialize_delta(delta)

    def note_deleted(self, path: str) -> GraphicsMaps | None:
        if not self._root:
            return None
        absolute_path = os.path.abspath(path)
        reference = self._reference_for_path(absolute_path)
        if reference is None:
            return None
        image_record = self._images.pop(reference, None)
        gfx_record = self._gfx_files.pop(reference, None)
        if image_record is None and gfx_record is None:
            return None
        self._file_order.pop(reference, None)
        self._update_directories(absolute_path)
        delta = _MapDelta()
        if image_record is not None:
            self._unclaim_image(image_record, absolute_path, delta)
            for name in self._declared_names_at(absolute_path):
                if self._ref_resolves_to(self._sprite_refs.get(name), absolute_path):
                    delta.upsert["sprites"].add(name)
                if self._ref_resolves_to(self._idea_refs.get(name), absolute_path):
                    delta.upsert["ideas"].add(name)
                if self._ref_resolves_to(self._decision_refs.get(name), absolute_path):
                    delta.upsert["decisions"].add(name)
        if gfx_record is not None:
            for declaration in gfx_record.declarations:
                self._unindex_declaration(declaration)
                last = self._last_declarer.get(declaration.name)
                if last is not None and last[1] == reference:
                    self._remove_declared_name(declaration.name, declaration, delta)
        self.generation += 1
        self._cache_dirty = True
        return self._materialize_delta(delta)

    def flush_cache(self) -> None:
        """Persist the patched snapshot if it changed since the last store."""
        self._flush_cache()

    def _flush_cache(self) -> None:
        if not self._cache_dirty:
            return
        self._cache_dirty = False
        if not self._root:
            return
        snapshot = self._snapshot_for_store()
        if not snapshot.cacheable:
            return
        WorkspaceCache(scan_cache.database_path(self._root)).store_graphics(
            snapshot.to_data(),
            schema_version=_CACHE_VERSION,
            root_identity=self._root_identity,
            config_fingerprint=self._config_fingerprint,
        )

    def _snapshot_for_store(self) -> GraphicsSnapshot:
        goals_root = self._goals_root
        ideas_root = self._ideas_root
        return GraphicsSnapshot(
            directories=tuple(self._directories.values()),
            images=tuple(self._images.values()),
            gfx_files=tuple(self._gfx_files.values()),
            goal_images=tuple(
                record.path
                for record in self._images.values()
                if goals_root
                and _is_under(record.path.resolve(self._source_roots), goals_root)
            ),
            idea_images=tuple(
                record.path
                for record in self._images.values()
                if ideas_root
                and _is_under(record.path.resolve(self._source_roots), ideas_root)
            ),
        )

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
        for record in self._images.values():
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

    def _apply_image_record(
        self, reference: PathReference, record: ImageRecord
    ) -> _MapDelta:
        self._images[reference] = record
        delta = _MapDelta()
        absolute_path = record.path.resolve(self._source_roots)
        self._apply_image_claims(record, absolute_path, delta)
        for name in self._declared_names_at(absolute_path):
            if self._ref_resolves_to(self._sprite_refs.get(name), absolute_path):
                delta.upsert["sprites"].add(name)
            if self._ref_resolves_to(self._idea_refs.get(name), absolute_path):
                delta.upsert["ideas"].add(name)
            if self._ref_resolves_to(self._decision_refs.get(name), absolute_path):
                delta.upsert["decisions"].add(name)
        return delta

    def _apply_gfx_record(
        self, reference: PathReference, record: GfxFileRecord
    ) -> _MapDelta:
        delta = _MapDelta()
        old_declaration: SpriteDeclaration | None
        old_record = self._gfx_files.get(reference)
        old_by_name = (
            {declaration.name: declaration for declaration in old_record.declarations}
            if old_record is not None
            else {}
        )
        new_by_name = {
            declaration.name: declaration for declaration in record.declarations
        }
        self._gfx_files[reference] = record
        position = self._file_order.get(reference)
        if position is None:
            position = max(self._file_order.values(), default=-1) + 1
            self._file_order[reference] = position

        for name, old_declaration in old_by_name.items():
            self._unindex_declaration(old_declaration)
            if name in new_by_name:
                continue
            last = self._last_declarer.get(name)
            if last is not None and last[1] == reference:
                self._remove_declared_name(name, old_declaration, delta)
        for name, new_declaration in new_by_name.items():
            self._index_declaration(new_declaration)
            old_declaration = old_by_name.get(name)
            if old_declaration is not None:
                # A re-declared name can switch families (texture path, or the
                # top-level/strict flags that gate the sprite maps).
                for family in _declaration_families(old_declaration):
                    if (
                        family not in _declaration_families(new_declaration)
                        and self._refs_for(family).get(name)
                        == old_declaration.texture_path
                    ):
                        del self._refs_for(family)[name]
                        delta.remove[family].add(name)
            last = self._last_declarer.get(name)
            if (
                last is not None
                and last[1] != reference
                and self._file_order.get(last[1], -1) >= position
            ):
                continue  # a later file still has the last word on this name
            old_texture = (
                old_declaration.texture_path if old_declaration is not None else None
            )
            families_changed = old_declaration is not None and set(
                _declaration_families(old_declaration)
            ) != set(_declaration_families(new_declaration))
            for family in _declaration_families(new_declaration):
                self._refs_for(family)[name] = new_declaration.texture_path
                if old_texture != new_declaration.texture_path or families_changed:
                    # Only names whose entry actually changed need re-applying;
                    # a same-texture rewrite leaves the decoded image valid.
                    delta.upsert[family].add(name)
            self._last_declarer[name] = (position, reference)
        return delta

    def _remove_declared_name(
        self, name: str, old_declaration: SpriteDeclaration, delta: _MapDelta
    ) -> None:
        for family in _declaration_families(old_declaration):
            refs = self._refs_for(family)
            if refs.get(name) == old_declaration.texture_path:
                del refs[name]
                delta.remove[family].add(name)
        # Another file may still declare the name; last-wins like the full
        # derive. Otherwise the disk-derived claim (if any) can surface.
        winner = None
        winner_position = -1
        for file_ref, gfx_record in self._gfx_files.items():
            file_position = self._file_order.get(file_ref, 0)
            for declaration in gfx_record.declarations:
                if declaration.name == name and file_position > winner_position:
                    winner = (file_position, file_ref, declaration)
                    winner_position = file_position
        if winner is None:
            self._last_declarer.pop(name, None)
            self._unshadow(name, delta)
        else:
            winner_position, file_ref, declaration = winner
            self._last_declarer[name] = (winner_position, file_ref)
            for family in _declaration_families(declaration):
                self._refs_for(family)[name] = declaration.texture_path
                delta.upsert[family].add(name)

    def _unshadow(self, name: str, delta: _MapDelta) -> None:
        sprite_claim = self._sprite_claims.get(name)
        if sprite_claim is not None:
            self._sprite_refs.setdefault(name, sprite_claim)
            delta.upsert["sprites"].add(name)
        idea_claim = self._idea_claims.get(name)
        if idea_claim is not None:
            self._idea_refs.setdefault(name, idea_claim[1])
            delta.upsert["ideas"].add(name)
        decision_claim = self._decision_claims.get(name)
        if decision_claim is not None:
            self._decision_refs.setdefault(name, decision_claim)
            delta.upsert["decisions"].add(name)

    def _unclaim_image(
        self, record: ImageRecord, absolute_path: str, delta: _MapDelta
    ) -> None:
        claims = self._claim_names_for(record, absolute_path)
        removed: list[tuple[str, str]] = []
        for name in claims.sprites:
            if self._sprite_claims.get(name) == record.path:
                del self._sprite_claims[name]
                if self._sprite_refs.get(name) == record.path:
                    del self._sprite_refs[name]
                    delta.remove["sprites"].add(name)
                    removed.append(("sprites", name))
        for _priority, name in claims.ideas:
            claim = self._idea_claims.get(name)
            if claim is not None and claim[1] == record.path:
                del self._idea_claims[name]
                if self._idea_refs.get(name) == record.path:
                    del self._idea_refs[name]
                    delta.remove["ideas"].add(name)
                    removed.append(("ideas", name))
        for name in claims.decisions:
            if self._decision_claims.get(name) == record.path:
                del self._decision_claims[name]
                if self._decision_refs.get(name) == record.path:
                    del self._decision_refs[name]
                    delta.remove["decisions"].add(name)
                    removed.append(("decisions", name))
        if not removed:
            return
        # A sibling with the same stem may now win the dropped names.
        stem = Path(record.path.relative_path).stem
        for candidate in self._images.values():
            if Path(candidate.path.relative_path).stem != stem:
                continue
            try:
                candidate_path = candidate.path.resolve(self._source_roots)
            except KeyError:
                continue
            self._apply_image_claims(candidate, candidate_path)
        for family, name in removed:
            if self._refs_for(family).get(name) is not None:
                delta.upsert[family].add(name)

    def _apply_image_claims(
        self, record: ImageRecord, absolute_path: str, delta: _MapDelta | None = None
    ) -> None:
        claims = self._claim_names_for(record, absolute_path)
        for name in claims.sprites:
            self._claim_sprite(name, record.path)
            if delta is not None:
                delta.upsert["sprites"].add(name)
        for priority, name in claims.ideas:
            self._claim_idea(name, priority, record.path)
            if delta is not None:
                delta.upsert["ideas"].add(name)
        for name in claims.decisions:
            self._claim_decision(name, record.path)
            if delta is not None:
                delta.upsert["decisions"].add(name)

    def _claim_sprite(self, name: str, path: PathReference) -> None:
        if name in self._sprite_claims:
            return
        self._sprite_claims[name] = path
        self._sprite_refs.setdefault(name, path)

    def _claim_idea(
        self, name: str, priority: tuple[int, ...], path: PathReference
    ) -> None:
        existing = self._idea_claims.get(name)
        if existing is not None and existing[0] <= priority:
            return
        old_path = existing[1] if existing is not None else None
        self._idea_claims[name] = (priority, path)
        if old_path is not None and self._idea_refs.get(name) == old_path:
            self._idea_refs[name] = path
        else:
            self._idea_refs.setdefault(name, path)

    def _claim_decision(self, name: str, path: PathReference) -> None:
        if name in self._decision_claims:
            return
        self._decision_claims[name] = path
        self._decision_refs.setdefault(name, path)

    def _claim_names_for(self, record: ImageRecord, absolute_path: str) -> _ImageClaims:
        stem = Path(record.path.relative_path).stem
        sprites: list[str] = []
        ideas: list[tuple[tuple[int, ...], str]] = []
        decisions: list[str] = []
        if self._goals_root and _is_under(absolute_path, self._goals_root):
            sprites.append(f"GFX_focus_{stem}")
        if self._ideas_root and _is_under(absolute_path, self._ideas_root):
            ideas.append(((2,), f"GFX_idea_{stem}"))
        for index, custom_root in enumerate(self._custom_roots):
            if _is_under(absolute_path, custom_root):
                ideas.append(((3, index), f"GFX_idea_{stem}"))
                break
        if self._gfx_root and _is_under(absolute_path, self._gfx_root):
            relative = (
                os.path.relpath(absolute_path, self._root).replace(os.sep, "/").lower()
            )
            if "decisions" in relative:
                decisions.append(f"GFX_decision_{stem}")
                decisions.append(f"GFX_decision_category_{stem}")
            elif "ideas" in relative:
                decisions.append(f"GFX_idea_{stem}")
            elif "goals" not in relative and "focus" not in relative:
                decisions.append(f"GFX_{stem}")
        return _ImageClaims(tuple(sprites), tuple(ideas), tuple(decisions))

    def _index_declaration(self, declaration: SpriteDeclaration) -> None:
        key = self._texture_key(declaration)
        counts = self._declared_names_by_texture.setdefault(key, {})
        counts[declaration.name] = counts.get(declaration.name, 0) + 1

    def _unindex_declaration(self, declaration: SpriteDeclaration) -> None:
        key = self._texture_key(declaration)
        counts = self._declared_names_by_texture.get(key)
        if counts is None:
            return
        count = counts.get(declaration.name, 0) - 1
        if count > 0:
            counts[declaration.name] = count
        else:
            counts.pop(declaration.name, None)
            if not counts:
                self._declared_names_by_texture.pop(key, None)

    def _texture_key(self, declaration: SpriteDeclaration) -> str:
        return _absolute_key(declaration.texture_path.resolve(self._source_roots))

    def _declared_names_at(self, absolute_path: str) -> set[str]:
        names: set[str] = set()
        for key in _absolute_candidates(absolute_path):
            names.update(self._declared_names_by_texture.get(key, ()))
        return names

    def _ref_resolves_to(self, ref: PathReference | None, absolute_path: str) -> bool:
        if ref is None:
            return False
        try:
            resolved = ref.resolve(self._source_roots)
        except KeyError:
            return False
        return _absolute_key(resolved) == _absolute_key(absolute_path)

    def _materialize_delta(self, delta: _MapDelta) -> GraphicsMaps:
        def resolve_family(refs, names):
            return {
                name: refs[name].resolve(self._source_roots)
                for name in names
                if name in refs
            }

        return GraphicsMaps(
            sprites=resolve_family(self._sprite_refs, delta.upsert["sprites"]),
            idea_sprites=resolve_family(self._idea_refs, delta.upsert["ideas"]),
            decision_sprites=resolve_family(
                self._decision_refs, delta.upsert["decisions"]
            ),
            removed_sprites=tuple(sorted(delta.remove["sprites"])),
            removed_idea_sprites=tuple(sorted(delta.remove["ideas"])),
            removed_decision_sprites=tuple(sorted(delta.remove["decisions"])),
        )

    def _refs_for(self, family: str) -> dict[str, PathReference]:
        return {
            "sprites": self._sprite_refs,
            "ideas": self._idea_refs,
            "decisions": self._decision_refs,
        }[family]

    def _update_directories(self, changed_path: str) -> None:
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
            self._directories[reference] = record
            parent = os.path.dirname(directory)
            if parent == directory:
                break
            directory = parent

    def _reference_for_path(self, path: str) -> PathReference | None:
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
            record = self._images.get(candidate)
            if record is not None:
                return record.stamp
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

        for gfx_record in snapshot.gfx_files:
            self.last_metrics.gfx_file_stats += 1
            try:
                stat = os.stat(gfx_record.path.resolve(source_roots))
            except KeyError, OSError:
                current = False
                continue
            if _stamp_from_stat(stat) != gfx_record.stamp:
                current = False

        # Stat the known image paths too. Directory mtimes don't change when a
        # file is overwritten in place, so an image edit that keeps the same
        # name would otherwise leave a stale FileStamp — and that stamp is the
        # thumbnail cache key. Restatting is cheaper than a full rescan.
        for image_record in snapshot.images:
            self.last_metrics.image_stats += 1
            try:
                stat = os.stat(image_record.path.resolve(source_roots))
            except KeyError, OSError:
                current = False
                continue
            if _stamp_from_stat(stat) != image_record.stamp:
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
        self._sprite_refs = {}
        self._idea_refs = {}
        self._decision_refs = {}
        sprite_claims: dict[str, PathReference] = {}
        idea_claims: dict[str, tuple[tuple[int, ...], PathReference]] = {}
        decision_claims: dict[str, PathReference] = {}
        for record in self._images.values():
            try:
                full_path = record.path.resolve(self._source_roots)
            except KeyError:
                continue
            claims = self._claim_names_for(record, full_path)
            for name in claims.sprites:
                sprite_claims.setdefault(name, record.path)
            for priority, name in claims.ideas:
                existing = idea_claims.get(name)
                if existing is None or priority < existing[0]:
                    idea_claims[name] = (priority, record.path)
            for name in claims.decisions:
                decision_claims.setdefault(name, record.path)
        self._sprite_claims = sprite_claims
        self._idea_claims = idea_claims
        self._decision_claims = decision_claims
        self._declared_names_by_texture = {}
        self._last_declarer = {}
        self._file_order = {}
        for position, (file_ref, gfx_record) in enumerate(self._gfx_files.items()):
            self._file_order[file_ref] = position
            for declaration in gfx_record.declarations:
                self._last_declarer[declaration.name] = (position, file_ref)
                self._index_declaration(declaration)
                for family in _declaration_families(declaration):
                    self._refs_for(family)[declaration.name] = declaration.texture_path
        # Declared entries win; disk-derived claims only fill gaps.
        for name, path in sprite_claims.items():
            self._sprite_refs.setdefault(name, path)
        for name, (_priority, path) in idea_claims.items():
            self._idea_refs.setdefault(name, path)
        for name, path in decision_claims.items():
            self._decision_refs.setdefault(name, path)

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
        candidates = [
            ("goals", goals_root),
            ("ideas", _configured_path(root, config.path_ideas_gfx)),
        ]
        if config.path_event_pictures:
            candidates.append(
                ("events", _configured_path(root, config.path_event_pictures))
            )
        candidates.extend(
            (f"custom:{index}", os.path.abspath(path))
            for index, path in enumerate(config.custom_gfx_dirs)
        )
        # Mirrors the scan-skip in _scan_snapshot: a root nested inside an
        # already-scanned root is scanned under that outer root, never on its
        # own, so _reference_for_path must not attribute paths to it either.
        scanned = [interface_root, gfx_root]
        roots = {}
        for source_id, scan_root in candidates:
            if any(_is_under(scan_root, existing) for existing in scanned):
                continue
            roots[source_id] = scan_root
            scanned.append(scan_root)
        return roots


def _declaration_families(declaration: SpriteDeclaration) -> tuple[str, ...]:
    families = ["decisions"]
    if declaration.top_level and declaration.strict_extension:
        if (
            "goals" in declaration.texture_path_lower
            or "focus" in declaration.texture_path_lower
        ):
            families.append("sprites")
        if (
            "ideas" in declaration.texture_path_lower
            or "idea" in declaration.texture_path_lower
        ):
            families.append("ideas")
    return tuple(families)


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


def _absolute_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _absolute_candidates(path: str) -> tuple[str, ...]:
    keys = [_absolute_key(path)]
    stem = os.path.splitext(path)[0]
    if path.lower().endswith(".dds"):
        keys.extend(_absolute_key(stem + extension) for extension in (".png", ".tga"))
    else:
        keys.append(_absolute_key(stem + ".dds"))
    return tuple(keys)


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
