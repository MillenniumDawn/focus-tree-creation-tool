"""Helpers for preserving and extending Clausewitz ``spriteTypes`` files."""

from __future__ import annotations

import os
import re
from collections.abc import Collection, Iterable, Mapping
from pathlib import Path
from typing import cast

from hoi4cm.script.syntax import match_brace

DEFAULT_FOCUS_ICON = "GFX_goal_generic_political_pressure"

_SPRITE_BLOCK_RE = re.compile(r'"[^"]*"|#[^\n]*|(?<!\w)spriteType\s*=\s*\{')
_SPRITE_NAME_RE = re.compile(r'"[^"]*"|#[^\n]*|\bname\s*=\s*"([^"]+)"')
_WRAPPER_RE = re.compile(r'"[^"]*"|#[^\n]*|(?<!\w)spriteTypes\s*=\s*\{')

SpriteTypeEntry = tuple[str, str]


def build_sprite_type(name: str, texture_path: str) -> str:
    """Return one indented ``spriteType`` declaration."""
    return (
        "\tspriteType = {\n"
        f'\t\tname = "{name}"\n'
        f'\t\ttexturefile = "{texture_path}"\n'
        "\t}"
    )


def append_sprite_types(
    existing: str | None,
    entries: Mapping[str, str] | Iterable[SpriteTypeEntry],
) -> tuple[str, int]:
    """Append missing declarations while leaving existing text untouched.

    A missing file is wrapped in ``spriteTypes``. Existing wrappers receive the
    declarations before their matching close brace; unwrapped files are kept
    as-is and receive declarations at the end.
    """
    requested: Iterable[SpriteTypeEntry]
    if isinstance(entries, Mapping):
        requested = cast(Iterable[SpriteTypeEntry], entries.items())
    else:
        requested = entries
    pending: list[SpriteTypeEntry] = []
    seen: set[str] = set()
    for name, texture_path in requested:
        if name in seen:
            continue
        seen.add(name)
        pending.append((name, texture_path))

    if not pending:
        return existing or "", 0

    source = existing
    existing_names = _declared_sprite_names(source or "")
    new_entries = [
        (name, texture_path)
        for name, texture_path in pending
        if name not in existing_names
    ]
    if not new_entries:
        return source or "", 0

    blocks = "\n".join(
        build_sprite_type(name, texture_path) for name, texture_path in new_entries
    )
    if source is None:
        return f"spriteTypes = {{\n\n{blocks}\n\n}}\n", len(new_entries)

    wrapper = _next_code_match(_WRAPPER_RE, source)
    if wrapper is not None:
        close = match_brace(source, wrapper.end() - 1)
        if close < len(source):
            prefix = source[:close]
            separator = "\n" if not prefix.endswith("\n\n") else ""
            return (
                f"{prefix}{separator}{blocks}\n{source[close:]}",
                len(new_entries),
            )

    separator = "" if source.endswith(("\n", "\r")) else "\n"
    return f"{source}{separator}{blocks}\n", len(new_entries)


def resolve_mod_texture_path(
    mod_root: str, image_path: str | os.PathLike[str] | None
) -> str | None:
    """Return a slash-separated mod-relative image path when it is safe."""
    if not mod_root or not image_path:
        return None
    from hoi4cm.core.safe_path import safe_join

    root = os.path.realpath(mod_root)
    candidate = os.fspath(image_path)
    if not os.path.isabs(candidate):
        candidate = os.path.join(root, candidate)
    try:
        relative = os.path.relpath(candidate, root)
        resolved = safe_join(root, relative)
    except OSError, ValueError:
        return None
    if not os.path.isfile(resolved):
        return None
    return os.path.relpath(resolved, root).replace(os.sep, "/")


def build_focus_sprite_entries(
    icon_names: Iterable[str],
    *,
    declared_names: Collection[str],
    image_paths: Mapping[str, str | os.PathLike[str]],
    mod_root: str,
) -> tuple[tuple[SpriteTypeEntry, ...], tuple[str, ...]]:
    """Build safe declarations and report icon keys with unresolved images."""
    candidates = sorted(
        {
            name
            for name in icon_names
            if name and name != DEFAULT_FOCUS_ICON and name not in declared_names
        }
    )
    entries: list[SpriteTypeEntry] = []
    unresolved: list[str] = []
    for name in candidates:
        texture_path = resolve_mod_texture_path(mod_root, image_paths.get(name))
        if texture_path is None:
            unresolved.append(name)
        else:
            entries.append((name, texture_path))
    return tuple(entries), tuple(unresolved)


def resolve_focus_image_paths(
    icon_names: Iterable[str],
    *,
    catalog,
    mod_root: str,
    goals_path: str,
) -> dict[str, str]:
    """Resolve selected focus icons through the graphics catalog."""
    paths: dict[str, str] = {}
    names = tuple(dict.fromkeys(icon_names))
    for name in names:
        try:
            asset = catalog.resolve(name)
        except KeyError, OSError, ValueError, TypeError, RuntimeError:
            asset = None
        if asset is not None:
            try:
                paths[name] = catalog.path_for(asset)
            except KeyError, OSError, ValueError, TypeError, RuntimeError:
                pass

    unresolved = [name for name in names if name not in paths]
    if not unresolved:
        return paths

    roots = []
    configured = goals_path
    if not os.path.isabs(configured):
        configured = os.path.join(mod_root, configured)
    roots.append(os.path.realpath(configured))
    roots.append(os.path.realpath(os.path.join(mod_root, "gfx", "interface")))
    for root in dict.fromkeys(roots):
        try:
            assets = catalog.query(under=root)
        except KeyError, OSError, ValueError, TypeError, RuntimeError:
            continue
        by_stem: dict[str, str] = {}
        for asset in assets:
            try:
                path = catalog.path_for(asset)
            except KeyError, OSError, ValueError, TypeError, RuntimeError:
                continue
            by_stem.setdefault(Path(path).stem, path)
        for name in unresolved:
            stem = _focus_icon_stem(name)
            path = by_stem.get(stem)
            if path is not None:
                paths[name] = path
        unresolved = [name for name in unresolved if name not in paths]
        if not unresolved:
            break
    return paths


def _focus_icon_stem(name: str) -> str:
    for prefix in ("GFX_focus_", "GFX_goal_"):
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def _declared_sprite_names(source: str) -> set[str]:
    names: set[str] = set()
    for match in _SPRITE_BLOCK_RE.finditer(source):
        if match.group().startswith(('"', "#")):
            continue
        close = match_brace(source, match.end() - 1)
        if close >= len(source):
            continue
        for name in _SPRITE_NAME_RE.finditer(source, match.end(), close):
            if name.group(1) is not None:
                names.add(name.group(1))
                break
    return names


def _next_code_match(pattern: re.Pattern[str], source: str) -> re.Match[str] | None:
    for match in pattern.finditer(source):
        if not match.group().startswith(('"', "#")):
            return match
    return None


__all__ = [
    "DEFAULT_FOCUS_ICON",
    "SpriteTypeEntry",
    "append_sprite_types",
    "build_focus_sprite_entries",
    "build_sprite_type",
    "resolve_focus_image_paths",
    "resolve_mod_texture_path",
]
